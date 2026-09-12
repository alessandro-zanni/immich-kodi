"""Generate resources/fanart.png.

No image tooling on this machine, so the fanart is code: a tiny PNG writer plus
a shader. The icon is not generated - it is the official Immich logomark,
resized from immich-app/immich design/ with:

    sips -z 512 512 immich-logo-w-bg-android.png --out resources/icon.png
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


def fanart(u, v):
    base = mix(NIGHT, INDIGO, (u * 0.4 + v * 0.9))
    glow = max(0.0, 1.0 - math.hypot((u - 0.22) * 1.4, (v - 0.18) * 2.2) * 1.6)
    return mix(base, VIOLET, glow * 0.55)


if __name__ == "__main__":
    render(os.path.join(ART, "fanart.png"), 1280, 720, fanart, samples=1)
