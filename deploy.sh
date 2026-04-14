#!/bin/bash
# Deploy Thermal Printer Terminal to remote node
# Requires: rsync, ssh (Linux/macOS only)
#
# Usage:
#   ./deploy.sh              # deploy to default target
#   ./deploy.sh 10.42.10.41  # deploy to specific IP
#   ./deploy.sh user@host    # deploy with custom user

set -e

TARGET="${1:-root@10.42.10.41}"
REMOTE_DIR="/opt/thermalprinter"

echo "=== Thermal Printer Terminal Deployer ==="
echo "Target: $TARGET:$REMOTE_DIR"
echo ""

# Sync files
echo "[1/4] Syncing files..."
rsync -avz --delete \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.venv' \
    --exclude='.env' \
    --exclude='data/' \
    --exclude='.git' \
    ./ "$TARGET:$REMOTE_DIR/"

# Copy .env.example if .env doesn't exist
echo "[2/4] Checking config..."
ssh "$TARGET" "cd $REMOTE_DIR && [ -f .env ] || cp .env.example .env && echo 'Created .env from example'"

# Install dependencies
echo "[3/4] Installing dependencies..."
ssh "$TARGET" "cd $REMOTE_DIR && \
    python3 -m venv .venv 2>/dev/null || true && \
    .venv/bin/pip install -q -r requirements.txt"

# Install and restart service
echo "[4/4] Restarting service..."
ssh "$TARGET" "cp $REMOTE_DIR/thermalprinter.service /etc/systemd/system/ && \
    systemctl daemon-reload && \
    systemctl enable thermalprinter && \
    systemctl restart thermalprinter && \
    echo 'Service restarted.'"

echo ""
echo "=== Deployment complete ==="
echo "App should be running at http://$( echo $TARGET | sed 's/.*@//' ):8080"
