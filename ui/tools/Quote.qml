import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "quote"
  label: "Quote"
  icon: "󰉾"

  function execute() {
    editor.transformBlocks(function(line) {
      return (/^>[ \t]/.test(line.prefix) ? "" : "> ") + line.content
    }, { unchangedMessage: "Quotes cannot be applied inside tables or code blocks" })
  }
}
