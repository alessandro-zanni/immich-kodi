"""Exercise every view against a real Immich server, without Kodi.

    python3 tools/smoke.py --url https://photos.example.com --key <API_KEY>
    python3 tools/smoke.py --url ... --email me@example.com --password ... --insecure
"""

import argparse
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import kodistub  # noqa: E402


def run(views, name, label, **params):
    kodistub.CAPTURED.clear()
    try:
        views.ACTIONS[name](**params)
    except Exception as err:
        print("FAIL %-22s %s" % (label, err))
        traceback.print_exc()
        return []
    items = list(kodistub.CAPTURED)
    first = items[0][1].getLabel() if items else "-"
    print("ok   %-22s %4d items   first: %s" % (label, len(items), first))
    return items


def param_of(target, key):
    from urllib.parse import parse_qsl, urlsplit
    return dict(parse_qsl(urlsplit(target).query)).get(key)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--key", default="")
    p.add_argument("--email", default="")
    p.add_argument("--password", default="")
    p.add_argument("--insecure", action="store_true")
    p.add_argument("--query", default="beach")
    args = p.parse_args()

    views = kodistub.install({
        "server_url": args.url,
        "auth_mode": 0 if args.key else 1,
        "api_key": args.key,
        "email": args.email,
        "password": args.password,
        "verify_tls": not args.insecure,
        "image_size": 0, "video_source": 0, "label_mode": 0,
        "page_size": 100, "newest_first": True, "include_partners": False,
    })
    try:
        print("server:", views.api().me().get("email"), "\n")
    except Exception as err:
        sys.exit("cannot reach Immich: %s" % err)

    run(views, "root", "root")
    buckets = run(views, "buckets", "timeline")
    if buckets:
        run(views, "bucket", "timeline/first month",
            timeBucket=param_of(buckets[0][0], "timeBucket"))
    albums = run(views, "albums", "albums")
    if albums:
        run(views, "album", "albums/first", id=param_of(albums[0][0], "id"))
    run(views, "videos", "videos")
    run(views, "buckets", "favourites", isFavorite="1")
    people = run(views, "people", "people")
    if people:
        run(views, "buckets", "people/first", personId=param_of(people[0][0], "personId"))
    places = run(views, "places", "places")
    if places:
        run(views, "place", "places/first", city=param_of(places[0][0], "city"))
    run(views, "tags", "tags")
    memories = run(views, "memories", "memories")
    if memories:
        run(views, "memory", "memories/first", id=param_of(memories[0][0], "id"))
    run(views, "folders", "folders")
    run(views, "partners", "partners")
    run(views, "explore", "explore")
    run(views, "random", "random")
    run(views, "search", "search '%s'" % args.query, q=args.query)


if __name__ == "__main__":
    main()
