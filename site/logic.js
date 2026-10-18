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

export function chipsFor(tags) {
  return tags.map((t) => ({ id: `is:${t}`, label: t }));
}

// Selected chips combine with AND: an item must have every selected tag.
export function itemMatches(tags, selected) {
  return selected.every((id) => tags.includes(id.slice(3)));
}

export function isStale(generatedAt, now = new Date()) {
  return now - new Date(generatedAt) > STALE_AFTER_HOURS * 3600 * 1000;
}
