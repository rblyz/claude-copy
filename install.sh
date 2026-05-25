#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$SCRIPT_DIR/dist/Claude Copy.app"
BINARY="$APP/Contents/MacOS/Claude Copy"
PLIST_DST="$HOME/Library/LaunchAgents/com.claude-copy.plist"

if [ ! -d "$APP" ]; then
  echo "Error: $APP not found."
  echo "Build it first: python3 -m PyInstaller claude-copy.spec --noconfirm"
  exit 1
fi

echo "Installing LaunchAgent..."
cat > "$PLIST_DST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.claude-copy</string>

  <key>ProgramArguments</key>
  <array>
    <string>$BINARY</string>
  </array>

  <key>SessionCreate</key>
  <true/>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <true/>

  <key>ThrottleInterval</key>
  <integer>30</integer>

  <key>StandardOutPath</key>
  <string>/tmp/claude-copy.log</string>

  <key>StandardErrorPath</key>
  <string>/tmp/claude-copy.log</string>
</dict>
</plist>
EOF

if launchctl bootout "gui/$(id -u)/com.claude-copy" 2>/dev/null; then
  sleep 1
fi
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"

echo ""
echo "Claude Copy installed."
echo ""
echo "┌─────────────────────────────────────────────────────────────────┐"
echo "│  ACTION REQUIRED: Grant Accessibility Access                    │"
echo "│                                                                 │"
echo "│  1. Open: System Settings → Privacy & Security → Accessibility  │"
echo "│  2. Click [+], navigate to:                                     │"
echo "│                                                                 │"
echo "│     $APP"
echo "│                                                                 │"
echo "│  3. Select Claude Copy.app and turn on the toggle.              │"
echo "└─────────────────────────────────────────────────────────────────┘"
