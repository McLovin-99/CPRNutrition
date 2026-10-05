#!/usr/bin/env python3
"""Sends a carousel to the CPR Nutrition TikTok inbox as a draft photo post.

TikTok's Content Posting API (MEDIA_UPLOAD mode) pulls the images from a URL
prefix verified in the developer portal, then notifies the account owner, who
adds a sound and taps Post. Needs TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET.

    python3 tools/tiktok.py auth CODE --token-file out/tiktok-token.enc
    python3 tools/tiktok.py upload out/2026-10-05-x --base-url https://.../carousels/2026-10-05-x/ \
        --token-file out/tiktok-token.enc

The refresh token is kept encrypted with the client secret, because the file
lives in a public repo and TikTok hands out a new refresh token on each refresh.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://open.tiktokapis.com"
REDIRECT_URI = "https://mclovin-99.github.io/CPRNutrition/tiktok/"


def call(path, form=None, body=None, token=None):
    headers = {"User-Agent": "cpr-nutrition-carousels"}
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    else:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json; charset=UTF-8"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(API + path, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"TikTok {path} failed ({e.code}): {e.read().decode(errors='replace')}")


def openssl(args, data):
    return subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt", "-a", "-A",
                           "-pass", "env:TIKTOK_CLIENT_SECRET", *args],
                          input=data, capture_output=True, check=True).stdout


def save_token(path, tok):
    keep = {"refresh_token": tok["refresh_token"], "open_id": tok.get("open_id"),
            "refresh_expires_at": int(time.time()) + int(tok.get("refresh_expires_in", 0))}
    with open(path, "wb") as f:
        f.write(openssl([], json.dumps(keep).encode()) + b"\n")


def load_token(path):
    with open(path, "rb") as f:
        return json.loads(openssl(["-d"], f.read().strip() + b"\n"))


def token_request(form):
    tok = call("/v2/oauth/token/", form={"client_key": os.environ["TIKTOK_CLIENT_KEY"],
                                          "client_secret": os.environ["TIKTOK_CLIENT_SECRET"], **form})
    if "access_token" not in tok:
        raise SystemExit(f"TikTok token request failed: {tok}")
    return tok


def auth(args):
    tok = token_request({"code": args.code.strip(), "grant_type": "authorization_code",
                         "redirect_uri": REDIRECT_URI})
    if "video.upload" not in tok.get("scope", ""):
        raise SystemExit(f"Connected, but without the video.upload permission (got {tok.get('scope')}).")
    save_token(args.token_file, tok)
    print("TikTok connected. Refresh token saved.")


def upload(args):
    if not os.path.exists(args.token_file):
        print("TikTok isn't connected yet; skipping the draft upload.")
        return
    saved = load_token(args.token_file)
    if saved.get("refresh_expires_at", 0) < time.time() + 7 * 86400:
        print("::warning::The TikTok connection expires within a week; reconnect at " + REDIRECT_URI)
    tok = token_request({"grant_type": "refresh_token", "refresh_token": saved["refresh_token"]})
    save_token(args.token_file, tok)

    slides = sorted((f for f in os.listdir(args.dir) if f.startswith("slide-") and f.endswith(".jpg")),
                    key=lambda f: int(f[6:-4]))
    with open(os.path.join(args.dir, "caption.txt")) as f:
        caption = f.read().strip()
    title = caption.split("#")[0].strip()[:90]
    base = args.base_url.rstrip("/") + "/"
    res = call("/v2/post/publish/content/init/", token=tok["access_token"], body={
        "post_info": {"title": title, "description": caption[:4000]},
        "source_info": {"source": "PULL_FROM_URL", "photo_cover_index": 0,
                        "photo_images": [base + s for s in slides]},
        "post_mode": "MEDIA_UPLOAD",
        "media_type": "PHOTO",
    })
    if res.get("error", {}).get("code") not in (None, "ok"):
        raise SystemExit(f"TikTok rejected the post: {res['error']}")
    publish_id = res["data"]["publish_id"]
    for _ in range(30):
        time.sleep(10)
        st = call("/v2/post/publish/status/fetch/", token=tok["access_token"], body={"publish_id": publish_id})
        status = st.get("data", {}).get("status")
        print("TikTok status:", status)
        if status in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"):
            print("Sent to the TikTok inbox as a draft.")
            return
        if status == "FAILED":
            raise SystemExit(f"TikTok couldn't use the images: {st['data'].get('fail_reason')}")
    raise SystemExit("TikTok was still processing after 5 minutes.")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("auth")
    a.add_argument("code")
    a.add_argument("--token-file", required=True)
    u = sub.add_parser("upload")
    u.add_argument("dir")
    u.add_argument("--base-url", required=True)
    u.add_argument("--token-file", required=True)
    args = ap.parse_args()
    for k in ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"):
        if not os.environ.get(k):
            sys.exit(f"Missing {k}.")
    auth(args) if args.cmd == "auth" else upload(args)


if __name__ == "__main__":
    main()
