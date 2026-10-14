from pathlib import Path
import json

root_dir = Path(__file__).resolve().parent.parent
stage = root_dir / '.test-artifacts'
stage.mkdir(exist_ok=True)
source = (root_dir / 'plugin/Dock.qml').read_text()
source = source.replace('import QtQuick\n', 'import QtQuick\nimport QtQuick.Window\n')
source = source.replace('    id: root\n', '    id: root\n    property var testPanel\n    property alias fixturePins: config.pinned\n    property alias fixtureMagnify: config.magnify\n    property int activations: 0\n    property int launches: 0\n    property var fixtureMonitor: null\n    property var dispatches: []\n    function fixtureDispatch(value) { dispatches = dispatches.concat([value]) }\n', 1)
source = source.replace('Quickshell.env("HOME") + "/.config/omarchy-dock/config.json"', json.dumps(str(stage / 'config.json')))
start = source.index('    readonly property var windows: {')
end = source.index('    function windowsOf', start)
source = source[:start] + '    readonly property var windows: []\n\n' + source[end:]
source = source.replace('model: Quickshell.screens', 'model: [{ width: 1000, name: "fixture" }]')
source = source.replace('PanelWindow {', 'Window {')
source = source.replace('            screen: modelData\n', '')
source = source.replace('            anchors.bottom: true\n', '')
source = source.replace('            exclusiveZone: restHeight + root.bottomGap\n', '')
source = source.replace('            mask: Region { item: zone }\n', '')
source = source.replace('            WlrLayershell.namespace: "omarchy-dock"\n            WlrLayershell.layer: WlrLayer.Top\n', '')
source = source.replace('            color: "transparent"\n', '''            color: "#283940"
            property real implicitWidth
            property real implicitHeight
            width: implicitWidth
            height: implicitHeight
            visible: true
            property alias testFrame: inputFrame
            property alias testMenu: menu
            property alias testTip: tooltip
            function testIcon(index) { return appRepeater.itemAt(index) }
            function testMinIcon(index) { return minRepeater.itemAt(index) }
            Component.onCompleted: root.testPanel = panel
''', 1)
source = source.replace('PopupWindow {', 'Window {')
source = source.replace('                anchor.window: panel\n                anchor.edges: Edges.Top\n                anchor.gravity: Edges.Top\n', '')
source = source.replace('                id: menu\n', '''                id: menu
                property real implicitWidth
                property real implicitHeight
                width: implicitWidth
                height: implicitHeight
                property QtObject anchor: QtObject {
                    property var window
                    property int edges
                    property int gravity
                    property rect rect: Qt.rect(0, 0, 0, 0)
                }
''')
start = source.index('                HyprlandFocusGrab {')
end = source.index('\n\n                Rectangle {', start)
source = source[:start] + source[end:]
source = source.replace('    Component.onCompleted: Hyprland.refreshToplevels()\n', '')
source = source.replace('    function saveConfig() {\n        configFile.writeAdapter()\n    }', '    function saveConfig() {}')


def stub_function(text, name, body):
    start = text.index('    function ' + name + '(')
    brace = text.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        if text[end] == '{':
            depth += 1
        elif text[end] == '}':
            depth -= 1
        end += 1
    return text[:brace + 1] + '\n        ' + body + '\n    }' + text[end:]


source = stub_function(source, 'activateApp', 'activations += 1')
source = stub_function(source, 'launch', 'launches += 1; launched(cls)')
source = source.replace('Hyprland.dispatch(', 'fixtureDispatch(')
source = source.replace('Hyprland.focusedMonitor', 'fixtureMonitor')
fixture_names = {'fixture.files': 'Files', 'fixture.browser': 'Browser', 'fixture.terminal': 'Terminal', 'fixture.mail': 'Mail', 'fixture.activity': 'Activity'}
fixture_icons = {cls: (root_dir / 'tests/fixtures' / (name + '.svg')).as_uri() for cls,name in fixture_names.items()}
source = stub_function(source, 'nameFor', 'return ' + json.dumps(fixture_names) + '[cls] || \"Application\"')
source = stub_function(source, 'iconFor', 'return ' + json.dumps(fixture_icons) + '[cls] || \"\"')
start = source.index('    IpcHandler {')
end = source.index('    function nameFor', start)
source = source[:start] + source[end:]

# Qt's test runner cannot load Quickshell's statically linked runtime. Replace
# only service adapters; geometry, handlers, animations and painted items stay intact.
source = '\n'.join(line for line in source.splitlines() if not line.startswith('import Quickshell')) + '\n'
source = source.replace('import qs.Commons', 'import "TestPalette"')
source = source.replace('Scope {', 'Item {', 1)
start = source.index('    FileView {')
end = source.index('    // A file replaced', start)
pins = [{"class": cls} for cls in fixture_names]
source = source[:start] + '''    QtObject {
        id: config
        property var pinned: ''' + json.dumps(pins) + '''
        property real iconSize: 52
        property real magnification: 1.55
        property bool magnify: true
    }

''' + source[end:]
start = source.index('    Timer {\n        interval: 3000')
end = source.index('    function saveConfig', start)
source = source[:start] + source[end:]
start = source.index('    Connections {\n        target: Hyprland')
end = source.index('    // --- the dock, one per screen', start)
source = source[:start] + source[end:]
source = source.replace('    readonly property var windows: []', '    property var windows: []')
source = source.replace('Variants {\n        model:', 'Item {\n        id: fixtureVariant\n        property var model:')
source = source.replace('required property var modelData\n', 'property var modelData: fixtureVariant.model[0]\n')
source = source.replace('model: ScriptModel { values: root.apps }', 'model: root.apps')
source = source.replace('model: ScriptModel { values: root.minimizedAddresses }', 'model: root.minimizedAddresses')
source = source.replace('IconImage {', 'Image {')
source = source.replace('            implicitSize: icon.size', '            width: icon.size\n            height: icon.size')
palette = stage / 'TestPalette'
palette.mkdir(exist_ok=True)
(palette / 'qmldir').write_text('singleton Color 1.0 Color.qml\n')
(palette / 'Color.qml').write_text('pragma Singleton\nimport QtQuick\nQtObject { property color foreground: "#cacccc"; property color background: "#101315"; property color accent: "#9fc4cc"; property color urgent: "#a55555" }\n')
(stage / 'DockFixture.qml').write_text(source)
(stage / 'DockMotion.js').write_text((root_dir / 'plugin/DockMotion.js').read_text())
(stage / 'config.json').write_text(json.dumps({'iconSize': 52, 'magnification': 1.55, 'magnify': True, 'pinned': pins}))

surface = (root_dir / 'tests/Surface.qml.in').read_text()
surface = surface.replace('__HOVER_IMAGE__', str(stage / 'hover.png')).replace('__REST_IMAGE__', str(stage / 'rest.png'))
(stage / 'Surface.qml').write_text(surface)
