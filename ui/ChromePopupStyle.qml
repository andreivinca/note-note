import QtQuick
import "../design"

// Shared by application menus, editing menus and their popup panels: the
// theme's popup colours and one set of measures.
QtObject {
  readonly property color text: Color.token("popup.foreground")
  readonly property color fill: Color.token("popup.background")
  readonly property var borderSpec: Border.flat(Color.token("popup.border"), 1)
  readonly property real radius: Style.popupRadius
  readonly property real padding: Style.spacing.xs
  readonly property real rowRadius: Math.max(0, radius - padding)
  readonly property real rowHeight: Style.spacing.popupRowHeight
  readonly property real horizontalPadding: Style.spacing.controlPaddingX
  readonly property real verticalPadding: Style.spacing.sm
}
