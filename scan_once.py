import contextlib, io, json, random, time
from pathlib import Path
from playwright.sync_api import sync_playwright
import vinted_bot as b
import vinted_server as server

def explain(page, cat, brand, n=5):
    c = b.CATEGORIES[cat]
    page.goto(f"{b.BASE_URL}/catalog?search_text={b.quote_plus(brand)}&order=newest_first&price_to={c['max']}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector('a[href*="/items/"]', timeout=15000)
    except Exception:
        print("DEBUG", brand, "keine Artikel gefunden")
        return
    for link in page.query_selector_all('a[href*="/items/"]')[:n]:
        attr = link.get_attribute("title") or ""
        card = link.evaluate_handle("""el => el.closest('[data-testid^="product-item"]') || el""").as_element()
        text = attr + " " + (card.inner_text() if card else "")
        cond = b.parse_condition(b.field(text, "Zustand") or b.field(text, "Condition") or text)
        print("DEBUG", cat, brand, repr(attr[:170]), "| Marke:", b.field(text, "Marke") or b.field(text, "Brand"), "| Groesse:", b.field(text, "Größe") or b.field(text, "Size"), "| Zustand:", cond, "| Preis:", b.parse_price(attr) or b.parse_price(text))

DATA = Path("data")
DATA.mkdir(exist_ok=True)
HITS = DATA / "hits.json"
server.HITS_FILE = HITS
t0 = int(time.time())
first = not b.SEEN_FILE.exists()
raw = {} if first else json.loads(b.SEEN_FILE.read_text())
if isinstance(raw, list):
    raw = {"clothing": raw}
seen_by = {cat: set(raw.get(cat, [])) for cat in b.CATEGORIES}
quiet = {cat: first or cat not in raw for cat in b.CATEGORIES}
old_ids = sum(len(v) for v in seen_by.values())
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
                    b.scan_brand(page, cat, brand, seen_by[cat], not quiet[cat])
                except Exception as e:
                    print(f"No items for {brand} (error: {e})")
                time.sleep(random.uniform(2, 4))
    explain(page, "clothing", "Prada")
    explain(page, "accessories", "Gucci")
    browser.close()
blocked = buf.getvalue().count("No items for")
hits = json.loads(HITS.read_text()) if HITS.exists() else []
cut = time.time() - 3 * 86400
HITS.write_text(json.dumps([h for h in hits if h["ts"] > cut]))
(DATA / "status.json").write_text(json.dumps({"last_run": int(time.time()), "blocked": blocked, "total": total}))
b.SEEN_FILE.write_text(json.dumps({c: sorted(v)[-20000:] for c, v in seen_by.items()}))
new_ids = sum(len(v) for v in seen_by.values()) - old_ids
new_hits = sum(1 for h in hits if h["ts"] >= t0)
print(f"scanned {total}, blocked {blocked}, new ids {new_ids}, new hits {new_hits}, in list {len(hits)}")
