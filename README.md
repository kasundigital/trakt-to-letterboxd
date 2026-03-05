# 🎬 trakt-to-letterboxd

**Automatically sync your Trakt watch history to Letterboxd — fully automated, self-hosted, browser-based.**

![Python](https://img.shields.io/badge/python-3.10+-blue?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![Docker](https://img.shields.io/badge/docker-ready-2496ed?style=flat-square)

---

## ✨ Features

- 🔄 **Full automation** — Trakt → CSV → Letterboxd, no human needed
- 🧙 **First-run wizard** — guided setup in the browser, no config files
- 🌐 **Web dashboard** — manage everything from your browser
- 🔐 **Login protected** — password-protected UI
- 🎬 **Movie browser** — searchable/filterable table of all synced films
- 📋 **Watchlist viewer** — live view of your Trakt watchlist
- 📊 **Sync history** — log of every past run with duration and count
- 🔍 **Movie search** — search Trakt database with IMDb/Letterboxd links
- ⏰ **Daily scheduler** — automatic sync at your chosen time
- 📱 **Telegram notifications** — get notified after every sync
- 🌙 **Dark / light theme**
- 🐳 **Docker ready**

---

## 🚀 Install

### One command — native (Linux)

```bash
git clone https://github.com/kasundigital/trakt-to-letterboxd
cd trakt-to-letterboxd
sudo ./install.sh
```

Installs dependencies, sets up a systemd service, and starts on boot. Then open:

```
http://YOUR_SERVER_IP:8888
```

---

### One command — Docker

```bash
git clone https://github.com/kasundigital/trakt-to-letterboxd
cd trakt-to-letterboxd
sudo ./install.sh --docker
```

Installs Docker if needed, builds the image, starts the container, and registers auto-start on boot.

---

### Custom port

```bash
PORT=9000 sudo ./install.sh
PORT=9000 sudo ./install.sh --docker
```

---

### Manual / development

```bash
git clone https://github.com/kasundigital/trakt-to-letterboxd
cd trakt-to-letterboxd
./run.sh
```

---

## 🧙 First-Run Wizard

On first visit, a **5-step setup wizard** guides you through everything in the browser:

| Step | What you configure |
|------|-------------------|
| 1 | Trakt API credentials (Client ID, Secret, Username) |
| 2 | Letterboxd login for auto-import |
| 3 | Sync schedule, mode, and what to sync |
| 4 | Telegram notifications (optional) |
| 5 | Dashboard username and password |

No config files, no `.env`, no editing YAML.

---

## ⚙️ Useful commands

### Native service

```bash
sudo systemctl status  trakt-sync      # check status
sudo systemctl restart trakt-sync      # restart
sudo systemctl stop    trakt-sync      # stop
sudo journalctl -u     trakt-sync -f   # live logs
sudo ./install.sh --uninstall          # remove
```

### Docker

```bash
docker compose ps                              # status
docker compose logs -f                         # live logs
docker compose restart                         # restart
docker compose down                            # stop
docker compose pull && docker compose up -d    # update to latest
```

---

## 🔑 Getting Trakt API Credentials

1. Go to [trakt.tv/oauth/applications](https://trakt.tv/oauth/applications)
2. Click **New Application**
3. Name it anything, set redirect URI to `urn:ietf:wg:oauth:2.0:oob`
4. Copy **Client ID** and **Client Secret** into the wizard

**Private profile?** You also need an Access Token:

```bash
# Step 1 — open this URL in your browser:
https://trakt.tv/oauth/authorize?response_type=code&client_id=YOUR_CLIENT_ID&redirect_uri=urn:ietf:wg:oauth:2.0:oob

# Step 2 — exchange the PIN for a token:
curl -s -X POST https://api.trakt.tv/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "code": "YOUR_PIN",
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
    "grant_type": "authorization_code"
  }' | python3 -m json.tool
# Copy "access_token" from the output into the wizard
```

---

## 📱 Telegram Notifications

1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token
2. Message [@userinfobot](https://t.me/userinfobot) → copy your Chat ID
3. Paste both into Step 4 of the wizard and click **Test**

---

## 📁 Project Structure

```
trakt-to-letterboxd/
├── app.py                   # Flask app + API + sync engine
├── letterboxd_importer.py   # Cloudflare bypass + Letterboxd upload
├── install.sh               # One-command installer (native + Docker)
├── run.sh                   # Manual / dev startup
├── templates/
│   ├── setup.html           # First-run wizard (5 steps)
│   ├── index.html           # Main dashboard
│   └── login.html           # Login page
├── output/                  # Generated CSV files (gitignored)
├── logs/                    # Config, state, history (gitignored)
├── Dockerfile
├── docker-compose.yml
├── trakt-sync.service       # systemd template (used by install.sh)
└── requirements.txt
```

---

## ⚠️ Notes

- Letterboxd has **no public write API** — this tool uploads CSVs via browser automation
- Your Letterboxd password is stored locally in `logs/config.json` — never commit this file
- Letterboxd supports up to **1,900 films per CSV** — chunking for larger libraries coming soon
- Cloudflare protects Letterboxd — `curl_cffi` handles this transparently

---

## 🤝 Contributing

PRs welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 📄 License

MIT © 2026 — [kasundigital](https://github.com/kasundigital)
