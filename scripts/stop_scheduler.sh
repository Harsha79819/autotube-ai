#!/bin/bash
# scripts/stop_scheduler.sh - Stops AutoTube AI 24/7 Channel 1 Automated Scheduler Daemon

PIDS=$(pgrep -f "daily_scheduler.py --daemon")

if [ -z "$PIDS" ]; then
    echo "ℹ️ No running Daily Scheduler Daemon found."
    exit 0
fi

echo "🛑 Stopping Daily Scheduler Daemon (PID: $PIDS)..."
kill $PIDS
sleep 1

if pgrep -f "daily_scheduler.py --daemon" > /dev/null; then
    echo "⚠️ Force killing..."
    kill -9 $PIDS
fi

echo "✅ Scheduler Daemon stopped."
