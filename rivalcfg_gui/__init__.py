"""Web GUI for configuring SteelSeries mice, built on rivalcfg."""

try:
    from ._version import __version__
except ImportError:  # a checkout that was never installed
    __version__ = "0.0.0"
