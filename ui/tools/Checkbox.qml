import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "todo"
  label: "Checkbox"
  icon: "󰄵"
  available: !editor.inCode
  shortcutKey: Qt.Key_1
  shortcutModifiers: Qt.ControlModifier

  function execute() {
    editor.toggleListStyle("todo")
  }
}
