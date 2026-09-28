import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC
import "../../design"
import ".." as AppUi
import "matching.js" as Matching

// One surface for two uses: the list of commands, and a choice a command
// asks for. It searches, moves and accepts; what a choice means is the
// command's own, through the callbacks it handed over.
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
  readonly property int pageStep: 8
  readonly property var steps: {
    var result = {}
    result[Qt.Key_Up] = -1
    result[Qt.Key_Down] = 1
    result[Qt.Key_PageUp] = -pageStep
    result[Qt.Key_PageDown] = pageStep
    return result
  }
  signal fallbackFocusRequested()
  visible: opened
  z: 1000
  anchors.fill: parent
  readonly property var current: currentIndex >= 0 && currentIndex < matches.length ? matches[currentIndex] : null
  readonly property string unavailableReason: current && current.enabled === false ? current.reason || "" : ""
  readonly property color ink: Color.token("palette.foreground")

  Connections {
    target: pickerRoot.registry
    function onListingChanged() {
      if (pickerRoot.opened && !pickerRoot.choosing && !pickerRoot.busy) {
        pickerRoot.items = pickerRoot.registry.list()
        pickerRoot.refilter()
      }
    }
  }

  function rememberFocus(owner) {
    pickerRoot.priorFocus = owner
  }

  function filter(preferredId) {
    var result = Matching.filter(pickerRoot.items, query.text, preferredId || (pickerRoot.current ? pickerRoot.current.id : ""))
    pickerRoot.matches = result.items
    pickerRoot.currentIndex = result.index
    results.positionViewAtIndex(Math.max(0, result.index), ListView.Contain)
  }

  function refilter() {
    pickerRoot.filter("")
    pickerRoot.preview()
  }

  function preview() {
    if (pickerRoot.choosing && pickerRoot.callbacks && pickerRoot.callbacks.preview && !pickerRoot.busy) {
      pickerRoot.callbacks.preview(pickerRoot.current ? pickerRoot.current.id : "")
    }
  }

  function previewFor(ticket) {
    if (pickerRoot.session === ticket) {
      pickerRoot.preview()
    }
  }

  // Both uses begin the same way and differ in what is listed and who is
  // told. The first preview follows once the caller holds what it asked for.
  function present(state) {
    var ticket = ++pickerRoot.session
    pickerRoot.choosing = !!state.callbacks
    pickerRoot.callbacks = state.callbacks || null
    pickerRoot.title = state.title
    pickerRoot.items = state.items
    pickerRoot.message = state.message || ""
    pickerRoot.busy = false
    pickerRoot.opened = true
    query.text = ""
    pickerRoot.filter(state.selectedId || "")
    query.forceActiveFocus()
    Qt.callLater(pickerRoot.previewFor, ticket)
    return ticket
  }

  function showCommands(commands, error) {
    pickerRoot.present({ title: "Commands", items: commands, message: error || registry.notice })
  }

  function focusQuery() {
    query.forceActiveFocus()
    query.selectAll()
  }

  function open(focusOwner) {
    if (pickerRoot.opened) {
      pickerRoot.focusQuery()
      return
    }
    pickerRoot.priorFocus = focusOwner
    pickerRoot.showCommands(registry.list(), "")
  }

  function pick(options, callbacks) {
    var ticket = pickerRoot.present({ callbacks: callbacks, title: options.title || "Choose",
      items: (options.items || []).slice(0, Matching.maxItems), message: options.message,
      selectedId: options.selectedId })
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

  function inside(item) {
    var ancestor = item
    while (ancestor && ancestor !== pickerRoot.parent) {
      ancestor = ancestor.parent
    }
    return !!ancestor
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
    if (owner && pickerRoot.inside(owner) && owner.visible && owner.enabled) {
      owner.forceActiveFocus()
    } else {
      pickerRoot.fallbackFocusRequested()
    }
  }

  function requestClose() {
    var waiting = registry.cancel()
    if (waiting) {
      pickerRoot.message = waiting
    } else {
      pickerRoot.close()
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

  function opens(event) {
    var binding = registry.keybindings ? registry.keybindings.match(event, "workspace") : null
    return !!binding && binding.id === "app/commandPalette"
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
    if (pickerRoot.steps[event.key] !== undefined) {
      pickerRoot.move(pickerRoot.steps[event.key])
      return true
    }
    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
      if (!query.inputMethodComposing) {
        pickerRoot.accept()
      }
      return true
    }
    if (pickerRoot.opens(event)) {
      pickerRoot.focusQuery()
      return true
    }
    return false
  }

  MouseArea {
    anchors.fill: parent
    acceptedButtons: Qt.AllButtons
    onPressed: pickerRoot.requestClose()
    onWheel: function(wheel) {
      wheel.accepted = true
    }
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
    color: Color.token("palette.background")
    border.width: Border.width(popupStyle.borderSpec)
    border.color: popupStyle.borderSpec.color
    clip: true

    AppUi.ChromePopupStyle {
      id: popupStyle
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
        maximumLength: Matching.maxQuery
        placeholderText: pickerRoot.choosing ? "Type to filter…" : "Type a command…"
        leftPadding: commandGlyph.visible ? commandGlyph.width + Style.spacing.md + Style.spacing.xs : horizontalPadding + 1
        Accessible.name: pickerRoot.choosing ? pickerRoot.title : "Search commands"
        Keys.priority: Keys.BeforeItem
        Keys.onPressed: function(event) {
          if (pickerRoot.handleKey(event)) {
            event.accepted = true
          }
        }
        onTextEdited: pickerRoot.refilter()
        Text {
          id: commandGlyph
          visible: !pickerRoot.choosing
          anchors.left: parent.left
          anchors.leftMargin: Style.spacing.md
          anchors.verticalCenter: parent.verticalCenter
          text: ">"
          color: query.placeholderTextColor
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
          readonly property string detail: modelData.detail || ""
          readonly property color ink: selected ? Color.token("palette.selectionForeground")
            : pickerRoot.ink
          readonly property color fill: {
            if (selected) {
              return Color.token("palette.selectionBackground")
            }
            return hovered ? Style.hoverFillFor(pickerRoot.ink, Color.accent) : "transparent"
          }
          objectName: "commandChoice-" + modelData.id
          width: results.width
          height: Math.max(popupStyle.rowHeight, contentItem.implicitHeight + topPadding + bottomPadding)
          leftPadding: popupStyle.horizontalPadding
          rightPadding: leftPadding + (scrollBar.visible ? scrollBar.width : 0)
          topPadding: popupStyle.verticalPadding
          bottomPadding: topPadding
          focusPolicy: Qt.NoFocus
          hoverEnabled: true
          Accessible.name: modelData.label + (detail ? ", " + detail : "")
            + (modelData.reason ? ", unavailable: " + modelData.reason : "")
          background: Rectangle {
            color: row.fill
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
            // Where the choice comes from, so two of one name can be told apart.
            Text {
              objectName: "commandDetail"
              visible: text.length > 0
              Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
              Layout.maximumWidth: row.width * 0.4
              text: row.detail
              textFormat: Text.PlainText
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.caption
              color: row.ink
              opacity: 0.6
              elide: Text.ElideRight
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
        readonly property string notice: pickerRoot.message || pickerRoot.unavailableReason
          || (pickerRoot.matches.length ? "" : "No matching results")
        Layout.fillWidth: true
        Layout.leftMargin: Style.spacing.sm
        Layout.rightMargin: Style.spacing.sm
        text: notice || "↑ ↓ to navigate · Enter to select · Esc to cancel"
        textFormat: Text.PlainText
        font.family: Style.font.menuFamily
        font.pixelSize: Style.font.caption
        color: pickerRoot.ink
        opacity: notice ? 1 : 0.6
        wrapMode: Text.WordWrap
        maximumLineCount: 3
        elide: Text.ElideRight
      }
    }
  }
}
