import contextlib, io, json, random, time
from pathlib import Path
from playwright.sync_api import sync_playwright
import vinted_bot as b
import vinted_server as server

DATA = Path("data")
DATA.mkdir(exist_ok=True)
HITS = DATA / "hits.json"
server.HITS_FILE = HITS
first = not b.SEEN_FILE.exists()
seen = set() if first else set(json.loads(b.SEEN_FILE.read_text()))
buf, total = io.StringIO(), 0
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
    ctx = browser.new_context(locale="de-DE")
    page = ctx.new_page()
    page.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image", "media", "font") else r.continue_())
    with contextlib.redirect_stdout(buf):
        for cat, cfg in b.CATEGORIES.items():
            for brand in cfg["brands"]:
                total += 1
                try:
                    b.scan_brand(page, cat, brand, seen, not first)
                except Exception as e:
                    print(f"No items for {brand} (error: {e})")
                time.sleep(random.uniform(2, 4))
    browser.close()
blocked = buf.getvalue().count("No items for")
hits = json.loads(HITS.read_text()) if HITS.exists() else []
cut = time.time() - 3 * 86400
HITS.write_text(json.dumps([h for h in hits if h["ts"] > cut]))
(DATA / "status.json").write_text(json.dumps({"last_run": int(time.time()), "blocked": blocked, "total": total}))
b.SEEN_FILE.write_text(json.dumps(sorted(seen)[-20000:]))
print(f"scanned {total}, blocked {blocked}, hits {len(hits)}")
