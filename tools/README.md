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

## Photo carousels for TikTok

`.github/workflows/slideshows.yml` runs Mon/Wed/Fri. It takes the next unused script from
`tools/slides/scripts.json`, pulls food photos from Pixabay (needs the `PIXABAY_API_KEY` repo secret;
a `PEXELS_API_KEY` works too),
puts TikTok-style captions on them, ends with a CPR Nutrition card, and saves the images
(posted as a TikTok photo carousel, not a video) as
`slide-*.jpg`, `caption.txt` and `credits.txt` to a dated folder on the `content` branch.
`content/log.json` records which scripts are used.

- Numbers in the text (`{cal}`, `{protein}`, `{total_cal}`, `{total_protein}`) are computed from the
  `food` list of `[usda_id, grams]` on each slide, so they match the website.
- Add scripts to keep it going; with three a week, each 12 scripts last about a month.
- Test locally: `python3 tools/slides/make.py --out /tmp/content --dry-run --id healthy-snack-trap`
  (plain backgrounds, no key needed; needs `pip install playwright`).
