import QtQuick
import QtQuick.Controls as QQC
import "../design"
import "../design/controls"

// Notebook tabs, search and the application menu.
Item {
  id: root

  function closeMenu() {
    menu.close()
  }

  // Search dims tabs with no matches.
  property string filterText: ""
  property var shortcutHandler: null
  property var keybindings: null
  readonly property bool searchFocused: search.searchFocused
  function focusSearch() { search.focusSearch() }
  function setSearchText(text) { search.setSearchText(text) }
  // The binder's tabs, passed straight through to the strip.
  property var sections: []
  property var matchCounts: ({})
  property string activeKey: ""
  property bool supportsOverlay: true
  property bool detached: false
  // True while any page stands in for the workspace — settings or the key
  // bindings. The bar only needs to know that the notes are not on screen,
  // not which page took them.
  property bool pageOpen: false
  property color background: Color.menu.background
  property color foreground: Color.menu.text
  property color accent: Color.accent
  property string fontFamily: Style.font.menuFamily
  property int tabFontSize: Style.font.bodySmall
  // The bar sits flush against the top of whatever hosts it. In the overlay
  // that host is a rounded card whose border is painted under the content,
  // so the bar's top corners must curve with it or they square it off.
  property real cornerRadius: 0

  signal sectionActivated(string key)
  signal filterEdited(string text)
  signal clearRequested()
  signal settingsRequested()
  signal keysRequested()
  signal detachToggled()

  height: tabStrip.railHeight

  // The background and overflow fades share this fill.
  readonly property color fill: Color.token("titlebar.background")

  ChromePopupStyle {
    id: popupStyle
  }

  Rectangle {
    anchors.fill: parent
    color: root.fill
    topLeftRadius: root.cornerRadius
    topRightRadius: root.cornerRadius
  }

  Item {
    id: inner
    anchors.fill: parent
    anchors.leftMargin: tabStrip.edgeInset
    // Match the menu button's outside gap to its gap beside Search.
    anchors.rightMargin: Style.spacing.lg

    TabStrip {
      id: tabStrip
      objectName: "notebookTabs"
      anchors.left: parent.left
      anchors.right: search.visible ? search.left : menuButton.left
      anchors.rightMargin: horizontalPadding
      anchors.bottom: parent.bottom
      anchors.alignWhenCentered: false
      height: implicitHeight
      sections: root.sections
      matchCounts: root.matchCounts
      activeKey: root.activeKey
      filtering: root.filterText.length > 0
      background: root.fill
      foreground: root.foreground
      fontFamily: root.fontFamily
      fontSize: root.tabFontSize
      onActivated: function(key) { root.sectionActivated(key) }
    }

    NoteSearch {
      id: search
      objectName: "noteSearch"
      visible: !root.pageOpen
      anchors.right: menuButton.left
      anchors.rightMargin: Style.spacing.lg
      anchors.verticalCenter: parent.verticalCenter
      anchors.alignWhenCentered: false
      width: Math.min(Style.space(220), Math.max(Style.space(140), root.width * 0.24))
      height: implicitHeight
      filterText: root.filterText
      background: root.background
      foreground: root.foreground
      accent: root.accent
      fontFamily: root.fontFamily
      shortcutHandler: root.shortcutHandler
      keybindings: root.keybindings
      onFilterEdited: function(text) { root.filterEdited(text) }
      onClearRequested: root.clearRequested()
    }

    // Everything you do to note-note rather than to the note in front of you
    // lives behind this one button: detaching the window, the settings page,
    // the key bindings. A row of pills along the bar would have to grow with
    // each new one, and each would spend the bar's width saying its own
    // name; the menu spends none until it is asked.
    ChromeButton {
      id: menuButton
      objectName: "applicationMenu"
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.alignWhenCentered: false
      // A tooltip under an open menu is one label too many, and it would
      // stand over the very rows it describes.
      tooltipText: menu.opened ? "" : "Detach the window, settings, key bindings"
      // Keep the filled selected state while the menu or a settings page is open.
      selected: root.pageOpen || menu.opened
      contentForeground: root.foreground
      surfaceColor: root.fill
      accent: root.accent
      width: search.implicitHeight
      height: width
      onClicked: menu.opened ? menu.close() : menu.open()
      // Detaching re-parents the whole content under a different window;
      // the menu that asked for it must not outlive the bar it hangs from.
      onVisibleChanged: if (!visible) {
        menu.close()
      }

      // Center the dots themselves so font baselines and fallback glyphs
      // cannot shift the icon inside its button.
      Row {
        id: menuIcon
        anchors.centerIn: parent
        anchors.alignWhenCentered: false
        readonly property real dotSize: Math.max(1, Style.font.iconLarge / 6)
        spacing: dotSize

        Repeater {
          model: 3
          Rectangle {
            width: menuIcon.dotSize
            height: width
            radius: width / 2
            antialiasing: true
            color: menuButton.contentColor
          }
        }
      }

      // The widest label the menu is about to show, measured at the size it
      // will be drawn: every row then takes the same width and the hover fill
      // is not ragged. Measured against what is on screen rather than every
      // label that could ever be, so an overlay's short menu is not held open
      // to the width of the detached one's longest word.
      TextMetrics {
        id: widestLabel
        text: root.detached ? "Back to overlay" : "Key bindings"
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
      }

      QQC.Popup {
        id: menu
        palette: ControlPalette {}
        // Hung from the button's right edge: the bar's own edge is a few
        // pixels further right, and a menu growing that way would run off it.
        x: menuButton.width - width
        y: menuButton.height + Style.spacing.xs
        readonly property real iconWidth: Math.ceil(Style.font.icon * 1.2)
        readonly property real rowWidth: popupStyle.horizontalPadding * 2 + iconWidth
          + Style.spacing.controlGap + Math.ceil(widestLabel.width)
        // Detaching first, as the one reached for often; the settings page
        // after it.
        readonly property var rows: [
          { id: "detach",
            icon: root.detached ? "󰨟" : "󰏌",
            label: root.detached ? "Back to overlay" : "Detach" },
          { id: "settings",
            icon: "󰒓",
            label: "Settings" },
          { id: "keys",
            icon: "󰌌",
            label: "Key bindings" }
        ].filter(function(row) { return row.id !== "detach" || root.supportsOverlay })

        padding: popupStyle.padding + Border.width(popupStyle.borderSpec)
        background: BorderSurface {
          color: popupStyle.fill
          borderSpec: popupStyle.borderSpec
          radius: popupStyle.radius
        }
        contentItem: Column {
          // Flush, not spaced: a gap between rows makes each read as its own
          // button floating on the card. The hover fill is the only divider
          // a two-row menu needs.
          spacing: 0
          Repeater {
            model: menu.rows
            delegate: Rectangle {
              id: menuRow
              required property var modelData
              width: menu.rowWidth
              height: popupStyle.rowHeight
              radius: popupStyle.rowRadius
              color: rowMouse.containsMouse ? Style.hoverFillFor(root.foreground, root.accent) : "transparent"

              // The row's ink, named once: the glyph and the label are one
              // thing lighting up, not two that agree by accident. The glyph
              // carries it a shade lighter — it labels the row, the word is
              // the row.
              readonly property color ink: rowMouse.containsMouse
                ? Style.hoverStateColor(popupStyle.text, root.accent) : popupStyle.text

              Text {
                id: rowIcon
                textFormat: Text.PlainText
                anchors.left: parent.left
                anchors.leftMargin: popupStyle.horizontalPadding
                anchors.verticalCenter: parent.verticalCenter
                width: menu.iconWidth
                horizontalAlignment: Text.AlignHCenter
                text: menuRow.modelData.icon
                color: Util.alpha(menuRow.ink, 0.75)
                font.family: Style.fontFamily
                font.pixelSize: Style.font.icon
              }

              Text {
                id: rowLabel
                textFormat: Text.PlainText
                anchors.left: rowIcon.right
                anchors.leftMargin: Style.spacing.controlGap
                anchors.verticalCenter: parent.verticalCenter
                text: menuRow.modelData.label
                color: menuRow.ink
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
              }

              MouseArea {
                id: rowMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                  menu.close()
                  if (menuRow.modelData.id === "detach") {
                    root.detachToggled()
                  } else if (menuRow.modelData.id === "settings") {
                    root.settingsRequested()
                  } else {
                    root.keysRequested()
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
