#!/bin/bash
# scripts/start_scheduler.sh - Starts AutoTube AI 24/7 Channel 1 Automated Scheduler Daemon

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

LOG_FILE="$DIR/logs/scheduler_daemon.log"
mkdir -p "$DIR/logs"

# Check if already running
if pgrep -f "daily_scheduler.py --daemon" > /dev/null; then
    echo "⚠️ Daily Scheduler Daemon is already running (PID: $(pgrep -f "daily_scheduler.py --daemon"))."
    exit 0
fi

echo "🚀 Starting 24/7 Daily Scheduler Daemon for Channel 1..."
nohup "$DIR/.venv/bin/python3" "$DIR/daily_scheduler.py" --daemon >> "$LOG_FILE" 2>&1 &
PID=$!
echo "✅ Scheduler started successfully (PID: $PID)!"
echo "📝 Logs: $LOG_FILE"
