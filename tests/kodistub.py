"""Minimal fakes for the xbmc* modules, so views.py can run outside Kodi.

Used by tests/test_immich.py and by tools/smoke.py.
"""

import os
import re
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_DIR = os.path.join(ROOT, "plugin.image.immich")
PO = os.path.join(ADDON_DIR, "resources", "language", "resource.language.en_gb", "strings.po")

SETTINGS = {}
CAPTURED = []          # every (url, ListItem, is_folder) handed to addDirectoryItems
CONTENT = []           # every setContent() value
INPUT = [""]           # queued Dialog().input() answers
DIALOGS = []           # every Dialog().ok() shown


def _strings():
    out, sid = {}, None
    for line in open(PO, encoding="utf-8"):
        m = re.match(r'msgctxt "#(\d+)"', line)
        if m:
            sid = int(m.group(1))
        m = re.match(r'msgid "(.*)"', line)
        if m and sid:
            out[sid] = m.group(1)
    return out


class ListItem:
    def __init__(self, label=""):
        self.label, self.art, self.props, self.date = label, {}, {}, None
        self.video = types.SimpleNamespace(
            setTitle=lambda v: None, setDuration=lambda v: None)

    def getLabel(self):
        return self.label

    def setArt(self, art):
        self.art.update(art)

    def setProperty(self, key, value):
        self.props[key] = value

    def setDateTime(self, value):
        self.date = value

    def getVideoInfoTag(self):
        return self.video


class Dialog:
    def input(self, *_a, **_k):
        return INPUT.pop(0) if INPUT else ""

    def ok(self, heading, message):
        DIALOGS.append((heading, message))
        return True

    def notification(self, *a, **k):
        DIALOGS.append(a)


class Addon:
    def __init__(self, *_a):
        self.strings = _strings()

    def getSetting(self, key):
        return str(SETTINGS.get(key, ""))

    def getSettingInt(self, key):
        return int(SETTINGS.get(key, 0))

    def getSettingBool(self, key):
        return bool(SETTINGS.get(key, False))

    def setSetting(self, key, value):
        SETTINGS[key] = value

    def getLocalizedString(self, sid):
        return self.strings.get(sid, str(sid))

    def getAddonInfo(self, key):
        return ADDON_DIR if key == "path" else "plugin.image.immich"

    def openSettings(self):
        pass


def install(settings=None, argv=None):
    """Put the fake modules in sys.modules and import the addon's own modules."""
    SETTINGS.clear()
    SETTINGS.update(settings or {})
    CAPTURED.clear()
    CONTENT.clear()
    DIALOGS.clear()

    xbmc = types.ModuleType("xbmc")
    xbmc.getRegion = lambda key: {"datelong": "%A %d %B %Y", "time": "%H:%M"}.get(key, "")
    xbmc.getUserAgent = lambda: "Kodi/21.0 (stub)"
    xbmc.getInfoLabel = lambda key: "English"
    xbmc.convertLanguage = lambda lang, fmt: "en"
    xbmc.log = lambda msg, level=0: None
    xbmc.LOGERROR = 4
    xbmc.ISO_639_1 = 0
    xbmc.executebuiltin = lambda cmd: None

    xbmcgui = types.ModuleType("xbmcgui")
    xbmcgui.ListItem = ListItem
    xbmcgui.Dialog = Dialog

    xbmcaddon = types.ModuleType("xbmcaddon")
    xbmcaddon.Addon = Addon

    xbmcplugin = types.ModuleType("xbmcplugin")
    xbmcplugin.setContent = lambda handle, content: CONTENT.append(content)
    xbmcplugin.addSortMethod = lambda handle, method: None
    xbmcplugin.addDirectoryItems = lambda handle, items, n=0: CAPTURED.extend(items)
    xbmcplugin.endOfDirectory = lambda handle, succeeded=True, **k: None
    for i, name in enumerate(("SORT_METHOD_UNSORTED", "SORT_METHOD_DATE", "SORT_METHOD_LABEL")):
        setattr(xbmcplugin, name, i)

    xbmcvfs = types.ModuleType("xbmcvfs")
    xbmcvfs.translatePath = lambda p: p

    for mod in (xbmc, xbmcgui, xbmcaddon, xbmcplugin, xbmcvfs):
        sys.modules[mod.__name__] = mod

    sys.argv = argv or ["plugin://plugin.image.immich/", "1", ""]
    sys.path.insert(0, os.path.join(ADDON_DIR, "resources", "lib"))
    for name in ("views", "immich"):
        sys.modules.pop(name, None)
    import views
    return views
