import QtQuick
import QtQuick.Controls as QQC
import "../../design"
import "../../design/controls"
import ".." as AppUi

// Input tools share one header, content inset and action row.
QQC.Control {
  id: form
  required property Tool action
  default property alias fields: fields.data
  property alias submitButton: confirmButton
  property alias cancelButton: rejectButton
  readonly property color foreground: Color.token("popup.foreground")
  readonly property string fontFamily: action.editor.fontFamily
  signal submitted()
  implicitWidth: Style.space(320)
  implicitHeight: contentItem.implicitHeight + topPadding + bottomPadding
  padding: Style.spacing.lg

  property AppUi.ChromeControlStyle controlStyle: AppUi.ChromeControlStyle {}

  contentItem: Column {
    spacing: Style.space(12)

    Text {
      width: parent.width
      text: form.action.label
      textFormat: Text.PlainText
      color: form.foreground
      font.family: form.fontFamily
      font.pixelSize: Style.font.subtitle
      font.weight: Font.DemiBold
      wrapMode: Text.Wrap
    }

    Column {
      id: fields
      width: parent.width
      spacing: Style.space(12)
    }

    Row {
      anchors.right: parent.right
      spacing: Style.spacing.lg
      Button {
        id: rejectButton
        text: "Cancel"
        width: Math.max(Style.space(64), implicitWidth)
        height: Math.max(form.controlStyle.height, implicitHeight)
        radius: form.controlStyle.radius
        focusable: true
        foreground: form.foreground
        accent: form.action.editor.accent
        fontFamily: form.fontFamily
        onClicked: form.action.cancelPanel()
      }
      Button {
        id: confirmButton
        text: "Insert"
        width: Math.max(Style.space(64), implicitWidth)
        height: Math.max(form.controlStyle.height, implicitHeight)
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
