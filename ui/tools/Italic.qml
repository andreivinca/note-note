import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "italic"
  checked: editor.italic
  label: "Italic"
  icon: "󰉷"
  available: !editor.inCode
  shortcutKey: Qt.Key_I
  shortcutModifiers: Qt.ControlModifier

  function execute() {
    editor.toggleFont("italic")
  }
}
