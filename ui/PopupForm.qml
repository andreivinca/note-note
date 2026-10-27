import QtQuick
import QtQuick.Controls as QQC
import QtQuick.Layouts
import "../design"
import "../design/controls"

// The card every form popup shares — a tool's popover, the name and the
// confirmation dialogs: what it is for (an icon and a title), its fields, and
// a footer that says how to finish beside the action. Escape or a click
// outside cancels, so only a choice that must be made on purpose shows a
// Cancel button as well (`cancelText`).
QQC.Control {
  id: form
  default property alias fields: fields.data
  property alias submitButton: confirmButton
  property alias cancelButton: cancelButton
  property string iconText: ""
  property string title: ""
  // How to finish, in the footer.
  property string hint: ""
  // What stands in the way of submitting, shown in place of the hint.
  property string message: ""
  property string confirmText: ""
  property string cancelText: ""
  property color foreground: Colors.token("popup.foreground")
  property color accent: Colors.accent
  property string fontFamily: Style.font.menuFamily
  signal submitted()
  signal canceled()
  implicitWidth: Style.space(320)
  implicitHeight: contentItem.implicitHeight + topPadding + bottomPadding
  padding: Style.spacing.md

  property ChromeControlStyle controlStyle: ChromeControlStyle {}

  contentItem: Column {
    spacing: Style.spacing.lg

    RowLayout {
      width: parent.width
      spacing: Style.spacing.controlGap
      Text {
        visible: text.length > 0
        Layout.alignment: Qt.AlignTop
        text: form.iconText
        textFormat: Text.PlainText
        color: Util.alpha(form.foreground, 0.55)
        font.family: Style.fontFamily
        font.pixelSize: Style.font.icon
      }
      Text {
        Layout.fillWidth: true
        text: form.title
        textFormat: Text.PlainText
        color: form.foreground
        font.family: form.fontFamily
        font.pixelSize: Style.font.body
        font.weight: Font.Medium
        wrapMode: Text.Wrap
      }
    }

    // A question alone has no fields, and no gap where they would be.
    Column {
      id: fields
      visible: children.length > 0
      width: parent.width
      spacing: Style.spacing.md
    }

    RowLayout {
      width: parent.width
      spacing: Style.spacing.controlGap
      Text {
        objectName: "toolFormNotice"
        Layout.fillWidth: true
        text: form.message || form.hint
        textFormat: Text.PlainText
        color: form.message ? Colors.urgent : form.foreground
        opacity: form.message ? 1 : 0.6
        font.family: form.fontFamily
        font.pixelSize: Style.font.caption
        wrapMode: Text.Wrap
      }
      Button {
        id: cancelButton
        visible: form.cancelText.length > 0
        text: form.cancelText
        Layout.preferredWidth: Math.max(Style.space(64), implicitWidth)
        Layout.preferredHeight: Math.max(form.controlStyle.height, implicitHeight)
        radius: form.controlStyle.radius
        foreground: form.foreground
        accent: form.accent
        fontFamily: form.fontFamily
        onClicked: form.canceled()
      }
      Button {
        id: confirmButton
        text: form.confirmText
        Layout.preferredWidth: Math.max(Style.space(64), implicitWidth)
        Layout.preferredHeight: Math.max(form.controlStyle.height, implicitHeight)
        radius: form.controlStyle.radius
        selected: true
        focusable: true
        foreground: form.foreground
        accent: form.accent
        fontFamily: form.fontFamily
        onClicked: form.submitted()
      }
    }
  }
}
