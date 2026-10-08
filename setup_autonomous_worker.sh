#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKER_SH="$REPO_DIR/run_worker.sh"
chmod +x "$WORKER_SH"

PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/com.neosfaozora.worker.plist"
mkdir -p "$PLIST_DIR"

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.neosfaozora.worker</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$WORKER_SH</string>
        <string>auto</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$REPO_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Hour</key>
            <integer>20</integer>
            <key>Minute</key>
            <integer>15</integer>
        </dict>
        <dict>
            <key>Hour</key>
            <integer>21</integer>
            <key>Minute</key>
            <integer>15</integer>
        </dict>
    </array>
    <key>StandardOutPath</key>
    <string>$REPO_DIR/worker_launchd.log</string>
    <key>StandardErrorPath</key>
    <string>$REPO_DIR/worker_launchd.err.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo "[OK] Installed macOS LaunchAgent: $PLIST_PATH"
echo "This Mac ($(hostname)) will now autonomously pull tasks from GitHub on boot and daily at 20:15/21:15, generate FLUX.2 illustrations, and push to GitHub Pages even when MINISFORUM64GB is off!"
