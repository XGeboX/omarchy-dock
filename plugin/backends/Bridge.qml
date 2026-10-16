import QtQuick
import Quickshell
import Quickshell.Io

Scope {
    id: root
    property var windows: []
    property var palette: null
    property string errorText: ""
    property bool closing: false
    Component.onDestruction: closing = true
    Process {
        id: bridge
        command: ["python3", Quickshell.shellDir + "/tools/desktop.py", "bridge", Quickshell.env("OMARCHY_DOCK_BACKEND")]
        stdinEnabled: true
        running: true
        stdout: SplitParser {
            onRead: data => {
                if (!data.trim()) return
                try {
                    const update = JSON.parse(data)
                    if (Array.isArray(update.windows)) { root.windows = update.windows; root.errorText = "" }
                    if (update.error) root.errorText = "Window action could not be completed"
                } catch (error) { console.error("Invalid dock bridge response") }
            }
        }
        onExited: (code, status) => {
            root.windows = []
            if (!root.closing) { root.errorText = "Window controls unavailable"; console.error("Dock window service stopped (" + code + ")") }
        }
    }
    function action(t, action) { bridge.write(JSON.stringify({ id: t.address, action: action }) + "\n") }
    function focusWindow(t) { action(t, "focus") }
    function minimizeWindow(t) { action(t, "minimize") }
    function restoreWindow(t) { action(t, "restore") }
    function closeWindow(t) { action(t, "close") }
}
