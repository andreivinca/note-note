import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "ol"
  label: "Numbered list"
  icon: "󰉻"
  shortcutKey: Qt.Key_Slash
  shortcutModifiers: Qt.ControlModifier

  function execute() {
    editor.toggleListStyle("ol")
  }
}
