import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "strikeout"
  checked: editor.strikeout
  label: "Strikethrough"
  icon: "󰊁"
  available: !editor.inCode
  shortcutKey: Qt.Key_S
  shortcutModifiers: Qt.ControlModifier

  function execute() {
    editor.toggleFont("strikeout")
  }
}
