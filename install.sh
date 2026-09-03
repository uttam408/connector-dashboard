#!/bin/bash
# One-time setup: symlink the launchd plist into ~/Library/LaunchAgents and
# load it. Safe to re-run (bootout first, then bootstrap).
set -euo pipefail

REPO="/Users/uttam/connector-dashboard"
LABEL="com.uttam.connector-dashboard"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

ln -sf "$REPO/com.uttam.connector-dashboard.plist" "$PLIST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"

echo "loaded $LABEL - next run 05:00; run now with:"
echo "  launchctl kickstart -k gui/$(id -u)/$LABEL"
