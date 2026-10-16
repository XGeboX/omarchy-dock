import QtQuick
import Quickshell
import Quickshell.Hyprland as Hypr

Scope {
    id: root
    property string minimizedWorkspace: "special:minimized"
    property var palette: null
    property string errorText: ""
    function classOf(t) {
        const o = t.lastIpcObject
        if (o && o["class"]) return o["class"]
        if (t.wayland && t.wayland.appId) return t.wayland.appId
        return ""
    }

    function isMinimized(t) {
        return !!(t.workspace && t.workspace.name === root.minimizedWorkspace)
    }

    // Every window Hyprland has, as { tl, cls, minimized }. Reading the toplevels,
    // their workspaces and their classes inside this binding is what makes the dock
    // update when a window opens, closes or moves.
    readonly property var windows: {
        const out = []
        const list = Hypr.Hyprland.toplevels.values
        for (let i = 0; i < list.length; i++) {
            const t = list[i]
            const cls = classOf(t)
            if (!cls) continue
            out.push({ tl: t, cls: cls, minimized: isMinimized(t) })
        }
        return out
    }

    function address(t) {
        const a = String(t.address || "")
        return a.indexOf("0x") === 0 ? a : "0x" + a
    }

    function focusWindow(t) {
        if (!Hypr.Hyprland.usingLua) { Hypr.Hyprland.dispatch('focuswindow address:' + address(t)); return }
        Hypr.Hyprland.dispatch('hl.dsp.focus({ window = "address:' + address(t) + '" })')
    }

    function minimizeWindow(t) {
        if (!Hypr.Hyprland.usingLua) { Hypr.Hyprland.dispatch('movetoworkspacesilent ' + root.minimizedWorkspace + ',address:' + address(t)); return }
        Hypr.Hyprland.dispatch('hl.dsp.window.move({ window = "address:' + address(t) + '", workspace = "'
            + root.minimizedWorkspace + '", follow = false })')
    }

    function restoreWindow(t) {
        const mon = Hypr.Hyprland.focusedMonitor
        const ws = mon && mon.activeWorkspace
        const selector = ws && ws.id > 0 ? String(ws.id) : ws && ws.name ? "name:" + ws.name : "1"
        if (!Hypr.Hyprland.usingLua) {
            Hypr.Hyprland.dispatch('movetoworkspace ' + selector + ',address:' + address(t))
            focusWindow(t)
            return
        }
        Hypr.Hyprland.dispatch('hl.dsp.window.move({ window = "address:' + address(t) + '", workspace = '
            + JSON.stringify(selector) + ', follow = true })')
        focusWindow(t)
    }

    function closeWindow(t) {
        if (!Hypr.Hyprland.usingLua) { Hypr.Hyprland.dispatch('closewindow address:' + address(t)); return }
        Hypr.Hyprland.dispatch('hl.dsp.window.close({ window = "address:' + address(t) + '" })')
    }

    Connections {
        target: Hypr.Hyprland
        function onRawEvent(event) {
            if (["openwindow", "closewindow", "movewindow", "movewindowv2", "windowtitle", "windowtitlev2"].indexOf(event.name) >= 0)
                Hypr.Hyprland.refreshToplevels()
        }
    }
    Component.onCompleted: Hypr.Hyprland.refreshToplevels()
}
