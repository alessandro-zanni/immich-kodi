"""Run with: python3 tests/test_immich.py

The point of these checks is the failure mode that killed the previous addon:
an Immich release adds or removes a field and every listing raises TypeError.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kodistub

SETTINGS = {
    "server_url": "https://immich.test",
    "auth_mode": 0,
    "api_key": "SECRET",
    "verify_tls": True,
    "image_size": 0,
    "video_source": 0,
    "label_mode": 0,
    "page_size": 100,
    "newest_first": True,
    "include_partners": False,
}

BUCKET = {  # shape of GET /api/timeline/bucket - parallel arrays, not objects
    "id": ["a1", "a2"],
    "fileCreatedAt": ["2026-09-11T22:30:00.000Z", "2026-09-11T23:00:00.000Z"],
    "localOffsetHours": [2, 2],
    "isImage": [True, False],
    "duration": [None, 12345],
    "city": ["Rome", None],
    "country": ["Italy", None],
    "ratio": [1.5, 1.77],
    "somethingImmichAddedLastWeek": ["x", "y"],
}


def setup(routes=None):
    views = kodistub.install(SETTINGS)
    import immich
    client = immich.Immich(base_url="https://immich.test", api_key="SECRET")
    if routes is not None:
        client._req = lambda method, path, params=None, body=None, retry=True: routes[
            (method, path)]
    views._api = client
    return views, client


def test_media_urls():
    _, client = setup()
    assert client.image_url("a1") == \
        "https://immich.test/api/assets/a1/thumbnail?size=preview|x-api-key=SECRET"
    assert client.image_url("a1", "original") == \
        "https://immich.test/api/assets/a1/original|x-api-key=SECRET"
    # Transcoded playback is the default: it has the EXIF rotation baked in.
    assert client.video_url("a1").endswith("/video/playback|x-api-key=SECRET")
    assert client.video_url("a1", "hls").startswith(
        "https://immich.test/api/assets/a1/video/stream/main.m3u8")

    import immich
    bearer = immich.Immich("https://immich.test/", token="T", verify_tls=False)
    url = bearer.thumb_url("a1")
    assert "Authorization=Bearer+T" in url and "verifypeer=false" in url, url


def test_bucket_is_read_columnwise():
    views, _ = setup()
    assets = views.norm_bucket(BUCKET)
    assert len(assets) == 2
    assert assets[0]["image"] is True and assets[1]["image"] is False
    assert assets[1]["duration"] == 12, assets[1]["duration"]      # ms -> s
    assert assets[0]["dt"].hour == 0 and assets[0]["dt"].day == 12  # 22:30Z +02:00
    assert assets[0]["city"] == "Rome"


def test_missing_and_unknown_fields_never_raise():
    views, _ = setup()
    # Columns dropped by a future Immich version, and a bucket with nothing at all.
    thin = {"id": ["a1"], "unknownField": [1]}
    assert views.norm_bucket(thin)[0]["dt"] is None
    assert views.norm_bucket({}) == [] and views.norm_bucket(None) == []
    # Asset objects with brand new fields, and duration in the old string form.
    assets = views.norm_assets([
        {"id": "a1", "type": "VIDEO", "duration": "0:01:05.500", "brandNewField": 42},
        {"id": "a2"},
    ])
    assert assets[0]["duration"] == 65 and assets[1]["image"] is True
    assert views.norm_assets(None) == []


def test_album_reads_its_assets_from_the_timeline():
    # /api/albums/{id} carries metadata only, so the assets come from buckets.
    routes = {("GET", "/timeline/buckets"): [{"timeBucket": "2026-09-01", "count": 2}],
              ("GET", "/timeline/bucket"): BUCKET}
    views, _ = setup(routes)
    views.album(id="al1")
    assert len(kodistub.CAPTURED) == 2, kodistub.CAPTURED   # flat, no month level
    assert kodistub.CONTENT == ["images"]


def test_empty_album_shows_a_placeholder():
    views, _ = setup({("GET", "/timeline/buckets"): []})
    views.album(id="empty")
    assert len(kodistub.CAPTURED) == 1 and kodistub.CAPTURED[0][1].getLabel() == "Nothing here"


def test_timeline_views_end_to_end():
    routes = {
        ("GET", "/timeline/buckets"): [{"timeBucket": "2026-09-01", "count": 2}],
        ("GET", "/timeline/bucket"): BUCKET,
    }
    views, _ = setup(routes)
    views.buckets()
    assert len(kodistub.CAPTURED) == 1
    target, item, is_folder = kodistub.CAPTURED[0]
    assert is_folder and "September 2026" in item.getLabel()
    assert "action=bucket" in target and "timeBucket=2026-09-01" in target

    kodistub.CAPTURED.clear()
    views.bucket(timeBucket="2026-09-01")
    photo, video = kodistub.CAPTURED
    assert "/thumbnail?size=preview" in photo[0]
    assert "/video/playback" in video[0] and video[1].props["IsPlayable"] == "true"
    # Kodi gets no extension in these URLs, so the type has to be declared.
    assert photo[1].props["MimeType"] == "image/jpeg"
    assert video[1].props["MimeType"] == "video/mp4"
    assert photo[1].art["thumb"].endswith("size=thumbnail|x-api-key=SECRET")


def test_every_action_is_routable():
    views, _ = setup()
    assert views.ACTIONS["root"] is views.root
    for name, fn in views.ACTIONS.items():
        assert callable(fn) and fn.__name__ == name


def test_router_turns_failures_into_dialogs():
    import importlib.util
    views = kodistub.install(SETTINGS, argv=["plugin://plugin.image.immich/", "1",
                                             "?action=nope"])
    spec = importlib.util.spec_from_file_location(
        "addon", os.path.join(kodistub.ADDON_DIR, "addon.py"))
    addon = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(addon)
    addon.run()
    assert kodistub.DIALOGS and "nope" in kodistub.DIALOGS[-1][1]

    # An unreachable server must reach the user as a dialog, not a traceback.
    kodistub.DIALOGS.clear()
    sys.argv[2] = "?action=albums"
    kodistub.SETTINGS["server_url"] = "https://immich.invalid"
    addon.run()
    assert kodistub.DIALOGS[-1][0] == "Cannot reach Immich", kodistub.DIALOGS


def test_label_modes():
    views, _ = setup()
    asset = views.norm_assets([{"id": "a1", "originalFileName": "IMG_1.jpg",
                                "exifInfo": {"city": "Rome", "country": "Italy"}}])[0]
    kodistub.SETTINGS["label_mode"] = 1
    assert views.label_for(asset) == "IMG_1.jpg"
    kodistub.SETTINGS["label_mode"] = 2
    assert views.label_for(asset) == "Rome, Italy"
    kodistub.SETTINGS["label_mode"] = 0
    assert views.label_for(asset) == "IMG_1.jpg"  # no date on this asset -> file name


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print("ok  %s" % test.__name__)
    print("\n%d checks passed" % len(tests))
