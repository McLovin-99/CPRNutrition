#!/usr/bin/env python3
"""Builds the CPR Nutrition protein-per-calorie site from USDA SR28 data.

Usage:
    python3 tools/build.py            # rebuild with the current published count
    python3 tools/build.py --grow     # publish the next batch of food pages, then rebuild

Food pages are released in batches (tools/state.json) so the site grows on a
schedule instead of appearing all at once. Everyday foods (tools/everyday.json)
get plain names and are what the home page, comparisons and rankings lead with.
Standard library only, so it runs on a bare GitHub Actions runner.
"""
import argparse
import html
import json
import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
STATE_PATH = os.path.join(TOOLS, "state.json")

APP_ID = "6745491382"
APP_URL = "https://apps.apple.com/us/app/cpr-nutrition/id" + APP_ID
FONTS = ("https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..900"
         "&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap")

# The home page chart, top to bottom.
HOME_CHART = ["05064", "01256", "01123", "11090", "18001", "16098"]
# Every food page compares itself with these two.
REFERENCE = ["05064", "16098"]
CAL = 200  # calorie budget used in every comparison

# SR28 food group code -> (url slug, plural label used in headings)
GROUPS = {
    "0100": ("dairy-and-eggs", "dairy and egg foods"),
    "0400": ("fats-and-oils", "fats and oils"),
    "0500": ("poultry", "poultry"),
    "0600": ("soups-and-sauces", "soups and sauces"),
    "0700": ("deli-meats-and-sausages", "deli meats and sausages"),
    "0800": ("breakfast-cereals", "breakfast cereals"),
    "0900": ("fruits", "fruits"),
    "1000": ("pork", "pork cuts"),
    "1100": ("vegetables", "vegetables"),
    "1200": ("nuts-and-seeds", "nuts and seeds"),
    "1300": ("beef", "beef cuts"),
    "1400": ("drinks", "drinks"),
    "1500": ("fish-and-seafood", "fish and seafood"),
    "1600": ("beans-and-legumes", "beans, legumes and soy foods"),
    "1700": ("lamb-veal-and-game", "lamb, veal and game meats"),
    "1800": ("baked-goods", "baked goods"),
    "1900": ("sweets", "sweets and desserts"),
    "2000": ("grains-and-pasta", "grains and pasta"),
    "2100": ("fast-food", "fast foods"),
    "2200": ("prepared-meals", "prepared meals"),
    "2500": ("snacks", "snacks"),
    "3600": ("restaurant-foods", "restaurant foods"),
}

# Groups that people search for most get their best foods published first.
GROUP_WEIGHT = {
    "0500": 0, "0100": 0, "1500": 0, "1600": 0, "1300": 1, "1200": 1,
    "1100": 1, "0900": 2, "1000": 2, "2000": 2, "0700": 2, "0800": 3,
    "2500": 3, "1700": 3, "1400": 4, "1800": 4, "1900": 4, "0600": 5,
    "2100": 5, "2200": 5, "3600": 5, "0400": 6,
}

# Foods people search for most, as patterns on the USDA name, with how many
# variants of each to publish first.
POPULAR = [
    ("^chicken, broilers? or fryers, breast", 7), ("^chicken, broilers or fryers, thigh", 3),
    ("^chicken, broilers or fryers, drumstick", 2), ("^chicken, broilers or fryers, wing", 2),
    ("^egg, whole", 4), ("^egg, white", 2), ("^egg, yolk", 1), ("^yogurt, greek", 4), ("^yogurt, plain", 2),
    ("^cheese, cottage", 4), ("^cheese, cheddar", 2), ("^cheese, mozzarella", 3), ("^cheese, parmesan", 2),
    ("^cheese, swiss", 1), ("^cheese, feta", 1), ("^cheese, ricotta", 2), ("^cheese, cream", 1),
    ("^milk, (whole|reduced fat|lowfat|nonfat)", 4), ("^milk, chocolate", 1), ("^beverages, protein powder", 2),
    ("^whey, sweet, dried", 1), ("^fish, salmon", 5), ("^fish, tuna", 5), ("^fish, cod", 2), ("^fish, tilapia", 2),
    ("^fish, halibut", 1), ("^fish, mackerel", 1), ("^fish, sardine", 1), ("^fish, trout", 1), ("^fish, catfish", 1),
    ("^fish, pollock", 1), ("^crustaceans, shrimp", 3), ("^crustaceans, crab", 1), ("^crustaceans, lobster", 1),
    ("^mollusks, scallop", 1), ("^beef, ground", 6), ("^beef, top sirloin", 2), ("^beef, round, eye of round", 1),
    ("^beef, flank", 1), ("^beef, ribeye|^beef, rib, eye", 1), ("^beef, chuck", 1), ("jerky", 2),
    ("^turkey, (whole|breast|ground)|^turkey, all classes", 4), ("^ground turkey", 3), ("^turkey bacon", 1),
    ("^pork, fresh, loin, tenderloin", 2), ("^pork, fresh, loin, (center|top)", 2), ("^pork, fresh, ground", 1),
    ("^pork, cured, bacon", 2), ("^ham", 2), ("^sausage", 2), ("^frankfurter", 2), ("^lamb, ground", 1),
    ("^game meat, bison", 1), ("^game meat, venison|^game meat, deer", 1),
    ("^tofu", 3), ("^tempeh", 1), ("^edamame", 1), ("^soybeans, mature seeds, (cooked|dry roasted)", 2),
    ("^vital wheat gluten", 1), ("^soy protein isolate", 1), ("^lentils", 2), ("^chickpeas", 2), ("^beans, black", 2),
    ("^beans, kidney", 1), ("^beans, pinto", 1), ("^beans, navy", 1), ("^hummus", 1), ("^peas, green", 1),
    ("^peanut butter", 2), ("^peanuts", 2), ("^nuts, almonds", 2), ("^nuts, cashew", 1), ("^nuts, walnuts", 1),
    ("^nuts, pistachio", 1), ("^seeds, chia", 1), ("^seeds, pumpkin", 1), ("^seeds, sunflower", 1),
    ("^seeds, hemp", 1), ("^seeds, flaxseed", 1),
    ("^oats", 1), ("^cereals, oats", 2), ("^quinoa", 2), ("^rice, white, long-grain", 2), ("^rice, brown, long-grain", 2),
    ("^pasta, (dry|cooked), enriched", 2), ("^pasta, whole-wheat", 1), ("^bread, whole-wheat", 1),
    ("^bread, white", 1), ("^bagels, plain", 1), ("^tortillas", 1), ("^potatoes, baked", 1),
    ("^sweet potato, (raw|cooked)", 2), ("^spinach, raw", 1), ("^broccoli, (raw|cooked)", 2), ("^kale, raw", 1),
    ("^asparagus, raw", 1), ("^brussels sprouts", 1), ("^cauliflower, raw", 1), ("^mushrooms, white", 1),
    ("^bananas, raw", 1), ("^apples, raw, with skin", 1), ("^avocados, raw, all", 1), ("^blueberries, raw", 1),
    ("^strawberries, raw", 1), ("^oranges, raw, all", 1), ("^grapes", 1),
    ("^ice creams, vanilla", 1), ("^frozen yogurts", 1), ("^pizza", 2), ("^fast foods, hamburger", 2),
    ("^fast foods, chicken", 2), ("^fast foods, burrito", 1), ("^snacks, popcorn", 1), ("^snacks, pretzels", 1),
    ("^snacks, potato chips", 1), ("^snacks, granola bars", 1), ("^butter, salted", 1), ("^oil, olive", 1),
    ("^chocolate, dark", 1), ("^cookies, chocolate chip", 1), ("^doughnuts", 1),
]


def esc(s):
    return html.escape(str(s), quote=True)


def slugify(s):
    s = s.lower().replace("&", " and ").replace("%", " percent ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:90].rstrip("-")


def fmt(x, digits=1):
    if x is None:
        return "n/a"
    if abs(x - round(x)) < 0.05 or abs(x) >= 100:
        return str(int(round(x)))
    return f"{x:.{digits}f}"


def grade(cpr):
    if cpr >= 100:
        return "Excellent", "hi"
    if cpr >= 70:
        return "Good", "ok"
    if cpr >= 40:
        return "Fair", "mid"
    return "Low", "lo"


def amount(grams, unit):
    """'2 tbsp', '6.5 cups chopped' — a household amount for a gram weight."""
    desc, unit_g = unit
    n = grams / unit_g
    if n >= 10:
        n_txt = str(int(round(n)))
    elif abs(n - round(n)) < 0.1:
        n_txt = str(int(round(n)))
    else:
        n_txt = f"{n:.1f}"
    if n > 1.05 and not desc.startswith(("oz", "tbsp")):
        word, _, rest = desc.partition(" ")
        if word in ("cup", "slice", "bagel", "burger", "tender", "fillet", "scoop", "avocado"):
            desc = (word + "s " + rest).strip()
        elif desc.startswith(("large egg", "medium")):
            desc = desc + "s"
        elif desc == "half cup":
            desc = "half cups"
        elif desc == "small order":
            desc = "small orders"
    return f"{n_txt} {desc}"


def load_foods():
    with open(os.path.join(TOOLS, "data", "sr28.json")) as f:
        raw = json.load(f)
    with open(os.path.join(TOOLS, "everyday.json")) as f:
        everyday = {fid: (name, short, unit) for fid, name, short, unit in json.load(f)}
    foods = []
    for r in raw:
        if r["g"] not in GROUPS:
            continue
        if not r["kcal"] or r["kcal"] < 10 or r["p"] is None:
            continue
        r["cpr"] = r["p"] / r["kcal"] * 1000  # same formula as the app
        r["p100"] = r["p"] / r["kcal"] * 100  # grams of protein per 100 calories
        if r["id"] in everyday:
            r["name"], r["short"], r["unit"] = everyday[r["id"]]
            r["every"] = True
        else:
            r["name"] = r["short"] = r["n"]
        foods.append(r)

    used = set()
    # Everyday foods claim the clean slugs first.
    for r in sorted(foods, key=lambda r: (not r.get("every"), r["id"])):
        base = slugify(r["name"]) or r["id"]
        slug = base if base not in used else f"{base}-{r['id']}"
        used.add(slug)
        r["slug"] = slug
    return foods


def publish_order(foods):
    """Most useful pages first: everyday foods, popular searches, each group's best, then the rest."""
    first, seen = [], set()

    def take(r):
        if r["id"] not in seen:
            seen.add(r["id"])
            first.append(r)

    for r in foods:
        if r.get("every"):
            take(r)
    plain = [r for r in foods if not r["b"]]
    for pattern, n in POPULAR:
        rx = re.compile(pattern)
        matches = sorted((r for r in plain if rx.search(r["n"].lower())), key=lambda r: (len(r["n"]), r["id"]))
        for r in matches[:n]:
            take(r)
    by_group = {}
    for r in plain:
        by_group.setdefault(r["g"], []).append(r)
    for g, items in sorted(by_group.items(), key=lambda kv: GROUP_WEIGHT[kv[0]]):
        for r in sorted(items, key=lambda r: -r["cpr"])[:10]:
            take(r)
    rest = sorted(
        (r for r in foods if r["id"] not in seen),
        key=lambda r: (bool(r["b"]), GROUP_WEIGHT[r["g"]] + len(r["n"]) / 25, r["id"]),
    )
    return first + rest


class Site:
    def __init__(self, state, published):
        self.base = state["base_path"]  # e.g. "/CPRNutrition/"
        self.url = state["site_url"].rstrip("/")  # e.g. "https://mclovin-99.github.io/CPRNutrition"
        self.published = published
        self.sitemap = []

    def href(self, path):
        return self.base + path

    def food_link(self, r, text=None):
        text = esc(text if text is not None else r["name"])
        if r["id"] in self.published:
            return f'<a href="{self.href("foods/" + r["slug"] + "/")}">{text}</a>'
        return text

    def page(self, path, title, description, body, crumbs=None, wide=False):
        canonical = f"{self.url}/{path}"
        extra_head = ""
        crumb_html = ""
        if crumbs:
            parts = [f'<a href="{self.href("")}">Home</a>']
            items = [{"@type": "ListItem", "position": 1, "name": "Home", "item": self.url + "/"}]
            for i, (label, p) in enumerate(crumbs, start=2):
                if p is None:
                    parts.append(f"<span>{esc(label)}</span>")
                else:
                    parts.append(f'<a href="{self.href(p)}">{esc(label)}</a>')
                items.append({"@type": "ListItem", "position": i, "name": label,
                              "item": f"{self.url}/{p if p is not None else path}"})
            crumb_html = '<nav class="crumbs" aria-label="Breadcrumb">' + " / ".join(parts) + "</nav>"
            ld = json.dumps({"@context": "https://schema.org", "@type": "BreadcrumbList",
                             "itemListElement": items})
            extra_head = f'\n<script type="application/ld+json">{ld}</script>'
        doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}">
<meta name="apple-itunes-app" content="app-id={APP_ID}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<link rel="stylesheet" href="{self.href('assets/site.css')}">{extra_head}
</head>
<body>
<header class="masthead">
  <div class="wrap masthead-inner">
    <a class="wordmark" href="{self.href('')}">CPR<span>Nutrition</span></a>
    <nav class="nav">
      <a href="{self.href('best/')}">Rankings</a>
      <a href="{self.href('foods/')}">Foods</a>
      <a href="{self.href('calculator/')}">Calculator</a>
      <a class="nav-app" href="{APP_URL}" rel="noopener">Get the app</a>
    </nav>
  </div>
</header>
<main class="wrap{' wide' if wide else ''}">
{crumb_html}
{body}
</main>
<footer class="foot">
  <div class="wrap">
    <p>Nutrition values come from the USDA National Nutrient Database for Standard Reference, Release 28 (public domain). They describe 100 g of food as USDA measured it and can differ from the brand you buy. General information, not medical advice.</p>
    <p class="attribution">
      <!-- Begin fatsecret Platform API HTML Attribution Snippet (required by the fatsecret Premier Free tier used in the app) -->
      <a href="https://platform.fatsecret.com"><img alt="Nutrition information provided by fatsecret Platform API" src="https://platform.fatsecret.com/api/static/images/powered_by_fatsecret_horizontal_brand.svg" border="0"></a>
      <br><a href="https://platform.fatsecret.com">Powered by fatsecret Platform API</a>
      <!-- End fatsecret Platform API HTML Attribution Snippet -->
    </p>
    <p><a href="{self.href('privacy.html')}">Privacy</a> · <a href="{self.href('terms.html')}">Terms</a> · <a href="mailto:CPRNutritionApp@gmail.com">Contact</a></p>
  </div>
</footer>
</body>
</html>
"""
        out = os.path.join(ROOT, path, "index.html") if (path == "" or path.endswith("/")) else os.path.join(ROOT, path)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            f.write(doc)
        self.sitemap.append(canonical)


def app_cta(headline="Know the score of every meal you eat."):
    return f"""<aside class="cta">
  <p class="cta-kicker">The app</p>
  <h2>{esc(headline)}</h2>
  <p>CPR Nutrition gives every meal and every day a protein-per-calorie score. Scan a label with your camera, log food in a few taps, and watch the score as you eat.</p>
  <a class="store" href="{APP_URL}" rel="noopener">Download on the App Store</a>
</aside>"""


def protein_chart(site, rows, highlight=None, caption=None):
    """Horizontal bars: grams of protein in CAL calories of each food."""
    top = max(CAL / r["kcal"] * r["p"] for r in rows) or 1
    out = ['<div class="chart" role="table" aria-label="Protein in %d calories">' % CAL]
    for r in rows:
        grams_food = CAL / r["kcal"] * 100
        prot = CAL / r["kcal"] * r["p"]
        how_much = amount(grams_food, r["unit"]) if r.get("unit") else f"{fmt(grams_food, 0)} g"
        cls = grade(r["cpr"])[1] + (" this" if highlight and r["id"] == highlight else "")
        out.append(
            f'<div class="chart-row {cls}" role="row">'
            f'<div class="chart-label" role="cell"><strong>{site.food_link(r, r["short"])}</strong>'
            f'<span>{esc(how_much)}</span></div>'
            f'<div class="chart-bar" role="cell"><i style="width:{max(prot / top * 100, 0.6):.1f}%"></i></div>'
            f'<div class="chart-val" role="cell">{fmt(prot)}<small> g</small></div></div>')
    out.append("</div>")
    if caption:
        out.append(f'<p class="chart-note">{caption}</p>')
    return "".join(out)


def score_meter(cpr):
    """A thin scale from 0 to 250% with the ideal (100%) marked."""
    pos = min(cpr, 250) / 250 * 100
    return (f'<div class="meter" aria-hidden="true"><i style="left:{pos:.1f}%"></i>'
            '<b style="left:40%"></b><span style="left:40%">100% ideal</span></div>')


def rank_table(site, rows, numbered=True):
    out = ['<table class="rank"><thead><tr>' + ("<th>#</th>" if numbered else "") +
           '<th>Food</th><th class="num">CPR</th><th class="num">Protein / 100 cal</th></tr></thead><tbody>']
    for i, r in enumerate(rows, start=1):
        width = min(r["cpr"], 250) / 250 * 100
        out.append(
            "<tr>" + (f'<td class="idx">{i}</td>' if numbered else "") +
            f'<td>{site.food_link(r)}</td>'
            f'<td class="num"><span class="mini {grade(r["cpr"])[1]}"><i style="width:{width:.0f}%"></i></span><span class="pct">{fmt(r["cpr"], 0)}%</span></td>'
            f'<td class="num">{fmt(r["p100"])} g</td></tr>')
    out.append("</tbody></table>")
    return "".join(out)


def build_food(site, r, by_id, foods_by_group, published_foods):
    g_slug, g_label = GROUPS[r["g"]]
    group = foods_by_group[r["g"]]
    g_text, g_cls = grade(r["cpr"])
    rank = 1 + sum(1 for x in group if x["cpr"] > r["cpr"])

    cal_for_30 = 30 / r["p"] * r["kcal"] if r["p"] else None
    grams_for_30 = 30 / r["p"] * 100 if r["p"] else None
    pc, fc, cc = r["p"] * 4, (r["fat"] or 0) * 9, (r["carb"] or 0) * 4
    total = pc + fc + cc or 1
    main_source = "fat" if fc > cc else "carbs"

    name = r["name"]
    if r["cpr"] >= 100:
        verdict = (f"{name} is an excellent source of protein for its calories: {fmt(r['p100'])} g per 100 calories, "
                   f"above the 10 g that counts as ideal.")
    elif r["cpr"] >= 70:
        verdict = (f"{name} is a good source of protein for its calories at {fmt(r['p100'])} g per 100 calories. "
                   f"A leaner protein alongside it gets a meal to the ideal 10 g.")
    elif r["cpr"] >= 40:
        verdict = (f"{name} gives a fair amount of protein for its calories, {fmt(r['p100'])} g per 100 calories. "
                   f"Most of its calories come from {main_source}.")
    else:
        verdict = (f"{name} is low in protein for its calories, {fmt(r['p100'])} g per 100 calories. "
                   f"Most of its calories come from {main_source}, so it works best next to a high-protein food.")

    servings = list(r["s"])
    serving_rows = "".join(
        f"<tr><td>{esc(desc)} <span class='muted'>({fmt(grams, 0)} g)</span></td>"
        f"<td class='num'>{fmt(r['kcal'] * grams / 100, 0)}</td><td class='num'>{fmt(r['p'] * grams / 100)} g</td></tr>"
        for desc, grams in servings)
    serving_html = ""
    if serving_rows:
        serving_html = ('<section><h2>Per serving</h2><table class="plain"><thead><tr><th>Serving</th>'
                        f'<th class="num">Calories</th><th class="num">Protein</th></tr></thead><tbody>{serving_rows}</tbody></table></section>')

    # Comparison with the two reference foods (a lean protein and a calorie-dense one).
    compare = [r] + [by_id[x] for x in REFERENCE if x != r["id"]]
    compare.sort(key=lambda x: -x["cpr"])
    compare_html = protein_chart(site, compare, highlight=r["id"])

    # Swaps: the same kind of food first (other cheeses for a cheese), then everyday foods
    # within reach, so they're things people actually buy.
    first_word = r["n"].split(",")[0].lower()
    better = [x for x in published_foods if x["cpr"] > r["cpr"] * 1.15 and not x["b"]]
    similar = [x for x in better if x["g"] == r["g"] and x["n"].split(",")[0].lower() == first_word]
    swaps = sorted(similar, key=lambda x: (not x.get("every"), -x["cpr"]))[:4]
    reach = max(r["cpr"] * 3, 100)
    if len(swaps) < 4:
        every = [x for x in better if x.get("every") and x not in swaps and x["cpr"] <= reach]
        same = sorted((x for x in every if x["g"] == r["g"]), key=lambda x: -x["cpr"])
        other = sorted((x for x in every if x["g"] != r["g"]), key=lambda x: -x["cpr"])
        swaps += same[: 4 - len(swaps)]
        swaps += other[: 4 - len(swaps)]
    swaps_html = ""
    if swaps:
        swaps_html = f'<section><h2>Swaps with more protein per calorie</h2>{rank_table(site, swaps, numbered=False)}</section>'

    usda = f'<p class="usda">USDA name: {esc(r["n"])}</p>' if r["n"] != name else ""
    brand = f'<p class="usda">Brand: {esc(r["b"])}</p>' if r["b"] else ""
    split = [("Protein", pc / total * 100), ("Fat", fc / total * 100), ("Carbs", cc / total * 100)]
    split_html = "".join(f'<li><span>{k}</span><b>{v:.0f}%</b></li>' for k, v in split)
    stack = "".join(f'<i class="s{i}" style="width:{v:.2f}%"></i>' for i, (_, v) in enumerate(split))

    body = f"""
<article class="food">
  <header class="food-head">
    <p class="kicker">{esc(g_label.capitalize())}</p>
    <h1>{esc(name)}</h1>
    {usda}{brand}
  </header>
  <div class="food-grid">
    <section class="facts" aria-label="CPR facts">
      <h2 class="facts-title">CPR Facts</h2>
      <p class="facts-serving">Per 100 g <span>{fmt(r['kcal'], 0)} calories</span></p>
      <div class="facts-score {g_cls}">
        <span class="facts-label">CPR score</span>
        <span class="facts-big">{fmt(r['cpr'], 0)}%</span>
      </div>
      {score_meter(r['cpr'])}
      <dl>
        <div><dt>Rating</dt><dd>{g_text}</dd></div>
        <div><dt>Protein per 100 calories</dt><dd>{fmt(r['p100'])} g</dd></div>
        <div><dt>Protein per 100 g</dt><dd>{fmt(r['p'])} g</dd></div>
        <div><dt>Calories to get 30 g protein</dt><dd>{fmt(cal_for_30, 0) if cal_for_30 else 'n/a'}</dd></div>
        <div><dt>Food for 30 g protein</dt><dd>{(fmt(grams_for_30, 0) + ' g') if grams_for_30 else 'n/a'}</dd></div>
      </dl>
      <div class="stack" aria-hidden="true">{stack}</div>
      <ul class="split">{split_html}</ul>
      <p class="facts-foot">Share of calories. CPR 100% = 10 g protein per 100 calories.</p>
    </section>
    <div class="food-body">
      <p class="lead">{esc(verdict)}</p>
      <section>
        <h2>What {CAL} calories gets you</h2>
        {compare_html}
      </section>
      <section>
        <h2>How it ranks</h2>
        <p>#{rank} of {len(group)} {esc(g_label)} in the USDA database for protein per calorie.
        <a href="{site.href('best/' + g_slug + '/')}">See the ranking</a>.</p>
      </section>
      {swaps_html}
      {serving_html}
    </div>
  </div>
</article>
{app_cta()}
"""
    title = f"{name[:70]}: protein per calorie ({fmt(r['p100'])} g per 100 cal)"
    desc = (f"{name} has {fmt(r['p'])} g protein and {fmt(r['kcal'], 0)} calories per 100 g, "
            f"or {fmt(r['p100'])} g protein per 100 calories (CPR score {fmt(r['cpr'], 0)}%). Compare it and find swaps.")
    site.page(f"foods/{r['slug']}/", title, desc, body,
              crumbs=[("Foods", "foods/"), (g_label.capitalize(), "best/" + g_slug + "/"), (name[:40], None)])


def build_rankings(site, foods, foods_by_group):
    everyday = sorted((r for r in foods if r.get("every")), key=lambda r: -r["cpr"])
    cats = []
    for code, (slug, label) in GROUPS.items():
        items = foods_by_group.get(code, [])
        if not items:
            continue
        common = sorted((r for r in items if r.get("every")), key=lambda r: -r["cpr"])
        full = sorted((r for r in items if not r.get("every")), key=lambda r: -r["cpr"])[:40]
        cats.append((slug, label, common[0] if common else full[0]))
        common_html = ""
        if common:
            common_html = f"<section><h2>Common {esc(label)}</h2>{rank_table(site, common)}</section>"
        body = f"""
<header class="page-head">
  <p class="kicker">Rankings</p>
  <h1>Which {esc(label)} have the most protein per calorie?</h1>
  <p class="lead">Ranked by CPR score: grams of protein per calorie, where 100% means 10 g of protein per 100 calories.</p>
</header>
{common_html}
<section>
  <h2>Top of the full USDA list</h2>
  <p class="muted">Every {esc(label[:-1] if label.endswith('s') else label)} entry USDA has measured, including less common ones.</p>
  {rank_table(site, full)}
</section>
{app_cta()}
"""
        site.page(f"best/{slug}/", f"Highest protein per calorie {label}, ranked",
                  f"The {label} with the most protein per calorie, ranked by CPR score using USDA data.", body,
                  crumbs=[("Rankings", "best/"), (label.capitalize(), None)])

    cat_list = "".join(
        f'<li><a href="{site.href("best/" + s + "/")}">{esc(l.capitalize())}</a></li>' for s, l, _ in cats)
    body = f"""
<header class="page-head">
  <p class="kicker">Rankings</p>
  <h1>Everyday foods ranked by protein per calorie</h1>
  <p class="lead">{len(everyday)} foods people actually eat, from shrimp to olive oil. 100% means 10 g of protein for every 100 calories.</p>
</header>
<div class="two-col">
  <section>{rank_table(site, everyday)}</section>
  <aside class="side">
    <h2>By category</h2>
    <ul class="cat-list">{cat_list}</ul>
  </aside>
</div>
{app_cta()}
"""
    site.page("best/", "Everyday foods ranked by protein per calorie",
              f"{len(everyday)} everyday foods ranked by protein per calorie (CPR score), plus rankings for 22 food categories.",
              body, crumbs=[("Rankings", None)])


def build_index(site, foods, published):
    everyday = sorted((r for r in foods if r.get("every")), key=lambda r: r["name"])
    by_group = {}
    for r in foods:
        if r["id"] in published and not r.get("every"):
            by_group.setdefault(r["g"], []).append(r)

    def li(r):
        return (f'<li data-n="{esc((r["name"] + " " + r["n"]).lower())}">{site.food_link(r)}'
                f' <span class="li-score">{fmt(r["cpr"], 0)}%</span></li>')

    sections = [f'<section class="az"><h2>Common foods</h2><ul>{"".join(li(r) for r in everyday)}</ul></section>']
    for code, (slug, label) in GROUPS.items():
        items = sorted(by_group.get(code, []), key=lambda r: r["name"])
        if items:
            sections.append(f'<section class="az"><h2>{esc(label.capitalize())}</h2><ul>{"".join(li(r) for r in items)}</ul></section>')
    body = f"""
<header class="page-head">
  <p class="kicker">Food lookup</p>
  <h1>Protein per calorie for {len(published):,} foods</h1>
  <p class="lead">Search any food to see its CPR score. 100% means 10 g of protein per 100 calories.</p>
</header>
<input id="q" class="search" type="search" placeholder="Search, for example greek yogurt" aria-label="Search foods">
{''.join(sections)}
<script>
const q=document.getElementById('q');
q.addEventListener('input',()=>{{const v=q.value.trim().toLowerCase();
document.querySelectorAll('.az').forEach(s=>{{let n=0;s.querySelectorAll('li').forEach(li=>{{const m=!v||li.dataset.n.includes(v);li.hidden=!m;if(m)n++;}});s.hidden=n===0;}});}});
</script>
"""
    site.page("foods/", "Protein per calorie of every food: CPR score lookup",
              f"Look up protein per calorie and CPR score for {len(published):,} foods, from chicken breast to peanut butter.",
              body, crumbs=[("Foods", None)])


def build_calculator(site):
    body = """
<header class="page-head">
  <p class="kicker">Calculator</p>
  <h1>Protein per calorie calculator</h1>
  <p class="lead">Type the calories and protein from a label, a meal or your whole day.</p>
</header>
<div class="calc-grid">
  <form class="calc" onsubmit="return false">
    <label>Calories<input id="kcal" type="number" min="0" step="any" inputmode="decimal" value="500"></label>
    <label>Protein (g)<input id="prot" type="number" min="0" step="any" inputmode="decimal" value="35"></label>
    <label>Your daily calories<input id="day" type="number" min="0" step="any" inputmode="decimal" value="2200"></label>
  </form>
  <section class="facts" aria-live="polite">
    <h2 class="facts-title">CPR Facts</h2>
    <p class="facts-serving">Your numbers</p>
    <div class="facts-score" id="sc"><span class="facts-label">CPR score</span><span class="facts-big" id="num">70%</span></div>
    <dl>
      <div><dt>Rating</dt><dd id="rating">Good</dd></div>
      <div><dt>Protein per 100 calories</dt><dd id="p100">7 g</dd></div>
      <div><dt>Daily protein for 100%</dt><dd id="d100">220 g</dd></div>
      <div><dt>Daily protein for 70%</dt><dd id="d70">154 g</dd></div>
    </dl>
  </section>
</div>
<section class="prose">
  <h2>How the score works</h2>
  <p>CPR stands for calories-to-protein ratio. Divide grams of protein by calories and compare the result with 1 g of protein for every 10 calories, which scores 100%. Lean meat, fish and egg whites score well above 100%. Bread, rice and nut butters score under 40%. Most people who eat well land between 70% and 100% for the whole day.</p>
</section>
<script>
function g(c){return c>=100?['Excellent','hi']:c>=70?['Good','ok']:c>=40?['Fair','mid']:['Low','lo'];}
function run(){
  const k=parseFloat(document.getElementById('kcal').value)||0,p=parseFloat(document.getElementById('prot').value)||0,d=parseFloat(document.getElementById('day').value)||0;
  const c=k>0?p/k*1000:0,[t,cls]=g(c);
  document.getElementById('sc').className='facts-score '+cls;
  document.getElementById('num').textContent=Math.round(c)+'%';
  document.getElementById('rating').textContent=t;
  document.getElementById('p100').textContent=(k>0?(p/k*100).toFixed(1):'0')+' g';
  document.getElementById('d100').textContent=Math.round(d/10)+' g';
  document.getElementById('d70').textContent=Math.round(d*0.07)+' g';
}
document.querySelectorAll('.calc input').forEach(i=>i.addEventListener('input',run));run();
</script>
""" + app_cta("Let the app do the math for every meal.")
    site.page("calculator/", "Protein per calorie calculator (CPR score)",
              "Free calculator: enter calories and protein to get protein per calorie and a CPR score, plus a daily protein target.",
              body, crumbs=[("Calculator", None)])


def build_home(site, foods, by_id):
    chart = [by_id[x] for x in HOME_CHART]
    pb, broc, chick = by_id["16098"], by_id["11090"], by_id["05064"]
    p_pb, p_broc, p_chick = (CAL / x["kcal"] * x["p"] for x in (pb, broc, chick))
    everyday = sorted((r for r in foods if r.get("every")), key=lambda r: r["short"].lower())
    data = {r["id"]: [r["short"], round(r["kcal"], 1), round(r["p"], 2), amount(CAL / r["kcal"] * 100, r["unit"]),
                      site.href("foods/" + r["slug"] + "/")] for r in everyday}
    options = "".join(f'<option value="{r["id"]}">{esc(r["short"])}</option>' for r in everyday)
    body = f"""
<section class="hero">
  <p class="kicker">Protein per calorie</p>
  <h1>Two tablespoons of peanut butter: {fmt(p_pb, 0)} g of protein. Six and a half cups of broccoli: {fmt(p_broc, 0)} g.</h1>
  <p class="lead">Both are {CAL} calories. The difference is protein per calorie, and it decides whether you can hit a protein goal without going over on calories. A cup of diced chicken breast gets you {fmt(p_chick, 0)} g.</p>
</section>
<section class="figure">
  <h2 class="figure-title">Protein in {CAL} calories</h2>
  {protein_chart(site, chart, caption="Amounts are how much of each food adds up to " + str(CAL) + " calories. USDA data.")}
</section>
<section class="compare" id="compare">
  <h2>Compare any two foods</h2>
  <div class="compare-pick">
    <select id="ca" aria-label="First food">{options}</select>
    <span>vs</span>
    <select id="cb" aria-label="Second food">{options}</select>
  </div>
  <div id="cout" class="chart"></div>
  <p id="csum" class="compare-sum"></p>
</section>
<section class="index-links">
  <a href="{site.href('best/')}"><strong>Rankings</strong><span>Everyday foods and 22 categories, ranked</span></a>
  <a href="{site.href('foods/')}"><strong>Food lookup</strong><span>Scores for {len(site.published):,} foods</span></a>
  <a href="{site.href('calculator/')}"><strong>Calculator</strong><span>Score a label, a meal or your day</span></a>
</section>
<section class="about">
  <h2>About the app</h2>
  <dl class="features">
    <div><dt>One number per meal</dt><dd>The CPR score tells you if a meal, or your whole day, has enough protein for its calories.</dd></div>
    <div><dt>Label scanner</dt><dd>Point the camera at a nutrition label and the numbers fill in.</dd></div>
    <div><dt>Protein quality</dt><dd>DIAAS scores show how much of a food's protein your body can use.</dd></div>
    <div><dt>Training log</dt><dd>Lifts, steps, weight and progress photos in the same app.</dd></div>
  </dl>
</section>
{app_cta()}
<script>
const D={json.dumps(data, separators=(',', ':'))};
const A=document.getElementById('ca'),B=document.getElementById('cb');
A.value='16098';B.value='11090';
function cls(c){{return c>=100?'hi':c>=70?'ok':c>=40?'mid':'lo';}}
function draw(){{
  const rs=[A.value,B.value].map(id=>D[id]);
  const pr=rs.map(r=>{CAL}/r[1]*r[2]),top=Math.max(...pr)||1;
  document.getElementById('cout').innerHTML=rs.map((r,i)=>'<div class="chart-row '+cls(r[2]/r[1]*1000)+'"><div class="chart-label"><strong><a href="'+r[4]+'">'+r[0]+'</a></strong><span>'+r[3]+'</span></div><div class="chart-bar"><i style="width:'+Math.max(pr[i]/top*100,0.6)+'%"></i></div><div class="chart-val">'+pr[i].toFixed(1)+'<small> g</small></div></div>').join('');
  const hi=pr[0]>=pr[1]?0:1,lo=1-hi,x=pr[lo]>0?pr[hi]/pr[lo]:0;
  document.getElementById('csum').textContent=A.value===B.value?'Pick two different foods.':pr[lo]===0?rs[hi][0]+' has protein; '+rs[lo][0]+' has none.':rs[hi][0]+' has '+(x>=1.95?Math.round(x*10)/10+' times as much protein per calorie as ':Math.round((x-1)*100)+'% more protein per calorie than ')+rs[lo][0]+'.';
}}
A.addEventListener('change',draw);B.addEventListener('change',draw);draw();
</script>
"""
    site.page("", "Protein per calorie: how much protein your food really gives you | CPR Nutrition",
              "200 calories of peanut butter has 7 g of protein; 200 calories of broccoli has 17 g. Compare foods by protein per calorie, see rankings, and score your meals.",
              body)


def write_static(site):
    with open(os.path.join(ROOT, "robots.txt"), "w") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {site.url}/sitemap.xml\n")
    urls = "".join(f"<url><loc>{esc(u)}</loc></url>" for u in site.sitemap)
    with open(os.path.join(ROOT, "sitemap.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')
    os.makedirs(os.path.join(ROOT, "assets"), exist_ok=True)
    shutil.copyfile(os.path.join(TOOLS, "site.css"), os.path.join(ROOT, "assets", "site.css"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grow", action="store_true", help="publish the next batch before building")
    args = ap.parse_args()

    with open(STATE_PATH) as f:
        state = json.load(f)
    foods = load_foods()
    order = publish_order(foods)
    if args.grow:
        state["published"] = min(len(order), state["published"] + state["batch_size"])
        with open(STATE_PATH, "w") as f:
            json.dump(state, f, indent=2)
            f.write("\n")

    published_foods = order[: state["published"]]
    published = {r["id"] for r in published_foods}
    by_id = {r["id"]: r for r in foods}
    foods_by_group = {}
    for r in foods:
        foods_by_group.setdefault(r["g"], []).append(r)

    for d in ("foods", "best", "calculator"):
        shutil.rmtree(os.path.join(ROOT, d), ignore_errors=True)
    site = Site(state, published)
    build_home(site, foods, by_id)
    build_rankings(site, foods, foods_by_group)
    build_index(site, foods, published)
    build_calculator(site)
    for r in published_foods:
        build_food(site, r, by_id, foods_by_group, published_foods)
    for extra in ("privacy.html", "terms.html"):
        if os.path.exists(os.path.join(ROOT, extra)):
            site.sitemap.append(f"{site.url}/{extra}")
    write_static(site)
    print(f"Built {len(site.sitemap)} pages; {state['published']} of {len(order)} food pages published.")


if __name__ == "__main__":
    main()
