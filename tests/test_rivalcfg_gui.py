"""Tests for the schema translation, the device wrapper and the HTTP guard."""

import os

import pytest

os.environ.setdefault("RIVALCFG_DRY", "1")
os.environ.setdefault("RIVALCFG_PROFILE", "1038:1838")

from rivalcfg_gui import errors, schema
from rivalcfg_gui.__main__ import parse_args
from rivalcfg_gui.device import Device
from rivalcfg_gui.errors import AppError
from rivalcfg_gui.server import create_app, hostname


# ---- schema ----------------------------------------------------------------
@pytest.mark.parametrize(
    "value, expected",
    [
        ("400, 800, 1200", {"presets": [400, 800, 1200], "active": 0}),
        ("400,800", {"presets": [400, 800], "active": 0}),
        (1600, {"presets": [1600], "active": 0}),
        ([400, 800], {"presets": [400, 800], "active": 0}),
        ([[400, 800], 1], {"presets": [400, 800], "active": 1}),
        ({"presets": [400], "active": 0}, {"presets": [400], "active": 0}),
    ],
)
def test_parse_dpi(value, expected):
    assert schema.parse_dpi(value) == expected


@pytest.mark.parametrize(
    "name, group",
    [
        ("sensitivity", "Performance"),
        ("polling_rate", "Performance"),
        ("z1_color", "Lighting"),
        ("sleep_timer", "Power"),
        ("buttons_mapping", "Buttons"),
        ("something_odd", "Other"),
    ],
)
def test_group_for(name, group):
    assert schema.group_for(name) == group


def test_unknown_value_type_falls_back_to_text():
    field = schema.describe("mystery", {"value_type": "rgbgradient", "label": "Mystery"})
    assert field["control"] == "text"
    assert field["hint"]


def test_labels_get_a_capital():
    assert schema.describe("x", {"label": "rainbow effect"})["label"] == "Rainbow effect"


def test_a_profile_without_a_range_still_describes():
    field = schema.describe("odd", {"value_type": "range", "label": "Odd"})
    assert (field["min"], field["max"], field["step"]) == (0, 100, 1)


def test_every_rivalcfg_device_describes_cleanly():
    """The UI is generated from profiles, so every supported mouse must survive it."""
    import json

    from rivalcfg import devices

    for profile in devices.PROFILES.values():
        fields = schema.describe_profile(profile)
        json.dumps(fields)
        for field in fields:
            assert field["control"] in {
                "select",
                "slider",
                "color",
                "dpi",
                "buttons",
                "action",
                "text",
            }
            if field["control"] in ("slider", "dpi"):
                assert field["min"] < field["max"]


def test_descriptor_is_json_safe():
    import json

    device = Device()
    json.dumps(device.schema())


# ---- device ----------------------------------------------------------------
@pytest.fixture
def device():
    return Device()


def test_status_reports_the_dry_run_mouse(device):
    status = device.status()
    assert status["connected"] is True
    assert status["id"] == "1038:1838"


def test_apply_round_trips(device):
    values = device.apply("polling_rate", 500)
    assert values["polling_rate"] == 500
    assert device.schema()["values"]["polling_rate"] == 500


def test_apply_dpi_keeps_the_active_stage(device):
    values = device.apply("sensitivity", {"presets": [400, 1600], "active": 1})
    assert values["sensitivity"] == {"presets": [400, 1600], "active": 1}


def test_unknown_setting_is_a_value_error(device):
    with pytest.raises(ValueError):
        device.apply("nope", 1)


def test_bad_value_does_not_drop_the_connection(device):
    device.status()
    with pytest.raises(ValueError):
        device.apply("polling_rate", 9999)
    assert device.status()["connected"] is True


def test_reset_restores_defaults(device):
    device.apply("polling_rate", 125)
    assert device.reset()["polling_rate"] == 1000


# ---- server ----------------------------------------------------------------
@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        test_client.token = app.config["TOKEN"]
        yield test_client


@pytest.mark.parametrize(
    "value, expected",
    [("127.0.0.1:8777", "127.0.0.1"), ("[::1]:8777", "::1"), ("http://localhost", "localhost")],
)
def test_hostname_handles_ipv6_and_ports(value, expected):
    assert hostname(value) == expected


def test_status_and_schema_are_readable(client):
    assert client.get("/api/status").get_json()["connected"] is True
    assert client.get("/api/schema").get_json()["fields"]


def test_post_without_a_token_is_refused(client):
    assert client.post("/api/save", json={}).status_code == 403


def test_post_with_a_bad_token_is_refused(client):
    assert client.post("/api/save", json={}, headers={"X-Token": "no"}).status_code == 403


def test_cross_origin_post_is_refused(client):
    response = client.post(
        "/api/save", json={}, headers={"X-Token": client.token, "Origin": "https://evil.test"}
    )
    assert response.status_code == 403


def test_a_rebound_host_is_refused(client):
    assert client.get("/api/status", headers={"Host": "evil.test"}).status_code == 403


def test_a_valid_write_succeeds(client):
    response = client.post(
        "/api/settings",
        json={"name": "polling_rate", "value": 250},
        headers={"X-Token": client.token},
    )
    assert response.status_code == 200
    assert response.get_json()["values"]["polling_rate"] == 250


def test_an_out_of_range_value_is_a_400(client):
    response = client.post(
        "/api/settings",
        json={"name": "polling_rate", "value": 9999},
        headers={"X-Token": client.token},
    )
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_a_missing_name_is_a_400(client):
    response = client.post("/api/settings", json={}, headers={"X-Token": client.token})
    assert response.status_code == 400


def test_security_headers_are_present(client):
    headers = client.get("/").headers
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"


def test_a_disconnected_mouse_reports_cleanly(monkeypatch):
    monkeypatch.setenv("RIVALCFG_PROFILE", "0000:0000")
    device = Device()
    status = device.status()
    assert status["connected"] is False
    assert status["kind"] == "absent"
    assert status["hint"]
    with pytest.raises(AppError):
        device.schema()


# ---- errors ----------------------------------------------------------------
def test_a_failed_open_asks_for_the_udev_rules(monkeypatch):
    monkeypatch.setattr(errors, "locked_node", lambda: "/dev/hidraw6")
    monkeypatch.setattr(os.path, "exists", lambda path: False)
    problem = errors.translate(OSError("open failed"))
    assert problem.kind == "permission"
    assert "/dev/hidraw6" in problem.hint
    assert problem.fix == errors.UDEV_FIX


def test_nixos_gets_the_config_line_not_a_command(monkeypatch):
    """rivalcfg --update-udev can't work here, /etc/udev/rules.d is read only."""
    monkeypatch.setattr(errors, "locked_node", lambda: "/dev/hidraw6")
    monkeypatch.setattr(os.path, "exists", lambda path: path == "/etc/NIXOS")
    problem = errors.translate(OSError("open failed"))
    assert problem.fix == errors.NIXOS_FIX
    assert "rebuild" in problem.hint


def test_a_dead_connection_reads_as_asleep():
    problem = errors.translate(OSError("read error"))
    assert problem.kind == "unreachable"
    assert not problem.fix


def test_an_unrecognised_error_keeps_its_own_words():
    assert errors.translate(RuntimeError("weird")).message == "weird"


def test_an_empty_error_still_says_something():
    assert errors.translate(RuntimeError()).message == "RuntimeError"


def test_usb_nodes_ignores_other_vendors(tmp_path, monkeypatch):
    logitech = tmp_path / "1-1"
    logitech.mkdir()
    (logitech / "idVendor").write_text("046d\n")
    monkeypatch.setattr(errors, "glob", lambda pattern: [str(logitech)])
    assert list(errors.usb_nodes()) == []


def test_usb_nodes_builds_the_bus_path(tmp_path, monkeypatch):
    mouse = tmp_path / "3-1.2"
    mouse.mkdir()
    for name, value in (("idVendor", "1038"), ("busnum", "3"), ("devnum", "10")):
        (mouse / name).write_text(value + "\n")
    monkeypatch.setattr(errors, "glob", lambda pattern: [str(mouse)])
    assert list(errors.usb_nodes()) == ["/dev/bus/usb/003/010"]


def test_hidraw_paths_win_when_hidapi_reports_them(monkeypatch):
    """The libusb backend hands back bus ids instead, and those need a different node."""
    monkeypatch.setattr("hid.enumerate", lambda *a: [{"path": b"/dev/hidraw6"}])
    assert errors.device_nodes() == ["/dev/hidraw6"]


def test_libusb_paths_fall_back_to_the_bus_node(monkeypatch):
    monkeypatch.setattr("hid.enumerate", lambda *a: [{"path": b"3-1.2:1.0"}])
    monkeypatch.setattr(errors, "usb_nodes", lambda: iter(["/dev/bus/usb/003/010"]))
    assert errors.device_nodes() == ["/dev/bus/usb/003/010"]


def test_the_ui_gets_a_hint_and_a_fix(client, monkeypatch):
    monkeypatch.setattr(errors, "locked_node", lambda: "/dev/hidraw6")
    monkeypatch.setattr(os.path, "exists", lambda path: False)
    monkeypatch.setattr(
        "rivalcfg.get_first_mouse", lambda: (_ for _ in ()).throw(OSError("open failed"))
    )
    body = client.get("/api/status").get_json()
    assert body["kind"] == "permission"
    assert body["fix"] == errors.UDEV_FIX
    assert body["hint"].startswith("/dev/hidraw6 belongs to root")


def test_a_crash_is_json_not_a_traceback(client, monkeypatch):
    monkeypatch.setattr(Device, "status", lambda self: 1 / 0)
    response = client.get("/api/status")
    assert response.status_code == 500
    assert response.get_json()["kind"] == "bug"


def test_an_unknown_route_is_json_too(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert "error" in response.get_json()


# ---- cli -------------------------------------------------------------------
def test_flags_beat_the_environment(monkeypatch):
    monkeypatch.setenv("RIVALCFG_GUI_PORT", "9999")
    monkeypatch.setenv("RIVALCFG_GUI_HOST", "0.0.0.0")
    assert parse_args([]).port == 9999
    assert parse_args(["--port", "1234"]).port == 1234
    assert parse_args([]).host == "0.0.0.0"


def test_a_nonsense_log_level_in_the_environment_is_ignored(monkeypatch):
    monkeypatch.setenv("RIVALCFG_GUI_LOG_LEVEL", "shouty")
    assert parse_args([]).log_level == "info"
    monkeypatch.setenv("RIVALCFG_GUI_LOG_LEVEL", "DEBUG")
    assert parse_args([]).log_level == "debug"


def test_demo_takes_an_optional_device():
    assert parse_args([]).demo is None
    assert parse_args(["--demo"]).demo == "1038:1838"
    assert parse_args(["--demo", "1038:1702"]).demo == "1038:1702"
