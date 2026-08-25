"""Console logging that stays readable at a glance."""

import logging
import os
import sys

LEVELS = ("debug", "info", "warning", "error")
COLOURS = {
    "DEBUG": "38;5;244",
    "INFO": "36",
    "WARNING": "33",
    "ERROR": "31",
    "CRITICAL": "97;41",
}
DIM = "38;5;244"


def use_colour(stream):
    """Colour unless we're piped somewhere, or NO_COLOR asks us not to."""
    return stream.isatty() and "NO_COLOR" not in os.environ


def paint(text, colour, enabled):
    return "\033[%sm%s\033[0m" % (colour, text) if enabled else text


class Formatter(logging.Formatter):
    """Dim clock, coloured level, plain message."""

    def __init__(self, colour, tracebacks):
        super().__init__(datefmt="%H:%M:%S")
        self.colour = colour
        self.tracebacks = tracebacks

    def format(self, record):
        clock = paint(self.formatTime(record, self.datefmt), DIM, self.colour)
        name = record.levelname
        level = paint("%-8s" % name.lower(), COLOURS.get(name, "0"), self.colour)
        line = "%s %s %s" % (clock, level, record.getMessage())
        if record.exc_info and self.tracebacks:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure(level="info"):
    """Send everything to stderr through our formatter."""
    handler = logging.StreamHandler()
    handler.setFormatter(Formatter(use_colour(handler.stream), level == "debug"))
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)
    noisy = logging.DEBUG if level == "debug" else logging.WARNING
    logging.getLogger("werkzeug").setLevel(noisy)


def banner(name, version, url):
    """One line saying what's running and where."""
    colour = use_colour(sys.stdout)
    parts = (paint(name, "1", colour), paint(version, DIM, colour), paint(url, "4;36", colour))
    print("%s %s  %s" % parts, flush=True)
