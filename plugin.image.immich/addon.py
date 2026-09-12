"""Entry point: route plugin:// calls to a view, and turn failures into dialogs."""

import os
import sys
from urllib.parse import parse_qsl

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "lib"))

import xbmc
import xbmcgui
import xbmcplugin

import views
from immich import ImmichError


def main():
    params = dict(parse_qsl(sys.argv[2].lstrip("?")))
    action = params.pop("action", "root")

    if not views.ADDON.getSetting("server_url"):
        views.ADDON.openSettings()
        return

    views.set_locale()
    view = views.ACTIONS.get(action)
    if view is None:
        raise ValueError("unknown action: %s" % action)
    view(**params)


def run():
    try:
        main()
    except ImmichError as err:
        if err.status in (401, 403):
            title, message = views.L(30062), views.L(30063)
        elif err.status == 0:
            title, message = views.L(30060), views.L(30061)
        else:
            title, message = views.L(30064), err.message
        _fail(title, message, err)
    except Exception as err:  # never show a raw Python traceback on a TV
        _fail(views.L(30064), str(err), err)


def _fail(title, message, err):
    xbmc.log("plugin.image.immich: %r" % (err,), xbmc.LOGERROR)
    xbmcgui.Dialog().ok(title, message)
    xbmcplugin.endOfDirectory(views.HANDLE, succeeded=False)


if __name__ == "__main__":
    run()
