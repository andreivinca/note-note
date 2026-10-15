import QtQuick
import QtQuick.Controls as Controls
import ".."

// A choice among `options`, showing `value`. The control announces a
// choice with `selected` and writes nothing back: the value shown is the
// caller's, bound or set, the way every control here keeps its inputs.
Controls.ComboBox {
  id: control
  property var options: []
  property string value: ""
  property string label: ""
  property bool showLabel: false
  property color foreground: Color.foreground
  property color accent: Color.accent
  property string fontFamily: Style.font.family
  readonly property bool popupOpen: popup.opened
  signal selected(string value)
  model: options
  textRole: "label"
  valueRole: "value"
  // Found in `options` itself: the ComboBox's indexOfValue answers -1 until
  // its model is in, and a binding on it is not asked again after, so a
  // dropdown made with its value already set would show none.
  currentIndex: options.findIndex(function(option) {
    return String(option.value) === value
  })
  font.family: fontFamily
  font.pixelSize: Style.font.body
  palette.text: foreground
  palette.buttonText: foreground
  palette.highlight: accent
  onActivated: selected(String(currentValue))
  function open() {
    forceActiveFocus()
    popup.open()
  }
  function close() {
    popup.close()
  }
}
