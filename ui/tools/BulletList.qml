import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "ul"
  label: "Bullet list"
  icon: "󰉹"
  available: !editor.inCode
  shortcutKey: Qt.Key_Period
  shortcutModifiers: Qt.ControlModifier

  function execute() {
    editor.toggleListStyle("ul")
  }
}
