import {
  chipsFor, defaultDate, defaultMeal, easternNow, isStale, itemMatches,
  mealHasData,
} from "./logic.js";

const FILTERS_KEY = "yale-menus:filters";
const MEAL_LABELS = { breakfast: "Breakfast", lunch: "Lunch", dinner: "Dinner" };
const ALL_DAY_LABELS = { "salad-bar": "Soup & salad bar", "daily-offerings": "Ice cream, cereal & more" };
const $ = (id) => document.getElementById(id);

let data;
const state = { date: null, meal: null, filters: [], col: 0 };

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) node.setAttribute(k, v === true ? "" : v);
  }
  node.append(...children.filter((c) => c != null && c !== false));
  return node;
}

function loadFilters() {
  try { return JSON.parse(localStorage.getItem(FILTERS_KEY)) || []; } catch { return []; }
}
function saveFilters() {
  try { localStorage.setItem(FILTERS_KEY, JSON.stringify(state.filters)); } catch { /* private mode */ }
}

const fmtTime = (iso) => new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York", weekday: "short", hour: "numeric", minute: "2-digit",
}).format(new Date(iso));
const fmtDate = (d) => new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC", weekday: "short", month: "short", day: "numeric",
}).format(new Date(`${d}T00:00:00Z`));
const officialUrl = (slug, menu, date) =>
  `https://yalehospitality.nutrislice.com/menu/${slug}/${menu}/${date}`;

function slugs() { return data.colleges.map((c) => c.slug); }

function renderHeader(today) {
  $("updated").textContent = `Updated ${fmtTime(data.generated_at)}`;
  const notes = [];
  if (isStale(data.generated_at)) notes.push("This menu data is over 16 hours old, so it may be out of date.");
  if (state.date !== today && !Object.hasOwn(data.days, today)) {
    notes.push(`Today's menu isn't available yet, so this shows ${fmtDate(state.date)}.`);
  }
  $("banner").hidden = notes.length === 0;
  $("banner").textContent = notes.join(" ");
}

function renderControls(today) {
  const day = data.days[state.date];
  $("date").replaceChildren(...Object.keys(data.days).map((d) =>
    el("option", { value: d, selected: d === state.date },
      d === today ? `${fmtDate(d)} · Today` : fmtDate(d))));

  $("meals").replaceChildren(...data.meals.map((m) =>
    el("button", {
      type: "button", role: "tab", "aria-selected": String(m === state.meal),
      class: mealHasData(day, m, slugs()) ? "" : "no-data",
      onclick: () => { state.meal = m; render(); },
    }, MEAL_LABELS[m] ?? m)));

  $("chips").replaceChildren(...chipsFor(data.filter_tags).map((c) =>
    el("button", {
      type: "button", class: "chip", "aria-pressed": String(state.filters.includes(c.id)),
      onclick: () => {
        state.filters = state.filters.includes(c.id)
          ? state.filters.filter((f) => f !== c.id) : [...state.filters, c.id];
        saveFilters();
        render();
      },
    }, c.label)));

  $("college-tabs").replaceChildren(...data.colleges.map((c, i) =>
    el("button", {
      type: "button", role: "tab", "aria-selected": String(i === state.col),
      onclick: () => { state.col = i; render(); },
    }, c.name)));
}

function renderItem(item) {
  return el("li", { class: itemMatches(item.tags, state.filters) ? "item" : "item dim" },
    el("span", { class: "name" }, item.name),
    ...item.tags.map((t) => el("span", { class: "tag" }, t)));
}

function renderEntry(entry, slug, menu) {
  if (!entry || entry.status === "empty") return [el("p", { class: "status" }, "No menu posted")];
  if (entry.status === "error") {
    return [el("p", { class: "status error" }, "Couldn't load this menu. ",
      el("a", { href: officialUrl(slug, menu, state.date) }, "Check Nutrislice"))];
  }
  return [
    entry.stale_from && el("p", { class: "status" }, `Saved copy from ${fmtTime(entry.stale_from)}`),
    ...entry.sections.map((sec) => el("div", { class: "section" },
      sec.section && el("h3", {}, sec.section),
      el("ul", {}, ...sec.items.map(renderItem)))),
  ];
}

function renderColumns() {
  const day = data.days[state.date] ?? {};
  $("columns").replaceChildren(...data.colleges.map((c, i) =>
    el("section", { class: i === state.col ? "col active" : "col" },
      el("h2", {}, c.name, el("span", { class: "circuit" }, `Circuit ${c.circuit}`)),
      ...renderEntry(day[state.meal]?.[c.slug], c.slug, state.meal),
      el("details", { class: "all-day" },
        el("summary", {}, "All day: soups, salad bar, ice cream"),
        ...data.all_day.map((m) => el("div", { class: "all-day-menu" },
          el("h3", { class: "menu-name" }, ALL_DAY_LABELS[m] ?? m),
          ...renderEntry(day[m]?.[c.slug], c.slug, m)))))));
}

function render() {
  const today = easternNow().date;
  renderHeader(today);
  renderControls(today);
  renderColumns();
}

async function init() {
  try {
    const res = await fetch("data/menus.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch (e) {
    $("columns").replaceChildren(el("p", { class: "status error" },
      `Couldn't load menus (${e.message}). Try again in a minute.`));
    return;
  }
  const { date, minutes } = easternNow();
  state.date = defaultDate(Object.keys(data.days), date);
  if (!state.date) {
    $("columns").replaceChildren(el("p", { class: "status" }, "No menus posted right now."));
    return;
  }
  state.meal = defaultMeal(data.days[state.date], minutes, data.meals, slugs());
  const known = new Set(chipsFor(data.filter_tags).map((c) => c.id));
  state.filters = loadFilters().filter((f) => known.has(f));

  $("date").addEventListener("change", (e) => {
    state.date = e.target.value;
    if (!mealHasData(data.days[state.date], state.meal, slugs())) {
      state.meal = defaultMeal(data.days[state.date], 0, data.meals, slugs());
    }
    render();
  });
  render();
}

init();
