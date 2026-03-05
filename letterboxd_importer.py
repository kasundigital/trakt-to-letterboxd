import logging, time, re, json
from pathlib import Path

logger = logging.getLogger("lb-importer")

def import_to_letterboxd(csv_path: Path, username: str, password: str, log_fn=None) -> dict:
    def log(msg, level="info"):
        logger.info(msg)
        if log_fn: log_fn(msg, level)

    if not csv_path.exists():
        return {"ok": False, "imported": 0, "message": f"CSV not found: {csv_path}"}
    if not username or not password:
        return {"ok": False, "imported": 0, "message": "Letterboxd credentials not configured"}

    try:
        from curl_cffi import requests as cf_requests
        from curl_cffi import CurlMime
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        return {"ok": False, "imported": 0, "message": f"Missing dependency: {e}"}

    log("🌐 Logging in via curl_cffi (Cloudflare bypass)...")

    # Step 1: Login with curl_cffi
    session = cf_requests.Session(impersonate='chrome120')
    r = session.get('https://letterboxd.com/sign-in/')
    csrf_match = re.search(r'name="__csrf"\s+value="([^"]+)"', r.text)
    if not csrf_match:
        return {"ok": False, "imported": 0, "message": "Could not get CSRF token"}

    csrf = csrf_match.group(1)
    login_r = session.post('https://letterboxd.com/user/login.do',
        data={'__csrf': csrf, 'username': username, 'password': password},
        headers={'X-Requested-With': 'XMLHttpRequest', 'Referer': 'https://letterboxd.com/sign-in/'})

    login_data = json.loads(login_r.text)
    if login_data.get('result') != 'success':
        return {"ok": False, "imported": 0, "message": f"Login failed: {login_r.text[:200]}"}

    fresh_csrf = login_data.get('csrf', csrf)
    cookies = dict(session.cookies)
    log("  ✓ Logged in successfully", "success")

    # Step 2: Try Playwright with injected cookies
    log("  → Opening import page with browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        ctx = browser.new_context()
        ctx.add_cookies([
            {'name': k, 'value': v, 'domain': '.letterboxd.com', 'path': '/'}
            for k, v in cookies.items()
        ])
        page = ctx.new_page()

        try:
            page.goto('https://letterboxd.com/import/csv/', wait_until='networkidle', timeout=30000)
            time.sleep(3)

            inputs = page.eval_on_selector_all('input', 'els => els.map(e => e.name)')
            log(f"  → Inputs found: {inputs}")

            if 'file' not in inputs:
                log("  → Browser blocked by Cloudflare, using direct upload...", "warn")
                browser.close()
                return _direct_upload(csv_path, session, fresh_csrf, log)

            page.set_input_files('input[name="file"]', str(csv_path))
            log("  ✓ File selected", "success")
            time.sleep(2)
            page.click('input[value="Start Import"]')
            log("  → Import started...")
            time.sleep(8)
            page.screenshot(path=str(csv_path.parent / 'import_result.png'))
            text = page.inner_text('body')
            match = re.search(r'(\d+)\s+film', text, re.IGNORECASE)
            count = int(match.group(1)) if match else 0
            try:
                page.click('input[value="Import"], button:has-text("Confirm")', timeout=3000)
                time.sleep(5)
                text = page.inner_text('body')
                match = re.search(r'(\d+)\s+film', text, re.IGNORECASE)
                count = int(match.group(1)) if match else count
            except: pass
            log(f"  ✓ Import complete — {count} films", "success")
            browser.close()
            return {"ok": True, "imported": count, "message": f"Imported {count} films"}

        except Exception as e:
            log(f"  ✗ Browser import failed: {e}", "error")
            try:
                page.screenshot(path=str(csv_path.parent / 'debug_screenshot.png'))
                log("  Debug screenshot saved", "warn")
            except: pass
            browser.close()
            log("  → Trying direct upload fallback...", "warn")
            return _direct_upload(csv_path, session, fresh_csrf, log)


def _direct_upload(csv_path, session, csrf, log):
    try:
        from curl_cffi import CurlMime
        r2 = session.get('https://letterboxd.com/import/csv/')
        import_csrf = re.search(r'id="imdb-form".*?name="__csrf"\s+value="([^"]+)"', r2.text, re.DOTALL)
        if import_csrf:
            csrf = import_csrf.group(1)
        with open(csv_path, 'rb') as f:
            csv_data = f.read()
        mp = CurlMime()
        mp.addpart(name='__csrf', data=csrf.encode())
        mp.addpart(name='file', data=csv_data, filename=csv_path.name, content_type='text/csv')
        upload = session.post('https://letterboxd.com/import/csv/',
            multipart=mp, headers={'Referer': 'https://letterboxd.com/import/csv/'})
        text = upload.text
        match = re.search(r'(\d+)\s+film', text, re.IGNORECASE)
        count = int(match.group(1)) if match else 0
        if upload.status_code == 200:
            log(f"  ✓ Direct upload complete — {count} films processed", "success")
            return {"ok": True, "imported": count, "message": f"Direct upload: {count} films"}
        else:
            return {"ok": False, "imported": 0, "message": "Upload did not process correctly"}
    except Exception as e:
        log(f"  ✗ Direct upload failed: {e}", "error")
        return {"ok": False, "imported": 0, "message": str(e)}
