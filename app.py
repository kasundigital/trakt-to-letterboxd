#!/usr/bin/env python3
"""
trakt-to-letterboxd
Automatically sync your Trakt watch history to Letterboxd.
https://github.com/YOUR_USERNAME/trakt-to-letterboxd
"""

import os, csv, json, time, logging, threading, schedule, requests, secrets
from io import StringIO
from datetime import datetime, timezone
from pathlib import Path
from functools import wraps
from flask import (Flask, render_template, request, jsonify,
                   send_file, session, redirect, url_for)

__version__ = "1.0.0"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

BASE_DIR     = Path(__file__).parent
OUTPUT_DIR   = BASE_DIR / "output"
LOG_DIR      = BASE_DIR / "logs"
STATE_FILE   = LOG_DIR / "state.json"
CONFIG_FILE  = LOG_DIR / "config.json"
MOVIES_FILE  = LOG_DIR / "movies.json"
HISTORY_FILE = LOG_DIR / "history.json"

for d in (OUTPUT_DIR, LOG_DIR): d.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("trakt-sync")

log_buffer        = []
scheduler_running = False
sync_in_progress  = False
scheduler_thread  = None

# ── Logging ───────────────────────────────────────────────────────
def add_log(msg, level="info"):
    entry = {"time": datetime.now().strftime("%H:%M:%S"), "msg": msg, "level": level}
    log_buffer.append(entry)
    if len(log_buffer) > 500: log_buffer.pop(0)
    logger.info(msg)

# ── Config ────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "client_id": "", "client_secret": "", "username": "", "access_token": "",
    "lb_username": "", "lb_password": "",
    "sync_history": True, "sync_ratings": True, "sync_watchlist": False,
    "sync_mode": "incremental", "sync_time": "03:00",
    "run_on_start": False, "auto_import": False,
    "ui_username": "admin", "ui_password": "admin123",
    "telegram_token": "", "telegram_chat_id": "",
    "theme": "dark", "setup_complete": False,
}

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f: return {**DEFAULT_CONFIG, **json.load(f)}
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f: json.dump(cfg, f, indent=2)

def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f: return json.load(f)
    return {"last_sync": None, "last_import": None,
            "total_synced": 0, "total_imported": 0, "runs": 0, "last_count": 0}

def save_state(s):
    with open(STATE_FILE, "w") as f: json.dump(s, f, indent=2)

def load_movies():
    if MOVIES_FILE.exists():
        with open(MOVIES_FILE) as f: return json.load(f)
    return []

def save_movies(movies):
    with open(MOVIES_FILE, "w") as f: json.dump(movies, f, indent=2)

def load_history():
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE) as f: return json.load(f)
    return []

def save_history(h):
    with open(HISTORY_FILE, "w") as f: json.dump(h, f, indent=2)

def is_setup_complete():
    return load_config().get("setup_complete", False)

# ── Auth ──────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_setup_complete():
            return redirect(url_for("setup_page"))
        if not session.get("logged_in"):
            if request.is_json: return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated

# ── Routes: Auth ──────────────────────────────────────────────────
@app.route("/")
def root():
    if not is_setup_complete(): return redirect(url_for("setup_page"))
    if not session.get("logged_in"): return redirect(url_for("login_page"))
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if not is_setup_complete(): return redirect(url_for("setup_page"))
    cfg = load_config()
    if request.method == "POST":
        data = request.json or request.form
        if (data.get("username") == cfg["ui_username"] and
                data.get("password") == cfg["ui_password"]):
            session["logged_in"] = True
            return jsonify({"ok": True}) if request.is_json else redirect(url_for("root"))
        return jsonify({"ok": False, "error": "Invalid credentials"}), 401
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))

# ── Routes: Setup Wizard ──────────────────────────────────────────
@app.route("/setup")
def setup_page():
    if is_setup_complete(): return redirect(url_for("root"))
    return render_template("setup.html", version=__version__)

@app.route("/api/setup/test-trakt", methods=["POST"])
def setup_test_trakt():
    data = request.json
    try:
        headers = {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": data["client_id"],
        }
        if data.get("access_token"):
            headers["Authorization"] = f"Bearer {data['access_token']}"
        r = requests.get(
            f"https://api.trakt.tv/users/{data['username']}/stats",
            headers=headers, timeout=10)
        r.raise_for_status()
        d = r.json()
        return jsonify({"ok": True,
                        "watched": d.get("movies", {}).get("watched", 0),
                        "username": data["username"]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

@app.route("/api/setup/complete", methods=["POST"])
def setup_complete():
    data = request.json
    cfg = {**DEFAULT_CONFIG, **data, "setup_complete": True}
    save_config(cfg)
    session["logged_in"] = True
    return jsonify({"ok": True})

# ── Trakt API ─────────────────────────────────────────────────────
def make_headers(cfg):
    h = {"Content-Type": "application/json",
         "trakt-api-version": "2", "trakt-api-key": cfg["client_id"]}
    if cfg.get("access_token"): h["Authorization"] = f"Bearer {cfg['access_token']}"
    return h

def trakt_pages(url, headers, params=None):
    items, page = [], 1
    while True:
        p = {**(params or {}), "limit": 100, "page": page}
        r = requests.get(url, headers=headers, params=p, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch: break
        items.extend(batch)
        total = int(r.headers.get("X-Pagination-Page-Count", 1))
        add_log(f"  page {page}/{total} — {len(items)} entries")
        if page >= total: break
        page += 1
        time.sleep(0.2)
    return items

def fetch_history(cfg, start_at=None):
    return trakt_pages(
        f"https://api.trakt.tv/users/{cfg['username']}/history/movies",
        make_headers(cfg), {"start_at": start_at} if start_at else {})

def fetch_ratings(cfg):
    r = requests.get(f"https://api.trakt.tv/users/{cfg['username']}/ratings/movies",
                     headers=make_headers(cfg), timeout=30)
    r.raise_for_status()
    return {i["movie"]["ids"]["imdb"]: i["rating"] for i in r.json()}

def fetch_watchlist(cfg):
    r = requests.get(f"https://api.trakt.tv/users/{cfg['username']}/watchlist/movies",
                     headers=make_headers(cfg), timeout=30)
    r.raise_for_status()
    return r.json()

# ── CSV ───────────────────────────────────────────────────────────
FIELDS = ["Title", "Year", "imdbID", "WatchedDate", "Rating10", "Rewatch"]

def build_csv(history, ratings_map, watchlist, cfg):
    rows, seen, movie_list = [], {}, []
    if cfg["sync_history"]:
        for e in history:
            m = e["movie"]
            imdb = m["ids"].get("imdb", "")
            key  = imdb or m["title"]
            rewatch = "true" if key in seen else "false"
            seen[key] = True
            date = (e.get("watched_at") or "")[:10]
            raw  = ratings_map.get(imdb, "")
            rating = ""
            if raw:
                rv = round(raw / 2, 1)
                rating = int(rv) if rv == int(rv) else rv
            rows.append({"Title": m["title"], "Year": m.get("year", ""),
                         "imdbID": imdb, "WatchedDate": date,
                         "Rating10": rating, "Rewatch": rewatch})
            movie_list.append({"title": m["title"], "year": m.get("year", ""),
                               "imdb": imdb, "date": date, "rating": rating,
                               "rewatch": rewatch == "true", "type": "watched"})
    if cfg["sync_watchlist"]:
        for e in watchlist:
            m = e["movie"]
            imdb = m["ids"].get("imdb", "")
            rows.append({"Title": m["title"], "Year": m.get("year", ""),
                         "imdbID": imdb, "WatchedDate": "", "Rating10": "", "Rewatch": "false"})
            movie_list.append({"title": m["title"], "year": m.get("year", ""),
                               "imdb": imdb, "date": "", "rating": "",
                               "rewatch": False, "type": "watchlist"})
    buf = StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS)
    w.writeheader(); w.writerows(rows)
    return buf.getvalue(), len(rows), movie_list

def write_csv_file(content):
    date_str = datetime.now().strftime("%Y-%m-%d")
    named  = OUTPUT_DIR / f"letterboxd-{date_str}.csv"
    latest = OUTPUT_DIR / "letterboxd-latest.csv"
    for p in (named, latest): p.write_text(content, encoding="utf-8")
    return latest

# ── Telegram ──────────────────────────────────────────────────────
def send_telegram(token, chat_id, msg):
    if not token or not chat_id: return
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                      timeout=10)
    except Exception as e:
        add_log(f"Telegram error: {e}", "warn")

# ── Letterboxd import ─────────────────────────────────────────────
def run_lb_import(cfg, csv_path, state):
    add_log("━━━ Starting Letterboxd auto-import ━━━")
    if not cfg.get("lb_username") or not cfg.get("lb_password"):
        add_log("⚠ Letterboxd credentials not set", "warn"); return
    try:
        from letterboxd_importer import import_to_letterboxd
        result = import_to_letterboxd(
            csv_path, cfg["lb_username"], cfg["lb_password"], log_fn=add_log)
        if result["ok"]:
            state["last_import"]     = datetime.now(timezone.utc).isoformat()
            state["total_imported"] += result["imported"]
            save_state(state)
            add_log(f"✓ Letterboxd import — {result['imported']} films", "success")
            send_telegram(cfg.get("telegram_token"), cfg.get("telegram_chat_id"),
                f"✅ *Trakt→Letterboxd Sync Complete*\n"
                f"📽 {result['imported']} films imported\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        else:
            add_log(f"✗ Import failed: {result['message']}", "error")
            send_telegram(cfg.get("telegram_token"), cfg.get("telegram_chat_id"),
                f"❌ *Letterboxd Import Failed*\n{result['message']}")
    except ImportError:
        add_log("✗ letterboxd_importer not found", "error")

# ── Core sync ─────────────────────────────────────────────────────
def run_sync_job():
    global sync_in_progress
    if sync_in_progress:
        add_log("Sync already running, skipping.", "warn"); return 0
    sync_in_progress = True
    cfg   = load_config()
    state = load_state()
    if not cfg["client_id"] or not cfg["username"]:
        add_log("❌ Missing Trakt credentials — go to Settings", "error")
        sync_in_progress = False; return 0

    add_log("━━━ Starting Trakt → Letterboxd sync ━━━")
    start_time = datetime.now()

    try:
        r = requests.get(f"https://api.trakt.tv/users/{cfg['username']}/stats",
                         headers=make_headers(cfg), timeout=10)
        r.raise_for_status()
        watched = r.json().get("movies", {}).get("watched", 0)
        add_log(f"✓ Trakt @{cfg['username']} — {watched} films total", "success")

        start_at = None
        if cfg["sync_mode"] == "incremental" and state["last_sync"]:
            start_at = state["last_sync"]
            add_log(f"Incremental from {start_at[:10]}")

        history, ratings_map, watchlist = [], {}, []
        if cfg["sync_history"]:
            add_log("Fetching watch history...")
            history = fetch_history(cfg, start_at)
            add_log(f"✓ {len(history)} entries", "success")
        if cfg["sync_ratings"]:
            add_log("Fetching ratings...")
            ratings_map = fetch_ratings(cfg)
            add_log(f"✓ {len(ratings_map)} ratings", "success")
        if cfg["sync_watchlist"]:
            add_log("Fetching watchlist...")
            watchlist = fetch_watchlist(cfg)
            add_log(f"✓ {len(watchlist)} items", "success")

        csv_content, count, movie_list = build_csv(history, ratings_map, watchlist, cfg)
        csv_path = write_csv_file(csv_content)
        add_log(f"✓ CSV saved — {count} entries", "success")

        # Persist movies
        existing = load_movies()
        existing_keys = {m["imdb"] or m["title"] for m in existing}
        new_movies = [m for m in movie_list if (m["imdb"] or m["title"]) not in existing_keys]
        save_movies(existing + new_movies)

        state["last_sync"]     = datetime.now(timezone.utc).isoformat()
        state["total_synced"] += count
        state["runs"]         += 1
        state["last_count"]    = count
        save_state(state)

        history_entry = {
            "run": state["runs"],
            "time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": count, "mode": cfg["sync_mode"],
            "duration": round((datetime.now() - start_time).total_seconds(), 1),
            "status": "success", "imported": 0,
        }

        if cfg.get("auto_import") and count > 0:
            run_lb_import(cfg, csv_path, state)
            history_entry["imported"] = state.get("total_imported", 0)
        elif count == 0:
            add_log("No new entries since last sync.")
            send_telegram(cfg.get("telegram_token"), cfg.get("telegram_chat_id"),
                "ℹ️ *Trakt Sync* — No new films since last run.")

        h = load_history(); h.insert(0, history_entry); save_history(h[:100])
        add_log(f"━━━ Done — {count} entries | run #{state['runs']} ━━━", "success")
        sync_in_progress = False
        return count

    except Exception as e:
        add_log(f"❌ Sync error: {e}", "error")
        send_telegram(cfg.get("telegram_token"), cfg.get("telegram_chat_id"),
            f"❌ *Sync Error*\n{str(e)[:200]}")
        h = load_history()
        h.insert(0, {"run": load_state().get("runs", 0), "time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                     "count": 0, "mode": "—", "duration": 0, "status": "error", "imported": 0})
        save_history(h[:100])
        sync_in_progress = False
        return 0

# ── Scheduler ─────────────────────────────────────────────────────
def start_scheduler(sync_time):
    global scheduler_thread, scheduler_running
    scheduler_running = True
    schedule.clear()
    schedule.every().day.at(sync_time).do(run_sync_job)
    add_log(f"🕐 Scheduler started — daily at {sync_time}", "success")
    def loop():
        while scheduler_running:
            schedule.run_pending()
            time.sleep(30)
    scheduler_thread = threading.Thread(target=loop, daemon=True)
    scheduler_thread.start()

def stop_scheduler():
    global scheduler_running
    scheduler_running = False
    schedule.clear()
    add_log("⏹ Scheduler stopped", "warn")

# ── API routes ────────────────────────────────────────────────────
@app.route("/api/config", methods=["GET"])
@login_required
def get_config():
    cfg = load_config()
    safe = {**cfg}
    for k in ("client_secret", "access_token", "lb_password", "ui_password"):
        if safe.get(k): safe[k] = "••••••••"
    return jsonify(safe)

@app.route("/api/config", methods=["POST"])
@login_required
def post_config():
    data = request.json
    cfg = load_config()
    for key in DEFAULT_CONFIG:
        if key in data and data[key] != "••••••••":
            cfg[key] = data[key]
    save_config(cfg)
    return jsonify({"ok": True})

@app.route("/api/status")
@login_required
def get_status():
    state = load_state()
    cfg   = load_config()
    return jsonify({
        "state": state,
        "scheduler_running": scheduler_running,
        "sync_in_progress":  sync_in_progress,
        "configured":        bool(cfg["client_id"] and cfg["username"]),
        "auto_import":       cfg.get("auto_import", False),
        "lb_configured":     bool(cfg.get("lb_username") and cfg.get("lb_password")),
        "sync_time":         cfg["sync_time"],
        "theme":             cfg.get("theme", "dark"),
        "version":           __version__,
        "outputs":           sorted([f.name for f in OUTPUT_DIR.glob("*.csv")], reverse=True)[:10],
    })

@app.route("/api/logs")
@login_required
def get_logs():
    since = int(request.args.get("since", 0))
    return jsonify(log_buffer[since:])

@app.route("/api/sync", methods=["POST"])
@login_required
def trigger_sync():
    threading.Thread(target=run_sync_job, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/api/import-only", methods=["POST"])
@login_required
def trigger_import_only():
    cfg = load_config()
    csv_path = OUTPUT_DIR / "letterboxd-latest.csv"
    if not csv_path.exists():
        return jsonify({"ok": False, "message": "No CSV found — run a sync first"}), 400
    if not cfg.get("lb_username") or not cfg.get("lb_password"):
        return jsonify({"ok": False, "message": "Letterboxd credentials not configured"}), 400
    def do_import():
        state = load_state()
        run_lb_import(cfg, csv_path, state)
    threading.Thread(target=do_import, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/api/test", methods=["POST"])
@login_required
def test_connection():
    cfg = load_config()
    try:
        r = requests.get(f"https://api.trakt.tv/users/{cfg['username']}/stats",
                         headers=make_headers(cfg), timeout=10)
        r.raise_for_status()
        watched = r.json().get("movies", {}).get("watched", 0)
        return jsonify({"ok": True, "watched": watched, "username": cfg["username"]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

@app.route("/api/scheduler", methods=["POST"])
@login_required
def toggle_scheduler():
    data = request.json or {}
    cfg  = load_config()
    if data.get("action") == "start":
        start_scheduler(cfg["sync_time"])
        return jsonify({"ok": True, "running": True})
    stop_scheduler()
    return jsonify({"ok": True, "running": False})

@app.route("/api/movies")
@login_required
def get_movies():
    movies = load_movies()
    q = request.args.get("q", "").lower()
    t = request.args.get("type", "all")
    page = int(request.args.get("page", 1))
    per_page = 50
    if q: movies = [m for m in movies if q in m["title"].lower()]
    if t != "all": movies = [m for m in movies if m.get("type") == t]
    total = len(movies)
    movies = movies[(page-1)*per_page : page*per_page]
    return jsonify({"movies": movies, "total": total, "page": page, "per_page": per_page})

@app.route("/api/history")
@login_required
def get_history():
    return jsonify(load_history())

@app.route("/api/watchlist")
@login_required
def get_watchlist():
    cfg = load_config()
    try:
        items = fetch_watchlist(cfg)
        return jsonify([{"title": i["movie"]["title"], "year": i["movie"].get("year",""),
                         "imdb": i["movie"]["ids"].get("imdb",""), "added": i.get("listed_at","")[:10]}
                        for i in items])
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/search")
@login_required
def search_movies():
    q = request.args.get("q", "")
    if not q: return jsonify([])
    try:
        r = requests.get(f"https://api.trakt.tv/search/movie?query={q}&limit=10",
                         headers=make_headers(load_config()), timeout=10)
        r.raise_for_status()
        return jsonify([{"title": i["movie"].get("title",""), "year": i["movie"].get("year",""),
                         "imdb": i["movie"].get("ids",{}).get("imdb",""), "score": i.get("score",0)}
                        for i in r.json()])
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/test-telegram", methods=["POST"])
@login_required
def test_telegram():
    cfg = load_config()
    try:
        send_telegram(cfg.get("telegram_token"), cfg.get("telegram_chat_id"),
            "✅ *Test Message*\nTrakt→Letterboxd notifications are working!")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

@app.route("/api/download/<filename>")
@login_required
def download_file(filename):
    path = OUTPUT_DIR / filename
    if not path.exists() or path.suffix != ".csv": return "Not found", 404
    return send_file(path, as_attachment=True, download_name=filename)

@app.route("/api/clear-logs", methods=["POST"])
@login_required
def clear_logs():
    log_buffer.clear()
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8888))
    add_log(f"🚀 trakt-to-letterboxd v{__version__} started on port {port}")
    if not is_setup_complete():
        add_log("⚙ First run — open browser to complete setup wizard", "warn")
    cfg = load_config()
    if cfg.get("run_on_start") and cfg["client_id"] and cfg["username"]:
        threading.Thread(target=run_sync_job, daemon=True).start()
    app.run(host="0.0.0.0", port=port, debug=False)
