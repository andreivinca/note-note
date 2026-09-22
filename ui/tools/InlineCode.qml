import QtQuick
import "../editing"
import "../Dialect.js" as Dialect

Tool {
  id: tool
  toolId: "code"
  label: "Inline code"
  icon: "󰅴"

  function execute() {
    if (!editor.acceptsInline() || editor.markedInCode(Dialect.INLINE_MARKERS.code)) {
      return
    }
    var range = editor.selection()
    if (range.from === range.to) {
      return
    }
    var html = Dialect.hasMonoFamily(range.html)
      ? editor.withoutChip(Dialect.withoutMonoFamily(range.html))
      : "<span style=\"font-family:'" + Dialect.MONO_FAMILY + "'; background-color:"
        + editor.codeChipColour + ';">' + range.html + "</span>"
    editor.replaceInline(html, true)
  }
}
