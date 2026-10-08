"""Talks to the mouse through rivalcfg."""

import logging
import os
import threading
from contextlib import contextmanager, suppress

import hid
import rivalcfg

from .errors import AppError, absent, translate
from .schema import (
    colors_are_volatile,
    control_for,
    describe_profile,
    parse_dpi,
    parse_gradient,
)

log = logging.getLogger(__name__)


def on_bus(mouse):
    """Still plugged in? Most profiles report no battery, so nothing else proves it."""
    if "RIVALCFG_DRY" in os.environ:
        return True
    try:
        return bool(hid.enumerate(mouse.vendor_id, mouse.product_id))
    except Exception:
        return True


class Device:
    """Owns the HID handle, and drops it on any failure so the next call re-detects."""

    def __init__(self):
        self._lock = threading.RLock()
        self._mouse = None

    def _connect(self):
        if self._mouse is None:
            try:
                mouse = rivalcfg.get_first_mouse()
            except Exception as error:
                raise translate(error) from error
            if mouse is None:
                raise absent()
            log.info("connected to %s", mouse.name)
            self._mouse = mouse
        return self._mouse

    def forget(self):
        """Drop the handle so the next call re-detects."""
        mouse, self._mouse = self._mouse, None
        if mouse is None:
            return
        log.debug("dropping the handle on %s", mouse.name)
        with suppress(Exception):
            mouse.close()

    @contextmanager
    def _session(self):
        with self._lock:
            try:
                yield self._connect()
            except (AppError, ValueError, TypeError, KeyError):
                # bad input, so the value is wrong but the connection is fine
                raise
            except Exception as error:
                self.forget()
                raise translate(error) from error

    def status(self):
        """Connection, identity and battery. Never raises, the UI polls it."""
        with self._lock:
            try:
                mouse = self._connect()
                battery = mouse.battery
                if battery["level"] is None and not on_bus(mouse):
                    self.forget()
                    raise absent()
            except AppError as error:
                return dict(error.as_dict(), connected=False)
            except Exception as error:
                self.forget()
                return dict(translate(error).as_dict(), connected=False)
            return {
                "connected": True,
                "name": mouse.name,
                "id": "%04x:%04x" % (mouse.vendor_id, mouse.product_id),
                "firmware": self._firmware(mouse),
                "battery": battery,
            }

    @staticmethod
    def _firmware(mouse):
        # not every profile has it and a sleeping mouse won't answer, so it's garnish
        try:
            return mouse.firmware_version
        except Exception:
            return None

    def schema(self):
        """The settings this mouse supports, with whatever is currently set."""
        with self._session() as mouse:
            return {
                "fields": describe_profile(mouse.mouse_profile),
                "values": self._values(mouse),
                "volatile": colors_are_volatile(mouse.mouse_profile),
            }

    @staticmethod
    def _values(mouse):
        values = {}
        for name, info in mouse.mouse_profile["settings"].items():
            control = control_for(info.get("value_type"))
            if control == "action":
                continue
            try:
                stored = mouse.mouse_settings.get(name)
            except KeyError:
                continue
            if control == "dpi":
                stored = parse_dpi(stored)
            elif control == "gradient":
                stored = parse_gradient(stored)
            values[name] = stored
        return values

    def apply(self, name, value):
        """Write one setting to the mouse."""
        with self._session() as mouse:
            settings = mouse.mouse_profile["settings"]
            if name not in settings:
                raise ValueError("This mouse has no %r setting." % name)

            log.debug("set %s to %r", name, value)
            control = control_for(settings[name].get("value_type"))
            write = getattr(mouse, "set_%s" % name)
            if control == "action":
                write()
            elif control == "dpi" and isinstance(value, dict):
                # DPI presets carry the active stage alongside the values
                write(value.get("presets") or [], value.get("active") or 0)
            else:
                write(value)

            mouse.mouse_settings.save()
            return self._values(mouse)

    def persist(self):
        """Commit the current config to the mouse's onboard memory."""
        with self._session() as mouse:
            log.info("saving to onboard memory")
            mouse.save()

    def reset(self):
        """Put every setting back to its factory default."""
        with self._session() as mouse:
            log.info("resetting to factory defaults")
            mouse.reset_settings()
            mouse.mouse_settings.save()
            return self._values(mouse)
