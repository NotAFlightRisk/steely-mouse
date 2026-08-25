"""Command line entry point."""

import argparse
import errno
import logging
import os
import threading
import webbrowser

from rivalcfg_gui import __version__, logs

DESCRIPTION = "Configure a SteelSeries mouse from your browser."
DEMO_DEVICE = "1038:1838"
log = logging.getLogger("rivalcfg_gui")


def setting(name, fallback):
    """Flags win, then RIVALCFG_GUI_* in the environment, then the built-in default."""
    return os.environ.get("RIVALCFG_GUI_" + name, fallback)


def parse_args(argv=None):
    level = setting("LOG_LEVEL", "info").lower()
    parser = argparse.ArgumentParser(prog="rivalcfg-gui", description=DESCRIPTION)
    parser.add_argument(
        "--host",
        default=setting("HOST", "127.0.0.1"),
        help="address to bind (only loopback requests are served, default: %(default)s)",
    )
    parser.add_argument(
        "--port", type=int, default=setting("PORT", "8777"), help="default: %(default)s"
    )
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser on start")
    parser.add_argument(
        "--demo",
        nargs="?",
        const=DEMO_DEVICE,
        metavar="VID:PID",
        help="run against a fake device instead of hardware (default: %(const)s)",
    )
    parser.add_argument(
        "--log-level",
        choices=logs.LEVELS,
        default=level if level in logs.LEVELS else "info",
        help="default: %(default)s",
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser.parse_args(argv)


def report(state):
    """Say what went wrong at startup, so a broken setup shows in the terminal."""
    if state.get("connected"):
        return
    log.warning("%s", state.get("error", "No mouse found."))
    if state.get("hint"):
        log.info("%s", state["hint"])
    if state.get("fix"):
        log.info("fix it with:  %s", state["fix"])


def serve(args):
    from werkzeug.serving import run_simple

    from rivalcfg_gui.device import Device
    from rivalcfg_gui.server import create_app

    device = Device()
    report(device.status())
    try:
        run_simple(args.host, args.port, create_app(device), threaded=True)
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            log.error("port %d is taken, try --port %d", args.port, args.port + 1)
        else:
            log.error("can't bind %s:%d (%s)", args.host, args.port, error.strerror)
        return 1
    return 0


def main(argv=None):
    args = parse_args(argv)
    if args.demo:
        os.environ["RIVALCFG_DRY"] = "1"
        os.environ["RIVALCFG_PROFILE"] = args.demo

    logs.configure(args.log_level)
    url = "http://localhost:%d/" % args.port
    logs.banner("rivalcfg-gui", __version__, url)
    if args.demo:
        log.info("demo mode on %s, no mouse will be touched", args.demo)

    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    return serve(args)


if __name__ == "__main__":
    raise SystemExit(main())
