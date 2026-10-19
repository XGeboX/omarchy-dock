# Changelog

## 0.7.0-dev

Experimental Linux desktop candidate.

- Standalone launcher, desktop detection and dependency diagnostics.
- Native GNOME extension using the shared motion geometry and original icons.
- KDE Plasma, Sway and EWMH X11 window-control adapters.
- Hyprland dispatch selection for Lua and configuration-file sessions.
- Reduced-motion preference, XDG configuration paths and safer extension updates.
- Regression fixes for stale menu targets, hover crossings and consecutive drags.
- External preference changes survive GNOME drag and resize gestures.
- Monitor removal cancels an unfinished GNOME resize.
- Failed Plasma actions unload temporary scripts and retain failed cleanup for shutdown retry.

Native checks cover selected virtual desktop versions, including GNOME 50.4 mixed scaling and monitor reconnection. Helper and installer smoke tests pass on Ubuntu 24.04, Debian 13 and Fedora 44. Live Omarchy and standalone Hyprland checks, other desktop versions and real hardware remain release gates.

## 0.6.1

First public release.

- Immediate pointer tracking with a shared magnification wave.
- Reduced horizontal shelf movement, including constrained screen layouts.
- Original themed icons, running indicators and launch feedback.
- Drag ordering, pinning, resizing and minimized-window controls.
- Per-user activation, preference backups and live version checks.
