import QtQuick
import "../editing"
import "../MarkdownBlocks.js" as MarkdownBlocks

Tool {
  id: tool
  toolId: "codeblock"
  label: "Code block"
  icon: "󰅩"
  available: !editor.inTable

  function execute() {
    if (editor.selectionInCode(true)) {
      editor.editBlocks(function(lines) {
        return lines
      }, editor.blockAt(editor.selection().from))
    } else {
      editor.editBlocks(fenceBlocks)
    }
  }

  function fenceBlocks(lines, map, range) {
    var first = range.first, last = range.last
    var code = MarkdownBlocks.fences(map)
    // A selection crossing a fence includes that entire code block.
    if (code[first]) {
      first = code[first].start
    }
    if (code[last]) {
      last = code[last].end
    }
    var from = range.from, to = range.to
    for (var i = first; i <= last; i++) {
      if (MarkdownBlocks.isTable(map, i) || map.kinds[i] === "rule") {
        editor.report("Code blocks cannot replace tables or horizontal rules")
        return
      }
      if (map.blocks[i] >= 0) {
        from = Math.min(from, map.blocks[i])
        to = Math.max(to, map.blocks[i])
      }
    }
    var text = editor.textOfBlocks(from, to)
    if (text.indexOf("\uFFFC") >= 0) {
      editor.report("Code blocks cannot contain images")
      return
    }
    // Code contains the visible text, without inline or block markers.
    // An empty paragraph's rendering filler is not part of its content.
    text = text.replace(/[\u2028\u2029]/g, "\n").replace(/\u00a0$/gm, "")
    var fence = "```", ticks = /`+/g, match
    while ((match = ticks.exec(text)) !== null) {
      if (match[0].length >= fence.length) {
        fence = match[0] + "`"
      }
    }
    return lines.slice(0, first).concat(["", fence, text, fence, ""], lines.slice(last + 1))
  }
}
