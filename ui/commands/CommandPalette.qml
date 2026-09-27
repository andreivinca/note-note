import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC
import "../../design"
import ".." as AppUi
import "matching.js" as Matching

FocusScope {
  id: pickerRoot
  property bool opened: false
  property bool choosing: false
  property bool busy: false
  property string title: "Commands"
  property string message: ""
  property var items: []
  property var matches: []
  property int currentIndex: -1
  property var callbacks: null
  property Item priorFocus: null
  property var registry: null
  property int session: 0
  signal fallbackFocusRequested()
  visible: opened
  z: 1000
  anchors.fill: parent
  readonly property var current: currentIndex >= 0 && currentIndex < matches.length ? matches[currentIndex] : null
  readonly property string unavailableReason: current && current.enabled === false ? current.reason || "" : ""

  Connections {
    target: pickerRoot.registry
    function onListingChanged() {
      if (pickerRoot.opened && !pickerRoot.choosing && !pickerRoot.busy) {
        pickerRoot.items = pickerRoot.registry.list()
        pickerRoot.refilter("")
      }
    }
  }

  function rememberFocus(owner) {
    pickerRoot.priorFocus = owner
  }

  function refilter(preferredId) {
    var result = Matching.filter(pickerRoot.items, query.text, preferredId || (pickerRoot.current ? pickerRoot.current.id : ""))
    pickerRoot.matches = result.items
    pickerRoot.currentIndex = result.index
    results.positionViewAtIndex(Math.max(0, result.index), ListView.Contain)
    pickerRoot.preview()
  }

  function preview() {
    if (pickerRoot.choosing && pickerRoot.callbacks && pickerRoot.callbacks.preview && !pickerRoot.busy) {
      pickerRoot.callbacks.preview(pickerRoot.current ? pickerRoot.current.id : "")
    }
  }

  function showCommands(commands, error) {
    pickerRoot.session++
    pickerRoot.choosing = false
    pickerRoot.callbacks = null
    pickerRoot.title = "Commands"
    pickerRoot.busy = false
    pickerRoot.items = commands
    pickerRoot.message = error || ""
    pickerRoot.opened = true
    query.text = ""
    pickerRoot.refilter("")
    query.forceActiveFocus()
  }

  function open(focusOwner) {
    if (pickerRoot.opened) {
      query.forceActiveFocus()
      query.selectAll()
      return
    }
    pickerRoot.priorFocus = focusOwner
    pickerRoot.showCommands(registry.list(), "")
  }

  function pick(options, callbacks) {
    var ticket = ++pickerRoot.session
    pickerRoot.choosing = true
    pickerRoot.callbacks = callbacks
    pickerRoot.title = options.title || "Choose"
    pickerRoot.items = (options.items || []).slice(0, 4096)
    pickerRoot.message = options.message || ""
    pickerRoot.busy = false
    pickerRoot.opened = true
    query.text = ""
    pickerRoot.refilter(options.selectedId || "")
    query.forceActiveFocus()
    return {
      setBusy: function(value, message) {
        if (pickerRoot.session === ticket) {
          pickerRoot.setBusy(value, message)
        }
      },
      showError: function(message) {
        if (pickerRoot.session === ticket) {
          pickerRoot.busy = false
          pickerRoot.message = message
        }
      },
      setMessage: function(message) {
        if (pickerRoot.session === ticket) {
          pickerRoot.message = message
        }
      }
    }
  }

  function setBusy(value, message) {
    pickerRoot.busy = value
    pickerRoot.message = message || ""
  }

  function close() {
    var owner = pickerRoot.priorFocus
    pickerRoot.priorFocus = null
    pickerRoot.busy = false
    pickerRoot.choosing = false
    pickerRoot.callbacks = null
    if (!pickerRoot.opened) {
      return
    }
    pickerRoot.session++
    pickerRoot.opened = false
    var ancestor = owner
    while (ancestor && ancestor !== pickerRoot.parent) {
      ancestor = ancestor.parent
    }
    if (owner && ancestor && owner.visible && owner.enabled) {
      owner.forceActiveFocus()
    } else {
      pickerRoot.fallbackFocusRequested()
    }
  }

  function requestClose() {
    if (registry.cancel()) {
      pickerRoot.close()
    } else {
      pickerRoot.message = "Finishing the settings save…"
    }
  }

  function accept() {
    var item = pickerRoot.current
    if (pickerRoot.busy || !item || item.enabled === false) {
      return
    }
    if (pickerRoot.choosing) {
      pickerRoot.callbacks.accept(item.id)
    } else {
      registry.execute(item.id, {})
    }
  }

  function move(delta) {
    if (!pickerRoot.matches.length || pickerRoot.busy) {
      return
    }
    pickerRoot.currentIndex = Math.max(0, Math.min(pickerRoot.matches.length - 1, pickerRoot.currentIndex + delta))
    results.positionViewAtIndex(pickerRoot.currentIndex, ListView.Contain)
    pickerRoot.preview()
  }

  function handleKey(event) {
    if (event.key === Qt.Key_Escape) {
      pickerRoot.requestClose()
      return true
    }
    if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
      query.forceActiveFocus()
      return true
    }
    if (event.key === Qt.Key_Up || event.key === Qt.Key_Down || event.key === Qt.Key_PageUp || event.key === Qt.Key_PageDown) {
      pickerRoot.move(event.key === Qt.Key_Up ? -1 : event.key === Qt.Key_Down ? 1 : event.key === Qt.Key_PageUp ? -8 : 8)
      return true
    }
    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
      if (!query.inputMethodComposing) {
        pickerRoot.accept()
      }
      return true
    }
    return false
  }

  MouseArea {
    anchors.fill: parent
    acceptedButtons: Qt.AllButtons
    onPressed: pickerRoot.requestClose()
    onWheel: function(wheel) { wheel.accepted = true }
  }

  Rectangle {
    id: panel
    objectName: "commandPanel"
    readonly property real padding: Style.spacing.lg
    anchors.horizontalCenter: parent.horizontalCenter
    y: Math.min(Style.space(56), parent.height * 0.08)
    width: Math.max(0, Math.min(Style.space(620), parent.width - Style.space(24)))
    implicitHeight: content.implicitHeight + padding * 2
    height: Math.max(0, Math.min(parent.height - y - Style.space(12), implicitHeight))
    radius: popupStyle.radius
    color: Color.token("palette.background", Color.background)
    border.width: Border.width(popupStyle.borderSpec)
    border.color: popupStyle.borderSpec.color
    clip: true

    AppUi.ChromePopupStyle {
      id: popupStyle
      background: panel.color
      foreground: Color.token("palette.foreground", Color.foreground)
    }

    MouseArea {
      anchors.fill: parent
      acceptedButtons: Qt.AllButtons
      onPressed: query.forceActiveFocus()
    }

    ColumnLayout {
      id: content
      anchors.fill: parent
      anchors.margins: panel.padding
      spacing: Style.spacing.sm

      AppUi.ChromeTextField {
        id: query
        objectName: "commandQuery"
        Layout.fillWidth: true
        // The query keeps focus throughout the session; retain the search bar's quiet border.
        focusBorderVisible: false
        maximumLength: 256
        placeholderText: pickerRoot.choosing ? "Type to filter…" : "Type a command…"
        leftPadding: commandGlyph.visible ? commandGlyph.width + Style.spacing.md + Style.spacing.xs : horizontalPadding + 1
        foreground: Color.token("palette.foreground", Color.foreground)
        color: foreground
        Accessible.name: pickerRoot.choosing ? pickerRoot.title : "Search commands"
        Keys.priority: Keys.BeforeItem
        Keys.onPressed: function(event) {
          if (pickerRoot.handleKey(event)) {
            event.accepted = true
          }
        }
        onTextChanged: pickerRoot.refilter("")
        Text {
          id: commandGlyph
          visible: !pickerRoot.choosing
          anchors.left: parent.left
          anchors.leftMargin: Style.spacing.md
          anchors.verticalCenter: parent.verticalCenter
          text: ">"
          color: Util.alpha(query.foreground, 0.55)
          font: query.font
        }
      }

      ListView {
        id: results
        objectName: "commandResults"
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.preferredHeight: contentHeight
        Layout.minimumHeight: 0
        clip: true
        model: pickerRoot.matches
        currentIndex: pickerRoot.currentIndex
        boundsBehavior: Flickable.StopAtBounds
        QQC.ScrollBar.vertical: QQC.ScrollBar {
          id: scrollBar
        }
        delegate: QQC.ItemDelegate {
          id: row
          required property var modelData
          required property int index
          readonly property bool selected: index === pickerRoot.currentIndex
          readonly property color ink: selected ? Color.token("palette.selectionForeground", Color.menu.selectedText)
            : Color.token("palette.foreground", Color.foreground)
          objectName: "commandChoice-" + modelData.id
          width: results.width
          height: Math.max(popupStyle.rowHeight, contentItem.implicitHeight + topPadding + bottomPadding)
          leftPadding: popupStyle.horizontalPadding
          rightPadding: leftPadding + (scrollBar.visible ? scrollBar.width : 0)
          topPadding: popupStyle.verticalPadding
          bottomPadding: topPadding
          focusPolicy: Qt.NoFocus
          hoverEnabled: true
          Accessible.name: modelData.label + (modelData.reason ? ", unavailable: " + modelData.reason : "")
          background: Rectangle {
            color: row.selected ? Color.token("palette.selectionBackground", Color.menu.selectedBackground)
              : row.hovered ? Style.hoverFillFor(popupStyle.foreground, Color.accent) : "transparent"
            radius: popupStyle.rowRadius
          }
          contentItem: RowLayout {
            spacing: Style.spacing.controlGap
            opacity: row.modelData.enabled === false ? 0.55 : 1
            Text {
              Layout.fillWidth: true
              text: row.modelData.label
              textFormat: Text.PlainText
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.body
              color: row.ink
              elide: Text.ElideRight
              verticalAlignment: Text.AlignVCenter
            }
            Text {
              visible: text.length > 0
              Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
              text: row.modelData.shortcut || ""
              textFormat: Text.PlainText
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.caption
              color: row.ink
              opacity: 0.7
            }
          }
          onClicked: {
            pickerRoot.currentIndex = index
            pickerRoot.preview()
            pickerRoot.accept()
          }
        }
      }

      Text {
        id: footer
        objectName: "commandFooter"
        Layout.fillWidth: true
        Layout.leftMargin: Style.spacing.sm
        Layout.rightMargin: Style.spacing.sm
        text: pickerRoot.message || pickerRoot.unavailableReason
          || (!pickerRoot.matches.length ? "No matching results" : "↑ ↓ to navigate · Enter to select · Esc to cancel")
        textFormat: Text.PlainText
        font.family: Style.font.menuFamily
        font.pixelSize: Style.font.caption
        color: Color.token("palette.foreground", Color.foreground)
        opacity: pickerRoot.message || pickerRoot.unavailableReason || !pickerRoot.matches.length ? 1 : 0.6
        wrapMode: Text.WordWrap
        maximumLineCount: 3
        elide: Text.ElideRight
      }
    }
  }
}
