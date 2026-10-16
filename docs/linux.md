# Linux desktop candidate

Version `0.7.0-dev` develops support beyond the original Omarchy plugin. Keep using the published release on an existing desktop while evaluating this branch separately. No universal compatibility claim is made for this candidate.

## Architecture and targets

The Quickshell interface shares the original artwork, geometry and pointer motion across Omarchy, standalone Hyprland, wlroots compositors, Plasma and X11. GNOME uses a native Shell extension because its desktop integration differs. Its motion module is derived from the same `plugin/DockMotion.js` source.

| Desktop | Integration | Status |
| --- | --- | --- |
| Omarchy | Existing shell plugin and theme interface | Original release target; extraction needs a live regression check |
| Standalone Hyprland | Quickshell Hyprland interface | Implemented; standalone session unverified |
| Sway | Native Sway IPC, scratchpad minimization and layer shell | Headless Sway 1.12 discovery, minimize, restore and close passed; desktop QA pending |
| Other compatible wlroots desktops | Foreign toplevel management and layer shell | Experimental; requires that exact protocol |
| KDE Plasma 6 on Wayland | Quickshell panel plus temporary KWin scripts | Virtual KWin 6.7.4 discovery, minimize, restore and close passed; desktop QA pending |
| Xfce, MATE and other EWMH X11 desktops | Quickshell panel plus X11 window events | Xvfb/Openbox launch, focus, minimize, restore and close passed; other window managers pending |
| GNOME Shell 45 to 51 | Native extension | Headless GNOME 50.4 hover, menus, pinning, window actions and fullscreen hiding passed; other versions pending |
| Other Wayland compositors | Depends on their window and panel protocols | Unsupported until an adapter is tested |

GNOME version declarations identify the API target. They do not establish that every listed version has been tested. A different distribution can use the same desktop adapter, but library and package availability must also be checked. XWayland does not expose every native Wayland window and is never used as a full desktop fallback.

## Dependencies

For the Quickshell adapters, install Quickshell 0.3.1 or newer and Python 3. Quickshell must include its X11 or Wayland support and the selected compositor module. Use the [upstream installation instructions](https://quickshell.org/docs/guide/install-setup/) when the distribution package is unavailable or too old.

X11 also needs Python Xlib and PyGObject. The window service uses X11 events and does not load application artwork. Plasma needs the `dbus` and `gi` Python modules and KWin 6 with its scripting service. The GNOME extension runs inside GNOME Shell and does not need Quickshell.

Distribution package names differ. For example, Arch calls the Python dependencies `python-gobject` and `python-dbus`; Debian and Ubuntu use `python3-gi` and `python3-dbus`. Python Xlib is packaged as `python-xlib` on Arch and `python3-xlib` on Debian and Ubuntu. These names do not promise that the repository also supplies a sufficiently recent Quickshell.

## Run outside Omarchy

Clone the candidate branch, then run it in the intended desktop session:

```bash
git clone --branch feat/linux-desktops https://github.com/XGeboX/omarchy-dock.git
cd omarchy-dock
```

```bash
./bin/omarchy-dock doctor
./bin/omarchy-dock run
```

`doctor` reports detected desktop and missing dependencies. Its readiness field covers dependency detection, not successful window control. `run` starts a standalone foreground process. Stop that process with Ctrl+C. It does not install autostart configuration or alter another panel.

Keep the checkout in place. Disable a conflicting dock yourself before evaluating this one. Keep your existing panel available until you have tested launching, focus, minimize, restore, close, menus, dragging and monitor changes.

## GNOME

Stage the native extension from this checkout:

```bash
./bin/omarchy-dock install-gnome
```

First installation may require logging out and back in before GNOME discovers the extension. Then run:

```bash
./bin/omarchy-dock run
```

Disable it with:

```bash
./bin/omarchy-dock disable-gnome
```

The installer archives an existing copy before replacing it and does not enable it during installation. Preferences remain in the shared dock configuration directory. GNOME extensions installed on the desktop may conflict with another dock; evaluate this candidate with only the intended dock enabled.

## Preferences and updates

Both interfaces use `$XDG_CONFIG_HOME/omarchy-dock/config.json`, defaulting to `~/.config/omarchy-dock/config.json`. Pins, icon size, magnification and custom trusted commands follow the existing format. Set `reducedMotion` to `true` to suppress magnification and launch motion in the Quickshell interface. GNOME's reduced-motion path uses immediate hover sizing.

For a source installation, disable or stop the candidate before updating its checkout with a fast-forward pull. Run the checks below before restarting. GNOME users should run `install-gnome` again to stage updated extension files. Existing extension files are archived under `$XDG_STATE_HOME/omarchy-dock/backups`, defaulting to `~/.local/state/omarchy-dock/backups`.

The `enable`, `disable` and `status` commands retain their Omarchy plugin meaning. Other desktops use `run`, `doctor` and the GNOME commands above.

## Checks

```bash
python3 tools/test.py
node tests/native_desktop.mjs
```

Install PyGObject and Node alongside the Qt test dependencies. The first command runs Python checks, rendered Qt interaction tests and synthetic platform-model checks. It also runs the native JavaScript model checks when Node is installed. These checks do not substitute for running the native desktop integration.

For X11, install Xvfb, Openbox, Qt's QML runner, the X11 adapter dependencies and libXtst, then run:

```bash
python3 tools/test_x11.py
```

The integration test uses a separate X server, temporary user directories and synthetic windows. It clicks the real dock to exercise launch, minimize and restore. Its artifacts remain in a temporary directory for inspection. No existing desktop session is targeted.

For GNOME Shell 50 with its headless backend, GTK 3, PyGObject and the GNOME extension tools, run:

```bash
python3 tools/test_gnome.py
```

This creates a separate session bus, headless compositor, temporary user directories and a synthetic GTK application. It checks native window controls, menus, pinning, hover, fullscreen hiding and a rendered capture. It leaves its artifacts for inspection.

After changing motion, regenerate the GNOME module and rerun the checks:

```bash
python3 tools/sync_motion.py
```

## Build the candidate package on Arch

The candidate has no published release asset or AUR entry. Generate its source archive locally so the staged recipe can use it:

```bash
python3 tools/release.py
cp .release-artifacts/omarchy-dock-0.7.0-dev.tar.gz packaging/aur/
cd packaging/aur
makepkg
```

The recipe checks the archive checksum and runs the synthetic suite. Package building does not activate the dock. Keep dependency installation under your package manager's control.

## Remaining release gates

Native sessions must establish window actions, clean shutdown, menu dismissal, pointer response, pin/reorder/remove behavior, monitor changes and fractional scaling. Distribution checks must establish package instructions and startup behavior. Keep untested combinations experimental and do not replace the published release until these gates pass.
