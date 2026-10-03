import QtQuick
import "../design"
import "../design/controls" as Controls

// Rounded chrome buttons use a quiet surface and brighter ink when selected.
Controls.Button {
  property color surfaceColor: Color.token("toolbar.background")
  property color contentForeground: Color.token("button.foreground")
  radius: Style.controlRadius
  foreground: Style.secondaryText(contentForeground, 0.72)
  selectedForeground: contentForeground
  hoverColor: Qt.tint(surfaceColor, Util.alpha(contentForeground, selected || active ? 0.14 : 0.08))
  pressedColor: Qt.tint(surfaceColor, Util.alpha(contentForeground, 0.18))
  selectedColor: Qt.tint(surfaceColor, Util.alpha(contentForeground, 0.10))
}
