import QtQuick
import "../design"
import "../design/controls" as Controls

// Shared typography, spacing and surface for search, commands and tool forms.
Controls.TextField {
  id: field
  property bool focusBorderVisible: activeFocus
  // A glyph at the leading edge says what the field is for, and stays while
  // you type — dimmed the standard way, a fade toward any background.
  property string iconText: ""
  foreground: controlStyle.text
  implicitHeight: Math.max(controlStyle.height, contentHeight + topPadding + bottomPadding)
  font.family: Style.font.menuFamily
  font.pixelSize: Style.font.body
  verticalPadding: Style.spacing.xs
  placeholderTextColor: controlStyle.placeholder
  leftPadding: leadingIcon.visible ? leadingIcon.width + Style.spacing.md + Style.spacing.xs : horizontalPadding + 1

  ChromeControlStyle {
    id: controlStyle
  }

  background: Rectangle {
    radius: controlStyle.radius
    color: controlStyle.fill
    border.width: controlStyle.borderWidth
    border.color: field.focusBorderVisible ? controlStyle.focusBorderColor : controlStyle.borderColor
  }

  Text {
    id: leadingIcon
    visible: field.iconText.length > 0
    textFormat: Text.PlainText
    anchors.left: parent.left
    // The glyph keeps its distance from the rounded edge; leftPadding
    // above follows it.
    anchors.leftMargin: Style.spacing.md
    anchors.verticalCenter: parent.verticalCenter
    text: field.iconText
    color: Util.alpha(field.foreground, 0.55)
    font.family: Style.fontFamily
    font.pixelSize: Style.font.iconSmall
  }
}
