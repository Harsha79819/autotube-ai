#!/usr/bin/env bash
# ==============================================================================
# AutoTube AI - Oracle Cloud Infrastructure (OCI) 1-Click Automated Setup
# Optimized for Always Free Tier:
#   - Ampere A1 (ARM64: 4 OCPU, 24 GB RAM, 200 GB Storage) OR AMD Micro (x86_64)
#   - Ubuntu 22.04 LTS / 24.04 LTS
# ==============================================================================

set -e

GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BOLD="\033[1m"
NC="\033[0m"

echo -e "${CYAN}${BOLD}"
echo "======================================================================"
echo "   🚀 AUTOTUBE AI - ORACLE CLOUD ALWAYS-FREE 1-CLICK DEPLOYMENT       "
echo "======================================================================"
echo -e "${NC}"

USER_NAME=$(whoami)
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo -e "${GREEN}✓ Target Directory:${NC} $APP_DIR"
echo -e "${GREEN}✓ Running as user:${NC}  $USER_NAME"

# 1. Architecture Detection
ARCH=$(uname -m)
echo -e "\n${CYAN}[1/7] Detecting Server Architecture...${NC}"
if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    CLOUDFLARED_ARCH="arm64"
    echo -e "${GREEN}✓ Detected ARM64 architecture (Oracle Ampere A1 Compute Instance).${NC}"
elif [ "$ARCH" = "x86_64" ]; then
    CLOUDFLARED_ARCH="amd64"
    echo -e "${GREEN}✓ Detected x86_64 architecture (Oracle AMD Compute Instance).${NC}"
else
    CLOUDFLARED_ARCH="amd64"
    echo -e "${YELLOW}⚠️ Unknown architecture ($ARCH), defaulting to amd64.${NC}"
fi

# 2. System Packages & Video Engine Tools
echo -e "\n${CYAN}[2/7] Installing System Packages, FFmpeg, and Typography Fonts...${NC}"
sudo apt update -y
sudo DEBIAN_FRONTEND=noninteractive apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    jq \
    ffmpeg \
    fonts-noto-extra \
    fonts-indic \
    fonts-dejavu-core \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libnss3 \
    libxss1 \
    ca-certificates

echo -e "${GREEN}✓ System packages and FFmpeg installed.${NC}"
ffmpeg -version | head -n 1

# 3. Cloudflared Binary Installation
echo -e "\n${CYAN}[3/7] Setting up Cloudflare Tunnel (cloudflared)...${NC}"
if ! command -v cloudflared >/dev/null 2>&1; then
    echo "Downloading cloudflared binary for $CLOUDFLARED_ARCH..."
    sudo wget -q -O /usr/local/bin/cloudflared \
        "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$CLOUDFLARED_ARCH"
    sudo chmod +x /usr/local/bin/cloudflared
    echo -e "${GREEN}✓ Cloudflared installed to /usr/local/bin/cloudflared.${NC}"
else
    echo -e "${GREEN}✓ Cloudflared is already installed.${NC}"
fi
cloudflared --version || true

# 4. Python Virtual Environment & Requirements
echo -e "\n${CYAN}[4/7] Setting up Python Virtual Environment & Dependencies...${NC}"
cd "$APP_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created.${NC}"
fi

echo "Upgrading pip, wheel, setuptools..."
./venv/bin/pip install --upgrade pip wheel setuptools --quiet

echo "Installing project dependencies from requirements.txt (this takes ~1-2 minutes)..."
./venv/bin/pip install -r requirements.txt --quiet

echo "Installing Playwright Chromium browser engine..."
./venv/bin/playwright install chromium || true
sudo ./venv/bin/playwright install-deps chromium 2>/dev/null || true

# 5. Permission & Script Helpers
echo -e "\n${CYAN}[5/7] Registering System Shortcuts...${NC}"
chmod +x "$APP_DIR/scripts/auto_sync.sh" || true
chmod +x "$APP_DIR/scripts/oracle_setup.sh" || true

# Helper: autotube-url
sudo tee /usr/local/bin/autotube-url > /dev/null << 'EOF'
#!/usr/bin/env bash
URL_FILE="/home/ubuntu/autotube-ai/output/tunnel_url.txt"
if [ ! -f "$URL_FILE" ]; then
    # Look in relative directory
    URL_FILE="$(dirname "$(readlink -f "$0")")/../output/tunnel_url.txt"
fi

# Fallback: search anywhere in app directory
if [ ! -f "$URL_FILE" ]; then
    URL_FILE=$(find /home -name "tunnel_url.txt" 2>/dev/null | head -n 1)
fi

echo "======================================================================"
echo "🌐 AUTOTUBE AI MOBILE ACCESS LINK"
echo "======================================================================"
if [ -f "$URL_FILE" ] && [ -s "$URL_FILE" ]; then
    URL=$(cat "$URL_FILE")
    echo -e "\n\033[1;32m👉 Mobile Link: $URL\033[0m\n"
    echo "Open this link in Safari/Chrome on your phone or tablet."
else
    echo "Tunnel is initializing or URL file not found yet. Please check back in 10 seconds:"
    echo "  sudo journalctl -u autotube -n 25 --no-pager"
fi
echo "======================================================================"
EOF
sudo chmod +x /usr/local/bin/autotube-url

# Helper: autotube-status
sudo tee /usr/local/bin/autotube-status > /dev/null << EOF
#!/usr/bin/env bash
cd "$APP_DIR"
./venv/bin/python daemon_runner.py --status
EOF
sudo chmod +x /usr/local/bin/autotube-status

# Helper: autotube-logs
sudo tee /usr/local/bin/autotube-logs > /dev/null << 'EOF'
#!/usr/bin/env bash
sudo journalctl -u autotube -f
EOF
sudo chmod +x /usr/local/bin/autotube-logs

# Helper: autotube-update
sudo tee /usr/local/bin/autotube-update > /dev/null << EOF
#!/usr/bin/env bash
"$APP_DIR/scripts/auto_sync.sh"
EOF
sudo chmod +x /usr/local/bin/autotube-update

# Helper: autotube-restart
sudo tee /usr/local/bin/autotube-restart > /dev/null << 'EOF'
#!/usr/bin/env bash
sudo systemctl restart autotube.service
echo "AutoTube service restarted. Fetching fresh URL in 5 seconds..."
sleep 5
autotube-url
EOF
sudo chmod +x /usr/local/bin/autotube-restart

echo -e "${GREEN}✓ Global CLI shortcuts registered: autotube-url, autotube-status, autotube-logs, autotube-update, autotube-restart${NC}"

# 6. Setup Systemd Service
echo -e "\n${CYAN}[6/7] Configuring Systemd Service (Auto-Start on Boot & Auto-Restart)...${NC}"

sudo tee /etc/systemd/system/autotube.service > /dev/null << EOF
[Unit]
Description=AutoTube AI Autonomous Video Studio & Mobile Cloudflare Tunnel
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=$APP_DIR/venv/bin/python daemon_runner.py --foreground --mode cloudflare-quick
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

# Setup Auto-Sync Timer (Option 2: Sync code from GitHub every 5 minutes)
sudo tee /etc/systemd/system/autotube-sync.service > /dev/null << EOF
[Unit]
Description=AutoTube AI GitHub Auto-Sync Service
After=network.target

[Service]
Type=oneshot
User=$USER_NAME
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/scripts/auto_sync.sh
EOF

sudo tee /etc/systemd/system/autotube-sync.timer > /dev/null << EOF
[Unit]
Description=Run AutoTube AI Auto-Sync every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Unit=autotube-sync.service

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable autotube.service
sudo systemctl enable autotube-sync.timer
sudo systemctl start autotube-sync.timer

echo -e "${GREEN}✓ Systemd service configured & timers enabled.${NC}"

# 7. Environment & Secrets Check
echo -e "\n${CYAN}[7/7] Checking API Keys and Secrets (.env)...${NC}"
if [ ! -f "$APP_DIR/.env" ]; then
    echo -e "${YELLOW}"
    echo "⚠️  CRITICAL NOTICE: .env file is not found in $APP_DIR!"
    echo "   AutoTube AI requires GEMINI_API_KEY to generate scripts and metadata."
    echo "   Please create it now by running:"
    echo "     nano $APP_DIR/.env"
    echo "   And paste your GEMINI_API_KEY and other credentials."
    echo -e "${NC}"
else
    echo -e "${GREEN}✓ .env file found! Starting AutoTube service...${NC}"
    sudo systemctl restart autotube.service
    echo -e "${GREEN}✓ AutoTube service active!${NC}"
    echo "Waiting 6 seconds for Cloudflare tunnel URL to generate..."
    sleep 6
    autotube-url
fi

echo -e "\n${GREEN}${BOLD}======================================================================"
echo "🎉 DEPLOYMENT READY ON ORACLE CLOUD ALWAYS FREE!"
echo "======================================================================"
echo -e "${NC}"
echo "Available commands on this server:"
echo "  👉 autotube-url     : Display the active mobile Cloudflare link"
echo "  👉 autotube-status  : Check process health, CPU/RAM usage"
echo "  👉 autotube-logs    : View live video generation and server logs"
echo "  👉 autotube-update  : Manually force update from GitHub and reload"
echo "  👉 autotube-restart : Restart the application service"
echo "======================================================================"
