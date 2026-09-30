import QtQuick
import QtQuick.Controls as Controls
import ".."

// A field in the ink it is given: its fill, border and placeholder are
// shades of `foreground`, so it reads on whatever surface holds it.
Controls.TextField {
  id: field
  property color foreground: Color.foreground
  property color accent: Color.accent
  property bool password: false
  property bool hasCursor: false
  property real horizontalPadding: Style.spacing.controlPaddingX
  property real verticalPadding: Style.spacing.sm
  color: foreground
  selectionColor: Util.alpha(accent, 0.35)
  selectedTextColor: foreground
  placeholderTextColor: Style.secondaryText(foreground, 0.5)
  echoMode: password ? TextInput.Password : TextInput.Normal
  font.family: Style.font.family
  font.pixelSize: Style.font.body
  leftPadding: horizontalPadding + 1
  rightPadding: leftPadding
  topPadding: verticalPadding + 1
  bottomPadding: topPadding
  background: Rectangle {
    radius: Style.cornerRadius
    color: Util.alpha(field.foreground, 0.04)
    border.width: 1
    border.color: field.activeFocus ? field.accent : Util.alpha(field.foreground, 0.3)
  }
}
