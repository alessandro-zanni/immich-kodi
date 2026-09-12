# Immich for Kodi

Unofficial Kodi addon to browse and play the photos and videos on your
[Immich](https://immich.app) server.

Replaces [vladd11/immich-kodi](https://github.com/vladd11/immich-kodi), which is
unmaintained. Written from scratch around the two things that broke it.

![icon](plugin.image.immich/resources/icon.png)

## What it does

Timeline · Videos · Albums · Favourites · People · Places · Tags · Memories ·
Folders · Shared with me · Explore · Search (Immich's CLIP smart search) ·
Random · Archive.

Photos and videos both play. Videos use Immich's transcoded stream by default,
so rotated clips come out the right way up.

## The two rules that keep it working

**1. The Immich API is never modelled.** The client returns plain `dict`s and
callers read them with `.get()`. The old addon mirrored the API with
`@dataclass`es, so every Immich release that added a field (`createdAt`,
`width`, `thumbhashV2`, …) crashed every listing — that is over half of its
closed issues. Here an unknown field is ignored and a missing one reads as
`None`; `tests/test_immich.py` asserts exactly that.

**2. One request per screen.** `GET /api/timeline/bucket` already returns every
column a listing needs (`id`, `isImage`, `fileCreatedAt`, `localOffsetHours`,
`duration`, `city`, …). The old addon threw that away and fetched
`/api/assets/{id}` once per asset — a 500-photo month cost 501 requests, which
is why its slideshow never finished on large libraries.

Also fixed by construction: empty albums no longer raise, dates use each photo's
own UTC offset instead of the server's, and there are no runtime dependencies to
resolve at install time (stdlib only).

## Install

**From the repository** (gets updates automatically): install
`repository.immich-1.0.0.zip` from the
[latest release](../../releases/latest), then *Add-ons → Install from
repository → Immich Kodi*.

**One-off**: install `plugin.image.immich-x.y.z.zip` from the same release.

The addon lives under **Pictures**, which is the only Kodi window that opens
both photos and videos; Kodi's video window cannot display a photo.

Then open the addon settings and fill in:

- **Server URL** — e.g. `https://photos.example.com`
- **Authentication** — either an **API key** (Immich → Account Settings → API
  Keys → New API Key) or your **email and password**, which is a lot less
  painful to type on a remote.

Turn off *Verify TLS certificate* only if your server uses a self-signed one.

Requires Kodi 21 (Omega) or newer.

## Settings worth knowing

| Setting | Why |
|---|---|
| Photo quality | `Preview` by default — a 45 MP original takes seconds to decode on a TV box. Switch to `Original` on a strong device. |
| Video source | `Transcoded` applies Immich's autorotate. `Original` is untouched, `HLS` adaptive. |
| Item label | Date taken, file name, or place. |
| Include partner photos | Adds photos shared with you by partners to the timeline. |

## Development

```sh
python3 tests/test_immich.py                          # unit checks, no Kodi needed
python3 tools/smoke.py --url https://... --key ...    # run every view against a real server
python3 tools/build.py                                # build docs/ (zip + Kodi repository)
python3 tools/make_art.py                             # regenerate icon and fanart
```

`tests/kodistub.py` fakes the `xbmc*` modules, so the whole addon runs — and is
testable — outside Kodi. `resources/lib/immich.py` never imports Kodi.

## Layout

```
plugin.image.immich/
  addon.py                 router: action -> view, and errors -> dialogs
  resources/lib/immich.py  API client and media URL builders (no Kodi imports)
  resources/lib/views.py   settings, list item building, one function per view
```

## Licence

GPL-3.0-only. Not affiliated with the Immich project; the icon is the official
Immich logomark from [immich-app/immich](https://github.com/immich-app/immich).
