"""
Scrapes the OSRS Wiki for monster attack styles and updates data.json.
Only updates attack style data — tips, descriptions, icons, and phase tags
are preserved from the existing file so manual edits are never overwritten.
"""

import json
import re
import time
import urllib.request
import urllib.parse
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent / "data.json"
API_URL = "https://oldschool.runescape.wiki/api.php"
HEADERS = {"User-Agent": "OSRSPrayGuide/1.0 (https://github.com/MannixaDev/OSRSPray)"}

STYLE_TO_TYPE = {
    "melee": "melee",
    "slash": "melee",
    "crush": "melee",
    "stab": "melee",
    "magic": "magic",
    "ranged": "ranged",
}

STYLE_TO_PRAYER = {
    "melee": "PROTECT_MELEE",
    "magic": "PROTECT_MAGIC",
    "ranged": "PROTECT_RANGED",
}

TYPE_TO_ICON = {
    "melee": "⚔️",
    "magic": "🔵",
    "ranged": "🏹",
}


def fetch_wikitext(page_name: str) -> str | None:
    params = urllib.parse.urlencode({
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "titles": page_name,
        "format": "json",
    })
    req = urllib.request.Request(f"{API_URL}?{params}", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        pages = data.get("query", {}).get("pages", {})
        page = next(iter(pages.values()))
        if "missing" in page:
            return None
        return page["revisions"][0]["slots"]["main"]["*"]
    except Exception as e:
        print(f"  ERROR fetching '{page_name}': {e}")
        return None


def parse_attack_styles(wikitext: str) -> list[str]:
    """Extract unique normalised attack styles from an infobox."""
    styles = []
    for match in re.finditer(r"\|\s*attack\s*style\d*\s*=\s*([^\n|]+)", wikitext, re.IGNORECASE):
        for raw in match.group(1).split(","):
            raw = raw.strip().lower()
            # skip typeless / none / empty
            if not raw or raw in ("typeless", "none", "n/a", "-"):
                continue
            mapped = STYLE_TO_TYPE.get(raw)
            if mapped and mapped not in styles:
                styles.append(mapped)
    return styles


def build_attacks_from_styles(styles: list[str], existing_attacks: list[dict]) -> list[dict]:
    """
    Merge wiki-derived styles with existing attack entries.
    - Attacks already in the file keep their name, detail, and phase.
    - New styles from the wiki get a generic entry added.
    - Styles no longer in the wiki are flagged but kept (manual review).
    """
    existing_by_type: dict[str, dict] = {}
    for atk in existing_attacks:
        t = atk.get("type")
        if t and t not in existing_by_type:
            existing_by_type[t] = atk

    result = []
    for style in styles:
        if style in existing_by_type:
            result.append(existing_by_type[style])
        else:
            result.append({
                "type": style,
                "icon": TYPE_TO_ICON.get(style, "❓"),
                "name": f"{style.capitalize()} Attack",
                "detail": "Added by wiki scraper — update detail manually",
                "prayer": STYLE_TO_PRAYER.get(style, "NONE"),
            })

    # Keep existing entries for styles NOT in wiki result (e.g. phase-specific)
    # so we don't silently drop them — mark them instead
    wiki_types = set(styles)
    for t, atk in existing_by_type.items():
        if t not in wiki_types and atk not in result:
            atk = dict(atk)
            atk["wiki_missing"] = True  # flag for manual review
            result.append(atk)

    return result


def main():
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)

    monsters = data["monsters"]
    changed = 0

    for monster in monsters:
        wiki_name = monster.get("wiki_name")
        if not wiki_name:
            continue

        print(f"Checking: {monster['name']} ({wiki_name})")
        wikitext = fetch_wikitext(wiki_name)
        if not wikitext:
            print(f"  Skipped — page not found")
            continue

        wiki_styles = parse_attack_styles(wikitext)
        if not wiki_styles:
            print(f"  No attack styles found in wikitext — skipping")
            continue

        existing_types = [a["type"] for a in monster.get("attacks", [])]
        if set(wiki_styles) == set(existing_types):
            print(f"  OK — no changes")
        else:
            print(f"  CHANGED: was {existing_types}, wiki says {wiki_styles}")
            monster["attacks"] = build_attacks_from_styles(wiki_styles, monster.get("attacks", []))
            changed += 1

        time.sleep(0.5)  # be polite to the wiki API

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nDone. {changed} monster(s) updated.")


if __name__ == "__main__":
    main()
