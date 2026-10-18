# Yale Menus

Silliman (circuit A), Grace Hopper (B) and Branford (C) dining hall menus side by side, with a Vegan filter and "Only here" badges for dishes just one college is serving. Each meal includes its desserts.

Live: https://daniel-lu32.github.io/yale-menus/

## How it works

- `scripts/fetch_menus.py` (Python standard library only) pulls this week and next week from the public Nutrislice API for each college: breakfast, lunch, dinner, salad bar and daily offerings. It writes `site/data/menus.json`.
- `.github/workflows/update.yml` runs the tests, fetches menus and deploys `site/` to GitHub Pages at 10:00, 14:00, 18:00 and 22:00 UTC, on every push to `main`, and on demand (Actions tab, "Run workflow").
- `.github/workflows/keepalive.yml` pushes an empty `chore: keepalive` commit if the repo has been quiet for 45 days, because GitHub turns off scheduled workflows after 60 days of inactivity.
- If some downloads fail, the last good copy of that menu is kept and marked "Saved copy from ...". If every download fails, the previous `menus.json` is redeployed and the page's stale banner appears after 16 hours.

Nothing runs on your laptop.

## Local preview

```sh
python3 scripts/fetch_menus.py
python3 -m http.server -d site 8000
# open http://localhost:8000
```

## Tests

```sh
npm test   # node --test + python unittest; no dependencies to install
```

## Changing colleges or tags

- Colleges: edit `COLLEGES` (slug, name, circuit) at the top of `scripts/fetch_menus.py`.
- Tags: `FILTER_TAGS` lists the only Nutrislice tags kept (currently just Vegan); each becomes a filter chip and a label on matching dishes.

## One-time setup

Repo Settings → Pages → Build and deployment → Source: **GitHub Actions**.

Design doc and review: `docs/designs/yale-menus-side-by-side.md`.
