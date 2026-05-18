# 🃏 Lorcana Missing Cards Sync

A Python script that reads your Lorcana collection tracker in Notion and generates a neatly formatted **"Missing Cards"** page with card names, rarities, prices, and Cardmarket links — all in one command.

---

## What it does

1. Reads your Lorcana sets table from Notion
2. For each set, looks at three columns: **Missing**, **Missing epics**, and **Wants**
3. Looks up each card number via the [Lorcast API](https://lorcast.com/docs/api) to get the full name, rarity, USD price (normal + foil), and a Cardmarket link
4. Creates a new Notion page called **"Missing Cards — \<date\>"** with everything organized by set, with separate sections for regular missing cards, epics, and wants
5. Each card entry includes a small card image inline

---

## Example output in Notion

```
Missing Cards — 18 May 2026
Total missing cards: 42

## Set 9 — Fabled

✨ Epics
• #206  Elsa — Spirit of Winter  (Enchanted)  Normal: $24.99  Foil: $89.99  🔗 Cardmarket
  [card image]

🛒 Wants
• #48  Simba — Returned King  (Legendary)  Normal: $12.50  Foil: N/A  🔗 Cardmarket
  [card image]
```

---

## Setup

### 1. Install dependencies

```bash
uv add requests "notion-client==2.2.1" python-dotenv
```

### 2. Create a Notion integration

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click **+ New integration**
3. Give it a name (e.g. "Lorcana Sync"), select your workspace, click Submit
4. Copy the **Internal Integration Token** (starts with `secret_...`)

### 3. Connect the integration to your Notion pages

You need to do this for **both** your main Lorcana page and your sets database:

1. Open each page/database in Notion
2. Click `...` in the top right → **Connect to** → select your integration

⚠️ If you skip this step the script will get a 404 error.

### 4. Get your Notion IDs

For both your **sets database** and your **main Lorcana page**, open them in Notion and copy the ID from the URL:

```
https://www.notion.so/2aef9fc4bed3806aad52cd2212c4df1f?v=...
                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                       this is your ID
```

### 5. Create a `.env` file

Create a file called `.env` in the same folder as the script:

```
NOTION_TOKEN=secret_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
DATABASE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LORCANA_PAGE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 6. Add `.env` to `.gitignore`

```
.env
```

---

## Notion table structure

The script expects your Lorcana sets table to have these columns:

| Column | Type | Description |
|---|---|---|
| **Name** | Title | The set name (e.g. "The First Chapter") |
| **Set number** | Number | Used to sort sets in the correct order |
| **Missing** | Text | Card numbers you're missing (e.g. `22, 48, 50`) |
| **Missing epics** | Text | Epic card numbers you're missing |
| **Wants** | Text | Card numbers you want but don't need |

Card numbers can be comma-separated (`1, 5, 23`) or ranges (`1-3, 7`).

---

## Running the script

```bash
python main.py
```

---

## Data sources

- **Card data & prices** — [Lorcast API](https://lorcast.com/docs/api) (free, no account needed). Prices are in USD from TCGPlayer, updated daily.
- **Cardmarket links** — generated from the `cardmarket_id` field in the Lorcast API. Cardmarket is the main European marketplace for Lorcana cards.
- **Notion API** — via the official [notion-client](https://pypi.org/project/notion-client/) Python SDK.

---

## Notes

- Prices are in **USD** (from TCGPlayer). There is no EUR price source available via free API — use the Cardmarket links for European pricing.
- The Lorcast API updates prices once per day, so running the script multiple times in a day won't yield fresher prices.
- The generated Notion page is created fresh each run — old pages are not deleted automatically.