#!/usr/bin/env bash
# ==============================================================================
# AutoTube AI - Fast Secrets Sync to Oracle Cloud VM
# Securely transfers .env and YouTube OAuth tokens to your Oracle VM instance.
#
# Usage:
#   bash scripts/deploy_secrets_to_oracle.sh <ORACLE_PUBLIC_IP> [SSH_KEY_PATH]
# Example:
#   bash scripts/deploy_secrets_to_oracle.sh 150.136.10.50 ~/.ssh/ssh-key.key
# ==============================================================================

set -e

GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BOLD="\033[1m"
NC="\033[0m"

ORACLE_IP="$1"
SSH_KEY="$2"

if [ -z "$ORACLE_IP" ]; then
    echo -e "${RED}Error: Oracle Cloud Instance Public IP is required!${NC}"
    echo "Usage:   bash scripts/deploy_secrets_to_oracle.sh <ORACLE_PUBLIC_IP> [SSH_KEY_PATH]"
    echo "Example: bash scripts/deploy_secrets_to_oracle.sh 129.153.22.45 ~/.ssh/id_rsa"
    exit 1
fi

SSH_OPTS=""
if [ -n "$SSH_KEY" ]; then
    if [ ! -f "$SSH_KEY" ]; then
        echo -e "${RED}Error: SSH key file not found at $SSH_KEY${NC}"
        exit 1
    fi
    chmod 400 "$SSH_KEY"
    SSH_OPTS="-i $SSH_KEY"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

echo -e "${CYAN}${BOLD}Transferring Secrets to Oracle Cloud VM ($ORACLE_IP)...${NC}"

# 1. Transfer .env
if [ -f ".env" ]; then
    echo -e "${GREEN}✓ Uploading .env...${NC}"
    scp $SSH_OPTS .env "ubuntu@$ORACLE_IP:/home/ubuntu/autotube-ai/.env"
else
    echo -e "${YELLOW}⚠️ Local .env file not found.${NC}"
fi

# 2. Transfer token.json
if [ -f "token.json" ]; then
    echo -e "${GREEN}✓ Uploading token.json (YouTube Channel 1)...${NC}"
    scp $SSH_OPTS token.json "ubuntu@$ORACLE_IP:/home/ubuntu/autotube-ai/token.json"
fi

# 3. Transfer token_channel2.json
if [ -f "token_channel2.json" ]; then
    echo -e "${GREEN}✓ Uploading token_channel2.json (YouTube Channel 2)...${NC}"
    scp $SSH_OPTS token_channel2.json "ubuntu@$ORACLE_IP:/home/ubuntu/autotube-ai/token_channel2.json"
fi

# 4. Restart AutoTube service on VM to load new secrets
echo -e "\n${CYAN}Restarting AutoTube service on Oracle Cloud VM...${NC}"
ssh $SSH_OPTS "ubuntu@$ORACLE_IP" "sudo systemctl restart autotube.service && autotube-url"

echo -e "\n${GREEN}${BOLD}🎉 Secrets successfully deployed & AutoTube is running!${NC}\n"
