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
    ("silliman-college", "Silliman", "A"),
    ("hopper-college", "Grace Hopper", "B"),
    ("branford-college", "Branford", "C"),
]
MEALS = ["breakfast", "lunch", "dinner"]
ALL_DAY = ["salad-bar", "daily-offerings"]
MENUS = MEALS + ALL_DAY

# Only these tags are kept; everything else (allergens etc.) is dropped.
FILTER_TAGS = ["Vegan"]
# Daily-offerings sections moved into the matching meal as "DESSERT".
DESSERT_SECTIONS = {"lunch": "LUNCH: DESSERT", "dinner": "DINNER: DESSERT"}
DROPPED_SECTIONS = {"GLUTEN FRIENDLY"}

SCHEMA_VERSION = 2
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
                        if i.get("name") in FILTER_TAGS]
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


def move_desserts(days):
    """Move each meal's dessert section out of daily-offerings into that meal.

    Runs on freshly fetched entries only, before carry-forward, so carried
    entries (which already include their dessert) are never doubled.
    """
    for menus in days.values():
        offerings = menus.get("daily-offerings", {})
        for slug, entry in offerings.items():
            keep = []
            for sec in entry["sections"]:
                meal = next((m for m, title in DESSERT_SECTIONS.items() if sec["section"] == title), None)
                if meal:
                    target = menus.get(meal, {}).get(slug)
                    if target and target["status"] == "ok":
                        target["sections"].append({"section": "DESSERT", "items": sec["items"]})
                elif sec["section"] not in DROPPED_SECTIONS:
                    keep.append(sec)
            entry["sections"] = keep
            if entry["status"] == "ok" and not keep:
                entry["status"] = "empty"


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

    for slug, _, _ in COLLEGES:
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

    move_desserts(days)

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

    data = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(timespec="seconds"),
        "colleges": [{"slug": s, "name": n, "circuit": c} for s, n, c in COLLEGES],
        "meals": MEALS,
        "all_day": ALL_DAY,
        "filter_tags": FILTER_TAGS,
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
