import QtQuick
import QtQuick.Controls as QQC
import QtQuick.Layouts
import "../../design"
import "../../design/controls"
import ".." as AppUi

// Input tools share one popover: the tool's name, its fields, and a footer
// that says how to finish beside the one action. Escape or a click outside
// cancels, as it does for every popup.
QQC.Control {
  id: form
  required property Tool action
  default property alias fields: fields.data
  property alias submitButton: confirmButton
  // What stands in the way of submitting, shown in place of the key hint.
  property string message: ""
  readonly property color foreground: Color.token("popup.foreground")
  readonly property string fontFamily: action.editor.fontFamily
  signal submitted()
  implicitWidth: Style.space(320)
  implicitHeight: contentItem.implicitHeight + topPadding + bottomPadding
  padding: Style.spacing.md

  property AppUi.ChromeControlStyle controlStyle: AppUi.ChromeControlStyle {}

  contentItem: Column {
    spacing: Style.spacing.lg

    RowLayout {
      width: parent.width
      spacing: Style.spacing.controlGap
      Text {
        visible: text.length > 0
        Layout.alignment: Qt.AlignTop
        text: form.action.icon
        textFormat: Text.PlainText
        color: Util.alpha(form.foreground, 0.55)
        font.family: Style.fontFamily
        font.pixelSize: Style.font.icon
      }
      Text {
        Layout.fillWidth: true
        text: form.action.label
        textFormat: Text.PlainText
        color: form.foreground
        font.family: form.fontFamily
        font.pixelSize: Style.font.body
        font.weight: Font.Medium
        wrapMode: Text.Wrap
      }
    }

    Column {
      id: fields
      width: parent.width
      spacing: Style.spacing.md
    }

    RowLayout {
      width: parent.width
      spacing: Style.spacing.controlGap
      Text {
        objectName: "toolFormNotice"
        Layout.fillWidth: true
        text: form.message || "Enter to insert · Esc to cancel"
        textFormat: Text.PlainText
        color: form.message ? Color.urgent : form.foreground
        opacity: form.message ? 1 : 0.6
        font.family: form.fontFamily
        font.pixelSize: Style.font.caption
        wrapMode: Text.Wrap
      }
      Button {
        id: confirmButton
        text: "Insert"
        Layout.preferredWidth: Math.max(Style.space(64), implicitWidth)
        Layout.preferredHeight: Math.max(form.controlStyle.height, implicitHeight)
        radius: form.controlStyle.radius
        selected: true
        focusable: true
        foreground: form.foreground
        accent: form.action.editor.accent
        fontFamily: form.fontFamily
        onClicked: form.submitted()
      }
    }
  }
}
