#!/bin/bash
# deploy.sh — Installer og start NEXUS på Hetzner-serveren
# Kjør: bash deploy.sh

set -e

NEXUS_DIR="/opt/nexus"
PYTHON="python3"
USER_NAME=$(whoami)

echo "========================================"
echo "  NEXUS — Deployment til Hetzner"
echo "========================================"

# 1. Oppdater system
echo "[1/7] Oppdaterer system..."
apt-get update -qq && apt-get upgrade -y -qq

# 2. Installer Python3 + venv
echo "[2/7] Sjekker Python3..."
apt-get install -y python3 python3-venv python3-dev -qq

# 3. Klargjør mappe
echo "[3/7] Klargjør $NEXUS_DIR..."
mkdir -p $NEXUS_DIR/logs

# 4. Virtual environment + pakker
echo "[4/7] Installerer Python-pakker..."
cd $NEXUS_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# 5. .env
if [ ! -f "$NEXUS_DIR/.env" ]; then
    echo "⚠️  Ingen .env funnet — kopierer fra .env.example"
    cp $NEXUS_DIR/.env.example $NEXUS_DIR/.env
    echo "   Rediger /opt/nexus/.env og fyll inn manglende nøkler!"
fi

# 6. Systemd: NEXUS Scheduler
echo "[5/7] Setter opp nexus-scheduler tjeneste..."
cat > /etc/systemd/system/nexus-scheduler.service <<EOF
[Unit]
Description=NEXUS Scheduler (morgen/middag/kveld rutiner)
After=network.target

[Service]
Type=simple
WorkingDirectory=$NEXUS_DIR
ExecStart=$NEXUS_DIR/venv/bin/python scheduler.py
Restart=always
RestartSec=30
EnvironmentFile=$NEXUS_DIR/.env
StandardOutput=append:$NEXUS_DIR/logs/scheduler.log
StandardError=append:$NEXUS_DIR/logs/scheduler.log

[Install]
WantedBy=multi-user.target
EOF

# 7. Systemd: NEXUS Telegram Bot
echo "[6/7] Setter opp nexus-bot tjeneste..."
cat > /etc/systemd/system/nexus-bot.service <<EOF
[Unit]
Description=NEXUS Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=$NEXUS_DIR
ExecStart=$NEXUS_DIR/venv/bin/python nexus_bot.py
Restart=always
RestartSec=10
EnvironmentFile=$NEXUS_DIR/.env
StandardOutput=append:$NEXUS_DIR/logs/telegram.log
StandardError=append:$NEXUS_DIR/logs/telegram.log

[Install]
WantedBy=multi-user.target
EOF

echo "[7/7] Aktiverer og starter tjenestene..."

# Platform service
cp $NEXUS_DIR/nexus-platform.service /etc/systemd/system/nexus-platform.service

systemctl daemon-reload
systemctl enable nexus-scheduler nexus-bot nexus-webhook nexus-dashboard nexus-platform
systemctl start nexus-scheduler nexus-bot nexus-webhook nexus-dashboard nexus-platform

echo ""
echo "========================================"
echo "  NEXUS er oppe og kjører!"
echo "========================================"
echo ""
echo "Status:"
systemctl is-active nexus-scheduler && echo "  ✅ nexus-scheduler: aktiv" || echo "  ❌ nexus-scheduler: feil"
systemctl is-active nexus-bot       && echo "  ✅ nexus-bot: aktiv"       || echo "  ❌ nexus-bot: feil"
systemctl is-active nexus-webhook   && echo "  ✅ nexus-webhook: aktiv"   || echo "  ❌ nexus-webhook: feil"
systemctl is-active nexus-dashboard && echo "  ✅ nexus-dashboard: aktiv" || echo "  ❌ nexus-dashboard: feil"
systemctl is-active nexus-platform  && echo "  ✅ nexus-platform: aktiv"  || echo "  ❌ nexus-platform: feil"
echo ""
echo "URLs:"
echo "  🏢 Kontoret (platform):  http://89.167.100.7:8091"
echo "  📊 Dashboard:            http://89.167.100.7:8090"
echo "  🔗 Webhook:              http://89.167.100.7:8080"
echo ""
echo "Nyttige kommandoer:"
echo "  journalctl -u nexus-platform -f    — Platform logg"
echo "  journalctl -u nexus-bot -f         — Telegram bot logg"
echo "  systemctl restart nexus-platform   — Restart plattformen"
echo ""
echo "Åpne Telegram og send /start til boten din!"
