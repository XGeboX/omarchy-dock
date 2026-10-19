import QtQuick
import Quickshell
import Quickshell.Wayland

Scope {
    id: root
    property var palette: null
    property string errorText: ""
    property var identifiers: ({ map: new Map(), nextId: 0 })
    function address(t) {
        if (!identifiers.map.has(t)) identifiers.map.set(t, String(++identifiers.nextId))
        return identifiers.map.get(t)
    }
    readonly property var windows: {
        const list = ToplevelManager.toplevels.values
        const alive = new Set(list)
        for (const t of identifiers.map.keys()) if (!alive.has(t)) identifiers.map.delete(t)
        return list.filter(t => t.appId).map(t => ({
            cls: t.appId, minimized: t.minimized,
            tl: { address: address(t), title: t.title, activated: t.activated, native: t }
        }))
    }
    function focusWindow(t) { if (t.native) t.native.activate() }
    function minimizeWindow(t) { if (t.native) t.native.minimized = true }
    function restoreWindow(t) { if (t.native) { t.native.minimized = false; t.native.activate() } }
    function closeWindow(t) { if (t.native) t.native.close() }
}
