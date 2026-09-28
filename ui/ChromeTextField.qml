import QtQuick
import "../design"
import "../design/controls" as Controls

// Shared typography, spacing and surface for search, commands and tool forms.
Controls.TextField {
  id: field
  property bool focusBorderVisible: activeFocus
  foreground: controlStyle.text
  implicitHeight: Math.max(controlStyle.height, contentHeight + topPadding + bottomPadding)
  font.family: Style.font.menuFamily
  font.pixelSize: Style.font.body
  verticalPadding: Style.spacing.xs
  placeholderTextColor: controlStyle.placeholder

  ChromeControlStyle {
    id: controlStyle
  }

  background: Rectangle {
    radius: controlStyle.radius
    color: controlStyle.fill
    border.width: controlStyle.borderWidth
    border.color: field.focusBorderVisible ? controlStyle.focusBorderColor : controlStyle.borderColor
  }
}
