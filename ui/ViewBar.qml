import QtQuick
import "../design"
import "statusbar" as Status

// Sidebar toggle, provider badge, status message, word count and save state.
Item {
  id: root

  property string sourceName: ""
  property url sourceLogo: ""
  property color sourceInk: Color.menu.text
  property color sourceBase: "transparent"
  property string crumb: ""
  property string storage: ""
  // Some providers include their name in the breadcrumb; the badge owns it.
  readonly property string shownCrumb: {
    if (root.crumb === root.sourceName) {
      return ""
    }
    if (root.sourceName && root.crumb.indexOf(root.sourceName + " › ") === 0) {
      return root.crumb.substring(root.sourceName.length + 3)
    }
    return root.crumb
  }
  // The note holds edits not yet confirmed saved: dirty, or a save in flight.
  property bool unsaved: false
  property bool loading: false
  property bool readOnly: false
  property string statusText: ""
  property string hoveredLink: ""
  // What there is to say for the moment: the link under the pointer, else
  // the workspace's passing status. It takes over the status message's text
  // and changes nothing else on the bar.
  readonly property string notice: root.hoveredLink || root.statusText
  property int wordCount: 0
  property bool countVisible: false
  // The sidebar is folded away: the toggle then points the way back.
  property bool listCollapsed: false
  signal listToggled()
  property color background: Color.menu.background
  property color foreground: Color.menu.text
  property color accent: Color.accent
  property string fontFamily: Style.font.menuFamily
  // One size for every caption on the bar.
  property int fontSize: Style.font.caption
  // The bar sits flush along the bottom of whatever hosts it. In the overlay
  // that host is a rounded card whose border is painted under the content,
  // so a bottom corner the bar reaches must curve with it or it squares the
  // card off. Each corner is the host's to set: the bar may stop short of
  // one, against the sidebar, and reach the other.
  property real leftRadius: 0
  property real rightRadius: 0
  implicitHeight: bar.implicitHeight + topDivider.height
  height: implicitHeight

  Status.StatusStyle {
    id: statusStyle
    foreground: root.foreground
    accent: root.accent
    fontFamily: root.fontFamily
    fontSize: root.fontSize
  }

  Rectangle {
    anchors.fill: parent
    color: root.background
    bottomLeftRadius: root.leftRadius
    bottomRightRadius: root.rightRadius
  }
  Rectangle {
    id: topDivider
    width: parent.width
    height: Style.spacing.hairline
    color: Util.alpha(root.foreground, 0.09)
  }

  Status.StatusBar {
    id: bar
    anchors.fill: parent
    anchors.topMargin: topDivider.height
    minimumContentHeight: statusStyle.controlHeight

    leftItems: [
      Status.StatusItem {
        Status.StatusButton {
          objectName: "sidebarToggle"
          style: statusStyle
          iconText: root.listCollapsed ? "󰅂" : "󰅁"
          tooltipText: root.listCollapsed ? "Show sidebar (ctrl+e)" : "Hide sidebar (ctrl+e)"
          Accessible.name: root.listCollapsed ? "Show sidebar" : "Hide sidebar"
          onClicked: root.listToggled()
        }
      },
      Status.StatusItem {
        visible: root.sourceName.length > 0
        ProviderBadge {
          objectName: "providerBadge"
          style: statusStyle
          text: root.sourceName
          logo: root.sourceLogo
          foreground: root.sourceInk
          base: root.sourceBase
        }
      },
      // Where the note lives, until there is a notice to show in its place.
      Status.StatusItem {
        fillWidth: true
        Status.StatusLabel {
          objectName: "statusMessage"
          style: statusStyle
          text: root.notice || [root.shownCrumb, root.storage].filter(function(part) {
            return !!part
          }).join(" › ")
          color: root.notice ? Qt.tint(root.foreground, Util.alpha(root.accent, 0.55))
            : Util.alpha(root.foreground, 0.55)
          // A URL says the most at its two ends; a breadcrumb reads from its start.
          elide: root.hoveredLink ? Text.ElideMiddle : Text.ElideRight
        }
      }
    ]

    rightItems: [
      Status.StatusItem {
        visible: root.countVisible && !root.loading
        Status.StatusLabel {
          objectName: "wordCount"
          style: statusStyle
          text: root.wordCount + (root.wordCount === 1 ? " word" : " words")
          color: Util.alpha(root.foreground, 0.45)
        }
      },
      Status.StatusItem {
        visible: root.loading || root.countVisible
        Status.StatusLabel {
          objectName: "saveStatus"
          style: statusStyle
          iconText: root.loading ? "" : root.unsaved ? "●" : "󰄬"
          iconColor: Qt.tint(root.foreground, Util.alpha(root.accent, 0.6))
          text: root.loading ? "Loading…" : root.unsaved ? "Unsaved"
            : root.readOnly ? "Read-only" : "Saved"
          color: Util.alpha(root.foreground, 0.5)
        }
      }
    ]
  }
}
