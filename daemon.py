#!/usr/bin/env python3
"""
claude-copy daemon: intercepts Cmd+C in terminal apps and cleans Claude TUI artifacts.

Usage:
  python3 daemon.py          # run in foreground
  launchctl load ~/Library/LaunchAgents/com.claude-copy.plist  # run as login agent
"""

import os
import subprocess
import sys
import signal
import threading
import time

import Quartz
from AppKit import NSWorkspace, NSPasteboard, NSStringPboardType
import clean

TERMINAL_APPS = {
    "Terminal",
    "iTerm2",
    "Ghostty",
    "Alacritty",
    "kitty",
    "WezTerm",
    "Hyper",
    "Warp",
    "Rio",
    "Tabby",
    "Wave",
}

COPY_TIMEOUT_S = 0.35
COPY_POLL_S = 0.01
COPY_MAX_BYTES = 50_000

_intercepting = False
_tap = None


def frontmost_app_name():
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return app.localizedName() if app else None


def is_terminal_focused():
    return frontmost_app_name() in TERMINAL_APPS


def clipboard_change_count():
    return NSPasteboard.generalPasteboard().changeCount()


def read_clipboard():
    return NSPasteboard.generalPasteboard().stringForType_(NSStringPboardType)


def write_clipboard(text):
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSStringPboardType)


def send_raw_cmd_c():
    # Disable the tap while posting so we don't re-intercept our own event.
    Quartz.CGEventTapEnable(_tap, False)
    try:
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        key_down = Quartz.CGEventCreateKeyboardEvent(src, 8, True)   # 8 = 'c'
        key_up   = Quartz.CGEventCreateKeyboardEvent(src, 8, False)
        Quartz.CGEventSetFlags(key_down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventSetFlags(key_up,   Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_up)
    finally:
        Quartz.CGEventTapEnable(_tap, True)


def handle_copy():
    before = clipboard_change_count()
    send_raw_cmd_c()

    elapsed = 0.0
    while elapsed < COPY_TIMEOUT_S:
        time.sleep(COPY_POLL_S)
        elapsed += COPY_POLL_S
        if clipboard_change_count() != before:
            break
    else:
        return  # clipboard didn't change

    content = read_clipboard()
    if not isinstance(content, str) or not content:
        return

    if len(content) > COPY_MAX_BYTES:
        return

    cleaned = clean.process(content)
    if cleaned != content:
        write_clipboard(cleaned)


def event_callback(proxy, event_type, event, refcon):
    global _intercepting

    if event_type != Quartz.kCGEventKeyDown:
        return event

    flags = Quartz.CGEventGetFlags(event)
    keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)

    cmd_only = (
        bool(flags & Quartz.kCGEventFlagMaskCommand)
        and not bool(flags & Quartz.kCGEventFlagMaskShift)
        and not bool(flags & Quartz.kCGEventFlagMaskAlternate)
        and not bool(flags & Quartz.kCGEventFlagMaskControl)
    )

    if keycode != 8 or not cmd_only:  # 8 = 'c'
        return event

    if _intercepting:
        return event

    if not is_terminal_focused():
        return event

    _intercepting = True

    def _run():
        global _intercepting
        try:
            handle_copy()
        except Exception as e:
            print(f"claude-copy: error: {e}", file=sys.stderr)
        finally:
            _intercepting = False

    threading.Thread(target=_run, daemon=True).start()

    return None  # swallow the original event; handle_copy sent a new one


_NOTIFY_COOLDOWN_S = 300  # don't bug the user more than once per 5 min
_NOTIFY_STAMP = "/tmp/claude-copy.notify-stamp"


def notify_accessibility_missing():
    """Show a macOS notification and open Accessibility settings.

    Also clears any stale TCC entry for claude-copy so the user doesn't see
    a "checked but broken" duplicate in the Accessibility list. Throttled via
    mtime stamp file so launchd's KeepAlive loop doesn't spam.
    """
    print(
        "claude-copy: failed to create event tap.\n"
        "Grant Accessibility access: System Settings → Privacy & Security → Accessibility",
        file=sys.stderr,
    )

    now = time.time()
    try:
        last = os.path.getmtime(_NOTIFY_STAMP)
    except OSError:
        last = 0
    if now - last < _NOTIFY_COOLDOWN_S:
        return
    try:
        with open(_NOTIFY_STAMP, "w"):
            pass
    except OSError:
        pass

    title = "Claude Copy needs Accessibility access"
    body  = "Settings opened — toggle Claude Copy on (or re-add if needed)."
    try:
        # NSUserNotification — deprecated but still works for sandbox-less apps
        # and shows as coming from "Claude Copy" (not osascript / Script Editor).
        from Foundation import NSUserNotification, NSUserNotificationCenter
        note = NSUserNotification.alloc().init()
        note.setTitle_(title)
        note.setInformativeText_(body)
        note.setSoundName_("Funk")
        NSUserNotificationCenter.defaultUserNotificationCenter().deliverNotification_(note)
    except Exception:
        # Fallback to osascript if Foundation isn't available
        script = f'display notification {body!r} with title {title!r} sound name "Funk"'
        try:
            subprocess.Popen(["osascript", "-e", script])
        except OSError:
            pass
    # Open Accessibility settings pane so the user can fix it in one click.
    try:
        subprocess.Popen([
            "open",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
        ])
    except OSError:
        pass


def stop(sig=None, frame=None):
    global _tap
    if _tap:
        Quartz.CGEventTapEnable(_tap, False)
    print("claude-copy: stopped")
    sys.exit(0)


def main():
    global _tap

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    mask = (1 << Quartz.kCGEventKeyDown)
    _tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionDefault,
        mask,
        event_callback,
        None,
    )

    if not _tap:
        notify_accessibility_missing()
        sys.exit(1)

    loop_source = Quartz.CFMachPortCreateRunLoopSource(None, _tap, 0)
    Quartz.CFRunLoopAddSource(
        Quartz.CFRunLoopGetCurrent(),
        loop_source,
        Quartz.kCFRunLoopCommonModes,
    )
    Quartz.CGEventTapEnable(_tap, True)

    print("claude-copy: running (Ctrl+C to stop)")
    Quartz.CFRunLoopRun()


if __name__ == "__main__":
    main()
