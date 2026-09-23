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

// The inline-code family, exactly as dialect.MONO_FAMILY: a run is code
// when this generic family is among the families its style names, not
// when a family's name holds "mono" — a monospace note face is prose
// (docs/engine-notes.md).
var MONO_FAMILY = "monospace"

// The families one font-family value names, unquoted:
// "'DejaVu Sans Mono','monospace'" -> ["DejaVu Sans Mono", "monospace"].
function fontFamilies(value) {
  var out = []
  var names = value.split(",")
  for (var i = 0; i < names.length; i++) {
    var name = names[i].trim().replace(/^['"]|['"]$/g, "")
    if (name !== "") {
      out.push(name)
    }
  }
  return out
}

// Whether the HTML holds a run in the inline-code family.
function hasMonoFamily(html) {
  var re = /font-family\s*:\s*([^;"]*)/g, m
  while ((m = re.exec(html)) !== null) {
    if (fontFamilies(m[1]).indexOf(MONO_FAMILY) >= 0) {
      return true
    }
  }
  return false
}

// The HTML with its inline-code family declarations taken out; every
// other family stays.
function withoutMonoFamily(html) {
  return html.replace(/font-family\s*:\s*([^;"]*);?\s*/g, function(declaration, value) {
    return fontFamilies(value).indexOf(MONO_FAMILY) >= 0 ? "" : declaration
  })
}

// The background colours a run's style declares, lower-cased.
function backgroundColours(html) {
  var re = /background-color\s*:\s*([^;"]*)/gi, out = [], m
  while ((m = re.exec(html)) !== null) {
    out.push(m[1].trim().toLowerCase())
  }
  return out
}

// Whether the HTML holds a highlight: a background that is not the inline
// code chip's (`chip`), which is display only and never a marker.
function hasHighlight(html, chip) {
  return backgroundColours(html).some(function(colour) { return colour !== String(chip).toLowerCase() })
}

// The HTML with one background colour's declarations taken out; every
// other declaration stays. `keep` true takes out every background *but*
// that colour instead — the highlight off, the chip left.
function withoutBackground(html, colour, keep) {
  var wanted = String(colour).toLowerCase()
  return html.replace(/background-color\s*:\s*([^;"]*);?\s*/gi, function(declaration, value) {
    var matches = value.trim().toLowerCase() === wanted
    return (keep ? !matches : matches) ? "" : declaration
  })
}

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
