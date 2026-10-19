import QtQuick
import qs.Commons

Hyprland {
    palette: QtObject {
        readonly property color background: Color.background
        readonly property color foreground: Color.foreground
        readonly property color accent: Color.accent
        readonly property color urgent: Color.urgent
    }
}
