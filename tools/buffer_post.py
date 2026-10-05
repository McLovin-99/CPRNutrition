#!/usr/bin/env python3
"""Schedules a carousel as public posts through Buffer (needs BUFFER_API_KEY).

    python3 tools/buffer_post.py out/2026-10-05-x --base-url https://.../carousels/2026-10-05-x/ \
        --services tiktok,instagram

TikTok gets the 9:16 slides; Instagram gets the 4:5 crops (ig-N.jpg), since its
feed rejects taller images. Posts go out at 7pm New York time the same day, or
in 15 minutes if that has passed. A service with no connected channel is skipped.
"""
import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.buffer.com"
POST_HOUR_UTC = 23  # 7pm EDT / 6pm EST


def gql(query, variables=None):
    req = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables or {}}).encode(),
                                 headers={"Authorization": "Bearer " + os.environ["BUFFER_API_KEY"],
                                          "Content-Type": "application/json", "User-Agent": "cpr-nutrition-carousels"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Buffer request failed ({e.code}): {e.read().decode(errors='replace')[:500]}")
    if data.get("errors"):
        raise SystemExit(f"Buffer error: {data['errors']}")
    return data["data"]


def channels():
    org = gql("{ account { organizations { id } } }")["account"]["organizations"][0]["id"]
    return gql("""query($org: OrganizationId!) { channels(input: {organizationId: $org}) {
        id service displayName isDisconnected } }""", {"org": org})["channels"]


def due_at():
    now = datetime.datetime.now(datetime.timezone.utc)
    t = now.replace(hour=POST_HOUR_UTC, minute=0, second=0, microsecond=0)
    if t < now + datetime.timedelta(minutes=15):
        t = now + datetime.timedelta(minutes=15)
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def numbered(folder, prefix):
    files = [f for f in os.listdir(folder) if f.startswith(prefix) and f.endswith(".jpg")]
    return sorted(files, key=lambda f: int(f[len(prefix):-4]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--services", default="tiktok,instagram")
    args = ap.parse_args()
    if not os.environ.get("BUFFER_API_KEY"):
        sys.exit("Missing BUFFER_API_KEY.")

    with open(os.path.join(args.dir, "caption.txt")) as f:
        caption = f.read().strip()
    base = args.base_url.rstrip("/") + "/"
    when = due_at()
    by_service = {}
    for c in channels():
        if not c["isDisconnected"]:
            by_service.setdefault(c["service"].lower(), c)

    for service in [s.strip() for s in args.services.split(",") if s.strip()]:
        ch = by_service.get(service)
        if not ch:
            print(f"::warning::No connected {service} channel in Buffer; skipped.")
            continue
        if service == "instagram":
            images, meta = numbered(args.dir, "ig-"), {"instagram": {"type": "carousel", "shouldShareToFeed": True}}
        else:
            images, meta = numbered(args.dir, "slide-"), {}
        res = gql("""mutation($input: CreatePostInput!) { createPost(input: $input) {
            __typename ... on PostActionSuccess { post { id status dueAt } } ... on MutationError { message } } }""",
                  {"input": {"channelId": ch["id"], "text": caption,
                             "assets": [{"image": {"url": base + f}} for f in images[:10]],
                             "schedulingType": "automatic", "mode": "customScheduled", "dueAt": when,
                             "needsApproval": False, "metadata": meta}})["createPost"]
        if res.get("__typename") != "PostActionSuccess":
            raise SystemExit(f"Buffer refused the {service} post: {res.get('message')}")
        print(f"Scheduled on {service} ({ch['displayName']}) for {res['post']['dueAt']}.")


if __name__ == "__main__":
    main()
