# Protein-per-calorie site generator

`python3 tools/build.py` builds the home page, rankings (`best/`), food lookup (`foods/`),
calculator, `sitemap.xml` and `robots.txt` from USDA SR28 data in `tools/data/sr28.json`.

- `tools/state.json` holds how many food pages are live. The weekly workflow
  (`.github/workflows/grow-site.yml`) runs `build.py --grow`, which adds `batch_size` more and commits.
- Edit `tools/site.css` for styling; it is copied to `assets/site.css`.
- Generated folders (`foods/`, `best/`, `calculator/`) are rebuilt from scratch each run, so don't hand-edit them.
- `privacy.html`, `terms.html` and `style.css` are hand-written and untouched by the build.
- If the site moves to a custom domain, change `site_url` and `base_path` in `state.json`.

Data: USDA National Nutrient Database for Standard Reference, Release 28 (public domain),
via the `fda-nutrient-database` npm package.
