#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  trakt-to-letterboxd — installer
#  Usage:
#    ./install.sh              → install as systemd service
#    ./install.sh --docker     → install with Docker
#    ./install.sh --uninstall  → remove service
# ─────────────────────────────────────────────────────────────────
set -e

APP_NAME="trakt-to-letterboxd"
SERVICE_NAME="trakt-sync"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8888}"
CURRENT_USER="${SUDO_USER:-$USER}"
MODE="${1:-}"

# ── Colors ────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()     { echo -e "${GREEN}✓${NC} $1"; }
info()    { echo -e "${BLUE}→${NC} $1"; }
warn()    { echo -e "${YELLOW}⚠${NC} $1"; }
error()   { echo -e "${RED}✗${NC} $1"; exit 1; }
heading() { echo -e "\n${BOLD}${CYAN}$1${NC}"; }

banner() {
  echo ""
  echo -e "${BOLD}  ┌─────────────────────────────────────┐${NC}"
  echo -e "${BOLD}  │   trakt-to-letterboxd installer     │${NC}"
  echo -e "${BOLD}  │   Trakt → CSV → Letterboxd sync     │${NC}"
  echo -e "${BOLD}  └─────────────────────────────────────┘${NC}"
  echo ""
}

# ── Uninstall ─────────────────────────────────────────────────────
uninstall() {
  banner
  heading "Uninstalling $APP_NAME..."
  if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl stop "$SERVICE_NAME"
    log "Service stopped"
  fi
  if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl disable "$SERVICE_NAME"
    log "Service disabled"
  fi
  rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
  systemctl daemon-reload
  log "Service removed"
  echo ""
  echo -e "${GREEN}Done.${NC} App files in ${APP_DIR} were NOT deleted."
  echo ""
  exit 0
}

# ── Docker install ────────────────────────────────────────────────
install_docker() {
  banner
  heading "Installing with Docker..."

  # Check docker
  if ! command -v docker &>/dev/null; then
    info "Docker not found — installing..."
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker "$CURRENT_USER"
    log "Docker installed"
  else
    log "Docker found: $(docker --version)"
  fi

  # Check docker compose
  if ! docker compose version &>/dev/null 2>&1; then
    info "Installing Docker Compose plugin..."
    apt-get install -y docker-compose-plugin 2>/dev/null || \
    pip install docker-compose 2>/dev/null || \
    warn "Could not auto-install docker compose — install manually"
  else
    log "Docker Compose found"
  fi

  cd "$APP_DIR"

  # Build and start
  heading "Building image (this takes ~2 min first time)..."
  docker compose build

  heading "Starting container..."
  docker compose up -d

  sleep 3

  if docker compose ps | grep -q "Up"; then
    log "Container running"
  else
    warn "Container may have issues — check: docker compose logs"
  fi

  # Install as system service so it starts on boot
  heading "Installing Docker start-on-boot service..."
  cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=trakt-to-letterboxd (Docker)
After=docker.service network.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=${CURRENT_USER}

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME"
  log "Auto-start on boot enabled"

  print_success_docker
}

# ── Native install ────────────────────────────────────────────────
install_native() {
  banner
  heading "Installing as systemd service..."

  # Check running as root
  if [ "$EUID" -ne 0 ]; then
    error "Please run with sudo: sudo ./install.sh"
  fi

  # Check Python
  if ! command -v python3 &>/dev/null; then
    error "python3 not found. Install it: sudo apt install python3"
  fi
  log "Python: $(python3 --version)"

  # Check pip / venv
  if ! python3 -m venv --help &>/dev/null; then
    info "Installing python3-venv..."
    apt-get install -y python3-venv python3-pip
  fi

  cd "$APP_DIR"

  # Create venv
  heading "Setting up Python environment..."
  if [ ! -d "venv" ]; then
    python3 -m venv venv
    log "Virtual environment created"
  else
    log "Virtual environment already exists"
  fi

  info "Installing Python packages..."
  venv/bin/pip install -r requirements.txt -q --upgrade
  log "Python packages installed"

  # Playwright
  heading "Installing Playwright Chromium..."
  if [ ! -d "${HOME}/.cache/ms-playwright" ] && [ ! -d "/root/.cache/ms-playwright" ]; then
    venv/bin/playwright install chromium
    venv/bin/playwright install-deps chromium 2>/dev/null || true
    log "Playwright installed"
  else
    log "Playwright already installed"
  fi

  # Create systemd service
  heading "Creating systemd service..."
  cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=trakt-to-letterboxd sync service
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/python app.py
Environment=PORT=${PORT}
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME"
  systemctl start "$SERVICE_NAME"
  sleep 2

  if systemctl is-active --quiet "$SERVICE_NAME"; then
    log "Service started successfully"
  else
    warn "Service may have failed to start"
    warn "Check logs: journalctl -u $SERVICE_NAME -n 20"
  fi

  print_success_native
}

# ── Success messages ──────────────────────────────────────────────
print_success_native() {
  echo ""
  echo -e "${GREEN}${BOLD}  ✓ Installation complete!${NC}"
  echo ""
  echo -e "  ${BOLD}Dashboard:${NC}   http://$(hostname -I | awk '{print $1}'):${PORT}"
  echo -e "  ${BOLD}Local:${NC}       http://localhost:${PORT}"
  echo ""
  echo -e "  ${CYAN}Open the URL above to complete setup via the wizard.${NC}"
  echo ""
  echo -e "  ${BOLD}Useful commands:${NC}"
  echo -e "    systemctl status  $SERVICE_NAME   # check status"
  echo -e "    systemctl restart $SERVICE_NAME   # restart"
  echo -e "    systemctl stop    $SERVICE_NAME   # stop"
  echo -e "    journalctl -u     $SERVICE_NAME -f  # live logs"
  echo ""
  echo -e "  ${BOLD}Uninstall:${NC}   sudo ./install.sh --uninstall"
  echo ""
}

print_success_docker() {
  echo ""
  echo -e "${GREEN}${BOLD}  ✓ Docker installation complete!${NC}"
  echo ""
  echo -e "  ${BOLD}Dashboard:${NC}   http://$(hostname -I | awk '{print $1}'):${PORT}"
  echo -e "  ${BOLD}Local:${NC}       http://localhost:${PORT}"
  echo ""
  echo -e "  ${CYAN}Open the URL above to complete setup via the wizard.${NC}"
  echo ""
  echo -e "  ${BOLD}Useful commands:${NC}"
  echo -e "    docker compose ps           # check status"
  echo -e "    docker compose logs -f      # live logs"
  echo -e "    docker compose restart      # restart"
  echo -e "    docker compose down         # stop"
  echo -e "    docker compose pull && docker compose up -d  # update"
  echo ""
}

# ── Main ──────────────────────────────────────────────────────────
case "$MODE" in
  --uninstall)
    [ "$EUID" -ne 0 ] && error "Please run with sudo: sudo ./install.sh --uninstall"
    uninstall ;;
  --docker)
    [ "$EUID" -ne 0 ] && error "Please run with sudo: sudo ./install.sh --docker"
    install_docker ;;
  "")
    install_native ;;
  *)
    echo "Usage: sudo ./install.sh [--docker] [--uninstall]"
    exit 1 ;;
esac
