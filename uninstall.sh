#!/bin/bash
set -e

# Stop the daemon
launchctl bootout "gui/$(id -u)/com.claude-copy" 2>/dev/null || true

# Remove LaunchAgent plist
rm -f "$HOME/Library/LaunchAgents/com.claude-copy.plist"

# Remove cached notify stamp
rm -f "/tmp/claude-copy.notify-stamp"

echo "Claude Copy uninstalled."
echo ""
echo "Manual cleanup (optional):"
echo "  • System Settings → Privacy & Security → Accessibility — remove 'Claude Copy'"
echo "  • System Settings → General → Login Items → App Background Activity — remove 'Claude Copy'"
