import QtQuick
import "../design"
import "../design/controls"

// Asks for a name: for something about to be made — a section, from a row's
// menu item or a footer button that names a `prompt` — or a row's new one,
// for an item that renames it (docs/providers.md). The card is the one every
// form popup has (PopupForm), on a popup's surface: Enter goes ahead with a
// nonempty name; Escape or a click outside the card lets it go.
FocusScope {
  id: dialog
  // What is asked, or null when nothing is: { message, icon, placeholder,
  // text, confirmText }. The field opens on `text` — a rename's old name, to
  // change or add to — and shows `placeholder` while it is empty.
  property var prompt: null
  property color accent: Color.accent
  property color scrim: Color.menu.scrim
  property string fontFamily: Style.font.menuFamily
  signal canceled()
  signal submitted(string name)
  visible: prompt !== null

  function submit() {
    var name = field.text.trim()
    if (name) {
      dialog.submitted(name)
    }
  }

  // Focused as it appears: an item still hidden cannot take the keyboard.
  // The caret ends after the text it opens on.
  onVisibleChanged: {
    if (visible) {
      field.text = dialog.prompt.text
      field.forceActiveFocus()
    }
  }

  ChromePopupStyle {
    id: popupStyle
  }

  Rectangle {
    anchors.fill: parent
    color: dialog.scrim
    MouseArea {
      anchors.fill: parent
      onClicked: dialog.canceled()
    }
  }

  BorderSurface {
    id: card
    readonly property real inset: popupStyle.padding + Border.width(popupStyle.borderSpec)
    anchors.centerIn: parent
    width: Math.min(parent.width - Style.space(32), form.implicitWidth + inset * 2)
    height: form.implicitHeight + inset * 2
    color: popupStyle.fill
    borderSpec: popupStyle.borderSpec
    radius: popupStyle.radius

    // A click on the card is not a click outside it.
    MouseArea {
      anchors.fill: parent
    }

    PopupForm {
      id: form
      anchors.fill: parent
      anchors.margins: card.inset
      iconText: dialog.prompt ? dialog.prompt.icon : ""
      title: dialog.prompt ? dialog.prompt.message : ""
      confirmText: dialog.prompt ? dialog.prompt.confirmText : ""
      hint: "Enter to " + confirmText.toLowerCase() + " · Esc to cancel"
      accent: dialog.accent
      fontFamily: dialog.fontFamily
      submitButton.objectName: "promptConfirm"
      submitButton.enabled: field.text.trim().length > 0
      onSubmitted: dialog.submit()

      ChromeTextField {
        id: field
        objectName: "promptField"
        width: parent.width
        placeholderText: dialog.prompt ? dialog.prompt.placeholder : ""
        Accessible.name: placeholderText
        accent: dialog.accent
        font.family: form.fontFamily
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
    }
  }
}
