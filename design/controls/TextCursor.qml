import QtQuick

Rectangle {
  id: cursor
  required property var textInput
  width: 1
  visible: textInput.activeFocus && !textInput.readOnly && textInput.selectionStart === textInput.selectionEnd

  function restartBlink() {
    cursor.opacity = 1
    if (cursor.visible && Application.styleHints.cursorFlashTime > 0) {
      blink.restart()
    } else {
      blink.stop()
    }
  }
  Connections {
    target: cursor.textInput
    function onCursorPositionChanged() { cursor.restartBlink() }
    function onActiveFocusChanged() { cursor.restartBlink() }
  }
  Timer {
    id: blink
    interval: Math.max(1, Application.styleHints.cursorFlashTime / 2)
    running: cursor.visible && Application.styleHints.cursorFlashTime > 0
    repeat: true
    onTriggered: cursor.opacity = cursor.opacity === 1 ? 0 : 1
  }
}
