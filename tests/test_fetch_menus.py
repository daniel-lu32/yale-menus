import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import fetch_menus as fm  # noqa: E402

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=fm.TZ)  # a Wednesday


def week_payload(start="2026-10-11", rows=None):
    """Seven days; Wednesday gets the given rows, other days are empty."""
    days = []
    for i in range(7):
        d = f"2026-10-{11 + i:02d}" if start == "2026-10-11" else f"2026-10-{18 + i:02d}"
        days.append({"date": d, "menu_items": rows if d in ("2026-10-14", "2026-10-21") and rows else []})
    return {"days": days}


def food(name, *tags):
    return {"food": {"name": name, "icons": {"food_icons": [{"name": t} for t in tags]}}}


def title(text):
    return {"is_section_title": True, "text": text, "food": None}


ROWS = [title("DINNER"), food("Tofu", "Vegan", "Soy"), food("Chicken", "Gluten Friendly")]


def fake_fetch(fail=lambda url: False, rows=ROWS):
    def fetch(url):
        if fail(url):
            raise TimeoutError("boom")
        start = "2026-10-18" if "/2026/10/21/" in url else "2026-10-11"
        return week_payload(start, rows)
    return fetch


class ParseWeek(unittest.TestCase):
    def test_sections_items_and_tags(self):
        days = fm.parse_week(week_payload(rows=ROWS))
        wed = days["2026-10-14"]
        self.assertEqual(wed["status"], "ok")
        self.assertEqual(wed["sections"], [{"section": "DINNER", "items": [
            {"name": "Tofu", "tags": ["Vegan", "Soy"]},
            {"name": "Chicken", "tags": ["Gluten Friendly"]},
        ]}])
        self.assertEqual(days["2026-10-12"], {"status": "empty", "sections": []})

    def test_items_before_any_title_and_empty_sections(self):
        days = fm.parse_week(week_payload(rows=[food("Soup"), title("EMPTY"), title("X"), food("Pie")]))
        self.assertEqual([s["section"] for s in days["2026-10-14"]["sections"]], ["", "X"])


class WeekDates(unittest.TestCase):
    def test_sunday_to_saturday(self):
        self.assertEqual(fm.week_dates(NOW.date()), [f"2026-10-{d}" for d in range(11, 18)])
        sunday = datetime(2026, 10, 18).date()
        self.assertEqual(fm.week_dates(sunday)[0], "2026-10-18")


class Build(unittest.TestCase):
    def test_all_ok_covers_two_weeks_every_menu(self):
        data, warnings = fm.build(fake_fetch(), NOW, None)
        self.assertEqual(warnings, [])
        self.assertEqual(len(data["days"]), 14)
        self.assertEqual(set(data["days"]["2026-10-14"]), set(fm.MENUS))
        self.assertEqual(data["days"]["2026-10-14"]["dinner"]["hopper-college"]["status"], "ok")
        self.assertEqual(data["unknown_tags"], [])

    def test_partial_failure_is_error_without_previous(self):
        data, warnings = fm.build(fake_fetch(fail=lambda u: "silliman-college/menu-type/dinner" in u), NOW, None)
        entry = data["days"]["2026-10-14"]["dinner"]["silliman-college"]
        self.assertEqual(entry["status"], "error")
        self.assertEqual(data["days"]["2026-10-14"]["dinner"]["branford-college"]["status"], "ok")
        self.assertTrue(any("silliman-college dinner" in w for w in warnings))

    def test_partial_failure_carries_previous_ok_forward(self):
        good, _ = fm.build(fake_fetch(), NOW, None)
        good["generated_at"] = "2026-10-14T06:00:00-04:00"
        data, _ = fm.build(fake_fetch(fail=lambda u: "silliman-college/menu-type/dinner" in u), NOW, good)
        entry = data["days"]["2026-10-14"]["dinner"]["silliman-college"]
        self.assertEqual(entry["status"], "ok")
        self.assertEqual(entry["stale_from"], "2026-10-14T06:00:00-04:00")

    def test_carry_forward_keeps_original_stale_from(self):
        good, _ = fm.build(fake_fetch(), NOW, None)
        good["generated_at"] = "2026-10-14T10:00:00-04:00"
        good["days"]["2026-10-14"]["dinner"]["silliman-college"]["stale_from"] = "2026-10-13T18:00:00-04:00"
        data, _ = fm.build(fake_fetch(fail=lambda u: "silliman-college/menu-type/dinner" in u), NOW, good)
        self.assertEqual(data["days"]["2026-10-14"]["dinner"]["silliman-college"]["stale_from"],
                         "2026-10-13T18:00:00-04:00")

    def test_previous_empty_or_error_is_not_carried(self):
        good, _ = fm.build(fake_fetch(rows=[]), NOW, None)
        good["generated_at"] = "2026-10-14T06:00:00-04:00"
        data, _ = fm.build(fake_fetch(fail=lambda u: "silliman-college/menu-type/dinner" in u), NOW, good)
        self.assertEqual(data["days"]["2026-10-14"]["dinner"]["silliman-college"]["status"], "error")

    def test_total_failure_reuses_previous_unchanged(self):
        good, _ = fm.build(fake_fetch(), NOW, None)
        data, warnings = fm.build(fake_fetch(fail=lambda u: True), NOW, good)
        self.assertIs(data, good)
        self.assertTrue(any("previous menus.json unchanged" in w for w in warnings))

    def test_total_failure_without_previous_returns_none(self):
        data, _ = fm.build(fake_fetch(fail=lambda u: True), NOW, None)
        self.assertIsNone(data)

    def test_unknown_tags_reported(self):
        data, warnings = fm.build(fake_fetch(rows=[food("Satay", "Peanuts", "Lupin")]), NOW, None)
        self.assertEqual(data["unknown_tags"], ["Lupin"])
        self.assertTrue(any("Lupin" in w for w in warnings))


class LoadPrevious(unittest.TestCase):
    def test_rejects_missing_or_old_format(self):
        def raises(url):
            raise TimeoutError("404")
        self.assertIsNone(fm.load_previous(raises))
        self.assertIsNone(fm.load_previous(lambda url: {"days": {}}))
        self.assertIsNone(fm.load_previous(lambda url: [1, 2]))

    def test_accepts_current_format(self):
        prev = {"schema_version": fm.SCHEMA_VERSION, "generated_at": "x", "days": {}}
        self.assertIs(fm.load_previous(lambda url: prev), prev)


if __name__ == "__main__":
    unittest.main()
