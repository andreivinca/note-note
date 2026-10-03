import QtQuick
import "../design"

// The colours and sizes of the chrome's own inputs: the search field, the
// palette's query, a tool's form. They are the theme's input colours
// wherever the input stands.
QtObject {
  readonly property color text: Color.token("input.foreground")
  readonly property color placeholder: Color.token("input.placeholder")
  readonly property color fill: Color.token("input.background")
  readonly property color borderColor: Color.token("input.border")
  readonly property color focusBorderColor: Color.token("border.focus")
  readonly property real borderWidth: 1
  readonly property real radius: Style.controlRadius
  readonly property real height: Style.space(30)
}
