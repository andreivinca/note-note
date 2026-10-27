import QtQuick
import "../design"

// The colours and sizes of the chrome's own inputs: the search field, the
// palette's query, a tool's form. They are the theme's input colours
// wherever the input stands.
QtObject {
  readonly property color text: Colors.token("input.foreground")
  readonly property color placeholder: Colors.token("input.placeholder")
  readonly property color fill: Colors.token("input.background")
  readonly property color borderColor: Colors.token("input.border")
  readonly property color focusBorderColor: Colors.token("border.focus")
  readonly property real borderWidth: 1
  readonly property real radius: Style.controlRadius
  readonly property real height: Style.space(30)
}
