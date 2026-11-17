import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "quote"
  label: "Quote"
  icon: "󰉾"
  available: !editor.inTable && !editor.inCode

  function execute() {
    editor.toggleQuote()
  }
}
