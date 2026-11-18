import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "quote"
  label: "Quote"
  icon: "󰉾"
  available: !editor.inTable && !editor.inCode

  // In place through the native helper; a host without it, and a selection
  // it leaves — one holding a heading — take the Markdown route below.
  function execute() {
    if (editor.toggleQuote()) {
      return
    }
    editor.transformBlocks(function(line) {
      return (/^>[ \t]/.test(line.prefix) ? "" : "> ") + line.content
    }, { unchangedMessage: "Quotes cannot be applied inside tables or code blocks" })
  }
}
