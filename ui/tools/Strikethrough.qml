import QtQuick
import "../editing"
import "../Dialect.js" as Dialect

Tool {
  id: tool
  toolId: "strikeout"
  checked: editor.strikeout
  label: "Strikethrough"
  icon: "󰊁"
  shortcutKey: Qt.Key_S
  shortcutModifiers: Qt.ControlModifier

  function execute() {
    editor.toggleFont("strikeout", Dialect.INLINE_MARKERS.strikeout)
  }
}
