import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "indent"
  label: "Indent"
  icon: "󰉶"
  available: !editor.inTable && !editor.inCode

  function execute() {
    editor.transformBlocks(function(line) {
      return line.isList ? "  " + line.indent + line.prefix + line.content
                         : line.indent + line.prefix + editor.nbsp4 + line.content
    }, { unchangedMessage: "A nested list item needs one above it" })
  }
}
