#!/usr/bin/env python3
"""Fetch Yale dining menus from the Nutrislice API and write site/data/menus.json.

Standard library only. Runs in GitHub Actions on a schedule; see
docs/designs/yale-menus-side-by-side.md for the design.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

COLLEGES = [
    ("hopper-college", "Grace Hopper"),
    ("silliman-college", "Silliman"),
    ("branford-college", "Branford"),
]
MEALS = ["breakfast", "lunch", "dinner"]
ALL_DAY = ["salad-bar", "daily-offerings"]
MENUS = MEALS + ALL_DAY

IS_TAGS = ["Vegan", "Vegetarian", "Gluten Friendly", "9 In Mind"]
CONTAINS_TAGS = [
    "Gluten", "Milk", "Wheat", "Soy", "Sesame", "Eggs", "Coconut", "Pork",
    "Alcohol", "Fish", "Shellfish", "Peanuts", "Tree Nuts",
]
KNOWN_TAGS = set(IS_TAGS + CONTAINS_TAGS)

SCHEMA_VERSION = 1
TZ = ZoneInfo("America/New_York")
API = ("https://yalehospitality.api.nutrislice.com/menu/api/weeks/school/"
       "{slug}/menu-type/{menu}/{d.year}/{d.month:02d}/{d.day:02d}/")
PREVIOUS_URL = os.environ.get(
    "MENUS_PREVIOUS_URL",
    "https://daniel-lu32.github.io/yale-menus/data/menus.json")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "site", "data", "menus.json")

TIMEOUT_S = 15
ATTEMPTS = 3
BACKOFF_S = [2, 4]


def http_get_json(url):
    """GET a URL and parse JSON, retrying with backoff. Raises on final failure."""
    last_error = None
    for attempt in range(ATTEMPTS):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "yale-menus"})
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return json.load(resp)
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            last_error = e
            if attempt < ATTEMPTS - 1:
                time.sleep(BACKOFF_S[attempt])
    raise last_error


def parse_week(payload):
    """Turn one Nutrislice week payload into {date: entry} with ok/empty status."""
    days = {}
    for day in payload.get("days", []):
        sections = []
        for row in day.get("menu_items", []):
            food = row.get("food")
            if row.get("is_section_title"):
                sections.append({"section": (row.get("text") or "").strip(), "items": []})
            elif food and food.get("name"):
                if not sections:
                    sections.append({"section": "", "items": []})
                tags = [i["name"] for i in (food.get("icons") or {}).get("food_icons", [])
                        if i.get("name")]
                sections[-1]["items"].append({"name": food["name"].strip(), "tags": tags})
        sections = [s for s in sections if s["items"]]
        days[day["date"]] = {"status": "ok" if sections else "empty", "sections": sections}
    return days


def week_starts(today):
    """Dates to request: one in this Sunday-to-Saturday week, one in next week."""
    return [today, today + timedelta(days=7)]


def week_dates(d):
    """ISO dates of the Sunday-to-Saturday week containing d (the API's week)."""
    sunday = d - timedelta(days=(d.weekday() + 1) % 7)
    return [(sunday + timedelta(days=i)).isoformat() for i in range(7)]


def load_previous(fetch_json):
    """Return the deployed menus.json if it is usable, else None."""
    try:
        prev = fetch_json(PREVIOUS_URL)
    except Exception:
        return None
    if (isinstance(prev, dict) and prev.get("schema_version") == SCHEMA_VERSION
            and isinstance(prev.get("days"), dict) and prev.get("generated_at")):
        return prev
    return None


def build(fetch_json, now, previous):
    """Fetch every college and menu and assemble the output document.

    Returns (data, warnings). data is None when nothing could be fetched and
    there is no previous file to fall back on.
    """
    today = now.date()
    days = {}
    warnings = []
    attempts = 0
    failures = []

    for slug, _ in COLLEGES:
        for menu in MENUS:
            for start in week_starts(today):
                attempts += 1
                try:
                    week = parse_week(fetch_json(API.format(slug=slug, menu=menu, d=start)))
                except Exception as e:
                    failures.append((slug, menu, start))
                    warnings.append(f"fetch failed: {slug} {menu} week of {start}: {e}")
                    week = {d: {"status": "error", "sections": []} for d in week_dates(start)}
                for d, entry in week.items():
                    days.setdefault(d, {}).setdefault(menu, {})[slug] = entry

    if len(failures) == attempts:
        if previous is None:
            return None, warnings + ["every fetch failed and there is no previous menus.json"]
        return previous, warnings + ["every fetch failed; redeploying the previous menus.json unchanged"]

    if previous is not None:
        for d, menus in days.items():
            for menu, by_slug in menus.items():
                for slug, entry in by_slug.items():
                    if entry["status"] != "error":
                        continue
                    old = previous["days"].get(d, {}).get(menu, {}).get(slug)
                    if old and old.get("status") == "ok":
                        carried = dict(old)
                        carried["stale_from"] = old.get("stale_from") or previous["generated_at"]
                        by_slug[slug] = carried

    unknown = sorted({tag for menus in days.values() for by_slug in menus.values()
                      for entry in by_slug.values() for s in entry["sections"]
                      for item in s["items"] for tag in item["tags"]} - KNOWN_TAGS)
    if unknown:
        warnings.append("unknown tags (add them to IS_TAGS or CONTAINS_TAGS): " + ", ".join(unknown))

    data = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(timespec="seconds"),
        "colleges": [{"slug": s, "name": n} for s, n in COLLEGES],
        "meals": MEALS,
        "all_day": ALL_DAY,
        "is_tags": IS_TAGS,
        "contains_tags": CONTAINS_TAGS,
        "unknown_tags": unknown,
        "days": dict(sorted(days.items())),
    }
    return data, warnings


def main():
    now = datetime.now(TZ)
    previous = load_previous(http_get_json)
    data, warnings = build(http_get_json, now, previous)
    for w in warnings:
        print(f"::warning::{w}")
    if data is None:
        print("::error::no menu data to deploy")
        return 1
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"wrote {os.path.normpath(OUT_PATH)} ({len(data['days'])} days)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
