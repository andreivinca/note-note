import QtQuick
import QtQml.Models
import "../design"
import "../design/controls"

// Scrollable notebook tabs, with provider logos when available.
Item {
  id: root

  // The tabs as the host builds them: { key, provider, name, color, logo, count }.
  property var sections: []
  // Search hits per tab key; kept beside `sections` so a keystroke moves
  // the numbers without touching the tabs (see the host's rebuildRows).
  property var matchCounts: ({})
  property string activeKey: ""
  property bool filtering: false
  // The exact fill behind the strip, for the overflow fades to fade into.
  property color background: Color.menu.background
  property color activeBackground: Color.token("tab.activeBackground")
  property color activeForeground: Color.token("tab.activeForeground")
  property color inactiveForeground: Color.token("tab.inactiveForeground")
  property color foreground: Color.menu.text
  property string fontFamily: Style.font.menuFamily
  property int fontSize: Style.font.bodySmall
  // Tab geometry scales with typography, independently of shell spacing.
  readonly property real designScale: root.fontSize / 16
  readonly property real horizontalPadding: Math.round(12 * root.designScale)
  readonly property real contentGap: Math.round(8 * root.designScale)
  readonly property real iconSize: root.fontSize
  readonly property real edgeInset: Math.round(8 * root.designScale)
  readonly property real railHeight: Math.round(32 * root.designScale) + edgeInset * 2
  // Hover faces sit close to the content below, with more breathing room above.
  readonly property real topInset: Math.round(7 * root.designScale)
  readonly property real bottomInset: Math.round(5 * root.designScale)
  readonly property real tabRadius: Math.round(12 * root.designScale)
  readonly property real selectedRadius: Math.round(10 * root.designScale)
  readonly property real faceHeight: railHeight - topInset - bottomInset
  implicitHeight: faceHeight + bottomInset
  signal activated(string key)
  // A tab was right-clicked; what its menu offers is the bar's to say.
  signal menuRequested(var tab)
  // A tab was dragged to stand before the tab `before`, or last when
  // `before` is "". The order is the host's to keep: the strip shows the
  // sections it is given back.
  signal moved(string key, string before)

  clip: true
  onSectionsChanged: root.dragTab = null

  // ---- dragging a tab to another place
  // The tab being dragged, where in it the pointer took hold, and where the
  // pointer is now across the strip. The tab is drawn under the pointer
  // while its slot moves among the others, which take their places as it
  // passes them.
  property var dragTab: null
  property real grabX: 0
  property real pointerX: 0
  // Where the dragged tab is drawn across the row: under the pointer, from
  // the first slot to the last and no further.
  readonly property real dragX: root.dragTab
    ? Math.max(0, Math.min(strip.contentX + root.pointerX - root.grabX, row.width - root.dragTab.width)) : 0

  function startDrag(tab, origin, position) {
    root.grabX = tab.mapFromItem(null, origin).x
    root.pointerX = strip.mapFromItem(null, position).x
    root.dragTab = tab
  }

  function dragTo(tab, position) {
    if (root.dragTab !== tab) {
      return
    }
    root.pointerX = strip.mapFromItem(null, position).x
    root.placeDragged()
  }

  // The dragged tab takes the slot nearest to where it is drawn: of its
  // places among the others, the one whose start is closest. Where its slot
  // is now does not count, so carried back, a tab takes its own place back.
  function placeDragged() {
    var start = 0, slot = 0, place = 0, nearest = Math.abs(root.dragX)
    for (var i = 0; i < tabs.count; i++) {
      var other = tabs.itemAt(i)
      if (other === root.dragTab) {
        continue
      }
      slot++
      start += other.width + row.spacing
      if (Math.abs(root.dragX - start) < nearest) {
        nearest = Math.abs(root.dragX - start)
        place = slot
      }
    }
    if (place !== root.dragTab.visualIndex) {
      visualModel.items.move(root.dragTab.visualIndex, place)
    }
  }

  // The tab goes back to its own slot until the host answers with the
  // order it keeps.
  function finishDrag(tab) {
    if (root.dragTab !== tab) {
      return
    }
    root.dragTab = null
    var place = tab.visualIndex
    if (place === tab.index) {
      return
    }
    var before = place + 1 < tabs.count ? tabs.itemAt(place + 1).modelData.key : ""
    visualModel.items.move(place, tab.index)
    root.moved(tab.modelData.key, before)
  }

  function scrollTo(x) {
    strip.contentX = Math.max(0, Math.min(x, Math.max(0, strip.contentWidth - strip.width)))
  }

  // Scrolls while the dragged tab is held against either end of the strip,
  // its slot following the tabs it is carried past.
  Timer {
    interval: 30
    repeat: true
    running: root.dragTab !== null
    onTriggered: {
      var edge = Math.min(Style.space(48), strip.width / 4)
      var distance = root.pointerX < edge ? root.pointerX - edge
        : (root.pointerX > strip.width - edge ? root.pointerX - strip.width + edge : 0)
      if (!distance) {
        return
      }
      root.scrollTo(strip.contentX + Math.max(-Style.space(12), Math.min(distance / 4, Style.space(12))))
      root.placeDragged()
    }
  }

  // The open tab stays in sight: however it was switched — a click here,
  // ctrl+tab, a search hopping to the tab that has hits — the strip
  // scrolls to show it. A new set of tabs is revealed as its active one is
  // made (the repeater says), and the row is laid out here and now so the
  // tab's place is known.
  onActiveKeyChanged: revealActive()
  onWidthChanged: revealActive()
  function revealActive() {
    row.forceLayout()
    for (var i = 0; i < tabs.count; i++) {
      var it = tabs.itemAt(i)
      if (!it || it.modelData.key !== root.activeKey) {
        continue
      }
      var start = it.x
      var end = it.x + it.width
      if (strip.contentX > start) {
        strip.contentX = start
      } else if (strip.contentX + strip.width < end) {
        strip.contentX = Math.max(0, end - strip.width)
      }
      return
    }
  }

  Flickable {
    id: strip
    anchors.fill: parent
    contentWidth: row.width
    boundsBehavior: Flickable.StopAtBounds
    interactive: contentWidth > width && root.dragTab === null

    // Sideways is the only way this strip goes, so every wheel drives it
    // there — a mouse's vertical notches are the only wheel most mice have.
    WheelHandler {
      target: null
      acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
      onWheel: function(event) {
        var d = (event.pixelDelta.x !== 0 || event.pixelDelta.y !== 0)
          ? (event.pixelDelta.x + event.pixelDelta.y) * 3
          : ((event.angleDelta.x + event.angleDelta.y) / 120) * Style.space(56)
        root.scrollTo(strip.contentX - d)
      }
    }

    Row {
      id: row
      height: strip.height
      // Bounds include both shoulders. Share that unused corner space while
      // keeping the painted faces separated by the hover's lower inset.
      spacing: root.bottomInset - root.tabRadius * 2

      Repeater {
        id: tabs
        onItemAdded: function(index, item) {
          if (item.modelData.key === root.activeKey) {
            root.revealActive()
          }
        }

        // The tabs live behind a DelegateModel, as the note list's rows do,
        // so a drag moves a tab among the others without a model write: one
        // would build every tab again and drop the one under the pointer.
        model: DelegateModel {
          id: visualModel
          model: root.sections

          delegate: Item {
            id: tab
            required property var modelData
            required property int index
            objectName: "notebookTab-" + modelData.key
            readonly property bool current: modelData.key === root.activeKey
            readonly property int hits: root.matchCounts[modelData.key] || 0
            // While a search is on, a tab with nothing to show steps back —
            // the rail's old dimming, kept.
            readonly property bool dimmed: root.filtering && hits === 0
            readonly property bool branded: String(modelData.logo || "").length > 0
            readonly property string displayName: modelData.name || "Notes"
            readonly property real faceWidth: content.implicitWidth + root.horizontalPadding * 2
            // Where this tab sits on screen while a drag moves it.
            readonly property int visualIndex: tab.DelegateModel.itemsIndex
            readonly property bool dragged: tab === root.dragTab

            anchors.verticalCenter: parent.verticalCenter
            width: faceWidth + root.tabRadius * 2
            height: root.height
            // Selected shoulders own the painted area beneath neighboring faces,
            // and a dragged tab passes over them all.
            z: dragged ? 2 : (current ? 1 : 0)
            opacity: dimmed ? 0.38 : 1
            transform: Translate {
              x: tab.dragged ? root.dragX - tab.x : 0
            }

            TabSurface {
              id: tabSurface
              anchors.fill: parent
              radius: root.tabRadius
              selectedRadius: root.selectedRadius
              bottomInset: root.bottomInset
              selected: tab.current
              // The active notebook uses the theme's selected-tab colors.
              color: tab.current || hovered ? root.activeBackground : "transparent"
              onClicked: root.activated(tab.modelData.key)
              onMenuRequested: root.menuRequested(tab.modelData)
              onDraggedChanged: {
                if (tabSurface.dragged) {
                  root.startDrag(tab, tabSurface.dragOrigin, tabSurface.dragPosition)
                } else {
                  root.finishDrag(tab)
                }
              }
              onDragPositionChanged: root.dragTo(tab, tabSurface.dragPosition)
              Behavior on color {
                ColorAnimation {
                  duration: 120
                }
              }
            }

            Row {
              id: content
              anchors.left: parent.left
              anchors.leftMargin: root.tabRadius + root.horizontalPadding
              y: (tab.height - root.bottomInset - height) / 2
              spacing: root.contentGap
              anchors.alignWhenCentered: false

              Image {
                visible: tab.branded
                source: tab.modelData.logo || ""
                anchors.verticalCenter: parent.verticalCenter
                anchors.alignWhenCentered: false
                width: root.iconSize
                height: root.iconSize
                sourceSize.width: width * 2
                sourceSize.height: height * 2
                fillMode: Image.PreserveAspectFit
                smooth: true
                opacity: tab.current ? 1 : 0.72
              }

              Text {
                id: label
                textFormat: Text.PlainText
                anchors.verticalCenter: parent.verticalCenter
                anchors.alignWhenCentered: false
                // Capped the way a browser caps a tab: a long notebook name
                // elides, and the tooltip below says the whole of it.
                width: Math.min(implicitWidth, Style.space(200))
                text: tab.displayName
                color: tab.current ? root.activeForeground : root.inactiveForeground
                font.family: root.fontFamily
                font.pixelSize: root.fontSize
                elide: Text.ElideRight
              }

              // The tab's search hits, while a search is on — the number the
              // closed tabs answer with.
              Rectangle {
                visible: root.filtering && tab.hits > 0
                anchors.verticalCenter: parent.verticalCenter
                width: hitText.width + Style.spacing.sm * 2
                height: hitText.height + Style.spacing.xxs
                radius: height / 2
                color: Util.alpha(root.foreground, 0.1)

                Text {
                  id: hitText
                  textFormat: Text.PlainText
                  anchors.centerIn: parent
                  text: tab.hits
                  color: Util.alpha(root.foreground, 0.75)
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }
              }
            }

            PanelToolTip {
              visible: tabSurface.hovered && !tab.dragged && (label.implicitWidth > label.width || !root.filtering)
              text: tab.displayName + " · " + (root.filtering ? tab.hits : (tab.modelData.count || 0))
            }
          }
        }
      }
    }
  }

  // ---- there is more: fades at the ends the strip has scrolled past
  Rectangle {
    anchors.left: parent.left
    anchors.top: parent.top
    anchors.bottom: parent.bottom
    width: Style.space(18)
    visible: strip.contentWidth > strip.width + 1 && strip.contentX > 0
    gradient: Gradient {
      orientation: Gradient.Horizontal
      GradientStop { position: 0.0; color: Util.alpha(root.background, 0.95) }
      GradientStop { position: 1.0; color: "transparent" }
    }
  }

  Rectangle {
    anchors.right: parent.right
    anchors.top: parent.top
    anchors.bottom: parent.bottom
    width: Style.space(18)
    visible: strip.contentWidth > strip.width + 1
             && strip.contentX < strip.contentWidth - strip.width - 1
    gradient: Gradient {
      orientation: Gradient.Horizontal
      GradientStop { position: 0.0; color: "transparent" }
      GradientStop { position: 1.0; color: Util.alpha(root.background, 0.95) }
    }
  }
}
