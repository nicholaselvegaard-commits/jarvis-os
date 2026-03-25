#!/bin/bash
# NEXUS Deploy Script — scp to Hetzner + restart systemd service
# Usage: bash deploy/deploy.sh

set -e

SERVER="root@89.167.100.7"
REMOTE_DIR="/opt/nexus"
SERVICE_NAME="nexus"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=================================================="
echo " NEXUS Deploy"
echo " Local:  $LOCAL_DIR"
echo " Remote: $SERVER:$REMOTE_DIR"
echo "=================================================="

# Sync all files (exclude venv, __pycache__, .git, *.db, *.log)
echo "[1/4] Syncing files..."
rsync -avz --progress \
  --exclude='venv/' \
  --exclude='__pycache__/' \
  --exclude='.git/' \
  --exclude='*.db' \
  --exclude='*.log' \
  --exclude='memory/conversations/' \
  --exclude='memory/voice_*.ogg' \
  --exclude='.env' \
  "$LOCAL_DIR/" "$SERVER:$REMOTE_DIR/"

# Install/update systemd service
echo "[2/4] Installing systemd service..."
ssh "$SERVER" "cp $REMOTE_DIR/deploy/nexus.service /etc/systemd/system/$SERVICE_NAME.service && systemctl daemon-reload && systemctl enable $SERVICE_NAME"

# Install/update Python dependencies
echo "[3/4] Installing Python dependencies..."
ssh "$SERVER" "cd $REMOTE_DIR && /opt/nexus/venv/bin/pip install -r requirements.txt -q"

# Restart service
echo "[4/4] Restarting $SERVICE_NAME service..."
ssh "$SERVER" "systemctl restart $SERVICE_NAME"

# Wait and check status
sleep 3
echo ""
echo "=== Service Status ==="
ssh "$SERVER" "systemctl status $SERVICE_NAME --no-pager -l | head -30"

echo ""
echo "=== Recent Logs ==="
ssh "$SERVER" "journalctl -u $SERVICE_NAME -n 20 --no-pager"

echo ""
echo "✅ Deploy complete!"
echo "Run 'ssh $SERVER journalctl -u $SERVICE_NAME -f' to follow logs."
