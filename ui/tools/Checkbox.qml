import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "todo"
  label: "Checkbox"
  icon: "󰄵"
  shortcutKey: Qt.Key_1
  shortcutModifiers: Qt.ControlModifier

  function execute() {
    editor.toggleList("todo")
  }
}
