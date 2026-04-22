
import asyncio
import json
import os
import requests
from bs4 import BeautifulSoup
from telegram import Bot

# ── Konfiguration ──────────────────────────────────────────
BOT_TOKEN  = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))
BASE_URL       = "https://www.waffenboerse.ch"
URL            = "https://www.waffenboerse.ch/de/occasionen/gebrauchtwaffen/faustfeuerwaffen/"
SEEN_FILE      = "seen_products.json"
POLL_INTERVAL = 60  # Sekunden
FIRST_RUN_POST = 10  # Beim ersten Start: diese Anzahl posten
# ───────────────────────────────────────────────────────────

def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def is_first_run() -> bool:
    return not os.path.exists(SEEN_FILE)

def fetch_products() -> list:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = {
        "field-sort": "CI6",
        "originalUrl": "https://www.waffenboerse.ch/de/occasionen/gebrauchtwaffen/faustfeuerwaffen/",
    }
    response = requests.post(URL, headers=headers, data=payload, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    products = []
    for item in soup.select("article.article-list-item"):
        title_tag = item.select_one(".article-list-item-title a")
        if not title_tag:
            continue
        title = title_tag.text.strip()
        link  = BASE_URL + title_tag["href"]

        price_tag    = item.select_one(".article-list-item-price .price")
        currency_tag = item.select_one(".article-list-item-price .price-currency")
        price = f"{currency_tag.text.strip()} {price_tag.text.strip()}" if price_tag and currency_tag else "Preis auf Anfrage"

        img_tag = item.select_one(".article-list-item-image img")
        image   = BASE_URL + img_tag["src"] if img_tag else None

        products.append({
            "id":    link,
            "title": title,
            "price": price,
            "image": image,
            "link":  link,
        })

    return products


async def post_product(bot: Bot, product: dict):
    caption = (
        f"🆕 *{product['title']}*\n"
        f"💰 {product['price']}\n"
        f"🔗 [Zum Inserat]({product['link']})"
    )

    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

    try:
        if product["image"]:
            img_response = requests.get(product["image"], headers=headers, timeout=10)
            img_response.raise_for_status()

            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=img_response.content,  # Bild als Bytes senden
                caption=caption,
                parse_mode="Markdown"
            )
        else:
            raise Exception("Kein Bild")
    except Exception:
        # Fallback: nur Text senden
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=caption,
            parse_mode="Markdown"
        )


async def poll():
    bot  = Bot(token=BOT_TOKEN)
    seen = load_seen()
    first_run = is_first_run()
    print("✅ Bot gestartet — polling läuft...")

    while True:
        try:
            products = fetch_products()

            if first_run:
                # Ersten 10 posten, Rest nur als gesehen markieren
                to_post  = [p for p in products if p["id"] not in seen][:FIRST_RUN_POST]
                to_skip  = [p for p in products if p["id"] not in seen][FIRST_RUN_POST:]

                print(f"🚀 Erster Start: {len(to_post)} Produkte werden gepostet.")
                for product in to_post:
                    await post_product(bot, product)
                    seen.add(product["id"])
                    await asyncio.sleep(1)  # kurze Pause zwischen Posts

                for product in to_skip:
                    seen.add(product["id"])

                save_seen(seen)
                first_run = False

            else:
                new_products = [p for p in products if p["id"] not in seen]
                if new_products:
                    print(f"🆕 {len(new_products)} neue Produkte gefunden!")
                    for product in new_products:
                        await post_product(bot, product)
                        seen.add(product["id"])
                        await asyncio.sleep(1)
                    save_seen(seen)
                else:
                    print("Keine neuen Produkte.")

        except Exception as e:
            print(f"❌ Fehler: {e}")

        await asyncio.sleep(POLL_INTERVAL)

asyncio.run(poll())