import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Pango from 'gi://Pango';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as Motion from './motion.js';

const defaults = {pinned: [], iconSize: 52, magnification: 1.55, magnify: true, reducedMotion: false};

class DockPanel {
    constructor(owner, monitor) {
        this.owner = owner;
        this.monitor = monitor;
        this.items = new Map();
        this.state = {center: 0, strength: 0};
        this.pointerX = 0;
        this.hovered = false;
        this.actor = new St.Widget({layout_manager: new Clutter.FixedLayout()});
        this.shelf = new St.Widget({style_class: 'omarchy-dock-shelf'});
        this.divider = new St.Widget({reactive: true, style: 'background-color: rgba(236,237,239,0.4); border-radius: 2px;'});
        this.tip = new St.Label({style_class: 'omarchy-dock-tip', visible: false});
        this.tip.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        this.actor.add_child(this.shelf);
        this.actor.add_child(this.divider);
        this.actor.add_child(this.tip);
        this.divider.connect('button-press-event', (_actor, event) => {
            if (event.get_button() !== 1) return Clutter.EVENT_PROPAGATE;
            this.owner.grab?.dismiss();
            this.owner.grab = global.stage.grab(this.actor);
            this.owner.resize = {panel: this, y: event.get_coords()[1], size: this.owner.config.iconSize};
            return Clutter.EVENT_STOP;
        });
        this.timeline = new Clutter.Timeline({actor: this.actor, duration: 1000, repeat_count: -1});
        this.timeline.connect('new-frame', () => this.tick());
        this.lastFrame = GLib.get_monotonic_time();
        Main.layoutManager.addChrome(this.actor, {affectsStruts: true, trackFullscreen: true});
        this.actor.visible = !Main.overview.visible && !global.display.get_monitor_in_fullscreen(this.monitor.index);
        this.sync();
    }

    sync() {
        const entries = this.owner.entries();
        const wanted = new Set(entries.map(item => item.key));
        for (const [key, item] of this.items) {
            if (!wanted.has(key)) { item.actor.destroy(); this.items.delete(key); }
        }
        for (const entry of entries) {
            let item = this.items.get(entry.key);
            if (!item) {
                const actor = new St.Widget({reactive: true, can_focus: true, track_hover: true,
                    layout_manager: new Clutter.FixedLayout(), accessible_name: entry.label});
                const image = new St.Icon({gicon: entry.gicon ?? entry.app?.get_app_info()?.get_icon()
                    ?? new Gio.ThemedIcon({name: 'application-x-executable'})});
                const dot = new St.Widget();
                actor.add_child(image);
                actor.add_child(dot);
                this.actor.add_child(actor);
                item = {actor, image, dot, entry};
                actor.connect('button-press-event', (_actor, event) => this.press(item, event));
                actor.connect('key-press-event', (_actor, event) => {
                    const key = event.get_key_symbol();
                    if (key === Clutter.KEY_Return || key === Clutter.KEY_space) {
                        this.owner.activate(item.entry); return Clutter.EVENT_STOP;
                    }
                    if (key === Clutter.KEY_Menu) { this.openMenu(item); return Clutter.EVENT_STOP; }
                    return Clutter.EVENT_PROPAGATE;
                });
                this.items.set(entry.key, item);
            }
            item.entry = entry;
            item.image.gicon = entry.gicon ?? entry.app?.get_app_info()?.get_icon() ?? new Gio.ThemedIcon({name: 'application-x-executable'});
            item.actor.accessible_name = entry.label;
        }
        this.entries = entries;
        this.actor.set_position(this.monitor.x, this.monitor.y + this.monitor.height - this.restHeight());
        this.actor.set_size(this.monitor.width, this.restHeight());
        this.layout();
    }

    size() { return Motion.fitSize(this.owner.config.iconSize, this.entries.length, this.monitor.width); }
    restHeight() {
        const size = this.size();
        return size + Motion.metric(size, 0.18) * 2 + 16;
    }
    layout() {
        const size = this.size(), gap = Motion.metric(size, 0.14), pad = Motion.metric(size, 0.18);
        const apps = this.entries.filter(item => !item.window).length;
        const zoom = this.owner.config.magnify ? this.owner.config.magnification : 1;
        this.geometry = Motion.layout(apps, this.entries.length - apps, size, gap, pad,
            zoom, this.state.center, this.state.strength, this.monitor.width);
        const bottom = this.restHeight() - 8;
        this.shelf.set_position(this.geometry.left, 0);
        this.shelf.set_size(this.geometry.width, bottom);
        const divider = this.geometry.items[apps];
        this.divider.set_position(this.geometry.left + divider.x + 5, pad);
        this.divider.set_size(2, size + 8);
        this.entries.forEach((entry, index) => {
            const item = this.items.get(entry.key);
            const slot = this.geometry.items[index < apps ? index : index + 1];
            const x = this.geometry.left + slot.x, y = bottom - pad - slot.width - 8;
            item.actor.opacity = (this.owner.drag?.panel === this && this.owner.drag.entry.key === entry.key)
                || this.landing === entry.key ? 0 : 255;
            item.image.opacity = this.owner.press?.entry.key === entry.key && !this.owner.drag ? 200 : 255;
            item.actor.set_position(x, y);
            item.actor.set_size(slot.width, slot.width + 8);
            const textureSize = Math.ceil(this.owner.config.iconSize * 2.2);
            item.image.icon_size = textureSize;
            item.image.set_size(textureSize, textureSize);
            item.image.set_scale(slot.width / textureSize, slot.width / textureSize);
            const windows = entry.app?.get_windows() ?? [];
            item.dot.visible = !!entry.window || windows.length > 0;
            item.dot.style_class = windows.some(w => w.has_focus()) ? 'omarchy-dock-dot-active' : 'omarchy-dock-dot';
            item.dot.set_position(slot.width / 2 - 2, slot.width + 3);
            item.dot.set_size(4, 4);
        });
        this.drawGhost();
        this.actor.set_child_above_sibling(this.tip, null);
    }

    pointer(x, y) {
        const localX = x - this.monitor.x;
        const localY = y - this.monitor.y - this.monitor.height + this.restHeight();
        const rest = Motion.restWidth(this.entries.length, this.size(), Motion.metric(this.size(), 0.14), Motion.metric(this.size(), 0.18));
        const left = Math.min((this.monitor.width - rest) / 2, this.geometry.left);
        const right = Math.max((this.monitor.width + rest) / 2, this.geometry.left + this.geometry.width);
        this.hovered = localX >= left && localX <= right && localY <= this.restHeight()
            && localY >= (this.state.strength > 0 ? -this.size() * 1.8 : 0);
        this.pointerX = localX - (this.monitor.width - rest) / 2;
        if (this.hovered && !this.owner.drag && !this.owner.resize && !this.landing && !this.menu?.isOpen)
            this.state = Motion.track(this.state, this.pointerX);
        if (!this.menu?.isOpen) {
            if (this.owner.config.reducedMotion) {
                this.state = {...this.state, center: this.pointerX, strength: this.hovered && !this.owner.drag && !this.owner.resize ? 1 : 0};
                this.layout();
            } else if (!this.timeline.is_playing()) {
                this.lastFrame = GLib.get_monotonic_time();
                this.timeline.start();
            }
            this.layout();
        }
        const slot = this.hovered ? Motion.hit(this.geometry, localX, localY,
            this.restHeight() - 8 - Motion.metric(this.size(), 0.18), 8) : -1;
        const apps = this.entries.filter(item => !item.window).length;
        const entry = slot < 0 ? null : this.entries[slot < apps ? slot : slot - 1];
        this.tip.visible = !!entry && !this.owner.drag && !this.owner.resize && !this.menu?.isOpen;
        if (entry) {
            this.tip.text = entry.label;
            this.tip.set_width(-1);
            this.tip.width = Math.min(360, this.monitor.width - 16, this.tip.get_preferred_width(-1)[1]);
            const tipHeight = this.tip.get_preferred_height(this.tip.width)[1];
            this.tip.set_position(Math.max(4, Math.min(this.monitor.width - this.tip.width - 4,
                localX - this.tip.width / 2)), (this.items.get(entry.key)?.actor.y ?? 0) - tipHeight - 8);
        }
    }

    tick() {
        if (this.menu?.isOpen) { this.timeline.stop(); return; }
        const now = GLib.get_monotonic_time();
        const dragging = !!this.owner.drag || !!this.owner.resize || !!this.landing;
        const target = this.hovered && !dragging ? 1 : 0;
        this.state = Motion.advance(this.state, this.pointerX, target, (now - this.lastFrame) / 1000000, dragging);
        this.lastFrame = now;
        this.layout();
        if (Motion.settled(this.state, this.pointerX, target, dragging)) this.timeline.stop();
    }

    drawGhost() {
        const drag = this.owner.drag;
        if (!drag || drag.panel !== this) return;
        if (!this.ghost) {
            this.ghost = new St.Icon({gicon: drag.entry.gicon ?? drag.entry.app?.get_app_info()?.get_icon()
                ?? new Gio.ThemedIcon({name: 'application-x-executable'}), icon_size: Math.ceil(this.owner.config.iconSize * 2.2)});
            this.actor.add_child(this.ghost);
        }
        const size = this.size() * 1.15;
        this.ghost.set_scale(size / this.ghost.icon_size, size / this.ghost.icon_size);
        this.ghost.set_position(drag.x - this.monitor.x - size / 2,
            drag.y - this.monitor.y - this.monitor.height + this.restHeight() - size / 2);
        this.ghost.opacity = drag.y < this.monitor.y + this.monitor.height - this.restHeight() - this.size() ? 140 : 245;
    }

    clearGhost() {
        this.ghost?.destroy(); this.ghost = null; this.landing = null;
    }

    landGhost(entry) {
        if (!this.ghost) return;
        const ghost = this.ghost;
        const target = this.items.get(entry.key)?.actor;
        this.landing = entry.key;
        this.layout();
        const complete = () => {
            if (this.ghost !== ghost) return;
            this.clearGhost(); this.layout();
            const [x, y] = global.get_pointer(); this.pointer(x, y);
        };
        if (this.owner.config.reducedMotion) { complete(); return; }
        if (target) ghost.ease({x: target.x, y: target.y, scale_x: target.width / ghost.icon_size,
            scale_y: target.width / ghost.icon_size, opacity: 255, duration: 180,
            mode: Clutter.AnimationMode.EASE_OUT_CUBIC, onComplete: complete});
        else ghost.ease({opacity: 0, duration: 160, onComplete: complete});
    }

    press(item, event) {
        if (event.get_button() === 3) { this.openMenu(item); return Clutter.EVENT_STOP; }
        if (event.get_button() === 2) { this.owner.launch(item.entry); return Clutter.EVENT_STOP; }
        if (event.get_button() !== 1) return Clutter.EVENT_PROPAGATE;
        const [x, y] = event.get_coords();
        if (this.landing) { this.clearGhost(); this.layout(); }
        this.owner.grab?.dismiss();
        this.owner.grab = global.stage.grab(this.actor);
        this.owner.press = {panel: this, entry: item.entry, x, y};
        this.layout();
        return Clutter.EVENT_STOP;
    }

    openMenu(item) {
        this.menu?.destroy();
        this.menu = new PopupMenu.PopupMenu(item.actor, 0.5, St.Side.BOTTOM);
        this.manager ??= new PopupMenu.PopupMenuManager(this.actor);
        this.manager.addMenu(this.menu);
        Main.uiGroup.add_child(this.menu.actor);
        this.menu.actor.hide();
        const entry = item.entry;
        const windows = entry.window ? [entry.window] : (entry.app?.get_windows() ?? []);
        windows.forEach(window => this.menu.addAction(window.get_title() || entry.label,
            () => { window.unminimize(); Main.activateWindow(window); }));
        this.menu.addAction('Open', () => this.owner.launch(entry));
        if (windows.length) {
            this.menu.addAction('Minimize', () => windows.forEach(window => window.minimize()));
            this.menu.addAction('Restore', () => windows.forEach(window => { window.unminimize(); Main.activateWindow(window); }));
        }
        this.menu.addAction(this.owner.isPinned(entry.cls) ? 'Remove from Dock' : 'Keep in Dock', () => this.owner.pin(entry));
        if (windows.length) this.menu.addAction('Close', () => windows.forEach(window => window.delete(global.get_current_time())));
        this.menu.connect('open-state-changed', (_menu, open) => {
            if (!open) { const [x, y] = global.get_pointer(); this.pointer(x, y); }
        });
        this.menu.open();
        this.tip.hide();
    }

    destroy() {
        this.clearGhost();
        this.menu?.destroy();
        this.timeline.stop();
        Main.layoutManager.removeChrome(this.actor);
        this.actor.destroy();
    }
}

export default class OmarchyDock extends Extension {
    enable() {
        this.connections = [];
        this.panels = [];
        this.appSystem = Shell.AppSystem.get_default();
        this.tracker = Shell.WindowTracker.get_default();
        this.file = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_config_dir(), 'omarchy-dock', 'config.json']));
        this.config = {...defaults};
        this.reload();
        const directory = this.file.get_parent();
        GLib.mkdir_with_parents(directory.get_path(), 0o700);
        this.monitor = directory.monitor_directory(Gio.FileMonitorFlags.NONE, null);
        this.monitor.connect('changed', () => this.schedule(true));
        this.connect(Main.layoutManager, 'monitors-changed', () => this.rebuild());
        this.connect(Main.overview, 'showing', () => this.panels.forEach(panel => panel.actor.hide()));
        this.connect(Main.overview, 'hidden', () => this.panels.forEach(panel => {
            panel.actor.visible = !global.display.get_monitor_in_fullscreen(panel.monitor.index);
        }));
        this.connect(this.appSystem, 'app-state-changed', () => this.schedule());
        this.connect(global.display, 'notify::focus-window', () => this.schedule());
        this.connect(global.window_manager, 'map', () => this.schedule());
        this.connect(global.window_manager, 'destroy', () => this.schedule());
        this.connect(global.window_manager, 'minimize', () => this.schedule());
        this.connect(global.window_manager, 'unminimize', () => this.schedule());
        this.connect(global.stage, 'captured-event', (_actor, event) => this.event(event));
        this.rebuild();
    }

    connect(object, signal, handler) { this.connections.push([object, object.connect(signal, handler)]); }
    reload() {
        if (!this.file.query_exists(null)) return;
        try {
            const [, contents] = this.file.load_contents(null);
            const value = JSON.parse(new TextDecoder().decode(contents));
            if (!value || typeof value !== 'object' || Array.isArray(value)
                || (value.pinned !== undefined && !Array.isArray(value.pinned))) throw new Error('Invalid configuration');
            this.config = {...defaults, ...value};
            this.config.iconSize = Math.max(32, Math.min(96, Number(this.config.iconSize) || 52));
            this.config.magnification = Math.max(1, Math.min(2.2, Number(this.config.magnification) || 1.55));
        } catch (error) { console.error('Omarchy Dock: invalid preferences were preserved'); }
    }
    save() {
        if (this.file.query_exists(null)) {
            const backup = Gio.File.new_for_path(this.file.get_path() + '.backup-' + GLib.get_real_time());
            this.file.copy(backup, Gio.FileCopyFlags.NONE, null, null);
        }
        this.file.replace_contents(JSON.stringify(this.config, null, 2) + '\n', null, false,
            Gio.FileCreateFlags.REPLACE_DESTINATION, null);
        this.sync();
    }
    schedule(reload = false) {
        this.reloadPending ||= reload;
        if (this.idle) return;
        this.idle = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this.idle = 0;
            if (this.reloadPending) { this.reloadPending = false; this.reload(); }
            if (!this.press && !this.resize) this.sync();
            return GLib.SOURCE_REMOVE;
        });
    }
    rebuild() {
        this.grab?.dismiss(); this.grab = null;
        this.press = null; this.drag = null; this.resize = null;
        this.panels.forEach(panel => panel.destroy());
        this.panels = Main.layoutManager.monitors.map(monitor => new DockPanel(this, monitor));
    }
    sync() { this.panels.forEach(panel => panel.sync()); }
    isPinned(cls) { return this.config.pinned.some(pin => pin && pin.class === cls); }
    entries() {
        const apps = this.appSystem.get_running();
        const byId = new Map(apps.map(app => [app.get_id(), app]));
        const result = [], seen = new Set(), identities = new Map();
        for (const pin of this.config.pinned) {
            if (!pin?.class || seen.has(pin.class)) continue;
            const id = String(pin.desktop || pin.class).replace(/\.desktop$/, '') + '.desktop';
            if (identities.has(id)) continue;
            const app = byId.get(id) ?? this.appSystem.lookup_app(id);
            if (!app && !pin.command) continue;
            let gicon = null;
            if (pin.icon) {
                try { gicon = Gio.icon_new_for_string(String(pin.icon)); }
                catch (_error) { gicon = new Gio.ThemedIcon({name: 'application-x-executable'}); }
            }
            result.push({key: pin.class, cls: pin.class, app, pin, gicon,
                label: pin.name || app?.get_name() || pin.class});
            seen.add(pin.class); identities.set(id, pin.class); byId.delete(id);
        }
        for (const app of byId.values()) {
            const cls = app.get_id().replace(/\.desktop$/, '');
            if (seen.has(cls)) continue;
            result.push({key: cls, cls, app, label: app.get_name()}); seen.add(cls); identities.set(app.get_id(), cls);
        }
        for (const app of apps) for (const window of app.get_windows()) {
            if (window.minimized) result.push({key: 'min:' + window.get_stable_sequence(),
                cls: identities.get(app.get_id()) || app.get_id().replace(/\.desktop$/, ''), app, window, label: window.get_title() || app.get_name()});
        }
        return result;
    }
    activate(entry) {
        if (entry.window) { entry.window.unminimize(); Main.activateWindow(entry.window); return; }
        const windows = entry.app?.get_windows() ?? [];
        const shown = windows.filter(window => !window.minimized);
        const front = shown.find(window => window.has_focus());
        if (front) front.minimize();
        else if (shown.length) Main.activateWindow(shown[0]);
        else if (windows.length) { windows[0].unminimize(); Main.activateWindow(windows[0]); }
        else this.launch(entry);
    }
    launch(entry) {
        if (!this.config.reducedMotion && !(entry.app?.get_windows().length > 0)) {
            for (const panel of this.panels) {
                const image = panel.items.get(entry.key)?.image;
                if (image) image.ease({translation_y: -panel.size() * 0.35, duration: 240,
                    mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                    onComplete: () => image.ease({translation_y: 0, duration: 280, mode: Clutter.AnimationMode.EASE_IN_OUT_SINE})});
            }
        }
        if (entry.pin?.command) Gio.Subprocess.new(['sh', '-c', String(entry.pin.command)], Gio.SubprocessFlags.NONE);
        else entry.app?.open_new_window(-1);
    }
    pin(entry) {
        if (this.isPinned(entry.cls)) {
            const id = entry.app?.get_id()?.replace(/\.desktop$/, '');
            this.config.pinned = this.config.pinned.filter(pin => !pin || (pin.class !== entry.cls
                && (!id || String(pin.desktop || '').replace(/\.desktop$/, '') !== id)));
        }
        else this.config.pinned.push({class: entry.cls, desktop: entry.app.get_id()});
        this.save();
    }
    event(event) {
        const type = event.type();
        if (type === Clutter.EventType.MOTION) {
            const [x, y] = event.get_coords();
            if (this.resize) {
                this.config.iconSize = Math.max(32, Math.min(96, this.resize.size + (this.resize.y - y) / 2));
                this.sync();
            } else if (this.press) {
                if (!this.press.entry.window && Math.hypot(x - this.press.x, y - this.press.y) > 6)
                    this.drag = {...this.press, x, y};
            }
            this.panels.forEach(panel => panel.pointer(x, y));
        } else if (type === Clutter.EventType.LEAVE && !this.press && !this.resize) {
            const [x, y] = event.get_coords();
            this.panels.forEach(panel => panel.pointer(x, y));
        } else if (type === Clutter.EventType.BUTTON_RELEASE && event.get_button() === 1) {
            this.grab?.dismiss(); this.grab = null;
            if (this.resize) { this.resize = null; this.save(); return Clutter.EVENT_STOP; }
            if (this.press) {
                const press = this.press, drag = this.drag;
                this.press = null; this.drag = null;
                if (drag) {
                    const panel = press.panel;
                    const identity = pin => String(pin.desktop || pin.class).replace(/\.desktop$/, '');
                    const id = String(press.entry.app?.get_id() || press.entry.pin?.desktop || press.entry.cls).replace(/\.desktop$/, '');
                    const group = this.config.pinned.filter(pin => pin && (pin.class === press.entry.cls || identity(pin) === id));
                    const canonical = group.findIndex(pin => pin.class === press.entry.cls && identity(pin) === id);
                    if (canonical > 0) group.unshift(group.splice(canonical, 1)[0]);
                    const visible = panel.entries.filter(entry => entry.pin && entry.cls !== press.entry.cls
                        && identity(entry.pin) !== id).map(entry => entry.pin);
                    this.config.pinned = this.config.pinned.filter(pin => !group.includes(pin));
                    if (!group.length) group.push({class: press.entry.cls, desktop: press.entry.app?.get_id()});
                    if (drag.y >= panel.monitor.y + panel.monitor.height - panel.restHeight() - panel.size()
                        && drag.x >= panel.monitor.x && drag.x <= panel.monitor.x + panel.monitor.width) {
                        const at = Math.max(0, Math.min(this.config.pinned.length,
                            Math.round((drag.x - panel.monitor.x - (panel.monitor.width - panel.geometry.restWidth) / 2
                                - Motion.metric(panel.size(), 0.18) - panel.size() / 2)
                                / (panel.size() + Motion.metric(panel.size(), 0.14)))));
                        // The drop slot counts visible apps; unavailable pins and aliases
                        // keep their metadata without changing the displayed order.
                        const next = visible[Math.min(at, visible.length)];
                        const index = next ? this.config.pinned.findIndex(pin => pin?.class === next.class && identity(pin) === identity(next)) : -1;
                        this.config.pinned.splice(index < 0 ? this.config.pinned.length : index, 0, ...group);
                    }
                    this.save();
                    press.panel.landGhost?.(press.entry);
                } else this.activate(press.entry);
                this.sync();
                return Clutter.EVENT_STOP;
            }
        } else if (type === Clutter.EventType.KEY_PRESS && event.get_key_symbol() === Clutter.KEY_Escape) {
            if (this.press || this.resize) {
                if (this.resize) this.config.iconSize = this.resize.size;
                this.panels.forEach(panel => panel.clearGhost());
                this.grab?.dismiss(); this.grab = null;
                this.press = null; this.drag = null; this.resize = null;
                this.reload(); this.sync();
                return Clutter.EVENT_STOP;
            }
        }
        return Clutter.EVENT_PROPAGATE;
    }
    disable() {
        this.grab?.dismiss(); this.grab = null;
        if (this.idle) { GLib.source_remove(this.idle); this.idle = 0; }
        this.connections.forEach(([object, id]) => object.disconnect(id));
        this.connections = [];
        this.monitor?.cancel(); this.monitor = null;
        this.panels.forEach(panel => panel.destroy()); this.panels = [];
        this.press = null; this.drag = null; this.resize = null;
        this.file = null; this.appSystem = null; this.tracker = null;
    }
}
