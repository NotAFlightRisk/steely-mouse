"""Turns library and OS failures into something a person can act on."""

import os
import shlex
import sys
from glob import glob

VENDOR = 0x1038
NIXOS_FIX = "services.udev.packages = [ pkgs.rivalcfg ];"


class AppError(Exception):
    """A failure we can explain, carrying a hint and often a command to run."""

    def __init__(self, message, hint="", fix="", kind="unknown", status=503):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.fix = fix
        self.kind = kind
        self.status = status

    def as_dict(self):
        fields = {"error": self.message, "hint": self.hint, "fix": self.fix}
        return dict({k: v for k, v in fields.items() if v}, kind=self.kind)

    def log_line(self):
        return " ".join(filter(None, [self.message, self.hint, self.fix]))


def absent():
    return AppError(
        "No supported SteelSeries mouse found.",
        hint="Plug one in, or give it a click if it has gone to sleep.",
        kind="absent",
    )


def usb_nodes():
    """Bus nodes for every plugged SteelSeries device."""
    for entry in sorted(glob("/sys/bus/usb/devices/*")):
        try:
            with open(os.path.join(entry, "idVendor")) as handle:
                if int(handle.read(), 16) != VENDOR:
                    continue
            numbers = [_read_int(entry, name) for name in ("busnum", "devnum")]
        except (OSError, ValueError):
            continue
        yield "/dev/bus/usb/%03d/%03d" % tuple(numbers)


def _read_int(entry, name):
    with open(os.path.join(entry, name)) as handle:
        return int(handle.read())


def device_nodes():
    """What hidapi will open: /dev/hidraw* on the hidraw backend, bus nodes on libusb."""
    try:
        import hid

        paths = [entry["path"].decode("utf-8", "replace") for entry in hid.enumerate(VENDOR, 0)]
    except Exception:
        return []
    hidraw = [path for path in paths if path.startswith("/dev/")]
    return hidraw or list(usb_nodes())


def locked_node():
    """First node hidapi wants to open that this user isn't allowed to."""
    for node in device_nodes():
        if not os.access(node, os.R_OK | os.W_OK):
            return node
    return None


def udev_fix():
    """Our own --update-udev, spelled out in full so sudo can find it."""
    frozen = getattr(sys, "frozen", False)
    command = [sys.executable] if frozen else [sys.executable, "-m", "rivalcfg_gui"]
    return shlex.join(["sudo", *command, "--update-udev"])


def udev_advice():
    """How to install the rules here. NixOS keeps /etc/udev/rules.d read only."""
    if os.path.exists("/etc/NIXOS"):
        return NIXOS_FIX, "Add this to your NixOS config, then rebuild and replug."
    if sys.platform.startswith("linux"):
        return udev_fix(), "Run this once, then unplug and replug the mouse."
    return "", ""


def unopenable():
    fix, advice = udev_advice()
    node = locked_node()
    if node:
        message = "Your mouse is plugged in, but this user isn't allowed to open it."
        cause = "%s belongs to root until the udev rules are installed." % node
    else:
        message = "Found your mouse, but opening it failed."
        cause = "Another program may be holding it, or the permissions are wrong."
    return AppError(
        message, hint=" ".join(filter(None, [cause, advice])), fix=fix, kind="permission"
    )


def translate(error):
    """Best guess at what a rivalcfg, hidapi or OS failure actually means."""
    if isinstance(error, AppError):
        return error
    text = str(error).strip() or type(error).__name__
    if type(error).__name__ == "DeviceNotFound":
        return AppError(
            "Your mouse is there, but not on the endpoint rivalcfg expects.",
            hint="Wired and wireless count as different devices, so try the other one.",
            kind="absent",
        )
    if isinstance(error, OSError) and "open" in text.lower():
        return unopenable()
    if isinstance(error, OSError):
        return AppError(
            "Lost contact with the mouse.",
            hint="It has most likely gone to sleep, or swapped between wired and wireless.",
            kind="unreachable",
        )
    return AppError(text, kind="unknown")
