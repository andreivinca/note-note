import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "bold"
  checked: editor.bold
  label: "Bold"
  icon: "󰉤"
  available: !editor.inCode
  shortcutKey: Qt.Key_B
  shortcutModifiers: Qt.ControlModifier

  function execute() {
    editor.toggleFont("bold")
  }
}
