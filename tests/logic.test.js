import { test } from "node:test";
import assert from "node:assert/strict";
import {
  chipsFor, defaultDate, defaultMeal, easternNow, isStale, itemMatches,
  normalizeName, onlyHere,
} from "../site/logic.js";

const MEALS = ["breakfast", "lunch", "dinner"];
const SLUGS = ["a", "b", "c"];
const ok = (...names) => ({ status: "ok", sections: [{ section: "", items: names.map((name) => ({ name, tags: [] })) }] });
const empty = { status: "empty", sections: [] };
const error = { status: "error", sections: [] };

test("easternNow uses New York time, not the device zone", () => {
  // 03:30 UTC on Oct 18 is still Oct 17, 23:30 in New Haven (EDT).
  assert.deepEqual(easternNow(new Date("2026-10-18T03:30:00Z")), { date: "2026-10-17", minutes: 23 * 60 + 30 });
  // January is EST (UTC-5).
  assert.deepEqual(easternNow(new Date("2027-01-10T15:00:00Z")), { date: "2027-01-10", minutes: 10 * 60 });
});

test("defaultDate prefers today, else the nearest date", () => {
  const dates = ["2026-10-18", "2026-10-19", "2026-10-25"];
  assert.equal(defaultDate(dates, "2026-10-19"), "2026-10-19");
  assert.equal(defaultDate(dates, "2026-10-17"), "2026-10-18");
  assert.equal(defaultDate(dates, "2026-10-30"), "2026-10-25");
  assert.equal(defaultDate([], "2026-10-19"), null);
});

test("defaultMeal follows the clock and skips meals nobody serves", () => {
  const full = { breakfast: { a: ok("x") }, lunch: { a: ok("x") }, dinner: { a: ok("x") } };
  assert.equal(defaultMeal(full, 8 * 60, MEALS, SLUGS), "breakfast");
  assert.equal(defaultMeal(full, 10 * 60 + 30, MEALS, SLUGS), "lunch");
  assert.equal(defaultMeal(full, 14 * 60, MEALS, SLUGS), "dinner");
  const weekend = { breakfast: { a: empty, b: error }, lunch: { a: ok("x") }, dinner: { a: ok("x") } };
  assert.equal(defaultMeal(weekend, 8 * 60, MEALS, SLUGS), "lunch");
  const nothing = { breakfast: { a: empty }, lunch: { a: error }, dinner: { a: empty } };
  assert.equal(defaultMeal(nothing, 12 * 60, MEALS, SLUGS), "lunch");
});

test("normalizeName ignores case, accents, punctuation and & vs and", () => {
  assert.equal(normalizeName("  Mac & Cheese "), normalizeName("mac and cheese"));
  assert.equal(normalizeName("Crème Brûlée"), "creme brulee");
  assert.equal(normalizeName("General Tso's  Chicken,"), "general tso s chicken");
  assert.notEqual(normalizeName("Chicken"), normalizeName("Chickpeas"));
});

test("onlyHere badges dishes unique to one loaded college", () => {
  const day = { dinner: { a: ok("Tofu", "Rice"), b: ok("rice", "Soup"), c: ok("Rice", "Mac & Cheese") } };
  const { compared, unique } = onlyHere(day, "dinner", SLUGS);
  assert.deepEqual(compared, SLUGS);
  assert.deepEqual([...unique.a], ["tofu"]);
  assert.deepEqual([...unique.b], ["soup"]);
  assert.deepEqual([...unique.c], ["mac and cheese"]);
});

test("onlyHere compares only loaded colleges and needs at least two", () => {
  const two = { dinner: { a: ok("Tofu", "Rice"), b: ok("Rice"), c: error } };
  const r2 = onlyHere(two, "dinner", SLUGS);
  assert.deepEqual(r2.compared, ["a", "b"]);
  assert.deepEqual([...r2.unique.a], ["tofu"]);
  const one = { dinner: { a: ok("Tofu"), b: empty, c: error } };
  const r1 = onlyHere(one, "dinner", SLUGS);
  assert.deepEqual(r1.compared, ["a"]);
  assert.equal(r1.unique.a.size, 0);
});

test("chips match items that have the tag, combined with AND", () => {
  assert.deepEqual(chipsFor(["Vegan"]), [{ id: "is:Vegan", label: "Vegan" }]);
  assert.equal(itemMatches(["Vegan"], ["is:Vegan"]), true);
  assert.equal(itemMatches([], ["is:Vegan"]), false);
  assert.equal(itemMatches([], []), true);
});

test("isStale flips after 16 hours", () => {
  const gen = "2026-10-17T22:00:00Z";
  assert.equal(isStale(gen, new Date("2026-10-18T13:59:00Z")), false);
  assert.equal(isStale(gen, new Date("2026-10-18T14:01:00Z")), true);
});
