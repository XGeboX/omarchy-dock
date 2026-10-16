# Omarchy Dock

A responsive application dock that follows your Omarchy theme and keeps your existing app icons.

![Dock magnification preview](docs/hover.png)

Preview rendered from the dock with neutral test icons. Your desktop uses the icons supplied by its installed icon theme.

- Pin applications and reorder them by dragging.
- Switch between running windows from the dock.
- Minimize, restore, close and quit through app menus.
- Magnify icons with immediate pointer tracking and restrained sideways movement.
- Resize the dock by dragging its divider vertically.
- Fit each screen independently without changing your saved icon size.

## Linux desktop development

The `0.7.0-dev` candidate adds a standalone launcher and native desktop integrations. The published `0.6.1` release targets Omarchy. The new integrations are experimental until their desktop checks pass; this is not yet a universal Linux release.

See [Linux setup, compatibility and checks](docs/linux.md) before trying the candidate. Your existing dock is not replaced by cloning this repository.

## Requirements

Omarchy with its Quickshell shell and plugin API. This release was checked with Omarchy 4.0.4, Hyprland 0.56.2 and Quickshell 0.3.1. It uses Omarchy's theme singleton and Hyprland's Lua dispatch interface.

## Install from Git

```bash
git clone https://github.com/XGeboX/omarchy-dock.git
cd omarchy-dock
./bin/omarchy-dock enable
```

Keep the checkout in place: the plugin points to its `plugin/` directory. Run activation as your desktop user. Disable any other dock plugin first to avoid overlapping panels.

Activation registers `xgebox.dock`, backs up existing preferences, and asks the Omarchy shell to enable it. It confirms the running version before reporting success. If the shell keeps an older component cached, the command reports this and asks you to run `omarchy restart shell`.

## AUR package

The package is not available from AUR yet. The package recipe is in [`packaging/aur/`](packaging/aur/). After the package is submitted to AUR:

```bash
yay -S omarchy-dock
omarchy-dock enable
```

The package installs shared source under `/usr/share/omarchy-dock`. Activation is per user; installation does not change your desktop configuration.

## Configure

Right-click a running app to pin it. Preferences are stored in `$XDG_CONFIG_HOME/omarchy-dock/config.json` (default `~/.config/omarchy-dock/config.json`) and survive disabling or upgrading the dock. A new installation starts with no pinned apps.

```json
{
  "pinned": [
    { "class": "com.mitchellh.ghostty", "desktop": "com.mitchellh.ghostty" }
  ],
  "iconSize": 52,
  "magnification": 1.55,
  "magnify": true
}
```

`class` matches the application's window class. `desktop` selects its desktop entry. An optional `command` launches a custom shell command; optional `name` and `icon` override its label and theme icon. Use commands you trust.

Minimized windows use the reserved workspace `special:minimized`. The dock restores them to the active workspace.

```bash
omarchy-dock status
omarchy-dock disable
```

For a Git checkout, use `./bin/omarchy-dock` instead of `omarchy-dock`.

## Tests

From the source checkout on Arch, install `python`, `python-gobject`, `nodejs`, `qt6-declarative` and `qt6-svg`, then run:

```bash
python3 tools/test.py
```

The suite checks installation against synthetic user directories, motion geometry, and rendered hover, drag, menus and tooltips. Rendering uses Qt's offscreen software backend. Generated fixtures and captures are kept under `.test-artifacts/`.

## Licence

MIT. Developed by Anirudh Sharma.
