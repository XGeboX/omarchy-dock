//@ pragma ShellId omarchy-dock-standalone
import Quickshell
import "plugin"

ShellRoot {
    Dock {
        backendName: {
            const name = Quickshell.env("OMARCHY_DOCK_BACKEND")
            return name === "hyprland" ? "Hyprland" : name === "wlr" ? "Wlr" : "Bridge"
        }
    }
}
