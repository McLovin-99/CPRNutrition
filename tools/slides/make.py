#!/usr/bin/env python3
"""Makes one TikTok-style photo slideshow from tools/slides/scripts.json.

Each run picks the next script not yet in <out>/log.json, fetches food photos
from Pexels (PEXELS_API_KEY), renders 1080x1920 slides with Playwright, joins
them into an MP4 with ffmpeg, and writes:

    <out>/<date>-<id>/slide-1.jpg ... video.mp4, caption.txt, credits.txt

Numbers on the slides come from USDA SR28 via tools/build.py, so they always
match the website. Use --dry-run to render with plain backgrounds (no Pexels).
"""
import argparse
import datetime
import hashlib
import html
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import build  # noqa: E402

APP_LINE = "Scores every food by protein per calorie, so you can pick the ones that keep you full."
SLIDE_SECONDS, END_SECONDS = 3.0, 3.5


def food_totals(items, by_id):
    cal = sum(by_id[i]["kcal"] * g / 100 for i, g in items)
    prot = sum(by_id[i]["p"] * g / 100 for i, g in items)
    return cal, prot


def round_cal(x):
    return f"{int(round(x / 10.0) * 10):,}"


def fill_text(script, by_id):
    all_items = [it for s in script["slides"] for it in s.get("food", [])]
    t_cal, t_prot = food_totals(all_items, by_id) if all_items else (0, 0)
    out = []
    for s in script["slides"]:
        cal, prot = food_totals(s.get("food", []), by_id)
        out.append(s["text"].format(cal=round_cal(cal), protein=int(round(prot)),
                                    total_cal=round_cal(t_cal), total_protein=int(round(t_prot))))
    return out


def pexels_photo(query, seed, used):
    key = os.environ["PEXELS_API_KEY"]
    url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode(
        {"query": query, "orientation": "portrait", "per_page": 15})
    req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "cpr-nutrition-slides"})
    with urllib.request.urlopen(req, timeout=30) as r:
        photos = json.load(r)["photos"]
    photos = [p for p in photos if p["id"] not in used] or photos
    if not photos:
        raise SystemExit(f"No Pexels results for {query!r}")
    # Stable pick per script so reruns give the same slideshow.
    p = photos[int(hashlib.sha1(seed.encode()).hexdigest(), 16) % min(len(photos), 6)]
    used.add(p["id"])
    req = urllib.request.Request(p["src"]["large2x"], headers={"User-Agent": "cpr-nutrition-slides"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data, f'{p["photographer"]} on Pexels: {p["url"]}'


SLIDE_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700;800&display=swap">
<style>
*{{margin:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#222;font-family:Montserrat,Helvetica,Arial,sans-serif}}
.bg{{position:absolute;inset:0;background:{bg} center/cover no-repeat}}
.shade{{position:absolute;inset:0;background:rgba(0,0,0,{shade})}}
.txt{{position:absolute;left:90px;right:150px;top:{top}px;text-align:center}}
.txt span{{display:inline;background:#fff;color:#111;font-weight:700;font-size:{size}px;line-height:1.5;padding:6px 18px;
  -webkit-box-decoration-break:clone;box-decoration-break:clone;border-radius:14px}}
.end{{position:absolute;inset:0;background:#111;color:#fff;padding:560px 110px 0}}
.end h1{{font-size:96px;font-weight:800;letter-spacing:-.01em}}
.end p{{font-size:52px;line-height:1.35;font-weight:600;margin-top:40px;color:#eee}}
.end b{{display:inline-block;margin-top:60px;border:5px solid #fff;padding:24px 36px;font-size:46px}}
</style></head><body>{body}</body></html>"""


def slide_html(text, photo_path, index):
    bg = f"url('file://{photo_path}')" if photo_path else "#3a3a3a"
    hook = index == 0
    body = (f'<div class="bg"></div><div class="shade"></div>'
            f'<div class="txt"><span>{html.escape(text)}</span></div>')
    return SLIDE_HTML.format(bg=bg, shade=0.12 if hook else 0.18, top=520 if hook else 360,
                             size=64 if hook else 54, body=body)


def end_html():
    body = (f'<div class="end"><h1>CPR Nutrition</h1><p>{html.escape(APP_LINE)}</p>'
            f'<b>Free trial on the App Store</b></div>')
    return SLIDE_HTML.format(bg="#111", shade=0, top=0, size=0, body=body)


def render(pages, out_dir):
    from playwright.sync_api import sync_playwright
    paths = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(**json.loads(os.environ.get("SLIDES_LAUNCH", "{}")))
        page = b.new_page(viewport={"width": 1080, "height": 1920})
        for i, doc in enumerate(pages, start=1):
            f = os.path.join(out_dir, f"_slide-{i}.html")
            with open(f, "w") as fh:
                fh.write(doc)
            page.goto("file://" + f)
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(300)
            path = os.path.join(out_dir, f"slide-{i}.jpg")
            page.screenshot(path=path, type="jpeg", quality=90)
            os.remove(f)
            paths.append(path)
        b.close()
    return paths


def make_video(paths, out_dir):
    lst = os.path.join(out_dir, "_list.txt")
    with open(lst, "w") as f:
        for i, p in enumerate(paths):
            f.write(f"file '{p}'\nduration {END_SECONDS if i == len(paths) - 1 else SLIDE_SECONDS}\n")
        f.write(f"file '{paths[-1]}'\n")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-shortest",
                    "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "20",
                    "-c:a", "aac", "-movflags", "+faststart", os.path.join(out_dir, "video.mp4")], check=True)
    os.remove(lst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="content folder (holds log.json)")
    ap.add_argument("--id", help="make this script instead of the next one")
    ap.add_argument("--dry-run", action="store_true", help="no Pexels; plain backgrounds")
    args = ap.parse_args()

    with open(os.path.join(HERE, "scripts.json")) as f:
        scripts = json.load(f)
    log_path = os.path.join(args.out, "log.json")
    log = json.load(open(log_path)) if os.path.exists(log_path) else []
    done = {e["id"] for e in log}
    if args.id:
        script = next(s for s in scripts if s["id"] == args.id)
    else:
        todo = [s for s in scripts if s["id"] not in done]
        if not todo:
            print("All scripts used; add more to tools/slides/scripts.json.")
            return
        script = todo[0]

    by_id = {r["id"]: r for r in build.load_foods()}
    texts = fill_text(script, by_id)
    date = datetime.date.today().isoformat()
    out_dir = os.path.abspath(os.path.join(args.out, f"{date}-{script['id']}"))
    os.makedirs(out_dir, exist_ok=True)

    pages, credits, used = [], [], set()
    for i, (s, text) in enumerate(zip(script["slides"], texts)):
        photo = None
        if not args.dry_run:
            data, credit = pexels_photo(s["q"], f"{script['id']}-{i}", used)
            photo = os.path.join(out_dir, f"_photo-{i}.jpg")
            with open(photo, "wb") as fh:
                fh.write(data)
            credits.append(f"Slide {i + 1}: {credit}")
        pages.append(slide_html(text, photo, i))
    pages.append(end_html())
    paths = render(pages, out_dir)
    for f in os.listdir(out_dir):
        if f.startswith("_photo-"):
            os.remove(os.path.join(out_dir, f))
    make_video(paths, out_dir)

    with open(os.path.join(out_dir, "caption.txt"), "w") as f:
        f.write(script["caption"] + "\n")
    with open(os.path.join(out_dir, "credits.txt"), "w") as f:
        f.write("Photos from Pexels (free to use, https://www.pexels.com/license/).\n" + "\n".join(credits) + "\n")
    if not args.dry_run and not args.id:
        log.append({"id": script["id"], "date": date})
        with open(log_path, "w") as f:
            json.dump(log, f, indent=2)
            f.write("\n")
    print(f"Made {out_dir}")
    for t in texts:
        print(" -", t)


if __name__ == "__main__":
    main()
