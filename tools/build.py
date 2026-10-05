#!/usr/bin/env python3
"""Builds the CPR Nutrition protein-per-calorie site from USDA SR28 data.

Usage:
    python3 tools/build.py            # rebuild with the current published count
    python3 tools/build.py --grow     # publish the next batch of food pages, then rebuild

Food pages are released in batches (tools/state.json) so the site grows on a
schedule instead of appearing all at once. Rankings always use every food.
Standard library only, so it runs on a bare GitHub Actions runner.
"""
import argparse
import datetime
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
        return "Excellent", "excellent"
    if cpr >= 70:
        return "Good", "good"
    if cpr >= 40:
        return "Fair", "fair"
    return "Low", "low"


def load_foods():
    with open(os.path.join(TOOLS, "data", "sr28.json")) as f:
        raw = json.load(f)
    foods = []
    for r in raw:
        if r["g"] not in GROUPS:
            continue
        if not r["kcal"] or r["kcal"] < 10 or r["p"] is None:
            continue
        r["cpr"] = r["p"] / r["kcal"] * 1000  # same formula as the app
        r["p100"] = r["p"] / r["kcal"] * 100  # grams of protein per 100 calories
        foods.append(r)

    used = set()
    for r in sorted(foods, key=lambda r: r["id"]):
        base = slugify(r["n"]) or r["id"]
        slug = base
        if slug in used:
            slug = f"{base}-{r['id']}"
        used.add(slug)
        r["slug"] = slug
    return foods


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


def publish_order(foods):
    """Most useful pages first: popular foods, then each group's best, then the rest."""
    first, seen = [], set()

    def take(r):
        if r["id"] not in seen:
            seen.add(r["id"])
            first.append(r)

    plain = [r for r in foods if not r["b"]]
    for pattern, n in POPULAR:
        rx = re.compile(pattern)
        matches = sorted((r for r in plain if rx.search(r["n"].lower())), key=lambda r: (len(r["n"]), r["id"]))
        for r in matches[:n]:
            r["pop"] = True
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
    def __init__(self, state):
        self.base = state["base_path"]  # e.g. "/CPRNutrition/"
        self.url = state["site_url"].rstrip("/")  # e.g. "https://mclovin-99.github.io/CPRNutrition"
        self.today = datetime.date.today().isoformat()
        self.sitemap = []

    def href(self, path):
        return self.base + path

    def page(self, path, title, description, body, crumbs=None, extra_head=""):
        canonical = f"{self.url}/{path}"
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
            extra_head += f'\n<script type="application/ld+json">{ld}</script>'
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
<link rel="stylesheet" href="{self.href('assets/site.css')}">{extra_head}
</head>
<body>
<header class="top">
  <div class="wrap top-inner">
    <a class="brand" href="{self.href('')}"><span class="mark">CPR</span> Nutrition</a>
    <nav class="nav">
      <a href="{self.href('best/')}">Rankings</a>
      <a href="{self.href('foods/')}">Foods</a>
      <a href="{self.href('calculator/')}">Calculator</a>
    </nav>
  </div>
</header>
<main class="wrap">
{crumb_html}
{body}
</main>
<footer class="foot">
  <div class="wrap">
    <p>Nutrition values come from the USDA National Nutrient Database for Standard Reference, Release 28 (public domain). Values are per 100 g of food as listed by USDA and can differ from brands you buy. This site is for general information, not medical advice.</p>
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


def app_cta(text="Track your CPR score for every meal"):
    return f"""<section class="cta">
  <div>
    <h2>{esc(text)}</h2>
    <p>CPR Nutrition scores everything you eat by protein per calorie. Scan a label with AI, log meals in seconds, and see your daily CPR score climb.</p>
  </div>
  <a class="store" href="{APP_URL}" rel="noopener">Download on the App Store</a>
</section>"""


def stat(label, value, note=""):
    note_html = f'<span class="note">{esc(note)}</span>' if note else ""
    return f'<div class="stat"><span class="label">{esc(label)}</span><span class="value">{value}</span>{note_html}</div>'


def ranking_table(site, rows, published):
    out = ['<div class="table-wrap"><table class="rank"><thead><tr><th>#</th><th>Food</th>'
           '<th>CPR score</th><th>Protein per 100 cal</th><th>Calories per 100 g</th></tr></thead><tbody>']
    for i, r in enumerate(rows, start=1):
        g_label, g_cls = grade(r["cpr"])
        name = esc(r["n"])
        if r["id"] in published:
            name = f'<a href="{site.href("foods/" + r["slug"] + "/")}">{name}</a>'
        out.append(
            f'<tr><td>{i}</td><td>{name}</td>'
            f'<td><span class="pill {g_cls}">{fmt(r["cpr"], 0)}%</span></td>'
            f'<td>{fmt(r["p100"])} g</td><td>{fmt(r["kcal"], 0)}</td></tr>')
    out.append("</tbody></table></div>")
    return "".join(out)


def build_food(site, r, foods_by_group, published, published_foods):
    g_slug, g_label = GROUPS[r["g"]]
    group = foods_by_group[r["g"]]
    g_text, g_cls = grade(r["cpr"])
    rank = 1 + sum(1 for x in group if x["cpr"] > r["cpr"])
    pct_better = round(100 * (len(group) - rank) / max(1, len(group) - 1))

    cal_for_30 = 30 / r["p"] * r["kcal"] if r["p"] else None
    grams_for_30 = 30 / r["p"] * 100 if r["p"] else None
    pc, fc, cc = r["p"] * 4, (r["fat"] or 0) * 9, (r["carb"] or 0) * 4
    total = pc + fc + cc or 1
    split = [("Protein", pc / total * 100, "p"), ("Fat", fc / total * 100, "f"), ("Carbs", cc / total * 100, "c")]

    if r["cpr"] >= 100:
        verdict = (f"{r['n']} is an excellent protein source for its calories. It gives {fmt(r['p100'])} g of protein "
                   f"per 100 calories, which beats the 10 g per 100 calories that CPR Nutrition treats as ideal.")
    elif r["cpr"] >= 70:
        verdict = (f"{r['n']} is a good protein source for its calories at {fmt(r['p100'])} g of protein per 100 calories. "
                   f"Pair it with a leaner protein to reach the ideal of 10 g per 100 calories.")
    elif r["cpr"] >= 40:
        verdict = (f"{r['n']} gives a fair amount of protein for its calories, {fmt(r['p100'])} g per 100 calories. "
                   f"Most of its calories come from {'fat' if fc > cc else 'carbs'}.")
    else:
        verdict = (f"{r['n']} is low in protein for its calories, with {fmt(r['p100'])} g per 100 calories. "
                   f"Most of its calories come from {'fat' if fc > cc else 'carbs'}, so balance it with high-protein foods.")

    serving_rows = ""
    for desc, grams in r["s"]:
        k = r["kcal"] * grams / 100
        p = r["p"] * grams / 100
        serving_rows += f"<tr><td>{esc(desc)} ({fmt(grams, 0)} g)</td><td>{fmt(k, 0)}</td><td>{fmt(p)} g</td></tr>"
    serving_html = ""
    if serving_rows:
        serving_html = ('<h2>Per serving</h2><div class="table-wrap"><table class="plain"><thead><tr><th>Serving</th>'
                        f'<th>Calories</th><th>Protein</th></tr></thead><tbody>{serving_rows}</tbody></table></div>')

    # Same kind of food first (other cheeses for a cheese), then everyday foods
    # from any group, so swaps are things people actually buy.
    first_word = r["n"].split(",")[0].lower()
    better = [x for x in published_foods if x["cpr"] > r["cpr"] * 1.15 and not x["b"]]
    similar = [x for x in better if x["g"] == r["g"] and x["n"].split(",")[0].lower() == first_word]
    swaps = sorted(similar, key=lambda x: -x["cpr"])[:5]
    if len(swaps) < 5:
        pop = [x for x in better if x.get("pop") and x not in swaps]
        same = sorted((x for x in pop if x["g"] == r["g"]), key=lambda x: -x["cpr"])
        # Cross-category swaps only within reach: no protein powder for a banana.
        reach = max(r["cpr"] * 3, 100)
        other = sorted((x for x in pop if x["g"] != r["g"] and x["cpr"] <= reach), key=lambda x: -x["cpr"])
        swaps += same[: 5 - len(swaps)]
        swaps += other[: min(2, 5 - len(swaps))]
    swaps_html = ""
    if swaps:
        items = "".join(
            f'<li><a href="{site.href("foods/" + x["slug"] + "/")}">{esc(x["n"])}</a>'
            f'<span class="pill {grade(x["cpr"])[1]}">{fmt(x["cpr"], 0)}%</span></li>' for x in swaps)
        swaps_html = f"<h2>Higher-protein swaps</h2><ul class=\"swaps\">{items}</ul>"

    bars = "".join(
        f'<div class="bar-row"><span>{name}</span><div class="bar"><i class="{cls}" style="width:{v:.0f}%"></i></div>'
        f"<b>{v:.0f}%</b></div>" for name, v, cls in split)

    brand = f'<p class="muted">Brand: {esc(r["b"])}</p>' if r["b"] else ""
    body = f"""
<article class="food">
  <p class="eyebrow">{esc(g_label.capitalize())}</p>
  <h1>{esc(r['n'])}: protein per calorie</h1>
  {brand}
  <div class="score {g_cls}">
    <div class="score-num">{fmt(r['cpr'], 0)}%</div>
    <div><strong>CPR score: {g_text}</strong><br>{fmt(r['p100'])} g of protein per 100 calories</div>
  </div>
  <p class="lead">{esc(verdict)}</p>
  <div class="stats">
    {stat('Protein per 100 g', fmt(r['p']) + ' g')}
    {stat('Calories per 100 g', fmt(r['kcal'], 0))}
    {stat('Calories for 30 g protein', fmt(cal_for_30, 0) if cal_for_30 else 'n/a', 'a typical protein target per meal')}
    {stat('Food needed for 30 g protein', (fmt(grams_for_30, 0) + ' g') if grams_for_30 else 'n/a')}
  </div>
  <h2>Where the calories come from</h2>
  <div class="bars">{bars}</div>
  {serving_html}
  <h2>How it ranks</h2>
  <p>It ranks #{rank} of {len(group)} {esc(g_label)} for protein per calorie, ahead of {pct_better}% of them.
  See the <a href="{site.href('best/' + g_slug + '/')}">full ranking of {esc(g_label)}</a>.</p>
  {swaps_html}
</article>
{app_cta()}
"""
    title = f"{r['n'][:70]} protein per calorie: CPR score {fmt(r['cpr'], 0)}%"
    desc = (f"{r['n']} has {fmt(r['p'])} g protein and {fmt(r['kcal'], 0)} calories per 100 g, "
            f"or {fmt(r['p100'])} g protein per 100 calories. See its CPR score and higher-protein swaps.")
    site.page(f"foods/{r['slug']}/", title, desc, body,
              crumbs=[("Foods", "foods/"), (g_label.capitalize(), "best/" + g_slug + "/"), (r["n"][:40], None)])


def build_rankings(site, foods, foods_by_group, published):
    links = []
    for code, (slug, label) in GROUPS.items():
        rows = sorted(foods_by_group.get(code, []), key=lambda r: -r["cpr"])[:50]
        if not rows:
            continue
        links.append((slug, label, rows[0]))
        body = f"""
<h1>Highest protein per calorie {esc(label)}</h1>
<p class="lead">The {len(rows)} {esc(label)} with the most protein for their calories, ranked by CPR score.
A CPR score of 100% means 10 g of protein per 100 calories, the target CPR Nutrition uses for a high-protein diet.</p>
{ranking_table(site, rows, published)}
{app_cta('Find your best foods automatically')}
"""
        site.page(f"best/{slug}/", f"Highest protein per calorie {label} (ranked)",
                  f"The {label} with the most protein per calorie, ranked by CPR score using USDA data. "
                  f"Number one: {rows[0]['n']}.", body,
                  crumbs=[("Rankings", "best/"), (label.capitalize(), None)])

    top = sorted((r for r in foods if not r["b"]), key=lambda r: -r["cpr"])[:100]
    cards = "".join(
        f'<a class="card" href="{site.href("best/" + s + "/")}"><strong>{esc(l.capitalize())}</strong>'
        f'<span>Top pick: {esc(t["n"].split(",")[0])} ({fmt(t["cpr"], 0)}%)</span></a>' for s, l, t in links)
    body = f"""
<h1>Highest protein per calorie foods</h1>
<p class="lead">Every food in the USDA database ranked by how much protein you get for each calorie.
Pick a category, or see the overall top 100 below.</p>
<div class="cards">{cards}</div>
<h2>Top 100 overall</h2>
{ranking_table(site, top, published)}
{app_cta()}
"""
    site.page("best/", "Highest protein per calorie foods: rankings by category",
              "The foods with the most protein per calorie, ranked by CPR score across 22 categories using USDA data.",
              body, crumbs=[("Rankings", None)])


def build_index(site, foods, published):
    by_group = {}
    for r in foods:
        if r["id"] in published:
            by_group.setdefault(r["g"], []).append(r)
    sections = []
    for code, (slug, label) in GROUPS.items():
        items = sorted(by_group.get(code, []), key=lambda r: r["n"])
        if not items:
            continue
        lis = "".join(f'<li data-n="{esc(r["n"].lower())}"><a href="{site.href("foods/" + r["slug"] + "/")}">'
                      f'{esc(r["n"])}</a> <span class="pill {grade(r["cpr"])[1]}">{fmt(r["cpr"], 0)}%</span></li>'
                      for r in items)
        sections.append(f'<section class="az"><h2>{esc(label.capitalize())}</h2><ul>{lis}</ul></section>')
    body = f"""
<h1>Protein per calorie for {len(published):,} foods</h1>
<p class="lead">Look up any food's CPR score. 100% means 10 g of protein per 100 calories.</p>
<input id="q" class="search" type="search" placeholder="Search foods, for example greek yogurt" aria-label="Search foods">
{''.join(sections)}
<script>
const q=document.getElementById('q');
q.addEventListener('input',()=>{{const v=q.value.trim().toLowerCase();
document.querySelectorAll('.az').forEach(s=>{{let n=0;s.querySelectorAll('li').forEach(li=>{{const m=!v||li.dataset.n.includes(v);li.hidden=!m;if(m)n++;}});s.hidden=n===0;}});}});
</script>
"""
    site.page("foods/", "Protein per calorie of every food: CPR score lookup",
              f"Look up protein per calorie and CPR score for {len(published):,} foods, from chicken breast to greek yogurt.",
              body, crumbs=[("Foods", None)])


def build_calculator(site):
    body = """
<h1>Protein per calorie calculator</h1>
<p class="lead">Enter calories and protein from any nutrition label, meal or whole day to get its CPR score.
100% means 10 g of protein per 100 calories.</p>
<form class="calc" onsubmit="return false">
  <label>Calories<input id="kcal" type="number" min="0" step="any" inputmode="decimal" value="500"></label>
  <label>Protein (g)<input id="prot" type="number" min="0" step="any" inputmode="decimal" value="35"></label>
</form>
<div class="score" id="out"><div class="score-num" id="num">70%</div><div id="txt"></div></div>
<h2>Daily protein target</h2>
<form class="calc" onsubmit="return false">
  <label>Daily calories<input id="day" type="number" min="0" step="any" inputmode="decimal" value="2200"></label>
</form>
<p id="daytxt" class="lead"></p>
<script>
function g(c){return c>=100?['Excellent','excellent']:c>=70?['Good','good']:c>=40?['Fair','fair']:['Low','low'];}
function run(){
  const k=parseFloat(document.getElementById('kcal').value)||0,p=parseFloat(document.getElementById('prot').value)||0;
  const c=k>0?p/k*1000:0,[t,cls]=g(c);
  document.getElementById('out').className='score '+cls;
  document.getElementById('num').textContent=Math.round(c)+'%';
  document.getElementById('txt').innerHTML='<strong>CPR score: '+t+'</strong><br>'+(k>0?(p/k*100).toFixed(1):'0')+' g of protein per 100 calories';
  const d=parseFloat(document.getElementById('day').value)||0;
  document.getElementById('daytxt').textContent='At '+Math.round(d)+' calories a day, a 100% CPR score means about '+Math.round(d/10)+' g of protein, and a good 70% score means about '+Math.round(d*0.07)+' g.';
}
document.querySelectorAll('input').forEach(i=>i.addEventListener('input',run));run();
</script>
<h2>How the CPR score works</h2>
<p>CPR stands for calories-to-protein ratio. Divide grams of protein by calories, then compare the result with 1 g of protein for every 10 calories.
A chicken breast scores far above 100%, most bread scores below 40%, and a balanced high-protein day lands between 70% and 100%.</p>
""" + app_cta("Let the app calculate it for every meal")
    site.page("calculator/", "Protein per calorie calculator (CPR score)",
              "Free calculator: enter calories and protein to get protein per calorie and a CPR score, plus your daily protein target.",
              body, crumbs=[("Calculator", None)])


def build_home(site, foods, published):
    top = [r for r in sorted(foods, key=lambda r: -r["cpr"]) if r["id"] in published and not r["b"]][:8]
    picks = "".join(
        f'<li><a href="{site.href("foods/" + r["slug"] + "/")}">{esc(r["n"])}</a>'
        f'<span class="pill {grade(r["cpr"])[1]}">{fmt(r["cpr"], 0)}%</span></li>' for r in top)
    body = f"""
<section class="hero">
  <h1>Get more protein out of every calorie</h1>
  <p class="lead">CPR Nutrition scores every food by its calories-to-protein ratio, so you can hit your protein goal without overshooting your calories.</p>
  <a class="store big" href="{APP_URL}" rel="noopener">Download on the App Store</a>
  <p class="muted">Free 3-day trial. iPhone.</p>
</section>
<section class="cards three">
  <a class="card" href="{site.href('best/')}"><strong>Protein per calorie rankings</strong><span>The best foods in 22 categories</span></a>
  <a class="card" href="{site.href('foods/')}"><strong>Look up any food</strong><span>CPR scores for {len(published):,} foods</span></a>
  <a class="card" href="{site.href('calculator/')}"><strong>CPR calculator</strong><span>Score any meal or label</span></a>
</section>
<h2>What the app does</h2>
<ul class="features">
  <li><strong>AI label scanner.</strong> Point your camera at a nutrition label and it fills in the numbers.</li>
  <li><strong>CPR score.</strong> One number that tells you if a meal or your whole day has enough protein for its calories.</li>
  <li><strong>Protein quality.</strong> DIAAS scores show how well your body can use the protein in each food.</li>
  <li><strong>Workouts and progress.</strong> Log lifts, steps, weight and progress photos in the same app.</li>
  <li><strong>Friends and streaks.</strong> Compete with friends on leaderboards and keep your streak alive.</li>
</ul>
<h2>Highest-scoring foods</h2>
<ul class="swaps">{picks}</ul>
{app_cta()}
"""
    site.page("", "CPR Nutrition: protein per calorie tracker and food rankings",
              "CPR Nutrition is an iPhone app that scores food by protein per calorie. Free rankings, food lookup and CPR calculator.",
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

    published = {r["id"] for r in order[: state["published"]]}
    foods_by_group = {}
    for r in foods:
        foods_by_group.setdefault(r["g"], []).append(r)

    for d in ("foods", "best"):
        shutil.rmtree(os.path.join(ROOT, d), ignore_errors=True)
    site = Site(state)
    build_home(site, foods, published)
    build_rankings(site, foods, foods_by_group, published)
    build_index(site, foods, published)
    build_calculator(site)
    published_foods = order[: state["published"]]
    for r in published_foods:
        build_food(site, r, foods_by_group, published, published_foods)
    for extra in ("privacy.html", "terms.html"):
        if os.path.exists(os.path.join(ROOT, extra)):
            site.sitemap.append(f"{site.url}/{extra}")
    write_static(site)
    print(f"Built {len(site.sitemap)} pages; {state['published']} of {len(order)} food pages published.")


if __name__ == "__main__":
    main()
