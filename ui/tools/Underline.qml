import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "underline"
  checked: editor.underline
  label: "Underline"
  icon: "󰊇"
  available: !editor.inCode
  shortcutKey: Qt.Key_U
  shortcutModifiers: Qt.ControlModifier

  function execute() {
    editor.toggleFont("underline")
  }
}
