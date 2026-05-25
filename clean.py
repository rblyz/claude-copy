"""
claude-copy text cleaning pipeline.

Single entry point: process(text). Pipeline runs four steps in order,
each does exactly one safe thing — no mode switching, no heuristics
deciding "is this a TUI artifact".

  1. strip_box_drawing       — remove ╭ ╰ ╮ ╯ ─ ╌ ╍ ═ │ from any line
  2. rstrip every line       — kill terminal padding
  3. dedent_line_number_block — uniform-dedent diff blocks like "  101 + foo"
  4. recover_numbered_block  — split flattened "1 const ... 2 let ..." lines
"""

import re
import math


# ── 1. Box drawing ───────────────────────────────────────────────────────────

_RE_BOX_DRAWING_CHARS = re.compile(r'[╭╰╮╯─╌╍═│]')
_RE_BORDER_ONLY_LINE  = re.compile(r'^[╭╰╮╯─╌╍═│\s]*$')


def strip_box_drawing(text):
    """Drop pure-border rows, strip box chars from any line that has them,
    collapse the spaces they left behind."""
    out = []
    for line in text.splitlines():
        if not _RE_BOX_DRAWING_CHARS.search(line):
            out.append(line)
            continue
        if _RE_BORDER_ONLY_LINE.match(line):
            continue
        cleaned = _RE_BOX_DRAWING_CHARS.sub(' ', line)
        cleaned = re.sub(r' {2,}', ' ', cleaned).strip()
        if cleaned:
            out.append(cleaned)
    return '\n'.join(out)


# ── 2. Trailing whitespace (inlined in process) ──────────────────────────────


# ── 3. Line-number diff dedent ───────────────────────────────────────────────

_RE_LINE_NUM_PREFIX = re.compile(r'^( +)(\d+[ +\-])')


def dedent_line_number_block(text):
    """Remove uniform leading indent from line-numbered blocks.

    Terminal pads line numbers to a fixed width — two-digit lines get one
    extra leading space vs three-digit lines. Find the minimum indent among
    lines matching '<spaces><digits><space/+/->' and strip that many spaces
    from ALL non-empty lines, preserving relative alignment of continuations.
    """
    lines = text.splitlines()
    indents = [len(m.group(1)) for line in lines for m in [_RE_LINE_NUM_PREFIX.match(line)] if m]
    if not indents:
        return text
    min_indent = min(indents)
    if min_indent == 0:
        return text

    result = []
    for line in lines:
        if line and len(line) - len(line.lstrip(' ')) >= min_indent:
            result.append(line[min_indent:])
        else:
            result.append(line)
    return '\n'.join(result)


# ── 4. Flattened numbered-line recovery ──────────────────────────────────────

LINE_NUMBER_KEYWORDS = [
    "async", "await", "catch", "class", "const", "def", "enum", "export",
    "for", "function", "if", "import", "interface", "let", "local", "return",
    "struct", "try", "type", "var", "while",
]
_LNK_ALT = "|".join(LINE_NUMBER_KEYWORDS)

_RE_LNS_DIFF     = re.compile(r"\d+\s+[+\-]\s")
_RE_LNS_SINGLE   = re.compile(
    rf"(\d+)\s+(?:{_LNK_ALT}\b|//|/\*|[\[{{(]|[a-zA-Z_]\w*[({{=:.])"
)
_RE_LNS_DOUBLE   = re.compile(
    rf"(\d+)(\s+)\d+\s+(?:[+\-]\s|{_LNK_ALT}\b)"
)
_RE_LNS_WIDE     = re.compile(r"(\d+)(\s+)\d+\s{2,}\S")
_RE_LNS_FALLBACK = re.compile(r"\d+\s{2,}\S")

_RE_RECOVER_DIGIT_SPACE  = re.compile(r"^\d+\s")
_RE_RECOVER_TRAILING_NUM = re.compile(r"^(.*[)\]};,])\s+(\d+)$")


def _split_lines(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _collect_line_number_starts(flat):
    starts_set = set()
    diff_starts = 0

    def add_if_line_start(pos):
        if pos <= 0:
            return
        if flat[pos - 1] in " \t\n":
            starts_set.add(pos)

    for m in _RE_LNS_DIFF.finditer(flat):
        add_if_line_start(m.start())
        diff_starts += 1
    for m in _RE_LNS_SINGLE.finditer(flat):
        n = int(m.group(1))
        if 1 <= n <= 999:
            add_if_line_start(m.start())
    for m in _RE_LNS_DOUBLE.finditer(flat):
        add_if_line_start(m.start())
        add_if_line_start(m.start() + len(m.group(1)) + len(m.group(2)))
    for m in _RE_LNS_WIDE.finditer(flat):
        add_if_line_start(m.start())
        add_if_line_start(m.start() + len(m.group(1)) + len(m.group(2)))
    for m in _RE_LNS_FALLBACK.finditer(flat):
        add_if_line_start(m.start())

    return sorted(starts_set), diff_starts


def _has_plausible_number_progression(flat, starts):
    if len(starts) < 3:
        return False
    numbers = []
    for pos in starts:
        m = re.match(r"(\d+)", flat[pos:])
        if m:
            numbers.append(int(m.group(1)))
    if len(numbers) < 3:
        return False
    plausible = sum(1 for i in range(1, len(numbers)) if 0 <= numbers[i] - numbers[i - 1] <= 25)
    return plausible >= max(2, math.floor((len(numbers) - 1) * 0.6))


def _recover_flattened_numbered_line(flat):
    starts, diff_starts = _collect_line_number_starts(flat)
    if len(starts) < 3:
        return flat
    if diff_starts < 2 and not _has_plausible_number_progression(flat, starts):
        return flat

    split_at = set(starts)
    out = []
    for i, ch in enumerate(flat):
        if i in split_at:
            out.append("\n")
        out.append(ch)
    rebuilt = "".join(out).lstrip("\n")

    normalized = []
    for line in _split_lines(rebuilt):
        trimmed = line.lstrip()
        if _RE_RECOVER_DIGIT_SPACE.match(trimmed):
            normalized.append("  " + trimmed)
        else:
            normalized.append(line)

    final_lines = []
    for line in normalized:
        m = _RE_RECOVER_TRAILING_NUM.match(line)
        if m:
            n = int(m.group(2))
            if 1 <= n <= 999:
                final_lines.append(m.group(1))
                final_lines.append("  " + str(n))
                continue
        final_lines.append(line)

    return "\n".join(final_lines)


def recover_numbered_block(text):
    lines = _split_lines(text)
    if not lines:
        return text
    changed = False
    rebuilt = []
    for line in lines:
        recovered = _recover_flattened_numbered_line(line)
        if recovered != line:
            changed = True
        rebuilt.append(recovered)
    if not changed:
        return text
    return "\n".join(rebuilt)


# ── Entry point ──────────────────────────────────────────────────────────────

def process(text):
    """Run the full cleaning pipeline. Idempotent."""
    text = strip_box_drawing(text)
    text = "\n".join(line.rstrip() for line in text.splitlines())
    text = dedent_line_number_block(text)
    text = recover_numbered_block(text)
    return text
