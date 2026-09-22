.pragma library

// The document vocabulary shared by QML readers and editing tools.
// tests/test_regressions.py checks agreement with the Python and native adapters.
var QUOTE_PX = 40
var CODE_PAD_PX = 14
var MAX_IMAGE_DISPLAY = 640
var LINE_HEIGHT_PCT = 130
// The native text inspector's interface the editor was written against
// (cpp/textblocks.h, TextBlocks::Version): a built module of another
// version is refused whole at load.
var NATIVE_VERSION = 1

// The invisible characters the editor itself plants, mirrored from
// services/markdown/qthtml/dialect.py: Markdown has no empty paragraph, so a
// blank line the user lands on is a paragraph holding BLANK_PARAGRAPH; an
// image that opens a list item is painted too high by Qt, so IMAGE_LEAD goes
// in front of it. One character, several roles — the code says which one it
// is planting.
var BLANK_PARAGRAPH = "\u00a0"
var IMAGE_LEAD = "\u00a0"
// Qt drops a list item with no content, so an empty checkbox carries this.
var EMPTY_ITEM = "\u00a0"

// The inline tools' Markdown, by tool id — what a tool types inside a code
// block, where the fence holds the characters literally (NoteEditor,
// typeMarker). Mirrors reader.INLINE_MARKERS in
// services/markdown/qthtml/reader.py, plus the code span's backtick
// (services/markdown/mdtext.py, code_span).
var INLINE_MARKERS = { bold: "**", italic: "*", underline: "_", strikeout: "~~", highlight: "==", code: "`" }


function documentHtml(html) {
  return html.replace(/<!--(Start|End)Fragment-->/g, "")
    .replace(/<a\b([^>]*)>/gi, function(tag, attributes) {
      if (/\bstyle\s*=/i.test(attributes)) {
        return tag
      }
      return '<a' + attributes + ' style="-qt-foreground:none;">'
    })
}
