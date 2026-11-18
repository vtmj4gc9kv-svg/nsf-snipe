"""
NSF Snipebot - Vinted watcher (Playwright) with phone web app.

Setup:   pip install playwright requests && playwright install chromium
Login:   python vinted_bot.py --login      (once, manually; session is stored locally)
Run:     python vinted_bot.py              (then open the printed link on your phone)

Optional Telegram alerts for MYTHIC/RARE: set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID.
"""
import argparse, json, os, random, re, time
from pathlib import Path
from urllib.parse import quote_plus

import vinted_server as server
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE_URL = "https://www.vinted.de"
PROFILE_DIR = Path("vinted_profile")
SEEN_FILE = Path("seen_items.json")
CHECK_INTERVAL = (30, 60)   # pause between full rounds (seconds)
HEADLESS = True

# brand -> aliases matched against the item's brand field (word boundaries)
BRANDS = {
    "Moncler": ["moncler"], "Prada": ["prada"], "Stone Island": ["stone island"],
    "C.P. Company": ["c.p. company", "cp company", "c.p.company", "c.p."],
    "Luna Rossa": ["luna rossa"], "Dolce & Gabbana": ["dolce", "d&g"],
    "Gucci": ["gucci"], "Tom Ford": ["tom ford"], "Thom Browne": ["thom browne"],
    "Philipp Plein": ["philipp plein", "plein"], "Blauer": ["blauer"],
    "Loro Piana": ["loro piana"], "MCM": ["mcm"], "Coach": ["coach"],
    "Parajumpers": ["parajumpers"], "Fendi": ["fendi"],
    "Wellensteyn": ["wellensteyn"], "Armani": ["armani"], "Burberry": ["burberry"],
}
_BASE = [b for b in BRANDS if b != "Burberry"]

CATEGORIES = {
    "clothing": {
        "brands": _BASE,
        "keywords": ["pullover", "pulli", "sweater", "strick", "sweatshirt", "jacke", "jacket",
                     "weste", "vest", "gilet", "hoodie", "kapuzenjacke", "zip", "longsleeve",
                     "long sleeve", "langarm"],
        "sizes": {"XXS", "XS", "S", "M", "L", "XL"},
        "mythic": 25, "rare": 50, "max": 100,
    },
    "accessories": {
        "brands": _BASE + ["Burberry"],
        "keywords": ["tasche", "handtasche", "bag", "clutch", "pouch", "etui", "portemonnaie",
                     "geldbörse", "geldbeutel", "wallet", "kartenhalter", "cardholder",
                     "card holder", "gürtel", "belt", "schal", "scarf", "tuch"],
        "sizes": None,  # accessories: no size filter
        "mythic": 15, "rare": 35, "max": 100,
    },
}
ACCESSORY_WORDS = CATEGORIES["accessories"]["keywords"]
TOP_CONDITIONS = {"nwt", "nwot", "very_good"}


def parse_condition(text: str):
    t = text.lower()
    if "neu mit etikett" in t or "new with tags" in t: return "nwt"
    if "neu ohne etikett" in t or "new without tags" in t: return "nwot"
    if "sehr gut" in t or "very good" in t: return "very_good"
    if "zufriedenstellend" in t or "satisfactory" in t: return "satisfactory"
    if re.search(r"\b(gut|good)\b", t): return "good"
    return None


def parse_price(text: str):
    m = re.search(r"(\d+(?:[.,]\d{1,2})?)\s*€", text)
    return float(m.group(1).replace(",", ".")) if m else None


def field(text: str, name: str):
    m = re.search(rf"{name}:\s*([^,]+)", text)
    return m.group(1).strip() if m else ""


def classify(cat: str, price: float, cond: str):
    c = CATEGORIES[cat]
    if cond in TOP_CONDITIONS:
        if price <= c["mythic"]: return "mythic"
        if price <= c["rare"]: return "rare"
    if cond and price <= c["max"]: return "normal"
    return None


def notify(hit: dict) -> None:
    msg = f"[{hit['rarity'].upper()}] {hit['brand']} - {hit['title']} | {hit['price']:.2f} EUR\n{hit['url']}"
    print("\a" + msg)
    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if token and chat:
        try:
            import requests
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id": chat, "text": msg}, timeout=10)
        except Exception as e:
            print(f"Telegram error: {e}")


def scan_brand(page, cat, brand, seen, notify_ok):
    c = CATEGORIES[cat]
    page.goto(f"{BASE_URL}/catalog?search_text={quote_plus(brand)}&order=newest_first&price_to={c['max']}",
              wait_until="domcontentloaded")
    try:
        page.click("#onetrust-accept-btn-handler", timeout=1500)
    except PWTimeout:
        pass
    try:
        page.wait_for_selector('a[href*="/items/"]', timeout=15000)
    except PWTimeout:
        print(f"No items for {brand} (captcha or layout change?)")
        return
    aliases = BRANDS[brand]
    for link in page.query_selector_all('a[href*="/items/"]'):
        href = link.get_attribute("href") or ""
        m = re.search(r"/items/(\d+)", href)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        attr = link.get_attribute("title") or ""
        card = link.evaluate_handle("el => el.closest('[data-testid^=\"product-item\"]') || el").as_element()
        text = attr + " " + (card.inner_text() if card else "")
        title = attr.split(", Marke:")[0].split(", Brand:")[0].strip() or text.strip().split("\n")[0]
        item_brand = field(text, "Marke") or field(text, "Brand") or title
        if not any(re.search(rf"(?<!\w){re.escape(a)}(?!\w)", item_brand.lower()) for a in aliases):
            continue
        tl = title.lower()
        if not any(k in tl for k in c["keywords"]):
            continue
        if cat == "clothing" and any(k in tl for k in ACCESSORY_WORDS):
            continue
        if c["sizes"]:
            sm = re.search(r"\b(XXS|XS|S|M|L|XL)\b", (field(text, "Größe") or field(text, "Size")).upper())
            if not sm or sm.group(1) not in c["sizes"]:
                continue
            size = sm.group(1)
        else:
            size = field(text, "Größe") or field(text, "Size")
        cond = parse_condition(field(text, "Zustand") or field(text, "Condition") or text)
        price = parse_price(attr) or parse_price(text)
        if price is None:
            continue
        rarity = classify(cat, price, cond)
        if not rarity:
            continue
        hit = {"category": cat, "rarity": rarity, "brand": brand, "title": title[:100],
               "size": size, "condition": cond, "price": price,
               "url": href if href.startswith("http") else BASE_URL + href}
        server.add_hit(hit)
        if notify_ok and rarity in ("mythic", "rare"):
            notify(hit)


def run_login():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=False)
        ctx.new_page().goto(BASE_URL)
        input("Log in to Vinted in the browser, then press Enter here... ")
        ctx.close()
    print("Session saved.")


def run_bot():
    seen = set(json.loads(SEEN_FILE.read_text())) if SEEN_FILE.exists() else set()
    scanned = set()  # categories already scanned once this session (no alerts on the first pass)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=HEADLESS)
        page = ctx.new_page()
        server.start()
        try:
            while True:
                cat = server.state["category"]
                if not cat:
                    server.state["scanning"] = None
                    time.sleep(1)
                    continue
                for brand in CATEGORIES[cat]["brands"]:
                    if server.state["category"] != cat:
                        break
                    server.state["scanning"] = brand
                    try:
                        scan_brand(page, cat, brand, seen, cat in scanned)
                    except Exception as e:
                        print(f"Error ({brand}): {e}")
                    time.sleep(random.uniform(3, 6))
                else:
                    scanned.add(cat)
                server.state["last_check"] = int(time.time())
                SEEN_FILE.write_text(json.dumps(sorted(seen)))
                for _ in range(random.randint(*CHECK_INTERVAL)):  # wait, but react to category change
                    if server.state["category"] != cat:
                        break
                    time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            SEEN_FILE.write_text(json.dumps(sorted(seen)))
            ctx.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    run_login() if ap.parse_args().login else run_bot()
