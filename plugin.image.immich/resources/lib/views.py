"""Kodi-facing layer: settings, list item building, and one function per view.

Everything that touches the Immich JSON goes through norm_bucket()/norm_assets(),
so unknown or missing fields can never raise - they just come out as None.
"""

import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

from immich import Immich, ImmichError

ADDON = xbmcaddon.Addon()
PLUGIN = sys.argv[0]
HANDLE = int(sys.argv[1])

DATE_FMT = xbmc.getRegion("datelong")
TIME_FMT = xbmc.getRegion("time")
IMAGE_SIZES = ("preview", "fullsize", "original")
VIDEO_SOURCES = ("transcoded", "original", "hls")

_api = None


def L(sid):
    return ADDON.getLocalizedString(sid)


def api():
    global _api
    if _api is None:
        by_key = ADDON.getSettingInt("auth_mode") == 0
        _api = Immich(
            base_url=ADDON.getSetting("server_url"),
            api_key=ADDON.getSetting("api_key") if by_key else "",
            token="" if by_key else ADDON.getSetting("token"),
            email="" if by_key else ADDON.getSetting("email"),
            password="" if by_key else ADDON.getSetting("password"),
            verify_tls=ADDON.getSettingBool("verify_tls"),
            user_agent=xbmc.getUserAgent(),
            on_token=lambda t: ADDON.setSetting("token", t),
        )
        if not by_key and not _api.token:
            _api.login()
    return _api


def page_size():
    return max(20, ADDON.getSettingInt("page_size"))


def order():
    return "desc" if ADDON.getSettingBool("newest_first") else "asc"


# --- Kodi helpers --------------------------------------------------------

def url(**kwargs):
    return PLUGIN + "?" + urlencode({k: v for k, v in kwargs.items() if v not in (None, "")})


def folder_item(label, target, thumb=None, date=None):
    li = xbmcgui.ListItem(label)
    if thumb:
        li.setArt({"thumb": thumb, "icon": thumb})
    if date:
        li.setDateTime(date)
    return (target, li, True)


def listing(items, content="files", sort_methods=(xbmcplugin.SORT_METHOD_UNSORTED,)):
    xbmcplugin.setContent(HANDLE, content)
    if not items:
        # An empty album used to crash the old addon; show a placeholder instead.
        items = [(url(action="root"), xbmcgui.ListItem(L(30056)), True)]
    for method in sort_methods:
        xbmcplugin.addSortMethod(HANDLE, method)
    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.endOfDirectory(HANDLE)


def fmt(dt, with_time=True):
    if not dt:
        return ""
    f = DATE_FMT + (" " + TIME_FMT if with_time else "")
    # %-d/%-m are glibc-only; Kodi hands them out on platforms that choke on them.
    f = f.replace("%-d", str(dt.day)).replace("%-m", str(dt.month))
    return dt.strftime(f)


def set_locale():
    """Month names in the user's language, not the C locale's."""
    import locale
    code = xbmc.convertLanguage(xbmc.getInfoLabel("System.Language"), xbmc.ISO_639_1)
    if not code:
        return
    # Locale names differ per platform; try the usual spellings and give up quietly.
    for name in ("%s_%s.UTF-8" % (code, code.upper()), "%s_%s" % (code, code.upper()), code):
        try:
            locale.setlocale(locale.LC_TIME, name)
            return
        except (locale.Error, ValueError):
            continue


# --- asset normalisation -------------------------------------------------

def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def duration_secs(value):
    """Immich sends milliseconds now and 'H:MM:SS.mmm' on older servers."""
    if isinstance(value, (int, float)):
        return int(value / 1000)
    if isinstance(value, str) and ":" in value:
        parts = [float(p) for p in value.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0.0)
        return int(parts[0] * 3600 + parts[1] * 60 + parts[2])
    return 0


def norm_bucket(bucket):
    """Columnar timeline bucket -> list of asset dicts. One request, no N+1."""
    ids = (bucket or {}).get("id") or []

    def col(name):
        values = (bucket or {}).get(name) or []
        return values if len(values) == len(ids) else [None] * len(ids)

    created, offsets = col("fileCreatedAt"), col("localOffsetHours")
    images, durations = col("isImage"), col("duration")
    cities, countries = col("city"), col("country")
    out = []
    for i, asset_id in enumerate(ids):
        dt = parse_dt(created[i])
        if dt and offsets[i] is not None:
            dt = dt.astimezone(timezone(timedelta(hours=float(offsets[i]))))
        out.append({
            "id": asset_id,
            "image": images[i] is not False,
            "dt": dt,
            "duration": duration_secs(durations[i]),
            "city": cities[i],
            "country": countries[i],
            "filename": None,
            "mime": None,
        })
    return out


def norm_assets(assets):
    """AssetResponseDto list (albums, search, folders, memories) -> asset dicts."""
    out = []
    for a in assets or []:
        exif = a.get("exifInfo") or {}
        out.append({
            "id": a.get("id"),
            "image": a.get("type") != "VIDEO",
            "dt": parse_dt(a.get("localDateTime") or exif.get("dateTimeOriginal")
                           or a.get("fileCreatedAt")),
            "duration": duration_secs(a.get("duration")),
            "city": exif.get("city"),
            "country": exif.get("country"),
            "filename": a.get("originalFileName"),
            "mime": a.get("originalMimeType"),
        })
    return out


def label_for(asset):
    mode = ADDON.getSettingInt("label_mode")
    if mode == 1 and asset["filename"]:
        return asset["filename"]
    if mode == 2:
        place = ", ".join(p for p in (asset["city"], asset["country"]) if p)
        if place:
            return place
    return fmt(asset["dt"]) or asset["filename"] or asset["id"]


def asset_items(assets):
    client = api()
    size = IMAGE_SIZES[ADDON.getSettingInt("image_size")]
    source = VIDEO_SOURCES[ADDON.getSettingInt("video_source")]
    items = []
    for a in assets:
        li = xbmcgui.ListItem(label_for(a))
        li.setArt({"thumb": client.thumb_url(a["id"])})
        if a["dt"]:
            li.setDateTime(a["dt"].strftime("%Y-%m-%dT%H:%M:%S"))
        if a["image"]:
            target = client.image_url(a["id"], size)
            # Immich renders previews as JPEG whatever the original was, and the
            # URL carries no extension, so Kodi has nothing else to go on.
            mime = a["mime"] if size == "original" else "image/jpeg"
        else:
            target = client.video_url(a["id"], source)
            mime = {"original": a["mime"], "hls": None}.get(source, "video/mp4")
            li.setProperty("IsPlayable", "true")
            tag = li.getVideoInfoTag()
            tag.setTitle(li.getLabel())
            if a["duration"]:
                tag.setDuration(a["duration"])
        if mime:
            li.setProperty("MimeType", mime)
        items.append((target, li, False))
    return items


def asset_listing(assets):
    listing(asset_items(assets), "images",
            (xbmcplugin.SORT_METHOD_UNSORTED, xbmcplugin.SORT_METHOD_DATE,
             xbmcplugin.SORT_METHOD_LABEL))


# --- views ---------------------------------------------------------------

def root(**_):
    entries = [
        (30040, dict(action="buckets")),
        (30041, dict(action="videos")),
        (30042, dict(action="albums")),
        (30043, dict(action="buckets", isFavorite="1")),
        (30044, dict(action="people")),
        (30045, dict(action="places")),
        (30046, dict(action="tags")),
        (30047, dict(action="memories")),
        (30048, dict(action="folders")),
        (30049, dict(action="partners")),
        (30052, dict(action="explore")),
        (30050, dict(action="search")),
        (30051, dict(action="random")),
        (30057, dict(action="buckets", visibility="archive")),
        (30053, dict(action="settings")),
    ]
    listing([folder_item(L(sid), url(**params)) for sid, params in entries])


def settings(**_):
    ADDON.openSettings()


def _bucket_filters(params):
    filters = {"order": order()}
    for key in ("albumId", "personId", "tagId", "userId", "visibility"):
        if params.get(key):
            filters[key] = params[key]
    if params.get("isFavorite"):
        filters["isFavorite"] = True
    if ADDON.getSettingBool("include_partners"):
        filters["withPartners"] = True
    return filters


def buckets(**params):
    filters = _bucket_filters(params)
    items = []
    for b in api().buckets(**filters):
        when = parse_dt(b.get("timeBucket"))
        # Buckets are months by default, so a month/year label beats a full date.
        label = "%s  (%s)" % (when.strftime("%B %Y") if when else b.get("timeBucket"),
                              b.get("count", "?"))
        items.append(folder_item(label,
                                 url(action="bucket", timeBucket=b.get("timeBucket"), **params),
                                 date=when.strftime("%Y-%m-%dT00:00:00") if when else None))
    listing(items, "files", (xbmcplugin.SORT_METHOD_UNSORTED, xbmcplugin.SORT_METHOD_DATE))


def bucket(**params):
    filters = _bucket_filters(params)
    asset_listing(norm_bucket(api().bucket(params["timeBucket"], **filters)))


def albums(**_):
    items = []
    for a in api().albums():
        thumb = a.get("albumThumbnailAssetId")
        items.append(folder_item(
            "%s  (%s)" % (a.get("albumName", "?"), a.get("assetCount", 0)),
            url(action="album", id=a.get("id")),
            thumb=api().thumb_url(thumb) if thumb else None,
            date=(a.get("startDate") or "")[:19]))
    listing(items, "files", (xbmcplugin.SORT_METHOD_UNSORTED, xbmcplugin.SORT_METHOD_LABEL,
                             xbmcplugin.SORT_METHOD_DATE))


def album(**params):
    # /api/albums/{id} returns metadata only - the assets come from the timeline.
    filters = {"albumId": params["id"]}
    months = api().buckets(order=order(), **filters)
    if len(months) == 1:
        # Most albums sit inside one month; skip the pointless extra level.
        return bucket(timeBucket=months[0]["timeBucket"], **filters)
    return buckets(**filters)


def videos(**params):
    page = int(params.get("page", 1))
    res = api().search_metadata(type="VIDEO", page=page, size=page_size(),
                                order=order(), withExif=True)
    items = asset_items(norm_assets(res.get("items")))
    if res.get("nextPage"):
        items.append(folder_item(L(30054), url(action="videos", page=page + 1)))
    listing(items, "images", (xbmcplugin.SORT_METHOD_UNSORTED, xbmcplugin.SORT_METHOD_DATE))


def people(**params):
    page = int(params.get("page", 1))
    res = api().people(page=page, size=page_size())
    items = [folder_item(p.get("name") or "?",
                         url(action="buckets", personId=p.get("id")),
                         thumb=api().person_thumb_url(p.get("id")))
             for p in res.get("people") or [] if p.get("name")]
    if res.get("hasNextPage"):
        items.append(folder_item(L(30054), url(action="people", page=page + 1)))
    listing(items, "files", (xbmcplugin.SORT_METHOD_UNSORTED, xbmcplugin.SORT_METHOD_LABEL))


def places(**_):
    items = []
    for a in api().cities():
        exif = a.get("exifInfo") or {}
        city = exif.get("city")
        if not city:
            continue
        items.append(folder_item(", ".join(p for p in (city, exif.get("country")) if p),
                                 url(action="place", city=city, country=exif.get("country")),
                                 thumb=api().thumb_url(a.get("id"))))
    listing(items, "files", (xbmcplugin.SORT_METHOD_LABEL,))


def place(**params):
    page = int(params.get("page", 1))
    res = api().search_metadata(city=params.get("city"), country=params.get("country"),
                                page=page, size=page_size(), order=order(), withExif=True)
    items = asset_items(norm_assets(res.get("items")))
    if res.get("nextPage"):
        items.append(folder_item(L(30054), url(action="place", page=page + 1, **params)))
    listing(items, "images", (xbmcplugin.SORT_METHOD_UNSORTED, xbmcplugin.SORT_METHOD_DATE))


def tags(**_):
    items = [folder_item(t.get("value") or t.get("name") or "?",
                         url(action="buckets", tagId=t.get("id")))
             for t in api().tags()]
    listing(items, "files", (xbmcplugin.SORT_METHOD_LABEL,))


def memories(**_):
    today = datetime.now().strftime("%Y-%m-%dT00:00:00.000Z")
    items = []
    for m in api().memories(for_date=today):
        assets = m.get("assets") or []
        year = (m.get("data") or {}).get("year")
        when = parse_dt(m.get("memoryAt"))
        ago = datetime.now().year - year if year else None
        label = "%s  (%s)" % (L(30058) % ago if ago else fmt(when, False), len(assets))
        items.append(folder_item(label, url(action="memory", id=m.get("id")),
                                 thumb=api().thumb_url(assets[0]["id"]) if assets else None))
    listing(items, "files")


def memory(**params):
    for m in api().memories():
        if m.get("id") == params["id"]:
            return asset_listing(norm_assets(m.get("assets")))
    return asset_listing([])


def folders(**params):
    path = params.get("path", "")
    children = set()
    for p in api().folder_paths():
        if not p.startswith(path):
            continue
        rest = p[len(path):].strip("/")
        if rest:
            children.add(rest.split("/")[0])
    items = [folder_item(name, url(action="folders", path=path.rstrip("/") + "/" + name))
             for name in sorted(children)]
    if path:
        items += asset_items(norm_assets(api().folder(path)))
    listing(items, "images", (xbmcplugin.SORT_METHOD_UNSORTED,))


def partners(**_):
    items = [folder_item(p.get("name") or p.get("email") or "?",
                         url(action="buckets", userId=p.get("id")))
             for p in api().partners()]
    listing(items, "files", (xbmcplugin.SORT_METHOD_LABEL,))


def explore(**_):
    items = []
    for group in api().explore():
        field = group.get("fieldName")
        for entry in group.get("items") or []:
            value, data = entry.get("value"), entry.get("data") or {}
            if not value or not data.get("id"):
                continue
            target = (url(action="buckets", personId=data.get("id")) if field == "people"
                      else url(action="place", city=value))
            items.append(folder_item(value, target, thumb=api().thumb_url(data.get("id"))))
    listing(items, "files", (xbmcplugin.SORT_METHOD_LABEL,))


def search(**params):
    query = params.get("q")
    page = int(params.get("page", 1))
    if not query:
        query = xbmcgui.Dialog().input(L(30055))
        if not query:
            return xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    try:
        res = api().search_smart(query, page=page, size=page_size())
    except ImmichError:
        # Smart search needs machine learning enabled; fall back to file names.
        res = api().search_metadata(originalFileName=query, page=page, size=page_size(),
                                    withExif=True)
    items = asset_items(norm_assets(res.get("items")))
    if res.get("nextPage"):
        items.append(folder_item(L(30054), url(action="search", q=query, page=page + 1)))
    return listing(items, "images", (xbmcplugin.SORT_METHOD_UNSORTED,))


def random(**_):
    asset_listing(norm_assets(api().search_random(size=page_size())))


ACTIONS = {f.__name__: f for f in (
    root, settings, buckets, bucket, albums, album, videos, people, places, place,
    tags, memories, memory, folders, partners, explore, search, random,
)}
