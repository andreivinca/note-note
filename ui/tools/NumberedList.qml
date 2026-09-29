import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "ol"
  label: "Numbered list"
  icon: "󰉻"
  available: !editor.inCode
  shortcutKey: Qt.Key_Slash
  shortcutModifiers: Qt.ControlModifier

  function execute() {
    editor.toggleListStyle("ol")
  }
}
