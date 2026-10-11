import QtQuick
import ".."

// Asks for a name before something is made — a section, from a row's menu
// item or a footer button that names a `prompt` (docs/providers.md). Enter
// goes ahead with a nonempty name; Escape, Cancel or a click outside the
// card lets it go.
FocusScope {
  id: dialog
  property bool opened: false
  property string message: ""
  property string placeholderText: ""
  property string confirmText: "Create"
  property color background: Color.background
  property color foreground: Color.foreground
  property color accent: Color.accent
  property color scrim: Color.menu.scrim
  property string fontFamily: Style.font.family
  property real cornerRadius: Style.cornerRadius
  signal canceled()
  signal submitted(string name)
  visible: opened

  function submit() {
    var name = field.text.trim()
    if (name) {
      dialog.submitted(name)
    }
  }

  // Focused as it appears: an item still hidden cannot take the keyboard.
  onVisibleChanged: {
    if (visible) {
      field.text = ""
      field.forceActiveFocus()
    }
  }

  Rectangle {
    anchors.fill: parent
    color: dialog.scrim
    MouseArea {
      anchors.fill: parent
      onClicked: dialog.canceled()
    }
    Rectangle {
      anchors.centerIn: parent
      width: Math.min(parent.width - 32, 400)
      height: contents.implicitHeight + 40
      color: dialog.background
      radius: dialog.cornerRadius
      border.color: Util.alpha(dialog.foreground, 0.3)
      MouseArea {
        anchors.fill: parent
      }
      Column {
        id: contents
        anchors.centerIn: parent
        width: parent.width - 40
        spacing: 20
        Text {
          width: parent.width
          text: dialog.message
          textFormat: Text.PlainText
          wrapMode: Text.Wrap
          color: dialog.foreground
          font.family: dialog.fontFamily
          font.pixelSize: Style.font.title
        }
        TextField {
          id: field
          objectName: "promptField"
          width: parent.width
          placeholderText: dialog.placeholderText
          foreground: dialog.foreground
          accent: dialog.accent
          font.family: dialog.fontFamily
          Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Escape) {
              dialog.canceled()
              event.accepted = true
            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
              dialog.submit()
              event.accepted = true
            }
          }
        }
        Row {
          anchors.right: parent.right
          spacing: 12
          Button {
            text: "Cancel"
            onClicked: dialog.canceled()
          }
          Button {
            text: dialog.confirmText
            enabled: field.text.trim().length > 0
            onClicked: dialog.submit()
          }
        }
      }
    }
  }
}
