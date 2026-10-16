// Developed by Anirudh Sharma. Shared dock surface for Omarchy and standalone sessions.
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Widgets
import "DockMotion.js" as Motion

Scope {
    id: root

    // Handed in by the Omarchy shell when it creates the service.
    property var shell
    property var manifest
    property string omarchyPath

    property string backendName: "Omarchy"
    readonly property var backend: platform.item
    readonly property var palette: backend && backend.palette ? backend.palette : fallbackPalette
    QtObject {
        id: fallbackPalette
        property color background: "#202428"
        property color foreground: "#ecedef"
        property color accent: "#a1c4d8"
        property color urgent: "#ef8484"
    }
    Loader {
        id: platform
        source: "backends/" + root.backendName + ".qml"
        onStatusChanged: if (status === Loader.Error) console.error("Dock backend could not load: " + root.backendName)
    }
    // Outside the plugin directory on purpose: the shell reloads a plugin whenever
    // anything in its directory changes, so a config kept there would reload the
    // whole dock every time an app was pinned.
    readonly property string configPath: (Quickshell.env("XDG_CONFIG_HOME") || Quickshell.env("HOME") + "/.config") + "/omarchy-dock/config.json"

    // --- geometry ------------------------------------------------------------------------
    readonly property real iconSize: Math.max(32, Math.min(96, config.iconSize))
    readonly property real magnification: config.magnify && !config.reducedMotion ? Math.max(1.0, Math.min(2.2, config.magnification)) : 1.0
    readonly property real pad: Math.round(iconSize * 0.18)
    readonly property real gap: Math.round(iconSize * 0.14)
    readonly property real dotSpace: 8
    readonly property real bottomGap: 8
    // What a fully magnified icon rises above the dock, plus room for its name.
    readonly property real lift: Math.ceil(iconSize * (magnification - 1 + 0.35)) + 44

    // --- configuration: pinned apps, size and magnification ------------------------------
    FileView {
        id: configFile
        path: root.configPath
        watchChanges: true
        onFileChanged: reload()

        JsonAdapter {
            id: config
            // Each entry: { "class": window class, and either "desktop": desktop
            // entry id, or "command": shell command; optional "name", "icon" }.
            property var pinned: []
            property real iconSize: 52
            property real magnification: 1.55
            property bool magnify: true
            property bool reducedMotion: false
        }
    }

    // A file replaced by rename leaves the watcher on the old inode, so edits made
    // from outside (a script, an editor that saves by rename) would never arrive.
    // Re-reading a few hundred bytes every few seconds closes that gap.
    // True while the divider is being dragged, so the re-read below cannot snap the
    // size back to the saved value mid-drag.
    property bool editing: false

    Timer {
        interval: 3000
        running: !root.editing
        repeat: true
        onTriggered: configFile.reload()
    }

    function saveConfig() {
        configFile.writeAdapter()
    }

    // --- the window model ------------------------------------------------------------
    readonly property var windows: backend ? backend.windows : []

    function windowsOf(cls) {
        return root.windows.filter(w => w.cls === cls)
    }

    function pinnedIndex(cls) {
        const p = config.pinned || []
        for (let i = 0; i < p.length; i++) if (p[i] && p[i]["class"] === cls) return i
        return -1
    }

    function pinFor(cls) {
        const i = pinnedIndex(cls)
        return i >= 0 ? config.pinned[i] : null
    }

    // Left of the divider: pinned apps in their saved order, then running apps that are not
    // pinned. One icon per app, not per window. A function of the pin list, so a drag
    // can lay out the list its drop would leave with exactly the same rules.
    readonly property var apps: appsFor(config.pinned)
    function appsFor(pinned) {
        const out = []
        const seen = Object.create(null)
        const p = pinned || []
        for (let i = 0; i < p.length; i++) {
            const e = p[i]
            if (!e || !e["class"] || seen[e["class"]]) continue
            seen[e["class"]] = true
            out.push(e["class"])
        }
        for (let i = 0; i < root.windows.length; i++) {
            const c = root.windows[i].cls
            if (seen[c]) continue
            seen[c] = true
            out.push(c)
        }
        return out
    }

    // Right of the divider: one icon per minimized window, by address.
    readonly property var minimizedAddresses: root.windows.filter(w => w.minimized).map(w => address(w.tl))

    function windowAt(addr) {
        for (let i = 0; i < root.windows.length; i++)
            if (address(root.windows[i].tl) === addr) return root.windows[i]
        return null
    }

    // --- names and icons -----------------------------------------------------------------
    function entryFor(cls, pin) {
        // Read so every icon and name binding depends on the entry list: an entry added
        // or changed while the dock runs (a desktop entry update can otherwise need a dock
        // reload) then shows without one.
        void DesktopEntries.applications.values
        let e = null
        if (pin && pin.desktop) e = DesktopEntries.byId(String(pin.desktop).replace(/\.desktop$/, ""))
        if (!e && cls) e = DesktopEntries.byId(cls)
        if (!e && cls) e = DesktopEntries.heuristicLookup(cls)
        // Omarchy's TUIs run under classes like org.omarchy.btop.
        if (!e && cls && cls.indexOf("org.omarchy.") === 0) e = DesktopEntries.heuristicLookup(cls.slice(12))
        return e
    }

    function iconFor(cls) {
        const pin = pinFor(cls)
        const e = entryFor(cls, pin)
        const name = (pin && pin.icon) || (e && e.icon) || cls
        return Quickshell.iconPath(name, "application-x-executable")
    }

    IpcHandler {
        target: "omarchy-dock"
        function motionProfile(): string {
            return JSON.stringify({ version: "0.7.0-dev", tracking: "pointer-event",
                artwork: "theme-image", icons: "original", positioning: "reduced-drift", backend: root.backendName,
                windowControls: !!root.backend && !root.backend.errorText })
        }
    }

    function nameFor(cls) {
        const pin = pinFor(cls)
        if (pin && pin.name) return pin.name
        const e = entryFor(cls, pin)
        return e && e.name ? e.name : cls
    }

    // --- actions ---------------------------------------------------------------------------
    function address(t) {
        const a = String(t.address || "")
        return a
    }

    function focusWindow(t) { if (backend) backend.focusWindow(t) }
    function minimizeWindow(t) { if (backend) backend.minimizeWindow(t) }
    function restoreWindow(t) { if (backend) backend.restoreWindow(t) }
    function closeWindow(t) { if (backend) backend.closeWindow(t) }

    function quitApp(cls) {
        const ws = windowsOf(cls)
        for (let i = 0; i < ws.length; i++) closeWindow(ws[i].tl)
    }

    // Emitted so the icon can bounce until a window for its app appears.
    signal launched(string cls)

    function launch(cls) {
        const pin = pinFor(cls)
        root.launched(cls)
        if (pin && pin.command) {
            Quickshell.execDetached(["sh", "-c", String(pin.command)])
            return
        }
        const e = entryFor(cls, pin)
        const id = (pin && pin.desktop) || (e && e.id) || cls
        if (backendName === "Omarchy")
            Quickshell.execDetached(["uwsm-app", "--", String(id).replace(/\.desktop$/, "") + ".desktop"])
        else if (e) e.execute()
        else console.warn("No desktop entry for application: " + cls)
    }

    // Left-click on an app: focus it, restore it if every window is minimized, or
    // launch it if nothing is running. A click on the app already in front
    // minimizes it when it is already the active window.
    function activateApp(cls) {
        const ws = windowsOf(cls)
        const shown = ws.filter(w => !w.minimized)
        if (shown.length > 0) {
            const front = shown.find(w => w.tl.activated)
            if (front) minimizeWindow(front.tl)
            else focusWindow(shown[0].tl)
            return
        }
        if (ws.length > 0) {
            restoreWindow(ws[0].tl)
            return
        }
        launch(cls)
    }

    function togglePin(cls) {
        const p = (config.pinned || []).slice()
        const i = pinnedIndex(cls)
        if (i >= 0) p.splice(i, 1)
        else {
            const e = entryFor(cls, null)
            p.push(e && e.id ? { "class": cls, "desktop": e.id } : { "class": cls })
        }
        config.pinned = p
        saveConfig()
    }

    // --- dragging an icon: reorder the pins, or pull one off the dock ---------------------
    // The app list never changes while a drag is in flight, because rebuilding the icon
    // being held would drop the drag. The others slide to where the drop will put them
    // instead (dragShiftFor), and the new order is written once, on release.
    property string dragCls: ""
    property string dragScreen: ""
    property int dragTo: -1
    property bool dragOut: false
    property real dragX: 0
    property real dragY: 0
    property real dragSize: 0
    property real dragFade: 1
    // Off for the frame a drop lands in, so the icons do not slide back from their shifted
    // places while the new order puts them there anyway.
    property bool dragAnimate: true
    // After the drop, while the held icon glides into its slot. The new order is already
    // laid out, so nothing else moves.
    property bool dragSettling: false
    // Whether the held app has no icon left after the drop, so it fades instead of landing.
    property bool dragGone: false
    signal dragSettle()
    signal dragSettleStop()

    // The pin list as the dock shows it: entries with a class, each class once. Positions
    // in it are the visible positions, which a raw list with a duplicate or a skipped entry
    // breaks: with pins [a, a, b, c], dropping c back on its own slot rewrote the order.
    function pinsShown() {
        const out = [], seen = Object.create(null)
        const p = config.pinned || []
        for (let i = 0; i < p.length; i++) {
            const e = p[i]
            if (!e || !e["class"] || seen[e["class"]]) continue
            seen[e["class"]] = true
            out.push(e)
        }
        return out
    }

    // The pin list a drop would leave, from the drag as it stands. The drop writes exactly
    // this, and the preview is laid out from it, so the two cannot disagree.
    function pinnedAfterDrop() {
        const p = pinsShown()
        const at = p.findIndex(e => e["class"] === dragCls)
        if (dragOut) {
            // A running app taken off the dock remains visible until it closes.
            if (at >= 0) p.splice(at, 1)
        } else if (at >= 0) {
            if (dragTo !== at) { const e = p.splice(at, 1)[0]; p.splice(dragTo, 0, e) }
        } else if (dragTo <= p.length) {
            // A running app dropped among the pins is kept in the dock there.
            const e = entryFor(dragCls, null)
            p.splice(dragTo, 0, e && e.id ? { "class": dragCls, "desktop": e.id } : { "class": dragCls })
        }
        return p
    }

    // Where each item will sit after the drop, against where it sits now. Items are named,
    // not counted, so a list that re-indexes mid-drag (a running app closing) cannot shift
    // the wrong icon. The dock stays centred, so a drop that adds or removes a slot moves
    // its left edge by half a slot, and every offset carries that half.
    function previewFor() {
        if (!dragCls || dragSettling) return null
        const after = appsFor(pinnedAfterDrop())
        const slot = iconSize + gap
        const half = (apps.length - after.length) * slot / 2
        const shift = Object.create(null)
        for (let i = 0; i < apps.length; i++) {
            const j = after.indexOf(apps[i])
            shift[apps[i]] = j < 0 ? 0 : (j - i) * slot + half
        }
        return { shift: shift, tail: (after.length - apps.length) * slot + half,
                 width: (after.length - apps.length) * slot }
    }
    readonly property var dropPreview: previewFor()

    // How far an icon slides to show the drop's layout; the divider and the minimized
    // windows slide by the tail.
    function dragShiftFor(cls) {
        return dropPreview && cls !== dragCls ? (dropPreview.shift[cls] || 0) : 0
    }

    // If the held app's icon goes away mid-drag (its last window closed and it is not
    // pinned), its press goes with it and no release will come, so end the drag here.
    onAppsChanged: if (dragCls && !dragSettling && apps.indexOf(dragCls) < 0) endDrag(false)

    function pinnedShown() {
        return apps.filter(c => pinnedIndex(c) >= 0).length
    }

    // The drop. The new order and the cleared slides land in the same frame, and the dock
    // is flat while an icon is held (no magnification), so every icon is exactly where the
    // slide had put it: nothing jumps. Then the held icon glides into its slot (the panel's
    // settle), and only after that does it become the real icon again.
    function endDrag(commit) {
        const cls = dragCls
        if (!cls || dragSettling) return
        dragAnimate = false
        if (commit) {
            // Written only when the visible order changes, so a drop that moves nothing
            // leaves the saved configuration unchanged, including duplicate entries.
            const p = pinnedAfterDrop()
            if (JSON.stringify(p) !== JSON.stringify(pinsShown())) {
                config.pinned = p
                saveConfig()
            }
        }
        dragGone = pinnedIndex(cls) < 0 && windowsOf(cls).length === 0
        dragSettling = true
        dragSettle()
    }

    function finishDrag() {
        dragCls = ""
        dragSettling = false
        dragGone = false
        dragFade = 1
        Qt.callLater(() => { root.dragAnimate = true })
    }

    // Menu actions are plain ids, because JavaScript functions do not survive being
    // handed to a Repeater as model data.
    function menuActions(cls, addr) {
        if (addr) return [
            { id: "restore-one", text: "Restore" },
            { id: "close-one", text: "Close Window", danger: true }
        ]
        const ws = windowsOf(cls)
        const shown = ws.filter(w => !w.minimized)
        const pinned = pinnedIndex(cls) >= 0
        const out = []
        // Mark the active window and minimized windows before listing actions.
        // Choosing a window brings it forward.
        for (let i = 0; i < ws.length; i++) {
            const w = ws[i]
            out.push({ id: "win:" + address(w.tl), text: w.tl.title || nameFor(cls),
                       mark: w.minimized ? "◆" : (w.tl.activated ? "✓" : "") })
        }
        if (ws.length > 0) out.push({ id: "sep", sep: true })
        out.push({ id: "launch", text: ws.length > 0 ? "New Window" : "Open" })
        if (shown.length > 0) out.push({ id: "minimize-all", text: shown.length > 1 ? "Minimize All" : "Minimize" })
        if (ws.length > shown.length) out.push({ id: "restore-all", text: "Restore" })
        // Unpinned running apps remain visible until they close, so pinning is the
        // action that changes whether they remain after closing.
        out.push({ id: "pin", text: pinned ? "Remove from Dock" : "Keep in Dock" })
        if (ws.length > 0) out.push({ id: "quit", text: ws.length > 1 ? "Quit (" + ws.length + " windows)" : "Quit", danger: true })
        return out
    }

    function runAction(id, cls, addr) {
        const candidate = addr ? windowAt(addr) : null
        const w = candidate && candidate.cls === cls ? candidate : null
        const ws = windowsOf(cls)
        if (id.indexOf("win:") === 0) {
            const picked = windowAt(id.slice(4))
            if (picked && picked.cls === cls) {
                if (picked.minimized) restoreWindow(picked.tl)
                else focusWindow(picked.tl)
            }
            return
        }
        switch (id) {
        case "restore-one": if (w) restoreWindow(w.tl); break
        case "close-one": if (w) closeWindow(w.tl); break
        case "launch": launch(cls); break
        case "minimize-all": ws.filter(x => !x.minimized).forEach(x => minimizeWindow(x.tl)); break
        case "restore-all": ws.filter(x => x.minimized).forEach(x => restoreWindow(x.tl)); break
        case "pin": togglePin(cls); break
        case "quit": quitApp(cls); break
        }
    }

    // --- the dock, one per screen --------------------------------------------------------------
    Variants {
        model: Quickshell.screens

        PanelWindow {
            id: panel
            required property var modelData
            screen: modelData

            readonly property real fittedSize: Motion.fitSize(root.iconSize, root.apps.length + root.minimizedAddresses.length, modelData.width)
            property real dragSizeLock: 0
            readonly property real targetSize: root.dragCls && dragSizeLock > 0 ? dragSizeLock : fittedSize
            property real iconSize: targetSize
            Behavior on iconSize {
                enabled: panel.targetSize > panel.iconSize
                NumberAnimation { duration: 160; easing.type: Easing.OutCubic }
            }
            Connections {
                target: root
                function onDragClsChanged() {
                    if (root.dragCls && panel.dragSizeLock === 0) panel.dragSizeLock = panel.iconSize
                    else if (!root.dragCls) panel.dragSizeLock = 0
                }
            }
            readonly property real gap: Motion.metric(iconSize, 0.14)
            readonly property real pad: Motion.metric(iconSize, 0.18)
            readonly property real slotRatio: (iconSize + gap) / (root.iconSize + root.gap)
            readonly property real restWidth: Motion.restWidth(root.apps.length + root.minimizedAddresses.length, iconSize, gap, pad)
            readonly property real restHeight: iconSize + root.dotSpace + pad * 2

            anchors.bottom: true
            color: "transparent"
            implicitWidth: Math.min(modelData.width, Math.ceil(restWidth * root.magnification) + 260)
            implicitHeight: restHeight + root.bottomGap + root.lift
            exclusiveZone: restHeight + root.bottomGap
            mask: Region { item: zone }
            //@ if env("OMARCHY_DOCK_BACKEND") !== "x11"
            WlrLayershell.namespace: "omarchy-dock"
            WlrLayershell.layer: WlrLayer.Top
            //@ endif

            property real pointerSceneX: 0
            property real pointerSceneY: 0
            readonly property real pointerX: pointerSceneX - (width - restWidth) / 2
            readonly property bool hovering: dockHover.hovered
                && pointerSceneX >= zone.x && pointerSceneX <= zone.x + zone.width
                && pointerSceneY >= height - zone.height && pointerSceneY <= height
            property bool iconPressed: false
            property var motionState: ({ center: 0, strength: 0 })
            readonly property bool flattening: root.dragCls !== "" || root.editing
            readonly property real targetStrength: hovering && !flattening ? 1 : 0
            readonly property var geometry: Motion.layout(root.apps.length, root.minimizedAddresses.length,
                iconSize, gap, pad, root.magnification, motionState.center, motionState.strength, width)
            readonly property int hoverIndex: hovering && !iconPressed && !flattening && !menu.visible
                ? Motion.hit(geometry, pointerSceneX, pointerSceneY, height - root.bottomGap - pad, root.dotSpace) : -1

            // One snapshot drives every icon and the glass; no live child measurement can
            // steer the next frame or restart a neighbour's easing curve.
            FrameAnimation {
                running: !menu.visible && !Motion.settled(panel.motionState, panel.pointerX, panel.targetStrength, panel.flattening)
                onTriggered: panel.motionState = Motion.advance(panel.motionState, panel.pointerX,
                    panel.targetStrength, frameTime, panel.flattening)
            }

            function followPointer() {
                if (hovering && !flattening && !menu.visible)
                    motionState = Motion.track(motionState, pointerX)
            }

            function hoveredIcon() {
                const i = hoverIndex
                if (i < 0) return null
                return i < root.apps.length ? appRepeater.itemAt(i) : minRepeater.itemAt(i - root.apps.length - 1)
            }

            onHoverIndexChanged: {
                if (hoverIndex < 0) {
                    tipDelay.stop()
                    tooltip.fadingLabel = tooltip.label
                    tooltip.shown = false
                } else if (tooltip.shown) {
                    tooltip.slotIndex = hoverIndex
                    tooltip.item = hoveredIcon()
                } else tipDelay.restart()
            }

            // ScriptModel preserves delegates while their numeric slots change. Resolve
            // the painted slot after its model update, even if hoverIndex did not change.
            Connections {
                target: root
                function onAppsChanged() { Qt.callLater(panel.refreshTooltip) }
                function onMinimizedAddressesChanged() { Qt.callLater(panel.refreshTooltip) }
            }
            function refreshTooltip() {
                if (!tooltip.shown) return
                const item = hoveredIcon()
                if (item) {
                    tooltip.slotIndex = hoverIndex
                    tooltip.item = item
                } else {
                    tooltip.fadingLabel = tooltip.label
                    tooltip.shown = false
                }
            }

            function beginDrag(cls, index) {
                // A drag that starts while the last drop is still gliding in lands that drop
                // now, so its animation can neither steer this drag nor end it.
                if (root.dragSettling) {
                    root.dragSettleStop()
                    root.finishDrag()
                }
                root.dragAnimate = true
                root.dragSettling = false
                root.dragGone = false
                root.dragFade = 1
                root.dragSize = Math.round(panel.iconSize * 1.15)
                root.dragScreen = panel.modelData.name
                root.dragTo = index
                root.dragOut = false
                root.dragCls = cls
            }

            // Dragging flattens magnification, so drop slots use resting coordinates.
            // A pin lands among the pins; a running app may land anywhere, and is
            // kept in the dock only if it lands among them.
            function moveDrag(x, y) {
                // From the panel's centre: a drop that removes a slot resizes an unclamped
                // panel, which recentres, and window coordinates would make the fading icon
                // jump by half the change. The centre stays put on screen.
                root.dragX = x - panel.width / 2
                root.dragY = y
                const s = panel.iconSize, g = panel.gap
                const restX = x - (panel.width - panel.restWidth) / 2
                const last = root.pinnedIndex(root.dragCls) >= 0
                    ? Math.max(0, root.pinnedShown() - 1) : root.apps.length - 1
                root.dragTo = Math.max(0, Math.min(last, Math.round((restX - panel.pad - s / 2) / (s + g))))
                root.dragOut = y < panel.height - root.bottomGap - panel.restHeight - s * 0.8
            }

            // Where an app's icon rests in the flat dock, from the layout's own arithmetic. The
            // dock flattens over 110 ms once an icon is held, so sampling the icons after a
            // quick flick read them mid-animation and the glide ended beside its slot.
            // The dock stays flat until the glide ends, so this is where it lands. x is
            // from the panel's centre, as dragX is.
            function landingFor(cls) {
                const k = root.apps.indexOf(cls)
                if (k < 0) return null
                const s = panel.iconSize
                return { x: -panel.restWidth / 2 + panel.pad + k * (s + panel.gap) + s / 2,
                         y: panel.height - root.bottomGap - panel.pad - root.dotSpace - s / 2,
                         size: s }
            }

            // The glide after a drop: the held icon flies from the pointer into its own slot
            // at its own size, and only then shows as the real icon. An app left with no icon
            // fades instead.
            function settle() {
                const t = root.dragGone ? null : panel.landingFor(root.dragCls)
                if (!t) {
                    fadeAway.restart()
                    return
                }
                glideX.to = t.x
                glideY.to = t.y
                glideSize.to = t.size
                glide.restart()
            }
            Connections {
                target: root
                function onDragSettle() { if (root.dragScreen === panel.modelData.name) panel.settle() }
                function onDragSettleStop() {
                    glide.stop()
                    fadeAway.stop()
                }
            }
            // A screen that goes away takes this panel, its glide and any held icon with it,
            // while the shared drag state lives on in the Scope. Clear it here, or the dock
            // stays flat with an icon hidden.
            Component.onDestruction: if (root.dragCls && root.dragScreen === (panel.modelData ? panel.modelData.name : "")) root.finishDrag()
            ParallelAnimation {
                id: glide
                NumberAnimation { id: glideX; target: root; property: "dragX"; duration: 180; easing.type: Easing.OutCubic }
                NumberAnimation { id: glideY; target: root; property: "dragY"; duration: 180; easing.type: Easing.OutCubic }
                NumberAnimation { id: glideSize; target: root; property: "dragSize"; duration: 180; easing.type: Easing.OutCubic }
                onFinished: root.finishDrag()
            }
            NumberAnimation {
                id: fadeAway
                target: root
                property: "dragFade"
                to: 0
                duration: 160
                easing.type: Easing.OutCubic
                onFinished: root.finishDrag()
            }

            // The handler's frame never moves. The input mask always contains the resting
            // shelf and retains the raised area until the wave has finished settling.
            Item {
                id: inputFrame
                anchors.fill: parent
                HoverHandler {
                    id: dockHover
                    blocking: false
                    onPointChanged: {
                        panel.pointerSceneX = point.scenePosition.x
                        panel.pointerSceneY = point.scenePosition.y
                        panel.followPointer()
                    }
                    onHoveredChanged: panel.followPointer()
                }
                Item {
                    id: zone
                    x: Math.min((panel.width - panel.restWidth) / 2, panel.geometry.left)
                    width: Math.max((panel.width + panel.restWidth) / 2, panel.geometry.left + panel.geometry.width) - x
                    anchors.bottom: parent.bottom
                    height: panel.restHeight + root.bottomGap
                        + (panel.motionState.strength > 0 || menu.visible ? root.lift - 36 : 0)

                    // A soft shadow under the glass, built from layered rectangles so it needs
                    // no effect pipeline.
                    Repeater {
                        model: 5
                        Rectangle {
                            required property int index
                            anchors.horizontalCenter: dock.horizontalCenter
                            anchors.bottom: dock.bottom
                            anchors.bottomMargin: -2 - index * 2
                            width: dock.width + index * 4
                            height: dock.height + index * 2
                            radius: dock.radius + index * 2
                            color: Qt.rgba(0, 0, 0, 0.045 - index * 0.008)
                        }
                    }

                    Rectangle {
                        id: dock
                        x: panel.geometry.left - zone.x - previewWidth / 2
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: root.bottomGap
                        // During a drag the glass takes the width the drop will leave, centred,
                        // so nothing changes size when the drop lands.
                        property real previewWidth: root.dropPreview ? root.dropPreview.width * panel.slotRatio : 0
                        Behavior on previewWidth { enabled: root.dragAnimate; NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                        width: panel.geometry.width + previewWidth
                        height: panel.restHeight
                        radius: Math.round(panel.iconSize * 0.28)
                        // Translucent theme background; Hyprland blurs what shows through it.
                        color: Qt.rgba(root.palette.background.r, root.palette.background.g, root.palette.background.b, 0.46)
                        border.width: 1
                        border.color: Qt.rgba(root.palette.foreground.r, root.palette.foreground.g, root.palette.foreground.b, 0.14)

                        // The glass sheen: a soft highlight along the top edge.
                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: 1
                            radius: parent.radius - 1
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.09) }
                                GradientStop { position: 0.4; color: Qt.rgba(1, 1, 1, 0.03) }
                                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.0) }
                            }
                        }

                        Item {
                            id: row
                            x: panel.pad + dock.previewWidth / 2
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: panel.pad
                            width: panel.geometry.width - panel.pad * 2
                            height: panel.iconSize * root.magnification + root.dotSpace

                            Repeater {
                                id: appRepeater
                                // ScriptModel diffs, so an icon survives window events instead of
                                // being destroyed and rebuilt, which would flash every icon.
                                model: ScriptModel { values: root.apps }
                                DockIcon {
                                    palette: root.palette
                                    reducedMotion: config.reducedMotion
                                    id: appIcon
                                    required property string modelData
                                    required property int index
                                    baseSize: panel.iconSize
                                    dotSpace: root.dotSpace
                                    readonly property var slot: panel.geometry.items[index]
                                    x: slot ? slot.x - panel.pad : index * (panel.iconSize + panel.gap)
                                    y: row.height - height
                                    size: slot ? slot.width : panel.iconSize
                                    iconSource: root.iconFor(modelData)
                                    label: root.nameFor(modelData)
                                    running: root.windowsOf(modelData).length > 0
                                    active: root.windowsOf(modelData).some(w => w.tl.activated && !w.minimized)
                                    draggable: true
                                    held: root.dragCls === modelData
                                    dragShift: root.dragShiftFor(modelData) * panel.slotRatio
                                    dragAnimate: root.dragAnimate
                                    originX: panel.width / 2
                                    onPressChanged: pressed => panel.iconPressed = pressed
                                    onLeftClicked: root.activateApp(modelData)
                                    onMiddleClicked: root.launch(modelData)
                                    onRightClicked: menu.openFor(appIcon, modelData, "")
                                    onDragStarted: panel.beginDrag(modelData, index)
                                    onDragMoved: (x, y) => panel.moveDrag(x, y)
                                    // Later, not inside the release: a drop can remove this very
                                    // icon, and its handler should finish first.
                                    onDragEnded: Qt.callLater(() => root.endDrag(true))
                                    onDragCanceled: root.endDrag(false)
                                    Connections {
                                        target: root
                                        function onLaunched(cls) { if (cls === appIcon.modelData) appIcon.bounce() }
                                    }
                                }
                            }

                            // Drag the divider vertically to resize the dock.
                            Item {
                                id: divider
                                x: panel.geometry.items[root.apps.length]
                                    ? panel.geometry.items[root.apps.length].x - panel.pad
                                    : root.apps.length * (panel.iconSize + panel.gap)
                                y: row.height - height
                                width: 12
                                height: panel.iconSize
                                // Slides with the icons to where the drop will put it.
                                transform: Translate {
                                    x: root.dropPreview ? root.dropPreview.tail * panel.slotRatio : 0
                                    Behavior on x { enabled: root.dragAnimate; NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                                }
                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 1
                                    height: parent.height * 0.62
                                    color: Qt.rgba(root.palette.foreground.r, root.palette.foreground.g, root.palette.foreground.b, resize.containsMouse || resize.pressed ? 0.55 : 0.26)
                                }
                                MouseArea {
                                    id: resize
                                    anchors.fill: parent
                                    anchors.margins: -4
                                    hoverEnabled: true
                                    cursorShape: Qt.SizeVerCursor
                                    property real startY: 0
                                    property real startSize: 0
                                    onPressed: m => {
                                        root.editing = true
                                        startY = mapToGlobal(m.x, m.y).y
                                        startSize = config.iconSize
                                    }
                                    onPositionChanged: m => {
                                        if (!pressed) return
                                        const dy = mapToGlobal(m.x, m.y).y - startY
                                        config.iconSize = Math.round(Math.max(32, Math.min(96, startSize - dy)))
                                    }
                                    onReleased: {
                                        root.saveConfig()
                                        root.editing = false
                                    }
                                    onCanceled: {
                                        root.saveConfig()
                                        root.editing = false
                                    }
                                }
                            }

                            Repeater {
                                id: minRepeater
                                model: ScriptModel { values: root.minimizedAddresses }
                                DockIcon {
                                    palette: root.palette
                                    reducedMotion: config.reducedMotion
                                    id: minIcon
                                    required property string modelData
                                    required property int index
                                    readonly property var win: root.windowAt(modelData)
                                    baseSize: panel.iconSize
                                    dotSpace: root.dotSpace
                                    readonly property var slot: panel.geometry.items[root.apps.length + index + 1]
                                    x: slot ? slot.x - panel.pad : (root.apps.length + index) * (panel.iconSize + panel.gap) + 12 + panel.gap
                                    y: row.height - height
                                    size: slot ? slot.width : panel.iconSize
                                    iconSource: win ? root.iconFor(win.cls) : ""
                                    label: win ? root.nameFor(win.cls) + (win.tl.title ? " · " + win.tl.title : "") : ""
                                    minimizedStyle: true
                                    dragShift: root.dropPreview ? root.dropPreview.tail * panel.slotRatio : 0
                                    dragAnimate: root.dragAnimate
                                    onPressChanged: pressed => panel.iconPressed = pressed
                                    onLeftClicked: if (win) root.restoreWindow(win.tl)
                                    onRightClicked: if (win) menu.openFor(minIcon, win.cls, modelData)
                                }
                            }
                        }
                    }
                }

                Timer {
                    id: tipDelay
                    interval: 150
                    onTriggered: {
                        const item = panel.hoveredIcon()
                        if (!item) return
                        tooltip.slotIndex = panel.hoverIndex
                        tooltip.item = item
                        tooltip.shown = true
                    }
                }
                Rectangle {
                    id: tooltip
                    property bool shown: false
                    property string fadingLabel: ""
                    readonly property string label: shown && item ? item.label : fadingLabel
                    property int slotIndex: -1
                    property var item: null
                    opacity: shown ? 1 : 0
                    visible: opacity > 0
                    Behavior on opacity { NumberAnimation { duration: tooltip.shown ? 90 : 80 } }
                    width: Math.min(tip.implicitWidth + 20, panel.width - 12, 340)
                    height: tip.implicitHeight + 10
                    x: item && panel.geometry.items[slotIndex] ? Math.max(6, Math.min(panel.width - width - 6,
                        panel.geometry.left + panel.geometry.items[slotIndex].x + item.width / 2 - width / 2)) : 6
                    y: item ? Math.max(0, panel.height - root.bottomGap - panel.pad - root.dotSpace
                        - item.size - item.hop - height - 10) : 0
                    radius: 7
                    color: Qt.rgba(root.palette.background.r, root.palette.background.g, root.palette.background.b, 0.92)
                    border.width: 1
                    border.color: Qt.rgba(root.palette.foreground.r, root.palette.foreground.g, root.palette.foreground.b, 0.14)
                    Text {
                        id: tip
                        anchors.centerIn: parent
                        width: parent.width - 20
                        text: tooltip.label
                        color: root.palette.foreground
                        font.pixelSize: 12
                        font.weight: Font.Medium
                        elide: Text.ElideRight
                    }
                }
            }

            // The icon being dragged, under the pointer and above the dock. Pulled off the top
            // it fades and says Remove when releasing would unpin it. The label
            // sits below the icon because the surface ends just above the dock.
            Item {
                visible: root.dragCls !== "" && root.dragScreen === panel.modelData.name
                z: 10
                width: root.dragSize
                height: width
                x: panel.width / 2 + root.dragX - width / 2
                y: root.dragY - height / 2
                Image {
                    anchors.fill: parent
                    fillMode: Image.PreserveAspectFit
                    sourceSize: Qt.size(Math.ceil(panel.iconSize * 2.2), Math.ceil(panel.iconSize * 2.2))
                    source: root.dragCls ? root.iconFor(root.dragCls) : ""
                    mipmap: true
                    opacity: (root.dragOut && !root.dragSettling ? 0.55 : 0.95) * root.dragFade
                }
                Rectangle {
                    visible: root.dragOut && !root.dragSettling && root.pinnedIndex(root.dragCls) >= 0
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.top: parent.bottom
                    anchors.topMargin: 6
                    width: removeText.implicitWidth + 20
                    height: removeText.implicitHeight + 10
                    radius: height / 2
                    color: Qt.rgba(root.palette.background.r, root.palette.background.g, root.palette.background.b, 0.92)
                    border.width: 1
                    border.color: Qt.rgba(root.palette.foreground.r, root.palette.foreground.g, root.palette.foreground.b, 0.14)
                    Text {
                        id: removeText
                        anchors.centerIn: parent
                        text: "Remove"
                        color: root.palette.foreground
                        font.pixelSize: 12
                        font.weight: Font.Medium
                    }
                }
            }

            Rectangle {
                visible: !!root.backend && !!root.backend.errorText
                anchors.horizontalCenter: parent.horizontalCenter
                y: 4
                width: serviceError.implicitWidth + 24
                height: serviceError.implicitHeight + 16
                radius: 8
                color: root.palette.background
                Text {
                    id: serviceError
                    anchors.centerIn: parent
                    text: root.backend ? root.backend.errorText : ""
                    color: root.palette.foreground
                    font.pixelSize: 12
                }
            }

            // --- right-click menu ------------------------------------------------------------
            PopupWindow {
                id: menu
                grabFocus: true
                property string cls: ""
                property string addr: ""     // set for a minimized-window icon
                // A snapshot taken when the menu opens. Binding the list to live state
                // would rebuild the rows, and destroy the one being clicked, the moment
                // an action changed that state.
                property var items: []
                visible: false
                onVisibleChanged: if (!visible) panel.followPointer()
                color: "transparent"
                anchor.window: panel
                anchor.edges: Edges.Top
                anchor.gravity: Edges.Top
                implicitWidth: menuBox.implicitWidth
                implicitHeight: menuBox.implicitHeight

                function openFor(item, cls, addr) {
                    menu.cls = cls
                    menu.addr = addr
                    menu.items = root.menuActions(cls, addr)
                    const p = item.mapToItem(null, 0, 0)
                    anchor.rect.x = p.x
                    anchor.rect.y = p.y - 8
                    anchor.rect.width = item.width
                    anchor.rect.height = 1
                    menu.visible = true
                }

                Rectangle {
                    id: menuBox
                    // Wide enough for a window title, never so wide a long one swamps the screen.
                    implicitWidth: Math.min(360, Math.max(200, col.implicitWidth + 12))
                    implicitHeight: col.implicitHeight + 12
                    radius: 12
                    color: Qt.rgba(root.palette.background.r, root.palette.background.g, root.palette.background.b, 0.94)
                    border.width: 1
                    border.color: Qt.rgba(root.palette.foreground.r, root.palette.foreground.g, root.palette.foreground.b, 0.14)

                    ColumnLayout {
                        id: col
                        anchors.centerIn: parent
                        width: parent.width - 12
                        spacing: 1

                        Text {
                            Layout.fillWidth: true
                            Layout.leftMargin: 10
                            Layout.topMargin: 2
                            Layout.bottomMargin: 3
                            text: root.nameFor(menu.cls)
                            color: Qt.rgba(root.palette.foreground.r, root.palette.foreground.g, root.palette.foreground.b, 0.5)
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }

                        Repeater {
                            model: menu.items
                            Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                implicitWidth: modelData.sep ? 0 : rowText.implicitWidth + 36
                                implicitHeight: modelData.sep ? 9 : 30
                                radius: 7
                                color: !modelData.sep && hover.containsMouse ? Qt.rgba(root.palette.accent.r, root.palette.accent.g, root.palette.accent.b, 0.22) : "transparent"
                                // A hairline between the window list and the app's actions.
                                Rectangle {
                                    visible: !!modelData.sep
                                    anchors.centerIn: parent
                                    width: parent.width - 16
                                    height: 1
                                    color: Qt.rgba(root.palette.foreground.r, root.palette.foreground.g, root.palette.foreground.b, 0.14)
                                }
                                // Reserve a mark column on every row so the
                                // titles line up whether or not a row carries a mark.
                                Text {
                                    visible: !modelData.sep
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.left: parent.left
                                    anchors.leftMargin: 9
                                    text: modelData.mark || ""
                                    color: root.palette.foreground
                                    font.pixelSize: 12
                                }
                                Text {
                                    id: rowText
                                    visible: !modelData.sep
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.left: parent.left
                                    anchors.leftMargin: 26
                                    width: Math.min(implicitWidth, parent.width - 36)
                                    text: modelData.text || ""
                                    color: modelData.danger ? root.palette.urgent : root.palette.foreground
                                    font.pixelSize: 13
                                    elide: Text.ElideRight
                                }
                                MouseArea {
                                    id: hover
                                    anchors.fill: parent
                                    enabled: !modelData.sep
                                    hoverEnabled: true
                                    onClicked: {
                                        // Capture everything first: hiding the menu can tear
                                        // this row down, and a handler whose row is gone can
                                        // no longer see the dock. The action runs after.
                                        const dock = root
                                        const id = modelData.id
                                        const c = menu.cls
                                        const a = menu.addr
                                        menu.visible = false
                                        Qt.callLater(() => dock.runAction(id, c, a))
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // --- one icon ---------------------------------------------------------------------------
    // Inline components cannot see this file's ids, so everything they need is passed in.
    component DockIcon: Item {
        id: icon
        required property var palette
        property bool reducedMotion: false
        property real baseSize: 52
        property real dotSpace: 8
        property string iconSource
        property string label
        property bool running
        property bool active
        property bool minimizedStyle
        property bool draggable
        property bool held             // the icon being dragged: its slot shows as the gap
        property real dragShift: 0     // slides aside to open or close a gap
        property bool dragAnimate: true
        property real originX: 0       // the panel's centre, in window terms
        signal leftClicked()
        signal middleClicked()
        signal rightClicked()
        signal pressChanged(bool pressed)
        signal dragStarted()
        signal dragMoved(real x, real y)
        signal dragEnded()
        signal dragCanceled()

        opacity: held ? 0 : 1
        // A transform, not a layout change: the layout, and the magnification read from it,
        // stay exactly as they were while icons slide aside for a drag.
        transform: Translate {
            x: icon.dragShift
            Behavior on x { enabled: icon.dragAnimate; NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        }

        property real size: baseSize
        width: size
        height: size + dotSpace

        property real hop: 0
        function bounce() {
            if (!running && !held && !reducedMotion) {
                land.stop()
                hopAnim.restart()
            }
        }
        function landBounce() {
            hopAnim.stop()
            if (hop > 0) land.restart()
        }
        onRunningChanged: if (running) landBounce()
        onHeldChanged: if (held) landBounce()
        SequentialAnimation {
            id: hopAnim
            loops: 3
            NumberAnimation { target: icon; property: "hop"; to: icon.baseSize * 0.35; duration: 240; easing.type: Easing.OutQuad }
            NumberAnimation { target: icon; property: "hop"; to: 0; duration: 280; easing.type: Easing.InOutSine }
            PauseAnimation { duration: 100 }
        }
        NumberAnimation {
            id: land
            target: icon
            property: "hop"
            to: 0
            duration: 120
            easing.type: Easing.OutCubic
        }

        Image {
            id: img
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: icon.dotSpace + icon.hop
            width: icon.size
            height: icon.size
            fillMode: Image.PreserveAspectFit
            sourceSize: Qt.size(Math.ceil(icon.baseSize * 2.2), Math.ceil(icon.baseSize * 2.2))
            source: icon.iconSource
            mipmap: true
            asynchronous: false
            opacity: icon.minimizedStyle ? 0.88 : 1.0
            scale: mouse.pressed ? 0.97 : 1.0
            Behavior on scale { NumberAnimation { duration: 70; easing.type: Easing.OutCubic } }
        }

        // Darken slightly while pressed to show immediate click feedback.
        Rectangle {
            anchors.fill: img
            radius: width * 0.22
            color: Qt.rgba(0, 0, 0, mouse.pressed ? 0.18 : 0)
            scale: img.scale
        }

        // A dot under a running app, a ring under a minimized window.
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 1
            width: 4
            height: 4
            radius: 2
            visible: icon.running || icon.minimizedStyle
            color: icon.minimizedStyle ? "transparent"
                : icon.active ? icon.palette.accent
                : Qt.rgba(icon.palette.foreground.r, icon.palette.foreground.g, icon.palette.foreground.b, 0.8)
            border.width: icon.minimizedStyle ? 1 : 0
            border.color: Qt.rgba(icon.palette.foreground.r, icon.palette.foreground.g, icon.palette.foreground.b, 0.75)
        }

        MouseArea {
            id: mouse
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
            onPressedChanged: icon.pressChanged(pressed)
            // A left press that travels more than 6 px becomes a drag, so a slightly shaky
            // click is still a click. Measure from the stable panel centre: moving icon
            // bounds and a recentered panel edge can otherwise turn a small movement
            // into a false drag. The grab stays with this item while it is held, so it follows the pointer
            // even off the dock.
            property point pressScene
            property bool dragging: false
            onPressed: m => {
                const p = mapToItem(null, m.x, m.y)
                pressScene = Qt.point(p.x - icon.originX, p.y)
                dragging = false
            }
            onPositionChanged: m => {
                if (!icon.draggable || !(pressedButtons & Qt.LeftButton)) return
                const p = mapToItem(null, m.x, m.y)
                if (!dragging) {
                    if (Math.abs(p.x - icon.originX - pressScene.x) + Math.abs(p.y - pressScene.y) < 6) return
                    dragging = true
                    icon.dragStarted()
                }
                icon.dragMoved(p.x, p.y)
            }
            onReleased: if (dragging) icon.dragEnded()
            onCanceled: if (dragging) { dragging = false; icon.dragCanceled() }
            onClicked: m => {
                // The release that ends a drag is not a click.
                if (dragging) { dragging = false; return }
                if (m.button === Qt.RightButton) icon.rightClicked()
                else if (m.button === Qt.MiddleButton) icon.middleClicked()
                else icon.leftClicked()
            }
        }
    }
}
