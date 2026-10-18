// Pure functions behind the page. No DOM access, so they run under `node --test`.

export const STALE_AFTER_HOURS = 16;
// Minutes after midnight (Eastern) where the default meal switches.
const LUNCH_FROM = 10 * 60 + 30;
const DINNER_FROM = 14 * 60;

// Today's date and time of day in New Haven, whatever the device's time zone.
export function easternNow(now = new Date()) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    }).formatToParts(now).map((p) => [p.type, p.value]),
  );
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    minutes: Number(parts.hour) * 60 + Number(parts.minute),
  };
}

// Today if the data has it, otherwise the closest available date.
export function defaultDate(dates, today) {
  if (dates.length === 0) return null;
  if (dates.includes(today)) return today;
  const t = Date.parse(today);
  return dates.reduce((best, d) =>
    Math.abs(Date.parse(d) - t) < Math.abs(Date.parse(best) - t) ? d : best);
}

export function mealHasData(day, meal, slugs) {
  return slugs.some((s) => day?.[meal]?.[s]?.status === "ok");
}

// Meal by time of day; skip forward past meals nobody is serving (weekend
// breakfast), but keep the time-based meal if nothing later has data.
export function defaultMeal(day, minutes, meals, slugs) {
  const start = minutes < LUNCH_FROM ? 0 : minutes < DINNER_FROM ? 1 : 2;
  for (let i = start; i < meals.length; i++) {
    if (mealHasData(day, meals[i], slugs)) return meals[i];
  }
  return meals[start];
}

// Name used only to compare dishes across colleges; never displayed.
export function normalizeName(name) {
  return name
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// For one date and meal: which colleges are compared, and which normalized
// dish names are unique to each. Badges need at least two loaded colleges.
export function onlyHere(day, meal, slugs) {
  const compared = slugs.filter((s) => day?.[meal]?.[s]?.status === "ok");
  const unique = Object.fromEntries(slugs.map((s) => [s, new Set()]));
  if (compared.length < 2) return { compared, unique };
  const namesBySlug = Object.fromEntries(compared.map((s) => [
    s,
    new Set(day[meal][s].sections.flatMap((sec) => sec.items.map((i) => normalizeName(i.name)))),
  ]));
  for (const s of compared) {
    for (const name of namesBySlug[s]) {
      if (compared.every((o) => o === s || !namesBySlug[o].has(name))) unique[s].add(name);
    }
  }
  return { compared, unique };
}

export function chipsFor(isTags, containsTags) {
  return [
    ...isTags.map((t) => ({ id: `is:${t}`, label: t })),
    ...containsTags.map((t) => ({ id: `no:${t}`, label: `No ${t}` })),
  ];
}

// Selected chips combine with AND: an item must meet every constraint.
export function itemMatches(tags, selected) {
  return selected.every((id) => {
    const tag = id.slice(3);
    return id.startsWith("is:") ? tags.includes(tag) : !tags.includes(tag);
  });
}

export function isStale(generatedAt, now = new Date()) {
  return now - new Date(generatedAt) > STALE_AFTER_HOURS * 3600 * 1000;
}
