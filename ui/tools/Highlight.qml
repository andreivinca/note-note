import QtQuick
import "../editing"
import "../Dialect.js" as Dialect

Tool {
  id: tool
  toolId: "highlight"
  label: "Highlight"
  icon: "󰙒"
  shortcutKey: Qt.Key_H
  shortcutModifiers: Qt.ControlModifier | Qt.ShiftModifier

  function execute() {
    if (!editor.acceptsInline() || editor.markedInCode(Dialect.INLINE_MARKERS.highlight)) {
      return
    }
    var range = editor.selection()
    if (range.from === range.to) {
      return
    }
    var lit = Dialect.hasHighlight(range.html, editor.codeChipColour)
    // Off: only the marker background goes; text keeps its colour and code
    // its chip.
    var html = lit ? Dialect.withoutBackground(range.html, editor.codeChipColour, true)
                   : '<span style="background-color:' + editor.highlightColour + ';">' + range.html + "</span>"
    editor.replaceInline(html, true)
  }
}
