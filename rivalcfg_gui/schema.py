"""Turns a rivalcfg device profile into something the frontend can render."""

from rivalcfg.color_helpers import is_color, parse_color_gradient_string, parse_color_string
from rivalcfg.handlers.buttons import layout_multimedia, layout_qwerty
from rivalcfg.handlers.rgbgradient import is_rgbgradient
from rivalcfg.helpers import parse_param_string

# rivalcfg value_type -> the control we draw for it.
# Anything missing falls back to a text box that takes the same syntax the CLI
# does, so an odd setting on a mouse we can't test degrades instead of vanishing.
CONTROLS = {
    "choice": "select",
    "range": "slider",
    "range_choice": "slider",
    "rgbcolor": "color",
    "reactive_rgbcolor": "color",
    "rgbgradient": "gradient",
    "rgbgradientv2": "gradient",
    "multidpi_range_choice": "dpi",
    "multidpi_range": "dpi",
    "buttons": "buttons",
    "none": "action",
}

# Settings whose syntax is too rich for a widget, so we show the CLI hint.
HINTS = {
    "multidpi_range_choice_xy": "400, 800, 1200 or 800x600, 1200x900 for per-axis DPI",
}

# Where rivalcfg's own wording leaves the effect genuinely easy to misread.
NOTES = {
    "default_lighting": (
        "Colours aren't stored in the mouse, so this only picks blank or rainbow for waking up."
    ),
}

# rivalcfg caps a gradient at 14 stops, and durations are milliseconds per cycle.
MAX_STOPS = 14
DURATION = (100, 10000, 100)
GRADIENT_PARSERS = {"rgbgradient": {"duration": int, "colors": parse_color_gradient_string}}

GROUPS = (
    ("Buttons", ("button",)),
    ("Lighting", ("color", "light", "rainbow", "gradient", "effect", "led")),
    ("Performance", ("sensitivity", "dpi", "polling", "angle", "accel", "lift")),
    ("Power", ("timer", "sleep", "dim", "power", "battery")),
)


def parse_dpi(value, active=0):
    """DPI settings round-trip as a list of stages plus the active one."""
    if isinstance(value, dict):
        presets, active = value.get("presets") or [], value.get("active") or 0
    else:
        # two args went in as a tuple, so it can come back as (presets, active)
        pair = isinstance(value, (list, tuple)) and len(value) == 2
        if pair and isinstance(value[0], (list, tuple, str)):
            value, active = value
        if isinstance(value, str):
            presets = [part for part in value.replace(" ", "").split(",") if part]
        elif isinstance(value, (int, float)):
            presets = [value]
        else:
            presets = list(value or [])
    return {"presets": [int(dpi) for dpi in presets], "active": int(active or 0)}


def control_for(value_type):
    """The one place a value_type becomes a widget. Everything else asks here."""
    return CONTROLS.get(value_type or "none", "text")


def to_hex(colour):
    """Anything rivalcfg calls a colour, as #rrggbb for an <input type=color>."""
    if isinstance(colour, (list, tuple)) and len(colour) >= 3:
        return "#%02x%02x%02x" % tuple(colour[:3])
    if isinstance(colour, str) and is_color(colour):
        return to_hex(parse_color_string(colour))
    return "#ffffff"


def parse_gradient(value):
    """These settings take a plain colour or a gradient, so say which we've got."""
    duration, stops = DURATION[0] * 10, []
    if isinstance(value, dict) and "colors" in value:
        stops, duration = value.get("colors") or [], value.get("duration", duration)
    elif isinstance(value, str) and is_rgbgradient(value)[0]:
        parsed = parse_param_string(value, value_parsers=GRADIENT_PARSERS)["rgbgradient"]
        stops, duration = parsed.get("colors") or [], parsed.get("duration", duration)
    else:
        return {"mode": "solid", "color": to_hex(value), "duration": duration, "stops": []}
    return {
        "mode": "gradient",
        "color": to_hex(stops[0]["color"]) if stops else "#ffffff",
        "duration": int(duration),
        "stops": [{"pos": int(s["pos"]), "color": to_hex(s["color"])} for s in stops],
    }


def group_for(name):
    """Bucket a setting into a section. Profiles carry no grouping, so we guess."""
    lowered = name.lower()
    for group, keywords in GROUPS:
        if any(word in lowered for word in keywords):
            return group
    return "Other"


def _buttons(info):
    """Describe a button-mapping setting plus everything it can be mapped to."""
    buttons = [
        {"key": key, "default": meta.get("default", "default")}
        for key, meta in info.get("buttons", {}).items()
    ]
    keys = [button["key"].lower() for button in buttons]

    special = ["default", "disabled", "dpi"]
    if any(key.startswith("scroll") for key in keys):
        special += ["scrollup", "scrolldown"]

    return {
        "buttons": buttons,
        "actions": {
            "Special": special,
            "Mouse": sorted(key for key in keys if key.startswith("button")),
            "Multimedia": sorted(layout_multimedia.layout),
            "Keyboard": sorted(layout_qwerty.layout),
        },
    }


def describe(name, info):
    """Build a JSON-safe descriptor for one setting."""
    value_type = info.get("value_type") or "none"
    control = control_for(value_type)
    label = info.get("label") or name.replace("_", " ")
    low, high, step = ((info.get("input_range") or [0, 100]) + [1])[:3]

    field = {
        "name": name,
        "label": label[:1].upper() + label[1:],
        "description": ". ".join(filter(None, [info.get("description", ""), NOTES.get(name)])),
        "control": control,
        "group": group_for(name),
        "default": info.get("default"),
        # reactive colours accept "off", plain colour settings don't
        "nullable": value_type == "reactive_rgbcolor",
    }

    if control == "select":
        # Choice keys can be ints (polling rates) or strings (lighting modes), and
        # JSON object keys would stringify them, so keep a list to preserve types.
        field["options"] = list(info.get("choices", {}))
    elif control == "slider":
        field.update(min=low, max=high, step=step)
    elif control == "dpi":
        field.update(
            min=low,
            max=high,
            step=step,
            max_count=info.get("max_preset_count", 5),
            default=parse_dpi(info.get("default")),
        )
    elif control == "gradient":
        low, high, step = DURATION
        field.update(min=low, max=high, step=step, max_stops=MAX_STOPS)
        field["default"] = parse_gradient(info.get("default"))
    elif control == "buttons":
        field.update(_buttons(info))
    elif control == "text":
        field["hint"] = HINTS.get(value_type, "")

    return field


def colors_are_volatile(profile):
    """These mice only store a wake-up effect, so the zone colours go when they sleep."""
    return "default_lighting" in profile.get("settings", {})


def describe_profile(profile):
    """Describe every setting on a device, in the order the profile lists them."""
    return [describe(name, info) for name, info in profile.get("settings", {}).items()]
