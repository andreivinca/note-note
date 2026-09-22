import QtQuick
import "../editing"
import "../Dialect.js" as Dialect

Tool {
  id: tool
  toolId: "todo"
  label: "Checkbox"
  icon: "󰄵"

  function execute() {
    editor.transformBlocks(function(line) {
      return line.indent + (/\[[ xX]\]/.test(line.prefix) ? "" : "- [ ] ") + (line.content || Dialect.EMPTY_ITEM)
    }, { list: true })
  }
}
