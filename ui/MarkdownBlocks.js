.pragma library

// Where the blocks are in the Markdown the converter just handed over. The
// converter says what every line is (qthtml/reader.py, the `kinds` of its
// answer: "code" for a fenced block, fences included, "table" for a row,
// "html" for a nested table kept as HTML, "separator" for the blank between
// blocks, and so on), so nothing here parses Markdown: a second grammar in
// the editor was a second opinion, and it had drifted.

// Each line of `kind`, keyed by its index, pointing to the run it is in.
function runs(map, kind) {
  var result = {}, open = null, kinds = map.kinds || []
  for (var i = 0; i < kinds.length; i++) {
    if (kinds[i] !== kind) {
      open = null
      continue
    }
    if (!open) {
      open = { start: i, end: i }
    }
    open.end = i
    result[i] = open
  }
  return result
}

// Each fenced line points to its complete block.
function fences(map) {
  return runs(map, "code")
}

// The tables, in order, each as its span of rows.
function tables(map) {
  var byLine = runs(map, "table"), result = []
  for (var i = 0; i < (map.kinds || []).length; i++) {
    if (byLine[i] && byLine[i].start === i) {
      result.push(byLine[i])
    }
  }
  return result
}

// A row of a table the editor can rewrite as Markdown.
function isRow(map, i) {
  return (map.kinds || [])[i] === "table"
}

// A line of a table, in either form: a row, or a nested table kept as HTML.
function isTable(map, i) {
  var kind = (map.kinds || [])[i]
  return kind === "table" || kind === "html"
}

// Whether the note holds a nested table, which only the native inspector
// can edit.
function hasHtmlTable(map) {
  return (map.kinds || []).indexOf("html") >= 0
}
