import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "indent"
  label: "Indent"
  icon: "󰉶"
  available: (!editor.inTable || editor.inList) && !editor.inCode

  function execute() {
    if (editor.indentBlocks(1)) {
      return
    }
    editor.transformBlocks(function(line) {
      return line.isList ? "  " + line.indent + line.prefix + line.content
                         : line.indent + line.prefix + editor.nbsp4 + line.content
    }, { unchangedMessage: "A nested list item needs one above it" })
  }
}
