"""
sync_lorcana.py

Reads your Lorcana Notion table, looks up missing cards by name and rarity
using the Lorcast API, creates a new "Missing Cards - <date>" page in Notion,
and adds a link to it on your main Lorcana page.

SETUP (one time):
  1. Install dependencies:       pip install requests notion-client
  2. Fill in the three variables below: NOTION_TOKEN, DATABASE_ID, LORCANA_PAGE_ID
  3. Run:                         python sync_lorcana.py

HOW TO GET YOUR NOTION TOKEN & IDs — see bottom of this file.
"""

import time
import re
from dotenv import load_dotenv
import os
from datetime import date
from notion_client import Client
import requests

# ─── CONFIGURE THESE THREE VALUES ────────────────────────────────────────────

load_dotenv()

NOTION_TOKEN    = os.getenv("NOTION_TOKEN")
DATABASE_ID     = os.getenv("DATABASE_ID")
LORCANA_PAGE_ID = os.getenv("LORCANA_PAGE_ID")

# ─────────────────────────────────────────────────────────────────────────────

LORCAST_API      = "https://api.lorcast.com/v0"
CARDMARKET_BASE  = "https://www.cardmarket.com/en/Lorcana/Products/Singles"

notion = Client(auth=NOTION_TOKEN)


# ── Notion helpers ────────────────────────────────────────────────────────────

def get_set_rows():
    """Fetch all rows from the Lorcana database, sorted by set number column."""
    rows = []
    cursor = None
    while True:
        kwargs = {
            "database_id": DATABASE_ID,
            "page_size": 100,
            "sorts": [{"property": "Set number", "direction": "ascending"}]
        }
        if cursor:
            kwargs["start_cursor"] = cursor
        response = notion.databases.query(**kwargs)
        rows.extend(response["results"])
        if not response.get("has_more"):
            break
        cursor = response["next_cursor"]
    return rows


def get_row_name(row):
    """Extract the title/name from a Notion row."""
    for prop in row["properties"].values():
        if prop["type"] == "title":
            parts = prop["title"]
            if parts:
                return "".join(p.get("plain_text", "") for p in parts)
    return f"Row {row['id'][:8]}"


def get_prop_text(row, prop_name):
    """Extract plain text from a rich_text or title property by name."""
    prop = row["properties"].get(prop_name)
    if not prop:
        return ""
    ptype = prop["type"]
    if ptype == "rich_text":
        return "".join(p.get("plain_text", "") for p in prop["rich_text"])
    elif ptype == "title":
        return "".join(p.get("plain_text", "") for p in prop["title"])
    return ""


# ── Lorcast helpers ───────────────────────────────────────────────────────────

def parse_missing_numbers(text):
    """Parse '1, 5, 23' or '1-3, 7' into a sorted list of ints."""
    if not text or not text.strip():
        return []
    numbers = []
    for part in re.split(r"[,;\s]+", text.strip()):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                numbers.extend(range(int(start.strip()), int(end.strip()) + 1))
            except ValueError:
                pass
        else:
            try:
                numbers.append(int(part))
            except ValueError:
                pass
    return sorted(set(numbers))


def fetch_set_cards(set_number):
    """Fetch all cards for a set from Lorcast, keyed by collector_number (int)."""
    url = f"{LORCAST_API}/sets/{set_number}/cards"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        card_list = data if isinstance(data, list) else data.get("results", [])
        cards = {}
        for card in card_list:
            num = card.get("collector_number")
            if num is not None:
                try:
                    cards[int(num)] = card
                except (ValueError, TypeError):
                    pass
        return cards
    except requests.RequestException as e:
        print(f"  ⚠  Could not fetch set {set_number}: {e}")
        return {}


def build_card_entry(num, card):
    if not card:
        return {"number": num, "name": "Card not found", "rarity": "?", "usd": None, "usd_foil": None, "cardmarket_id": None, "image_url": None}

    full_name = card.get("name", "Unknown")
    version = card.get("version")
    if version:
        full_name = f"{full_name} — {version}"

    prices = card.get("prices", {})
    image_url = card.get("image_uris", {}).get("digital", {}).get("normal")

    return {
        "number": num,
        "name": full_name,
        "rarity": card.get("rarity", "Unknown"),
        "usd": prices.get("usd"),
        "usd_foil": prices.get("usd_foil"),
        "cardmarket_id": card.get("cardmarket_id"),
        "image_url": image_url,
    }

# ── Core logic ────────────────────────────────────────────────────────────────

def build_missing_cards_content(rows):
    results = []
    for set_number, row in enumerate(rows, start=1):
        set_name = get_row_name(row)
        missing_numbers = parse_missing_numbers(get_prop_text(row, "Missing"))
        epic_numbers = parse_missing_numbers(get_prop_text(row, "Missing epics"))
        wants_numbers = parse_missing_numbers(get_prop_text(row, "Wants"))

        if not missing_numbers and not epic_numbers and not wants_numbers:
            print(f"  Set {set_number} ({set_name}): nothing missing, skipping.")
            results.append((set_name, set_number, [], [], []))
            continue

        print(f"  Set {set_number} ({set_name}): fetching card data...")
        set_cards = fetch_set_cards(set_number)
        time.sleep(0.1)

        missing_cards = [build_card_entry(n, set_cards.get(n)) for n in missing_numbers]
        epic_cards    = [build_card_entry(n, set_cards.get(n)) for n in epic_numbers]
        wants_cards   = [build_card_entry(n, set_cards.get(n)) for n in wants_numbers]

        print(f"    {len(missing_cards)} missing, {len(epic_cards)} epics, {len(wants_cards)} wants.")
        results.append((set_name, set_number, missing_cards, epic_cards, wants_cards))

    return results  # ← outside the loop


# ── Notion page builder ───────────────────────────────────────────────────────

def format_card_line(card):
    """Format a single card as a display string."""
    usd      = f"${card['usd']}"      if card.get("usd")      else "N/A"
    usd_foil = f"${card['usd_foil']}" if card.get("usd_foil") else "N/A"
    return f"#{card['number']}  {card['name']}  ({card['rarity']})  Normal: {usd}  Foil: {usd_foil}"


def card_blocks(cards):
    blocks = []
    for card in cards:
        line = format_card_line(card)
        rich_text = [{"type": "text", "text": {"content": line}}]

        if card.get("cardmarket_id"):
            cm_url = f"{CARDMARKET_BASE}/{card['cardmarket_id']}"
            rich_text.append({
                "type": "text",
                "text": {"content": "  🔗 Cardmarket", "link": {"url": cm_url}},
            })

        blocks.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": rich_text}
        })

        if card.get("image_url"):
            blocks.append({
                "object": "block",
                "type": "image",
                "image": {
                    "type": "external",
                    "external": {"url": card["image_url"]}
                }
            })

    return blocks

def create_missing_cards_page(results):
    today_str = date.today().strftime("%d %B %Y")
    page_title = f"Missing Cards — {today_str}"
    total_missing = sum(len(c) + len(e) + len(w) for _, _, c, e, w in results)
    # Build all blocks
    all_blocks = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {"type": "text", "text": {"content": f"Total missing cards: {total_missing}"}}
                ]
            }
        }
    ]

    for set_name, set_number, missing_cards, epic_cards, wants_cards in results:
        if not missing_cards and not epic_cards and not wants_cards:
            continue

        all_blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {"type": "text", "text": {"content": f"Set {set_number} — {set_name}"}}
                ]
            }
        })

        if missing_cards:
            all_blocks.extend(card_blocks(missing_cards))

        if epic_cards:
            all_blocks.append({"object": "block", "type": "divider", "divider": {}})
            all_blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": "✨ Epics"}}]
                }
            })
            all_blocks.extend(card_blocks(epic_cards))
        
        if wants_cards:
            all_blocks.append({"object": "block", "type": "divider", "divider": {}})
            all_blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": "🛒 Wants"}}]
                }
            })
            all_blocks.extend(card_blocks(wants_cards))

    # Create page with first 100 blocks
    new_page = notion.pages.create(
        parent={"type": "page_id", "page_id": LORCANA_PAGE_ID},
        properties={
            "title": {
                "title": [{"type": "text", "text": {"content": page_title}}]
            }
        },
        children=all_blocks[:100]
    )

    # Append remaining blocks in chunks of 100
    page_id = new_page["id"]
    for i in range(100, len(all_blocks), 100):
        notion.blocks.children.append(
            block_id=page_id,
            children=all_blocks[i:i + 100]
        )

    return page_id, page_title


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("🃏 Lorcana Missing Cards Sync")
    print("─" * 40)

    print("📖 Fetching your Lorcana table from Notion...")
    rows = get_set_rows()
    print(f"   Found {len(rows)} set(s).\n")

    print("🔍 Looking up missing cards via Lorcast...")
    results = build_missing_cards_content(rows)

    total = sum(len(c) + len(e) + len(w) for _, _, c, e, w in results)
    if total == 0:
        print("\n✅ No missing cards found!")
        return

    print(f"\n📝 Creating 'Missing Cards' page in Notion ({total} cards total)...")
    new_page_id, page_title = create_missing_cards_page(results)
    print(f"   Created: {page_title}")

    print("\n✅ Done! Open your Lorcana page in Notion to see the new page.")


if __name__ == "__main__":
    main()


# ═══════════════════════════════════════════════════════════════════════════════
# HOW TO SET UP (read this once)
# ═══════════════════════════════════════════════════════════════════════════════
#
# STEP 1 — Install dependencies
#   uv add requests "notion-client==2.2.1"
#
# STEP 2 — Create a Notion integration & get your token
#   1. Go to https://www.notion.so/my-integrations
#   2. Click "+ New integration"
#   3. Give it a name (e.g. "Lorcana Sync"), select your workspace, click Submit
#   4. Copy the "Internal Integration Token" (starts with "secret_...")
#   5. Paste it as the value of NOTION_TOKEN at the top of this file
#
# STEP 3 — Connect the integration to your Lorcana page
#   1. Open your main Lorcana page in Notion
#   2. Click the "..." menu (top right) → "Connect to" → select your integration
#   ⚠  You MUST do this or the script cannot access your data!
#
# STEP 4 — Get your DATABASE_ID (your sets table)
#   1. Open your Lorcana sets table as a full page in Notion
#   2. Look at the URL: https://www.notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...
#   3. The 32-character string before the "?" is your DATABASE_ID
#   4. Paste it above (with or without hyphens, both work)
#
# STEP 5 — Get your LORCANA_PAGE_ID (the parent page)
#   1. Open your main Lorcana page in Notion
#   2. Same as above — copy the 32-character ID from the URL
#   3. Paste it as LORCANA_PAGE_ID above
#
# STEP 6 — Run!
#   python sync_lorcana.py
#
# ═══════════════════════════════════════════════════════════════════════════════