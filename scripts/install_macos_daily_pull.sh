#!/bin/zsh
set -eu

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="org.catbondflow.non-artemis-daily"
TEMPLATE="$PROJECT_ROOT/config/$LABEL.plist.template"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
TEMP_FILE="$(mktemp)"
trap 'rm -f "$TEMP_FILE"' EXIT INT TERM

mkdir -p "$HOME/Library/LaunchAgents"
sed "s#__PROJECT_ROOT__#$PROJECT_ROOT#g" "$TEMPLATE" > "$TEMP_FILE"
plutil -lint "$TEMP_FILE"
install -m 0644 "$TEMP_FILE" "$TARGET"

launchctl bootout "gui/$(id -u)" "$TARGET" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
launchctl enable "gui/$(id -u)/$LABEL"
print "installed $TARGET (daily at 02:15 local time)"
print "note: launchd cannot read macOS-protected folders (Desktop, Documents, Downloads)."
print "      If PROJECT_ROOT is inside one, grant /bin/zsh Full Disk Access or the job exits 127."
