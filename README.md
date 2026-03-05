# 🎬 trakt-to-letterboxd

**Automatically sync your Trakt watch history to Letterboxd — fully automated, self-hosted, browser-based.**

![Python](https://img.shields.io/badge/python-3.10+-blue?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![Docker](https://img.shields.io/badge/docker-ready-2496ed?style=flat-square)

---

## ✨ Features

- 🔄 **Full automation** — Trakt → CSV → Letterboxd, no human needed
- 🌐 **Web dashboard** — manage everything from your browser
- 🔐 **Login protected** — password-protected UI
- 🎬 **Movie browser** — searchable table of all synced films
- 📋 **Watchlist viewer** — live view of your Trakt watchlist  
- 📊 **Sync history** — log of every past run
- 🔍 **Movie search** — search Trakt database with IMDb/Letterboxd links
- ⏰ **Scheduler** — daily automatic sync at your chosen time
- 📱 **Telegram notifications** — get notified after every sync
- 🌙 **Dark / light theme**
- 🐳 **Docker ready**
- 🧙 **First-run setup wizard** — guided setup, no config files needed

---

## 🚀 Quick Start

### Option A — Python (recommended for Linux/Mac)

```bash
git clone https://github.com/kasundigital/trakt-to-letterboxd
cd trakt-to-letterboxd
./run.sh
```

Open **http://localhost:8888** — the setup wizard will guide you through everything.

### Option B — Docker

```bash
git clone https://github.com/kasundigital/trakt-to-letterboxd
cd trakt-to-letterboxd
docker compose up -d
```

Open **http://localhost:8888**

### Option C — Custom port

```bash
PORT=9000 ./run.sh
```

---

## ⚙️ Setup Wizard

On first launch, the setup wizard walks you through:

1. **Trakt API** — enter your Client ID, secret, and username
2. **Letterboxd** — enter your username and password for auto-import
3. **Schedule** — choose your daily sync time
4. **Notifications** — optional Telegram bot setup
5. **UI login** — set your dashboard username and password

No config files, no environment variables needed — just open the browser.

---

## 🔑 Getting Trakt API Credentials

1. Go to [trakt.tv/oauth/applications](https://trakt.tv/oauth/applications)
2. Click **New Application**
3. Fill in a name (e.g. "My Letterboxd Sync"), set redirect URI to `urn:ietf:wg:oauth:2.0:oob`
4. Copy the **Client ID** and **Client Secret** into the wizard

**Private profile?** You also need an Access Token:
```bash
# 1. Open this URL in your browser (replace YOUR_CLIENT_ID):
https://trakt.tv/oauth/authorize?response_type=code&client_id=YOUR_CLIENT_ID&redirect_uri=urn:ietf:wg:oauth:2.0:oob

# 2. Copy the PIN Trakt shows you, then run:
curl -X POST https://api.trakt.tv/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "code": "YOUR_PIN",
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
    "grant_type": "authorization_code"
  }'
# Copy "access_token" from the response
```

---

## 📱 Telegram Notifications

1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot`
2. Copy the bot token into Settings
3. Message [@userinfobot](https://t.me/userinfobot) to get your Chat ID
4. Click **Send Test Message** to verify

---

## 🐳 Docker Compose

```yaml
services:
  trakt-sync:
    build: .
    ports:
      - "8888:8888"
    volumes:
      - ./output:/app/output
      - ./logs:/app/logs
    restart: unless-stopped
```

Data persists in `./output` (CSV files) and `./logs` (config, state, history).

---

## 🖥️ Run as a System Service (Linux)

```bash
sudo cp trakt-sync.service /etc/systemd/system/
# Edit the file to set your username and path
sudo nano /etc/systemd/system/trakt-sync.service
sudo systemctl daemon-reload
sudo systemctl enable trakt-sync
sudo systemctl start trakt-sync
```

---

## 📁 Project Structure

```
trakt-to-letterboxd/
├── app.py                  # Flask web app
├── letterboxd_importer.py  # Letterboxd automation (curl_cffi + Playwright)
├── templates/
│   ├── index.html          # Main dashboard
│   ├── login.html          # Login page
│   └── setup.html          # First-run wizard
├── output/                 # Generated CSV files
├── logs/                   # Config, state, history (gitignored)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── run.sh
└── trakt-sync.service      # systemd service template
```

---

## ⚠️ Notes

- Letterboxd has no public write API — this tool uses browser automation to upload CSVs
- Your Letterboxd password is stored locally in `logs/config.json` — never commit this file
- Letterboxd's importer supports up to 1,900 films per CSV — larger libraries are split automatically (coming soon)
- Cloudflare protects Letterboxd — this tool uses `curl_cffi` to handle that transparently

---

## 🤝 Contributing

PRs welcome! Please open an issue first for major changes.

---

## 📄 License

MIT © 2026
