"""Immich API client.

Two rules keep this addon alive across Immich releases:

1. No data models. Every call returns the decoded JSON (dict/list) and callers
   read it with .get(). The predecessor addon mirrored the API with dataclasses
   and broke on every Immich release that added a field.
2. No Kodi imports here, so the client can be exercised by tests and by
   tools/smoke.py without Kodi.
"""

import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Kodi appends HTTP headers to a media URL after a "|", url-encoded.
# https://kodi.wiki/view/HTTP
HEADER_SEP = "|"


class ImmichError(Exception):
    def __init__(self, status, message):
        super().__init__("%s: %s" % (status, message))
        self.status = status
        self.message = message


class Immich:
    def __init__(self, base_url, api_key="", token="", email="", password="",
                 verify_tls=True, timeout=15, user_agent="Kodi", on_token=None):
        self.base = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.token = token
        self.email = email
        self.password = password
        self.verify_tls = verify_tls
        self.timeout = timeout
        self.user_agent = user_agent
        self.on_token = on_token  # called with a fresh token so it can be persisted
        self._ctx = None if verify_tls else ssl._create_unverified_context()

    # --- plumbing ---------------------------------------------------------

    def auth_headers(self):
        if self.api_key:
            return {"x-api-key": self.api_key}
        if self.token:
            return {"Authorization": "Bearer " + self.token}
        return {}

    def _req(self, method, path, params=None, body=None, retry=True):
        url = self.base + "/api" + path
        if params:
            url += "?" + urlencode({k: _qs(v) for k, v in params.items() if v is not None})
        headers = {"Accept": "application/json", "User-Agent": self.user_agent}
        headers.update(self.auth_headers())
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            with urlopen(Request(url, data=data, headers=headers, method=method),
                         timeout=self.timeout, context=self._ctx) as res:
                raw = res.read()
            return json.loads(raw.decode("utf-8")) if raw else None
        except HTTPError as e:
            # A session token expired: log in again once, then replay the request.
            if e.code == 401 and retry and not self.api_key and self.email:
                self.login()
                return self._req(method, path, params, body, retry=False)
            raise ImmichError(e.code, _http_message(e))
        except URLError as e:
            raise ImmichError(0, str(getattr(e, "reason", e)))

    def login(self):
        res = self._req("POST", "/auth/login",
                        body={"email": self.email, "password": self.password},
                        retry=False) or {}
        self.token = res.get("accessToken", "")
        if self.on_token:
            self.on_token(self.token)
        return res

    # --- media URLs (fetched by Kodi itself, auth goes in the |header part) ---

    def media_url(self, path, **params):
        url = self.base + "/api" + path
        if params:
            url += "?" + urlencode({k: _qs(v) for k, v in params.items() if v is not None})
        headers = self.auth_headers()
        if not self.verify_tls:
            headers["verifypeer"] = "false"
        return url + HEADER_SEP + urlencode(headers) if headers else url

    def image_url(self, asset_id, size="preview"):
        if size == "original":
            return self.media_url("/assets/%s/original" % asset_id)
        return self.media_url("/assets/%s/thumbnail" % asset_id, size=size)

    def thumb_url(self, asset_id):
        return self.media_url("/assets/%s/thumbnail" % asset_id, size="thumbnail")

    def video_url(self, asset_id, source="transcoded"):
        if source == "original":
            return self.media_url("/assets/%s/original" % asset_id)
        if source == "hls":
            return self.media_url("/assets/%s/video/stream/main.m3u8" % asset_id)
        # Default: Immich's transcode, which has the EXIF rotation baked in.
        return self.media_url("/assets/%s/video/playback" % asset_id)

    def person_thumb_url(self, person_id):
        return self.media_url("/people/%s/thumbnail" % person_id)

    # --- endpoints --------------------------------------------------------

    def me(self):
        return self._req("GET", "/users/me")

    def albums(self):
        return self._req("GET", "/albums") or []

    def album(self, album_id):
        return self._req("GET", "/albums/%s" % album_id) or {}

    def buckets(self, **filters):
        return self._req("GET", "/timeline/buckets", params=filters) or []

    def bucket(self, time_bucket, **filters):
        filters["timeBucket"] = time_bucket
        return self._req("GET", "/timeline/bucket", params=filters) or {}

    def search_metadata(self, **dto):
        res = self._req("POST", "/search/metadata", body=dto) or {}
        return res.get("assets") or {}

    def search_smart(self, query, page=1, size=100):
        res = self._req("POST", "/search/smart",
                        body={"query": query, "page": page, "size": size}) or {}
        return res.get("assets") or {}

    def search_random(self, size=100, **dto):
        dto["size"] = size
        return self._req("POST", "/search/random", body=dto) or []

    def people(self, page=1, size=100):
        return self._req("GET", "/people", params={"page": page, "size": size}) or {}

    def tags(self):
        return self._req("GET", "/tags") or []

    def memories(self, for_date=None):
        return self._req("GET", "/memories", params={"for": for_date}) or []

    def cities(self):
        return self._req("GET", "/search/cities") or []

    def explore(self):
        return self._req("GET", "/search/explore") or []

    def folder_paths(self):
        return self._req("GET", "/view/folder/unique-paths") or []

    def folder(self, path):
        return self._req("GET", "/view/folder", params={"path": path}) or []

    def partners(self, direction="shared-with-me"):
        return self._req("GET", "/partners", params={"direction": direction}) or []


def _qs(value):
    """Query-string form of a value; Immich wants lowercase JSON booleans."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _http_message(err):
    try:
        payload = json.loads(err.read().decode("utf-8"))
        msg = payload.get("message") or payload.get("error")
        if isinstance(msg, list):
            msg = ", ".join(str(m) for m in msg)
        return msg or err.reason
    except Exception:
        return getattr(err, "reason", "HTTP %s" % err.code)
