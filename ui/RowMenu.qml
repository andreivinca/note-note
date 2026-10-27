import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC
import "../design"
import "../design/controls"

// The actions a provider offers on one of its sidebar rows — the row's
// `menu` (docs/providers.md) — opened at the pointer by a right-click. The
// title bar opens it on a tab as well, with a `menu` of its own.
// Choosing an item only reports it: what the item does is the host's to run.
// An item the provider marks `enabled: false` is dimmed and cannot be chosen.
QQC.Menu {
  id: menu
  palette: ControlPalette {}
  // The row the menu was opened on; its `menu` is what the menu lists.
  property var row: null
  property color accent: Colors.accent
  property string fontFamily: Style.font.menuFamily
  readonly property var items: menu.row ? menu.row.menu || [] : []
  readonly property ChromePopupStyle popupStyle: ChromePopupStyle {}
  readonly property real iconColumnWidth: menu.items.some(function(item) {
    return !!item.icon
  }) ? Style.font.icon : 0

  signal chosen(var row, var item)

  function openFor(row) {
    menu.row = row
    menu.popup()
  }

  // The item chosen, reported once the menu has closed: closing hands the
  // keyboard back, and what an item opens next — a dialog asking for a name
  // — must take it after that, not before.
  property var picked: null
  onClosed: {
    var item = menu.picked
    menu.picked = null
    if (item) {
      menu.chosen(menu.row, item)
    }
  }

  objectName: "rowMenu"
  popupType: QQC.Popup.Item
  margins: Style.spacing.xxs
  implicitWidth: {
    var widest = 0
    for (var i = 0; i < count; i++) {
      var entry = itemAt(i)
      if (entry) {
        widest = Math.max(widest, entry.implicitWidth)
      }
    }
    return Math.ceil(widest) + leftPadding + rightPadding
  }
  implicitHeight: contentItem.implicitHeight + topPadding + bottomPadding
  leftPadding: Border.width(popupStyle.borderSpec) + popupStyle.padding
  rightPadding: leftPadding
  topPadding: leftPadding
  bottomPadding: leftPadding

  background: BorderSurface {
    color: menu.popupStyle.fill
    borderSpec: menu.popupStyle.borderSpec
    radius: menu.popupStyle.radius
  }
  contentItem: ListView {
    implicitHeight: contentHeight
    model: menu.contentModel
    currentIndex: menu.currentIndex
    spacing: 0
    clip: true
    boundsBehavior: Flickable.StopAtBounds
  }

  Instantiator {
    model: menu.items
    delegate: QQC.MenuItem {
      id: entry
      required property var modelData
      objectName: "rowMenu-" + entry.modelData.id
      text: entry.modelData.title
      enabled: entry.modelData.enabled !== false
      hoverEnabled: true
      implicitWidth: contentItem.implicitWidth + leftPadding + rightPadding
      implicitHeight: Math.max(menu.popupStyle.rowHeight, contentItem.implicitHeight + topPadding + bottomPadding)
      topPadding: menu.popupStyle.verticalPadding
      bottomPadding: topPadding
      leftPadding: menu.popupStyle.horizontalPadding
      rightPadding: menu.popupStyle.horizontalPadding
      font.family: menu.fontFamily
      font.pixelSize: Style.font.body

      contentItem: RowLayout {
        spacing: Style.spacing.controlGap
        opacity: entry.enabled ? 1 : 0.45

        Text {
          visible: menu.iconColumnWidth > 0
          Layout.preferredWidth: menu.iconColumnWidth
          Layout.alignment: Qt.AlignVCenter
          text: entry.modelData.icon || ""
          textFormat: Text.PlainText
          horizontalAlignment: Text.AlignHCenter
          color: entryLabel.color
          font.family: Style.font.family
          font.pixelSize: Style.font.icon
        }

        Text {
          id: entryLabel
          Layout.fillWidth: true
          text: entry.text
          textFormat: Text.PlainText
          verticalAlignment: Text.AlignVCenter
          elide: Text.ElideRight
          font: entry.font
          color: entry.highlighted ? Style.hoverStateColor(menu.popupStyle.text, menu.accent) : menu.popupStyle.text
        }
      }
      background: Rectangle {
        radius: menu.popupStyle.rowRadius
        color: entry.highlighted ? Style.hoverFillFor(menu.popupStyle.text, menu.accent) : "transparent"
      }
      onTriggered: menu.picked = entry.modelData
    }
    onObjectAdded: function(index, object) {
      menu.insertItem(index, object)
    }
    onObjectRemoved: function(index, object) {
      menu.removeItem(object)
    }
  }
}
