.pragma library
.import "Dialect.js" as Dialect
.import "QuoteBars.js" as QuoteBars
.import "AudioObjects.js" as AudioObjects

// A rich paste made to fit the notebook it lands in (docs/decisions.md, "A
// rich paste brings only what the notebook can keep"). The paste used to put
// in whatever the clipboard held, so a
// notebook with no table tool still showed a pasted table — which its save
// then flattened, or now refuses. The editor must not show what the
// notebook cannot keep.
//
// What is read here is Qt's own serialisation of the clipboard (the
// editor's pasteReader): the dialect's vocabulary, the one QuoteBars and the
// converter read, however the source wrote its HTML. Two answers:
//
// - colours the notebook has no tool for come off. A browser copies every
//   run's computed colour and background, which are the page's look rather
//   than formatting anyone chose, and taking them off loses no text;
// - anything else it has no tool for (`supports`, the provider's `tools`),
//   or a picture it cannot store (`canImages`), makes the paste plain text,
//   and is named so the editor can say why.
//
// Each pattern errs towards finding: a false find costs a paste its
// formatting, a miss costs the save — the provider refuses it.

// The style attribute of every span — where Qt writes a run's formatting.
function _spanStyles(html) {
  var out = [], re = /<span\b[^>]*\bstyle="([^"]*)"/gi, m
  while ((m = re.exec(html)) !== null) {
    out.push(m[1])
  }
  return out
}

function _inSpan(pattern) {
  return function(html) {
    return _spanStyles(html).some(function(style) {
      return pattern.test(style)
    })
  }
}

function _inHtml(pattern) {
  return function(html) {
    return pattern.test(html)
  }
}

function _ofKind(kind) {
  return function(html, kinds) {
    return kinds.indexOf(kind) >= 0
  }
}

// Each tool's construct as Qt writes it, and what the status line calls it.
// The colours are not here: they come off instead (withoutColours).
var CONSTRUCTS = [
  { capability: "table", name: "tables", found: _inHtml(/<table\b/i) },
  { capability: "rule", name: "rules", found: _ofKind("rule") },
  { capability: "quote", name: "quotes", found: _ofKind("quote") },
  { capability: "codeblock", name: "code blocks", found: _ofKind("code") },
  { capability: "h1", name: "headings", found: _inHtml(/<h1\b/i) },
  { capability: "h2", name: "headings", found: _inHtml(/<h2\b/i) },
  { capability: "h3", name: "headings", found: _inHtml(/<h3\b/i) },
  { capability: "ul", name: "bulleted lists", found: _inHtml(/<ul\b/i) },
  { capability: "ol", name: "numbered lists", found: _inHtml(/<ol\b/i) },
  { capability: "todo", name: "checklists", found: _inHtml(/<li\b[^>]*\bclass="(checked|unchecked)"/i) },
  { capability: "indent", name: "nested lists", found: _inHtml(/-qt-list-indent:\s*([2-9]|\d\d)/i) },
  { capability: "link", name: "links", found: _inHtml(/<a\b[^>]*\bhref=/i) },
  { capability: "bold", name: "bold text", found: _inSpan(/font-weight\s*:\s*[6-9]\d\d/i) },
  { capability: "italic", name: "italic text", found: _inSpan(/font-style\s*:\s*italic/i) },
  { capability: "underline", name: "underlined text", found: _inSpan(/text-decoration\s*:[^;]*underline/i) },
  { capability: "strikeout", name: "struck-out text", found: _inSpan(/text-decoration\s*:[^;]*line-through/i) },
  { capability: "code", name: "inline code", found: function(html) {
    return _spanStyles(html).some(Dialect.hasMonoFamily)
  } }
]

// The paste without the colours the notebook has no tool for: a text
// colour without textColor, a highlight without highlight. The inline code
// chip is the editor's own paint, never a highlight (Dialect.hasHighlight).
function withoutColours(html, supports, chip) {
  return html.replace(/(<span\b[^>]*\bstyle=")([^"]*)(")/gi, function(match, open, style, close) {
    var kept = style
    if (!supports("textColor")) {
      kept = kept.replace(/(^|[\s;])color\s*:[^;]*;?/gi, "$1")
    }
    if (!supports("highlight")) {
      kept = Dialect.withoutBackground(kept, chip, true)
    }
    return open + kept + close
  })
}

// What the paste holds that the notebook cannot store, by name, in
// CONSTRUCTS order and without repeats; pictures and recordings last.
function lacking(html, supports, canImages) {
  var kinds = QuoteBars.kinds(html), names = []
  function add(name) {
    if (names.indexOf(name) < 0) {
      names.push(name)
    }
  }
  for (var i = 0; i < CONSTRUCTS.length; i++) {
    var construct = CONSTRUCTS[i]
    if (!supports(construct.capability) && construct.found(html, kinds)) {
      add(construct.name)
    }
  }
  if (!canImages) {
    var re = /<img\b[^>]*\bsrc="([^"]*)"/gi, m
    while ((m = re.exec(html)) !== null) {
      add(AudioObjects.recording(m[1]) ? "recordings" : "pictures")
    }
  }
  return names
}

// { html, lacking }: the paste as the notebook can take it, and what it
// holds that the notebook cannot — which, when there is any, makes it the
// plain paste.
function fit(html, supports, canImages, chip) {
  var fitted = withoutColours(html, supports, chip)
  return { html: fitted, lacking: lacking(fitted, supports, canImages) }
}
