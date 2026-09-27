import QtQuick
import "../design"
import "../design/controls" as Controls

// Shared typography, spacing and surface for search, commands and tool forms.
Controls.TextField {
  id: field
  property color surfaceBackground: Color.menu.background
  property bool focusBorderVisible: activeFocus
  foreground: Color.menu.text
  implicitHeight: Math.max(controlStyle.height, contentHeight + topPadding + bottomPadding)
  font.family: Style.font.menuFamily
  font.pixelSize: Style.font.body
  verticalPadding: Style.spacing.xs
  placeholderTextColor: Color.token("input.placeholder", Util.alpha(foreground, 0.45))

  ChromeControlStyle {
    id: controlStyle
    background: field.surfaceBackground
    foreground: field.foreground
  }

  background: Rectangle {
    objectName: "searchSurface"
    radius: controlStyle.radius
    color: controlStyle.fill
    border.width: controlStyle.borderWidth
    border.color: field.focusBorderVisible ? controlStyle.focusBorderColor : controlStyle.borderColor
  }
}
