// KWin 6 scripting integration. No compositor configuration is changed.
function publish() {
    var result = workspace.windowList().filter(function (w) {
        return !w.skipTaskbar && !w.dock && !w.desktopWindow && String(w.resourceClass);
    }).map(function (w) {
        return { cls: String(w.resourceClass), minimized: w.minimized,
            tl: { address: String(w.internalId), title: w.caption,
                activated: workspace.activeWindow === w } };
    });
    callDBus("org.xgebox.OmarchyDock", "/org/xgebox/OmarchyDock",
        "org.xgebox.OmarchyDock", "Update", JSON.stringify(result));
}
function watch(w) {
    w.minimizedChanged.connect(publish);
    w.captionChanged.connect(publish);
    w.windowClassChanged.connect(publish);
    w.skipTaskbarChanged.connect(publish);
}
workspace.windowList().forEach(watch);
workspace.windowAdded.connect(function (w) { watch(w); publish(); });
workspace.windowRemoved.connect(publish);
workspace.windowActivated.connect(publish);
publish();

// Observe the unique bridge owner so a crash or replacement cannot retain
// compositor watchers for the rest of the desktop session.
var ownerWatch = new QTimer();
ownerWatch.interval = 2000;
ownerWatch.timeout.connect(function () {
    callDBus("org.freedesktop.DBus", "/org/freedesktop/DBus",
        "org.freedesktop.DBus", "NameHasOwner", dockOwner, function (alive) {
            if (!alive) {
                ownerWatch.stop();
                callDBus("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", "unloadScript", dockScript);
            }
        });
});
ownerWatch.start();
