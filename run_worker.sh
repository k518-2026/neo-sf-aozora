#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
ROLE="${1:-auto}"
echo "[$(date '+%H:%M:%S')] Syncing latest code & task queue from GitHub (git pull --rebase origin main)..."
git pull --rebase origin main || true
echo "[$(date '+%H:%M:%S')] Starting Distributed Local LLM Worker (Role: $ROLE) in $(pwd)..."
python3 -m src.task_worker --role "$ROLE"
