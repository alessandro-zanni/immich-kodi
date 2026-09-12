"""Generate resources/icon.png and resources/fanart.png.

The addon needs artwork and this machine has no image tooling, so the art is
code: a tiny PNG writer plus a couple of shape functions. Re-run to tweak.
"""

import math
import os
import struct
import zlib

ART = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "plugin.image.immich", "resources")


def write_png(path, width, height, rows):
    raw = b"".join(b"\x00" + bytes(row) for row in rows)

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    open(path, "wb").write(png)
    print("%s  %dx%d  %.0f KB" % (path, width, height, len(png) / 1024.0))


def render(path, width, height, shader, samples=2):
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            r = g = b = 0
            for sy in range(samples):
                for sx in range(samples):
                    c = shader((x + (sx + 0.5) / samples) / width,
                               (y + (sy + 0.5) / samples) / height)
                    r, g, b = r + c[0], g + c[1], b + c[2]
            n = samples * samples
            row += bytes((int(r / n), int(g / n), int(b / n)))
        rows.append(row)
    write_png(path, width, height, rows)


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


NIGHT = (15, 15, 26)
INDIGO = (49, 46, 129)
VIOLET = (99, 102, 241)
CYAN = (34, 211, 238)
SUN = (251, 191, 36)


def icon(u, v):
    # Rounded-square card, so the icon keeps its shape on skins that don't crop.
    pad, radius = 0.05, 0.16
    dx = max(pad - u, u - (1 - pad), 0.0)
    dy = max(pad - v, v - (1 - pad), 0.0)
    inset = min(min(u, 1 - u), min(v, 1 - v)) - pad
    if dx or dy or (inset < 0):
        return NIGHT
    corner = radius - min(min(u, 1 - u), min(v, 1 - v))
    if corner > 0:
        cx = radius if u < 0.5 else 1 - radius
        cy = radius if v < 0.5 else 1 - radius
        if math.hypot(u - cx, v - cy) > radius - pad and \
           (abs(u - 0.5) > 0.5 - radius and abs(v - 0.5) > 0.5 - radius):
            return NIGHT

    if v > 0.58 + abs(u - 0.66) * 0.72:                 # near peak, in front
        return mix(CYAN, (13, 90, 120), (v - 0.55) * 1.9)
    if v > 0.42 + abs(u - 0.33) * 0.60:                 # far peak, behind
        return mix(VIOLET, (55, 48, 163), (v - 0.40) * 1.5)
    if math.hypot(u - 0.70, v - 0.28) < 0.105:          # sun
        return SUN
    return mix((38, 34, 96), (86, 78, 190), v * 1.1)    # sky


def fanart(u, v):
    base = mix(NIGHT, INDIGO, (u * 0.4 + v * 0.9))
    glow = max(0.0, 1.0 - math.hypot((u - 0.22) * 1.4, (v - 0.18) * 2.2) * 1.6)
    return mix(base, VIOLET, glow * 0.55)


if __name__ == "__main__":
    render(os.path.join(ART, "icon.png"), 512, 512, icon, samples=3)
    render(os.path.join(ART, "fanart.png"), 1280, 720, fanart, samples=1)
