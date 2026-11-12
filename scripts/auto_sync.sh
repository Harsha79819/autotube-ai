#!/usr/bin/env bash
# ==============================================================================
# AutoTube AI - Autonomous GitHub Sync & Hot-Reload Watcher
# Automatically checks origin/main for new code improvements and cleanly restarts
# the service without touching secrets (.env, token.json) or generated outputs.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
cd "$APP_DIR"

if [ ! -d ".git" ]; then
    echo "[$(date)] Not a git repository: $APP_DIR. Skipping sync."
    exit 0
fi

# Fetch remote changes silently
git fetch origin main --quiet 2>/dev/null || {
    echo "[$(date)] Warning: Could not reach GitHub remote. Retrying next cycle."
    exit 0
}

LOCAL_HASH=$(git rev-parse HEAD)
REMOTE_HASH=$(git rev-parse origin/main)

if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
    echo "======================================================================"
    echo "[$(date)] 🚀 New updates detected on GitHub repository!"
    echo "Local:  $LOCAL_HASH"
    echo "Remote: $REMOTE_HASH"
    echo "Pulling latest improvements into Oracle Cloud VM..."
    echo "======================================================================"

    # Hard reset to origin main (preserves untracked .env, token.json, output/)
    git reset --hard origin/main

    # Upgrade any newly added Python packages
    if [ -f "requirements.txt" ] && [ -d "venv" ]; then
        echo "Verifying Python dependencies..."
        ./venv/bin/pip install -r requirements.txt --quiet
    fi

    # Restart AutoTube systemd service
    if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet autotube.service; then
        echo "Restarting autotube.service..."
        sudo systemctl restart autotube.service
        echo "✅ AutoTube successfully restarted with latest updates!"
    fi
else
    # Up to date
    exit 0
fi
