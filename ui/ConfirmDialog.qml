import QtQuick
import "../design"
import "../design/controls"

// Asks before something that cannot be taken back: the question as the card
// every form popup has (PopupForm), on a popup's surface, with Cancel beside
// the action because the choice must be made on purpose. The workspace hands
// it the keys (handleKey): Cancel is chosen first, the arrows and Tab move
// the choice, Enter takes it and Escape cancels.
FocusScope {
  id: dialog
  property bool opened: false
  property string iconText: ""
  property string message: ""
  property string confirmText: "Confirm"
  property color accent: Colors.accent
  property color scrim: Colors.menu.scrim
  property string fontFamily: Style.font.menuFamily
  property int selectedIndex: 0
  signal canceled()
  signal confirmed()
  visible: opened
  function handleKey(event) {
    if (!opened) {
      return false
    }
    if (event.key === Qt.Key_Escape) {
      canceled()
      return true
    }
    if ([Qt.Key_Left, Qt.Key_Right, Qt.Key_Tab, Qt.Key_Backtab].indexOf(event.key) >= 0) {
      selectedIndex = 1 - selectedIndex
      return true
    }
    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
      if (selectedIndex === 0) {
        canceled()
      } else {
        confirmed()
      }
      return true
    }
    return false
  }
  onOpenedChanged: {
    if (opened) {
      selectedIndex = 0
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
      iconText: dialog.iconText
      title: dialog.message
      hint: "Enter to choose · Esc to cancel"
      cancelText: "Cancel"
      confirmText: dialog.confirmText
      accent: dialog.accent
      fontFamily: dialog.fontFamily
      cancelButton.selected: dialog.selectedIndex === 0
      submitButton.selected: dialog.selectedIndex === 1
      submitButton.foreground: Colors.urgent
      onCanceled: dialog.canceled()
      onSubmitted: dialog.confirmed()
    }
  }
}
