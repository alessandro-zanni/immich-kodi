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
<addon id="{id}" name="Immich Kodi repository" version="{version}" provider-name="alessandro-zanni">
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

INDEX = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Immich for Kodi</title>
<style>
  :root {{ color-scheme: light dark; --fg: #16161a; --dim: #5b5b66; --bg: #fbfbfd;
           --card: #fff; --line: #e4e4ec; --accent: #4f46e5; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --fg: #ececf1; --dim: #a0a0b0; --bg: #0f0f14; --card: #17171f;
             --line: #2a2a36; --accent: #8b87f5; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 48px 20px; background: var(--bg); color: var(--fg);
         font: 16px/1.6 system-ui, -apple-system, Segoe UI, sans-serif; }}
  main {{ max-width: 46rem; margin: 0 auto; }}
  header {{ display: flex; gap: 18px; align-items: center; margin-bottom: 8px; }}
  header img {{ width: 72px; height: 72px; border-radius: 16px; }}
  h1 {{ font-size: 1.9rem; margin: 0; letter-spacing: -0.02em; }}
  p.lead {{ color: var(--dim); margin: 4px 0 32px; }}
  ol {{ padding-left: 1.2em; }}
  li {{ margin: 10px 0; }}
  code {{ background: var(--card); border: 1px solid var(--line); border-radius: 6px;
         padding: 2px 6px; font-size: 0.9em; word-break: break-all; }}
  a {{ color: var(--accent); }}
  .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px;
          padding: 20px 24px; margin: 24px 0; }}
  footer {{ color: var(--dim); font-size: 0.9rem; border-top: 1px solid var(--line);
           padding-top: 20px; margin-top: 40px; }}
</style>
<main>
  <header>
    <img src="{addon}/icon.png" alt="">
    <div>
      <h1>Immich for Kodi</h1>
      <p class="lead">Browse and play your Immich photos and videos. Version {version}.</p>
    </div>
  </header>

  <div class="card">
    <strong>Install the repository</strong> to get updates automatically:
    <ol>
      <li>Download <a href="{repo}/{repo_zip}">{repo_zip}</a></li>
      <li>Kodi &rarr; Add-ons &rarr; <em>Install from zip file</em> &rarr; pick that file</li>
      <li>Add-ons &rarr; <em>Install from repository</em> &rarr; Immich Kodi &rarr; Immich</li>
    </ol>
    Or install <a href="{addon}/{addon_zip}">{addon_zip}</a> directly for a one-off install.
  </div>

  <p>Then open the addon settings and enter your server URL and either an API key
  or your Immich email and password. Requires Kodi 21 (Omega) or newer.</p>

  <footer>
    <a href="{source}">Source code</a> &middot; GPL-3.0 &middot;
    not affiliated with the Immich project.<br>
    Repository URL for Kodi: <code>{base}</code>
  </footer>
</main>
</html>
"""


def default_base_url():
    try:
        remote = subprocess.check_output(["git", "remote", "get-url", "origin"],
                                         cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    # Host may be an SSH alias from ~/.ssh/config, e.g. github.com-personal:user/repo.
    m = re.search(r"github\.com[^:/]*[:/]([^/]+)/([^/.]+)", remote)
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
    # Kodi only ever fetches addons.xml and the zips, but people open the bare URL.
    root = ElementTree.parse(os.path.join(addon_dir, "addon.xml")).getroot()
    source = root.find("./extension/source")
    open(os.path.join(DOCS, "index.html"), "w").write(INDEX.format(
        version=version, base=base, addon=ADDON, repo=REPO_ID,
        addon_zip="%s-%s.zip" % (ADDON, version),
        repo_zip="%s-%s.zip" % (REPO_ID, REPO_VERSION),
        source=source.text if source is not None else base))

    print("%s %s -> docs/  (repo base: %s)" % (ADDON, version, base))


if __name__ == "__main__":
    main()
