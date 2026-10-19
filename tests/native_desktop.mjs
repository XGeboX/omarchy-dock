import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const motionSource = readFileSync(new URL('../integrations/gnome/motion.js', import.meta.url), 'utf8');
const Motion = await import('data:text/javascript;base64,' + Buffer.from(motionSource).toString('base64'));

const code = readFileSync(new URL('../integrations/gnome/extension.js', import.meta.url), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace('export default class OmarchyDock', 'class OmarchyDock');
const context = vm.createContext({Extension: class {}, console, TextDecoder, Motion, Clutter: {EventType: {MOTION: 1, BUTTON_RELEASE: 2, KEY_PRESS: 3, LEAVE: 4}, KEY_Escape: 27, EVENT_STOP: 1, EVENT_PROPAGATE: 0}});
vm.runInContext(code + '\nglobalThis.Dock = OmarchyDock; globalThis.Panel = DockPanel;', context);
const dock = new context.Dock();
const window = {minimized: true, get_stable_sequence: () => 1, get_title: () => 'Fixture window'};
const app = {get_id: () => 'org.example.App.desktop', get_name: () => 'Fixture app', get_windows: () => [window]};
dock.appSystem = {get_running: () => [app], lookup_app: () => app};
dock.config = {pinned: [{class: 'FixtureClass', desktop: 'org.example.App', icon: 'fixture-icon'},
    {class: 'DuplicateAlias', desktop: 'org.example.App.desktop'}]};
// Use no icon override in this pure model check; native Gio icon loading is separate.
dock.config.pinned[0].icon = undefined;
const entries = dock.entries();
assert.equal(entries.length, 2);
assert.equal(entries[0].cls, 'FixtureClass');
assert.equal(entries[1].cls, entries[0].cls);
assert.equal(dock.isPinned(entries[1].cls), true);
dock.save = () => {};
dock.pin(entries[1]);
assert.equal(dock.isPinned('FixtureClass'), false);

dock.file = {query_exists: () => true, load_contents: () => [true, new TextEncoder().encode('{invalid')]};
assert.doesNotThrow(() => dock.reload());
const workingConfig = dock.config;
dock.file.load_contents = () => [true, new TextEncoder().encode('{"pinned":null}')];
dock.reload();
assert.equal(dock.config, workingConfig, 'Invalid null pins must preserve the working preferences');

dock.config = {pinned: [{class: 'a', name: 'Custom name', icon: 'custom-icon'}, {class: 'b'}, {class: 'c'}]};
const panel = {monitor: {x: 0, y: 0, width: 1207, height: 720}, restHeight: () => 86, size: () => 52,
    geometry: {left: 500, restWidth: 207}};
panel.entries = dock.config.pinned.map(pin => ({cls: pin.class, pin}));
dock.press = {panel, entry: {cls: 'a', app: {get_id: () => 'a.desktop'}}};
dock.drag = {x: 535, y: 680};
dock.sync = () => {};
dock.event({type: () => 2, get_button: () => 1});
assert.equal(dock.config.pinned[0].class, 'a', 'A vertical drag must keep the same slot');
assert.equal(dock.config.pinned[0].name, 'Custom name', 'A drag must preserve custom pin fields');

for (const duplicate of [false, true]) {
    const b = {class: 'b', desktop: 'b'}, c = {class: 'c', desktop: 'c'};
    dock.config.pinned = [{class: 'missing'}, b, ...(duplicate ? [{class: 'alias-b', desktop: 'b'}] : []), c];
    panel.entries = [{cls: 'b', pin: b}, {cls: 'c', pin: c}];
    panel.geometry.restWidth = 148;
    dock.press = {panel, entry: {cls: 'c', app: {get_id: () => 'c.desktop'}}};
    dock.drag = {x: 624, y: 680};
    dock.event({type: () => 2, get_button: () => 1});
    assert.equal(dock.config.pinned.indexOf(b) < dock.config.pinned.indexOf(c), true,
        'Unavailable pins must not shift a vertical drop to another visible slot');
    assert.equal(dock.config.pinned[0].class, 'missing', 'Unavailable pin metadata must survive a drop');
    dock.press = {panel, entry: {cls: 'b', app: {get_id: () => 'b.desktop'}}};
    dock.drag = {x: 624, y: 680};
    dock.event({type: () => 2, get_button: () => 1});
    assert.equal(dock.config.pinned.indexOf(c) < dock.config.pinned.indexOf(b), true);
    if (duplicate) assert.equal(dock.config.pinned.findIndex(pin => pin.class === 'alias-b') > dock.config.pinned.indexOf(b), true,
        'Moving a pin must keep its duplicate alias behind the canonical pin');
}

const applications = new Map(['a', 'b', 'c'].map(id => [id + '.desktop', {
    get_id: () => id + '.desktop', get_name: () => id, get_windows: () => []}]));
dock.appSystem = {get_running: () => [], lookup_app: id => applications.get(id)};
const hiddenAlias = {class: 'b', desktop: 'unavailable'};
dock.config.pinned = [hiddenAlias, ...['a', 'b', 'c'].map(id => ({class: id, desktop: id}))];
panel.entries = dock.entries();
panel.geometry.restWidth = 207;
dock.press = {panel, entry: panel.entries.find(entry => entry.cls === 'c')};
dock.drag = {x: 594, y: 680};
dock.event({type: () => 2, get_button: () => 1});
assert.deepEqual(Array.from(dock.entries(), entry => entry.cls), ['a', 'c', 'b'],
    'An unavailable class alias must not capture the insertion anchor');
assert.equal(dock.config.pinned.includes(hiddenAlias), true);

const pinCases = [
    [{class: 'a', desktop: 'a'}, {class: 'b', desktop: 'b'}, {class: 'a', desktop: 'c'}, {class: 'c', desktop: 'c'}],
    [{class: 'b', desktop: 'unavailable'}, ...['a', 'b', 'c'].map(id => ({class: id, desktop: id}))],
    [{class: 'a', desktop: 'a'}, {class: 'alias-a', desktop: 'a'}, {class: 'b', desktop: 'b'}, {class: 'c', desktop: 'c'}],
];
for (const pins of pinCases) {
    dock.config.pinned = pins.slice();
    const visible = Array.from(dock.entries(), entry => entry.cls);
    for (const cls of visible) for (let slot = 0; slot < visible.length; slot++) {
        dock.config.pinned = pins.slice();
        panel.entries = dock.entries();
        panel.geometry.restWidth = Motion.restWidth(visible.length, 52, Motion.metric(52, 0.14), Motion.metric(52, 0.18));
        dock.press = {panel, entry: panel.entries.find(entry => entry.cls === cls)};
        dock.drag = {x: (1207 - panel.geometry.restWidth) / 2 + Motion.metric(52, 0.18) + 26
            + slot * (52 + Motion.metric(52, 0.14)), y: 680};
        dock.event({type: () => 2, get_button: () => 1});
        const expected = visible.filter(value => value !== cls);
        expected.splice(slot, 0, cls);
        assert.deepEqual(Array.from(dock.entries(), entry => entry.cls), expected, 'Every visible drop must preserve canonical identities');
        assert.equal(dock.config.pinned.length, pins.length);
        assert.equal(pins.every(pin => dock.config.pinned.includes(pin)), true, 'All original pin metadata must survive reordering');
    }
}

dock.config.iconSize = 80;
dock.resize = {size: 52};
dock.panels = [];
dock.file = {query_exists: () => false};
dock.event({type: () => 3, get_key_symbol: () => 27});
assert.equal(dock.config.iconSize, 52, 'Escape must restore size without a preferences file');

const crossing = [];
dock.panels = [{pointer: (x, y) => crossing.push([x, y])}];
dock.event({type: () => 4, get_coords: () => [600, 700]});
assert.deepEqual(crossing, [[600, 700]], 'Child crossings must recompute hover from coordinates');

const repeatPanel = Object.create(context.Panel.prototype);
let destroyed = false;
repeatPanel.ghost = {destroy: () => { destroyed = true; }};
repeatPanel.landing = 'previous';
repeatPanel.layout = () => {};
repeatPanel.actor = {};
repeatPanel.owner = {};
context.global = {stage: {grab: () => ({dismiss() {}})}};
repeatPanel.press({entry: {key: 'next'}}, {get_button: () => 1, get_coords: () => [600, 700]});
assert.equal(destroyed, true);
assert.equal(repeatPanel.landing, null, 'A new drag must cancel the previous landing');

const queued = [];
context.GLib = {PRIORITY_DEFAULT_IDLE: 0, SOURCE_REMOVE: false,
    idle_add: (_priority, callback) => { queued.push(callback); return queued.length; }};
const resizing = new context.Dock();
resizing.config = {pinned: [], iconSize: 64, magnification: 1.55};
resizing.resize = {size: 52};
resizing.file = {query_exists: () => true, load_contents: () => [true,
    new TextEncoder().encode(JSON.stringify({pinned: [{class: 'external'}], iconSize: 52, magnification: 1.8}))]};
resizing.sync = () => {};
let saved;
resizing.save = () => { saved = {...resizing.config}; };
resizing.schedule(true);
queued.shift()();
assert.equal(resizing.config.iconSize, 64, 'A pending preferences reload must not undo a resize');
resizing.event({type: () => 2, get_button: () => 1});
assert.equal(saved.iconSize, 64, 'Release must save the size selected by the gesture');
assert.equal(saved.magnification, 1.8, 'Unrelated external preference changes must survive');
assert.equal(saved.pinned[0].class, 'external');

for (const [shownSize, externalSize, dropY] of [[52, 96], [96, 32], [32, 80], [96, 52, 500]]) {
    const changing = new context.Dock();
    const pins = ['a', 'b', 'c', 'd'].map(cls => ({class: cls, desktop: cls}));
    changing.config = {pinned: pins, iconSize: shownSize, magnification: 1.55};
    const displayed = Object.create(context.Panel.prototype);
    displayed.owner = changing;
    displayed.monitor = {x: 0, y: 0, width: 1207, height: 720};
    displayed.entries = pins.map(pin => ({cls: pin.class, pin}));
    const size = displayed.size(), gap = Motion.metric(size, 0.14), pad = Motion.metric(size, 0.18);
    displayed.geometry = {restWidth: Motion.restWidth(4, size, gap, pad)};
    changing.press = {panel: displayed, entry: {cls: 'a', app: {get_id: () => 'a.desktop'}}};
    changing.drag = {x: (displayed.monitor.width - displayed.geometry.restWidth) / 2 + pad + size / 2 + 3 * (size + gap),
        y: dropY ?? displayed.monitor.height - displayed.restHeight() / 2};
    changing.file = {query_exists: () => true, load_contents: () => [true, new TextEncoder().encode(JSON.stringify({
        pinned: pins.map(pin => ({...pin, name: 'Fresh ' + pin.class})), iconSize: externalSize, magnification: 1.8}))]};
    changing.sync = () => {};
    changing.save = () => {};
    changing.schedule(true);
    queued.shift()();
    changing.event({type: () => 2, get_button: () => 1});
    assert.deepEqual(Array.from(changing.config.pinned, pin => pin.class), ['b', 'c', 'd', 'a'],
        'Drop slots must use the geometry displayed before queued preferences reload');
    assert.equal(changing.config.iconSize, externalSize, 'The external size edit must survive the drag');
    assert.equal(changing.config.pinned.at(-1).name, 'Fresh a', 'Fresh pin metadata must survive the drag');
}

console.log('Native desktop model checks passed');

class Signal {
    constructor() { this.handlers = []; }
    connect(handler) { this.handlers.push(handler); }
    emit(...args) { this.handlers.slice().forEach(handler => handler(...args)); }
}
function kwinWindow(id) {
    return {resourceClass: 'fixture.' + id, internalId: id, caption: id, minimized: false,
        minimizedChanged: new Signal(), captionChanged: new Signal(), windowClassChanged: new Signal(), skipTaskbarChanged: new Signal()};
}
const firstWindow = kwinWindow('one'), nextWindow = kwinWindow('two');
let nativeWindows = [firstWindow], ownerAlive = true;
const updates = [], unloads = [], timers = [];
const workspace = {windowList: () => nativeWindows, activeWindow: firstWindow,
    windowAdded: new Signal(), windowRemoved: new Signal(), windowActivated: new Signal()};
const watcher = vm.createContext({workspace, dockOwner: ':1.fixture', dockScript: 'fixture-watcher',
    QTimer: class {
        constructor() { this.timeout = new Signal(); timers.push(this); }
        start() { this.running = true; }
        stop() { this.running = false; }
    },
    callDBus: (_service, _path, _interface, method, argument, callback) => {
        if (method === 'Update') updates.push(JSON.parse(argument));
        else if (method === 'NameHasOwner') { assert.equal(argument, ':1.fixture'); callback(ownerAlive); }
        else if (method === 'unloadScript') unloads.push(argument);
    }});
vm.runInContext(readFileSync(new URL('../integrations/plasma/windows.js', import.meta.url), 'utf8'), watcher);
assert.equal(updates.at(-1)[0].tl.activated, true);
nativeWindows.push(nextWindow); workspace.windowAdded.emit(nextWindow);
assert.equal(updates.at(-1).length, 2);
nextWindow.minimized = true; nextWindow.minimizedChanged.emit();
assert.equal(updates.at(-1)[1].minimized, true);
nextWindow.caption = 'Renamed fixture'; nextWindow.captionChanged.emit();
assert.equal(updates.at(-1)[1].tl.title, 'Renamed fixture');
nativeWindows = [nextWindow]; workspace.windowRemoved.emit(firstWindow);
assert.equal(updates.at(-1).length, 1);
timers[0].timeout.emit(); assert.equal(unloads.length, 0);
ownerAlive = false; timers[0].timeout.emit();
assert.deepEqual(unloads, ['fixture-watcher']);
assert.equal(timers[0].running, false);
console.log('Native KWin watcher checks passed');
