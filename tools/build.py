"""Build the installable zip and the Kodi repository served from docs/.

    python3 tools/build.py [--base-url https://user.github.io/immich-kodi]

Produces:
    docs/addons.xml, docs/addons.xml.md5
    docs/plugin.image.immich/plugin.image.immich-<version>.zip (+ icon, fanart)
    docs/repository.immich/repository.immich-<version>.zip
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import zipfile
from xml.etree import ElementTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
ADDON = "plugin.image.immich"
REPO_ID = "repository.immich"
REPO_VERSION = "1.0.0"
SKIP = re.compile(r"(^\.|__pycache__|\.pyc$|\.DS_Store)")

REPO_ADDON = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addon id="{id}" name="Immich Kodi repository" version="{version}" provider-name="alessandro">
    <extension point="xbmc.addon.repository" name="Immich Kodi">
        <dir>
            <info compressed="false">{base}/addons.xml</info>
            <checksum>{base}/addons.xml.md5</checksum>
            <datadir zip="true">{base}</datadir>
        </dir>
    </extension>
    <extension point="xbmc.addon.metadata">
        <summary lang="en_gb">Install and update the Immich addon for Kodi</summary>
        <description lang="en_gb">Repository for the unofficial Immich addon.</description>
        <platform>all</platform>
        <license>GPL-3.0-only</license>
    </extension>
</addon>
"""


def default_base_url():
    try:
        remote = subprocess.check_output(["git", "remote", "get-url", "origin"],
                                         cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", remote)
    return "https://%s.github.io/%s" % (m.group(1), m.group(2)) if m else None


def version_of(addon_xml):
    return ElementTree.parse(addon_xml).getroot().get("version")


def zip_dir(source, addon_id, version, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, "%s-%s.zip" % (addon_id, version))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for base, dirs, files in os.walk(source):
            dirs[:] = [d for d in dirs if not SKIP.search(d)]
            for name in files:
                if SKIP.search(name):
                    continue
                path = os.path.join(base, name)
                zf.write(path, os.path.join(addon_id, os.path.relpath(path, source)))
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=default_base_url())
    args = parser.parse_args()
    if not args.base_url:
        parser.error("no git origin found, pass --base-url")
    base = args.base_url.rstrip("/")

    shutil.rmtree(DOCS, ignore_errors=True)
    os.makedirs(DOCS)

    addon_dir = os.path.join(ROOT, ADDON)
    version = version_of(os.path.join(addon_dir, "addon.xml"))
    out = os.path.join(DOCS, ADDON)
    zip_dir(addon_dir, ADDON, version, out)
    for asset in ("addon.xml", "resources/icon.png", "resources/fanart.png"):
        shutil.copy(os.path.join(addon_dir, asset),
                    os.path.join(out, os.path.basename(asset)))

    repo_dir = os.path.join(DOCS, "_repo_src")
    os.makedirs(repo_dir)
    with open(os.path.join(repo_dir, "addon.xml"), "w") as fh:
        fh.write(REPO_ADDON.format(id=REPO_ID, version=REPO_VERSION, base=base))
    shutil.copy(os.path.join(addon_dir, "resources", "icon.png"),
                os.path.join(repo_dir, "icon.png"))
    zip_dir(repo_dir, REPO_ID, REPO_VERSION, os.path.join(DOCS, REPO_ID))
    shutil.copy(os.path.join(repo_dir, "addon.xml"), os.path.join(DOCS, REPO_ID, "addon.xml"))

    addons = ElementTree.Element("addons")
    for xml in (os.path.join(addon_dir, "addon.xml"), os.path.join(repo_dir, "addon.xml")):
        addons.append(ElementTree.parse(xml).getroot())
    body = ElementTree.tostring(addons, encoding="unicode")
    body = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + body
    open(os.path.join(DOCS, "addons.xml"), "w").write(body)
    open(os.path.join(DOCS, "addons.xml.md5"), "w").write(
        hashlib.md5(body.encode("utf-8")).hexdigest())
    shutil.rmtree(repo_dir)
    open(os.path.join(DOCS, ".nojekyll"), "w").close()

    print("%s %s -> docs/  (repo base: %s)" % (ADDON, version, base))


if __name__ == "__main__":
    main()
