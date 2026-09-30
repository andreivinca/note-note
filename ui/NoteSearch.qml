import QtQuick
import "../design"
import "../design/controls"

// Search field with keyboard navigation and a shortcut hint.
Item {
  id: root
  property string filterText: ""
  property color background: Color.menu.background
  property color foreground: Color.menu.text
  property color accent: Color.accent
  property string fontFamily: Style.font.menuFamily
  property var shortcutHandler: null
  property var keybindings: null
  readonly property bool searchFocused: searchField.activeFocus
  implicitHeight: searchField.implicitHeight
  signal filterEdited(string text)
  signal clearRequested()

  function focusSearch() {
    searchField.forceActiveFocus()
    searchField.selectAll()
  }
  function setSearchText(text) {
    searchField.text = text
  }

  ChromeTextField {
    id: searchField
    anchors.fill: parent
    placeholderText: "Search"
    iconText: "󰍉"
    accent: root.accent
    font.family: root.fontFamily
    onTextEdited: root.filterEdited(text)
    rightPadding: root.filterText.length > 0
      ? clearSearchButton.width + Style.spacing.xs
      : searchKeycap.width + (searchField.height - searchKeycap.height) / 2 + Style.spacing.xs

    Rectangle {
      id: searchKeycap
      visible: root.filterText.length === 0 && searchKeycapText.text.length > 0
      anchors.right: parent.right
      // The same air to the right edge as above and below it, so the
      // keycap sits centered in the field's corner.
      anchors.rightMargin: (searchField.height - height) / 2
      anchors.verticalCenter: parent.verticalCenter
      width: searchKeycapText.width + Style.spacing.sm * 2
      height: searchKeycapText.height + Style.spacing.xxs * 2
      // A square theme keeps its corners; a round one is capped where
      // a keycap stops looking like a key.
      radius: Math.min(Style.cornerRadius, height / 3)
      color: Util.alpha(root.foreground, 0.06)

      Text {
        id: searchKeycapText
        textFormat: Text.PlainText
        anchors.centerIn: parent
        text: root.keybindings ? root.keybindings.label("app/search") : ""
        color: Style.secondaryText(root.foreground, 0.6)
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
      }
    }

    Button {
      id: clearSearchButton
      visible: root.filterText.length > 0
      anchors.right: parent.right
      anchors.rightMargin: Style.spacing.xxs
      anchors.verticalCenter: parent.verticalCenter
      iconText: "󰅖"
      tooltipText: "Clear the search" + (root.keybindings ? root.keybindings.hint("app/back") : "")
      foreground: root.foreground
      accent: root.accent
      iconSize: Style.font.iconSmall
      horizontalPadding: Style.spacing.xs
      verticalPadding: Style.spacing.xxs
      onClicked: root.clearRequested()
    }

    Keys.priority: Keys.BeforeItem
    Keys.onPressed: function(event) {
      if (root.shortcutHandler && root.shortcutHandler(event)) {
        event.accepted = true
      }
    }
  }

}
