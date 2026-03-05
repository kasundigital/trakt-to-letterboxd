#!/bin/bash
set -e

PORT=${PORT:-8888}
VENV="venv"

echo ""
echo "  ┌─────────────────────────────────────┐"
echo "  │   trakt-to-letterboxd               │"
echo "  │   Trakt → CSV → Letterboxd sync     │"
echo "  └─────────────────────────────────────┘"
echo ""
echo "  Port : $PORT"
echo ""

# Create venv if needed
if [ ! -d "$VENV" ]; then
  echo "📦 Creating virtual environment..."
  python3 -m venv "$VENV"
fi

# Install / upgrade dependencies
echo "📦 Checking dependencies..."
"$VENV/bin/pip" install -r requirements.txt -q --upgrade

# Install Playwright browser if not present
if [ ! -d "$HOME/.cache/ms-playwright" ]; then
  echo "🎭 Installing Playwright Chromium (one-time)..."
  "$VENV/bin/playwright" install chromium
  "$VENV/bin/playwright" install-deps chromium 2>/dev/null || true
fi

echo "🚀 Starting server → http://localhost:$PORT"
echo "   Press Ctrl+C to stop"
echo ""

PORT=$PORT "$VENV/bin/python" app.py
