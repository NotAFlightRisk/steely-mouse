# rivalcfg-gui

A browser UI for configuring SteelSeries mice, sitting on top of
[rivalcfg](https://github.com/flozz/rivalcfg).

It reads whatever settings your mouse actually reports and builds the interface from
that, so it works with every device rivalcfg supports rather than just one. DPI stages,
polling rate, RGB zones, button mapping, sleep and dim timers, battery level.

## Getting Started

There are several options for running...

On Linux, whichever you pick, the mouse needs udev rules installed and your user in the
`input` group. Without them the device nodes are root only and nothing can be opened. The
NixOS module does both; everywhere else it's `sudo rivalcfg --update-udev`, once. macOS and
Windows need no setup.

### Download

Grab the binary for your system from the [latest release](https://github.com/Lissy93/rivalcfg-gui/releases/latest),
make it executable and run it.

```bash
chmod +x rivalcfg-gui-1.0.0-linux-x86_64
./rivalcfg-gui-1.0.0-linux-x86_64
```

> Self-contained, with Python and the device profiles inside, so there is nothing to
> install. Built for Linux and macOS on both Intel and ARM, and for Windows on x86_64. Each
> release also carries `SHA256SUMS` and a build provenance attestation, if you want to check
> what you downloaded.

### Nix

```bash
nix run github:lissy93/rivalcfg-gui
```

> Runs it without installing anything. You still need the udev rules from somewhere, so
> either use the module below or add `services.udev.packages = [ pkgs.rivalcfg ];` yourself.

### NixOS

```nix
inputs.rivalcfg-gui.url = "github:lissy93/rivalcfg-gui";

imports = [ inputs.rivalcfg-gui.nixosModules.default ];
programs.rivalcfg-gui.enable = true;
users.users.<your-username>.extraGroups = [ "input" ];
```

> Installs the app and the udev rules together. Rebuild, then log out and back in for the
> group change to apply.

Don't want rivalcfg in your closure at all? Write the rules yourself. `1038` is SteelSeries,
so these two lines cover every mouse it makes. Both subsystems matter, because which one
hidapi opens depends on whether it was built against hidraw or libusb.

```nix
services.udev.extraRules = ''
  SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1038", MODE="0660", GROUP="input"
  SUBSYSTEM=="usb", ATTRS{idVendor}=="1038", MODE="0660", GROUP="input"
'';
users.users.<your-username>.extraGroups = [ "input" ];
```

> `sudo rivalcfg --update-udev` is the answer on most distros, but not here. NixOS symlinks
> `/etc/udev/rules.d` into the store, so there's nothing for it to write to.

### Pip

```bash
pip install rivalcfg-gui
sudo rivalcfg --update-udev
rivalcfg-gui
```

> Works with `pipx install rivalcfg-gui` or `uv tool install rivalcfg-gui` too, which keep
> it out of your system Python.

### Docker

```bash
docker run --rm -p 8777:8777 --device /dev/hidraw0 ghcr.io/lissy93/rivalcfg-gui
```

> Then open [localhost:8777](http://localhost:8777). You have to pass the right hidraw node
> and the number shifts between reboots, so run `ls -l /dev/hidraw*` first. There's a
> `docker-compose.yml` in the repo if you'd rather not retype that every time.

The image also carries the udev rules, so you can install them without putting rivalcfg on
the host:

```bash
docker run --rm --entrypoint cat ghcr.io/lissy93/rivalcfg-gui \
  /udev/99-steelseries-rival.rules | sudo tee /etc/udev/rules.d/99-steelseries-rival.rules
```

### Build from Source

```bash
git clone git@github.com:Lissy93/rivalcfg-gui.git && \
cd rivalcfg-gui && \
pip install . && \
rivalcfg-gui
```

### No Mouse to Hand

```bash
rivalcfg-gui --demo
```

> Runs against a fake device, writing nothing to hardware. Useful for hacking on the UI, or
> just for a look before you commit. Pass a different id, like `--demo 1038:1702`, to see
> what another mouse would look like.

<details>

<summary><h4>Not sure which method to choose?</h4></summary>

- The download is the least fuss if you just want to use it. No Python, no package manager
- On NixOS, use the module. It's the only one that sorts out permissions for you
- `pipx` or `uv` is the tidiest option everywhere else, since it isolates the install
- Plain `pip` is fine if you don't mind it landing in your user site-packages
- Docker works, but passing USB devices into a container is more hassle than it saves here
- Build from source if you're changing the code, or your platform has no wheel for `hidapi`

</details>

---

## What You Get

Settings apply the moment you change them. **Save to mouse** writes the current config to
onboard memory so it survives a reboot. Some mice keep only part of that onboard: the
wireless Aerox models, for instance, remember the default lighting mode but not the colours,
so the colours come back after a power cycle. That is a firmware limit, not something the
GUI can work around.

Many wireless mice change USB product id when you plug the cable in, and drop off the bus
entirely when they sleep. The app polls for this and reconnects on its own, so a sleeping
mouse reads as disconnected rather than as a crash.

Effects like the rainbow are one-shot commands in the hardware rather than toggles, so
there is a **Restore colours** button next to them that writes your zone colours back.

---

## Configuration

Flags win, then the environment, then these defaults.

| Flag | Environment | Default | What it does |
|---|---|---|---|
| `--host` | `RIVALCFG_GUI_HOST` | `127.0.0.1` | Address to bind |
| `--port` | `RIVALCFG_GUI_PORT` | `8777` | Port to listen on |
| `--log-level` | `RIVALCFG_GUI_LOG_LEVEL` | `info` | `debug` adds request logs and tracebacks |
| `--no-browser` | | off | Don't open a browser on start |
| `--demo [VID:PID]` | | off | Fake device, touches no hardware |

---

## Security

The API can rewrite your mouse's config, so a random web page should not be able to reach
it. Requests are only served if their `Host` is loopback, which also stops DNS rebinding.
Every write needs a token that only the served page has, and cross origin requests are
rejected. That holds even in Docker, where the container binds `0.0.0.0` but anything
arriving from the LAN still gets a 403.

---

## Development

```sh
nix develop
python -m rivalcfg_gui --demo
pytest -q
```

The interesting part is `schema.py`. rivalcfg's device profiles are plain dicts that carry
their own labels, value types, ranges and defaults, so the frontend renders controls from
that description instead of hardcoding anything per device. Adding support for a new mouse
usually means adding nothing at all.

Settings whose syntax is richer than a widget can express (RGB gradients, per axis DPI) fall
back to a text box that takes the same string the rivalcfg CLI takes.

---

## License

> _**[Lissy93/rivalcfg-gui](https://github.com/Lissy93/rivalcfg-gui)** is licensed under [MIT](https://github.com/Lissy93/rivalcfg-gui/blob/HEAD/LICENSE) © [Alicia Sykes](https://aliciasykes.com) 2026._<br>
> <sup align="right">For information, see <a href="https://tldrlegal.com/license/mit-license">TLDR Legal > MIT</a></sup>
