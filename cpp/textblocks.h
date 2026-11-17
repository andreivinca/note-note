// The native text inspector: the things QML cannot ask a TextEdit —
// "what are your blocks, and what block format does each carry?", "where
// are your images, and how large are they drawn?"
//
// QML's TextEdit exposes the document only as serialised HTML
// (getFormattedText), so the editor's quote bars used to find quote blocks
// by scanning that HTML with a regex. This class reads the same answers from
// the QTextDocument itself, through the TextEdit's `textDocument` property.
// It is inspection first: the writes are canonical list margins
// (normalizeListMargins) and an image's display width (setImageWidth, the
// corner-handle resize), both format-only, a blank filler character
// into a block Qt would otherwise hide (fillEmptyBlocksBeforeTables), and
// text put in the way typing would (insertPlainText, the plain paste
// inside a code block).
// Removing an empty paragraph also lives here: it must keep the following
// block's list membership and character format, which QML cannot set.
// Table operations use native frame boundaries to target the caret's table,
// including Backspace immediately after a table and edits inside nested ones.
// List actions target document blocks directly, including empty table cells;
// textlists.cpp owns list membership, toggles and leaving an empty item.
// textparagraphs.cpp owns the paragraph styles the toolbar sets in place —
// quote, heading, code block — and the rules and tables it inserts, as the
// writer would make them (qthtml/writer.py), so that an edit and the same
// note reopened are one document. Both share textedits.h.
// TextLinks colours and locates URLs without changing the document, and
// clears inherited anchors from empty paragraphs.
// The edit-block brackets (beginEditBlock/
// endEditBlock) fence the editor's own strokes into one undo step, including
// the first paragraph's character format that Qt does not record itself.
//
// The module is OPTIONAL in the shell. It is built locally (`sh cpp/build.sh`)
// against the system Qt and loaded by a directory import
// (hosts/omarchy/TextInspector.qml); the executable links the same sources
// and registers the same types under the same name (hosts/standalone);
// when the library is absent the editor falls back to the HTML scan
// (ui/QuoteBars.js) and images simply have no resize handle. A module
// built from older sources is refused the same way, whole: the editor
// checks `version` once at load (ui/Dialect.js, NATIVE_VERSION) instead of
// feeling for each method. cpp/selftest.py asserts the fallback and the
// inspector agree.
//
// The header says what each call means; textblocks.cpp is how.
#pragma once

#include "dialect.h"
#include "textlinks.h"

#include <QObject>
#include <QQmlEngine>
#include <QQuickTextDocument>
#include <QTextBlock>
#include <QTextBlockFormat>
#include <QTextDocument>
#include <QTextImageFormat>
#include <QVariantList>
#include <QVariantMap>

class TextBlocks : public QObject
{
    Q_OBJECT
    QML_ELEMENT
    Q_PROPERTY(QQuickTextDocument *document READ document WRITE setDocument NOTIFY documentChanged)
    Q_PROPERTY(int linkRevision READ linkRevision NOTIFY linksChanged)
    // The interface this module offers. Bump it with any change to an
    // invokable's name, arguments or answer; the editor refuses a module
    // of another version at load.
    Q_PROPERTY(int version READ version CONSTANT)
    Q_PROPERTY(int contentRevision READ contentRevision NOTIFY contentChanged)
    // The width of a list level: the room in front of an item's text that
    // its number or checkbox sits in. Qt's 40px leaves a wide gap; the
    // editor sizes it to its font so a list sits close to the margin.
    Q_PROPERTY(qreal listIndent READ listIndent WRITE setListIndent NOTIFY listIndentChanged)
    static constexpr int Version = 9;

public:
    Q_INVOKABLE int insertFormattedText(int from, int to, const QString &text, const QVariantMap &styles);
    Q_INVOKABLE bool setTextColor(int from, int to, const QString &color);
    Q_INVOKABLE QVariantMap tableInfo(int position) const;
    Q_INVOKABLE int editTable(int position, const QString &operation, int index, int count);
    Q_INVOKABLE int appendTableRow(int position);
    Q_INVOKABLE int deletePreviousTable(int position);

    // Format the actual selected paragraphs, with an exclusive selection end.
    // Mixed selections adopt the style; a uniform selection toggles it off,
    // though checkboxes are checked first and come off once all are checked.
    // When `toggle` is false the style applies even where it is set.
    // List membership never crosses a table cell. Return the selection adjusted
    // for empty items' rendering fillers. The operation is one undo step.
    Q_INVOKABLE QVariantMap toggleList(int from, int to, const QString &style, bool toggle = true);
    // Quote the selected paragraphs, list items leaving their lists, or take
    // the quote off when they are all quoted already. A selection holding a
    // heading — Qt's heading tag, or text in a font size, which the dialect
    // reads as one — or reaching into a table answers nothing: the Markdown
    // route knows what a heading's size and weight become in a quote, and a
    // cell holds no quote. Returns the selection adjusted for empty lines'
    // fillers. One undo step.
    Q_INVOKABLE QVariantMap toggleQuote(int from, int to);
    // The selected paragraphs become headings of `level` (1 to 6), or plain
    // paragraphs at 0 — the Heading menu's Normal. List items leave their
    // lists and quotes their margins, as a heading line in Markdown holds
    // only its text. The text keeps its formats, its weight moved between a
    // paragraph's and a heading's (qthtml/dialect.py, HEAVY_WEIGHT). A
    // selection reaching into a table answers nothing: a cell holds no
    // heading. Returns the selection adjusted for empty lines' fillers.
    // One undo step.
    Q_INVOKABLE QVariantMap setHeading(int from, int to, int level);
    // Indent (`direction` 1) or outdent (-1) the selected paragraphs: a
    // list item moves a level, taking the style an earlier item has there
    // (with `cycleStyles`, the next marker in its family when none does),
    // and a plain paragraph gains or loses one INDENT_TEXT. One undo step;
    // false when the selection holds no paragraph to move.
    Q_INVOKABLE bool indentBlocks(int from, int to, int direction, bool cycleStyles = true);
    // A read-only projection for paragraph tools: selected list items become
    // paragraphs in a clone, while unselected list structure is retained.
    Q_INVOKABLE QString paragraphsForBlocks(int from, int to) const;
    // Backspace at the start of an item removes its marker and list indent
    // together, without deleting text or crossing a table-cell boundary.
    Q_INVOKABLE bool removeListAtStart(int position);
    // Backspace at the start of a quote line takes the quote's margins off
    // that line, which stays where it is; Qt's own Backspace would join it
    // to the line above. One undo step.
    Q_INVOKABLE bool removeQuoteAtStart(int position);
    // Enter on the empty last line of a quote: the line leaves the quote as
    // an empty paragraph, the way Enter leaves an empty list item. Lines
    // higher up are the quote's content and stay. One undo step.
    Q_INVOKABLE bool leaveEmptyQuote(int position);
    // The caret on a rule or in a code block, which it can stand on but
    // never after at the note's end: a paragraph goes in after the rule or
    // the whole code block, starting with `text` — the keystroke typed on a
    // rule — and the caret lands at its end, which this answers. -1 for
    // any other block. One undo step.
    Q_INVOKABLE int stepPastBlock(int position, const QString &text);
    // Enter on the empty last line of a code block: the line leaves the
    // block as an empty paragraph, the caret staying on it; a block's only
    // line stays and a paragraph lands after it (stepPastBlock). Answers the
    // caret, or -1 when the caret is not on such a line. One undo step.
    Q_INVOKABLE int leaveEmptyCode(int position);
    // The toolbar's horizontal rule and empty table (cpp/dialect.h), after
    // the caret's block or the whole code block it is in; a paragraph
    // follows when nothing else does. Answers the caret — on that paragraph
    // when the block ends the note, where it was otherwise — or -1 with the
    // caret in a table, where the Markdown route places it. One undo step.
    Q_INVOKABLE int insertRule(int position);
    Q_INVOKABLE int insertTable(int position);
    // The Code block tool on prose: the selected paragraphs become one code
    // block in the note's code `background` — their visible text, a line
    // per paragraph or soft line break, in the writer's code line format.
    // A selection the Markdown route has a rule for answers nothing: one
    // reaching into a code block it merges with, a list it may refuse, a
    // table or rule it refuses, an image. Returns the selection. One undo
    // step.
    Q_INVOKABLE QVariantMap makeCodeBlock(int from, int to, const QString &background);
    // The Code block tool in code: the code block holding `from` becomes
    // paragraphs, each line as the Markdown route reads it (paragraphText),
    // the selection keeping its lines. A line that route would lose answers
    // nothing. One undo step.
    Q_INVOKABLE QVariantMap unmakeCodeBlock(int from, int to);
    Q_INVOKABLE bool leaveEmptyList(int position);
    // Space typed after "1.", "1)", "a.", "A.", "-", "*" or "[]" on a
    // paragraph holding nothing else makes it a list item, Markdown's way.
    // typedListAt answers which list a Space at `position` would start —
    // `tool` (ol, ul or todo), `style` and `start`, the number typed — or
    // nothing. startTypedList types the Space, one undo step, then turns
    // the paragraph into that item, another: undo leaves the text as typed.
    // A number continues the list just above when it is that list's next
    // one and starts a list of its own otherwise. Answers the caret, in
    // front of the item's text, or -1 when the paragraph asks for no list.
    Q_INVOKABLE QVariantMap typedListAt(int position) const;
    Q_INVOKABLE int startTypedList(int position);

    explicit TextBlocks(QObject *parent = nullptr);

    int linkRevision() const { return m_linkRevision; }
    int version() const { return Version; }
    int contentRevision() const { return m_contentRevision; }
    qreal listIndent() const { return m_listIndent; }
    void setListIndent(qreal width);

    QQuickTextDocument *document() const { return m_document; }
    void setDocument(QQuickTextDocument *document);

    // The editor's tools edit in strokes — highlight inserts the restyled
    // copy and then removes the original; a block tool removes the whole
    // document and inserts the rewrite — and Qt's undo stack records every
    // stroke on its own, so ctrl+z used to surface a tool's intermediate
    // states. These brackets make the strokes one transaction: each edit
    // between them, whoever makes it (the QML insert/remove and the
    // normalize joins alike), lands in a single undo step. It is the same
    // QTextCursor edit block setImageWidth uses, document-global — but the
    // cursor that opens it is where undo puts the caret back: Qt records
    // its position with the transaction (QTextCursor::beginEditBlock). A
    // throwaway cursor stood at 0, so undoing a paste sent the caret to the
    // top of the note. `caret` is the editor's caret before the edit; a
    // position the document does not have opens nothing. Joining the
    // previous transaction records no caret: that one's stands. The depth
    // guard keeps a stray end from underflowing Qt's counter — the QML side
    // brackets in try/finally (NoteEditor.atomic), so depth here never
    // outlives a tool.
    Q_INVOKABLE void beginEditBlock(int caret);
    Q_INVOKABLE void joinPreviousEditBlock();
    Q_INVOKABLE void endEditBlock();

    // Forward Delete across a paragraph boundary is one undo transaction,
    // including the margin repairs it triggers. joinPreviousEditBlock cannot
    // attach those repairs to Qt's ungrouped, single-character deletion.
    // Delete an empty paragraph as a block, including its rendering filler.
    // Deleting only its separator would merge the next item into that filler
    // and discard its list membership. The surviving paragraph owns the
    // format: an empty heading must not enlarge the list item moved up into it.
    // Return the new caret position, or -1 when ordinary Delete should apply.
    Q_INVOKABLE int deleteParagraphBoundary(int position);

    // Every block in document order — paragraphs, list items and table
    // cells alike, the same order the document's plain text walks them.
    // `position` is the block's first character, `end` its last (the
    // block separator's place), both valid for positionToRectangle.
    // The margins and the background are what the dialect stores meaning
    // in: the 40/40 margin pair is a quote, left-only steps are indents,
    // and a block background marks a code line (qthtml/dialect.py).
    // `list` says the block is an item of a QTextList, which is how the
    // editor knows a second Enter should leave the list. `marker` is the
    // item's task-list state — 0 none, 1 an unchecked box, 2 a checked one.
    // Non-list paragraphs have no marker, even when Qt retains an old flag.
    // Qt Quick paints the marker as a raw ☐/☒ glyph hardcoded in its
    // renderer, so the editor covers it and draws its own box over the
    // glyph's cell (NoteEditor.qml, block decorations).
    Q_INVOKABLE QVariantList blocks() const;

    // Every inline image in document order: where it sits (`position` is
    // its object-replacement character, valid for positionToRectangle),
    // what it names (`source`), the size it is drawn at (`width`/`height`,
    // resolved the way Qt's own image handler does: stated dimensions win,
    // one stated dimension scales the other by the aspect, none means
    // natural size), the file's own size (`naturalWidth`/`naturalHeight`,
    // 0 while the resource has not loaded), and `ascent` — the image's
    // baseline within its line, which is where its bottom edge sits, so the
    // editor can place the resize handle on the drawn corner exactly.
    Q_INVOKABLE QVariantList images() const;

    // The corner-handle resize: the image keeps its source and alignment and
    // gets a display width; the stored height is cleared so Qt scales it by
    // the aspect, and the same rule keeps `images()` above and Qt's painter
    // agreeing. One format-only edit — its own undo step, or joined to the
    // edit before it (`join`, for the paste that fits its fresh image so one
    // Ctrl+Z takes both). False when `position` does not hold an image.
    Q_INVOKABLE bool setImageWidth(int position, qreal width, bool join = false);

    // The plain paste inside a code block: `text` replaces the selection
    // from `from` to `to` the way typing would put it there — each newline
    // starts a block in the caret's own block format, and the text takes
    // the caret's character format (QTextCursor::insertText). A pasted
    // fragment cannot do that: it brings the clipboard's formats, block
    // formats included (docs/engine-notes.md), and a code line stays code
    // only while it is all-monospace on the block background. One undo
    // step. Answers with the caret's place after the text, or -1 for a
    // range the document does not have.
    Q_INVOKABLE int insertPlainText(int from, int to, const QString &text);

    Q_INVOKABLE void normalizeLinks();

    Q_INVOKABLE void configureLinks(const QColor &colour, bool plainText,
                                   const QColor &quoteInk = QColor("#9399b2"),
                                   const QColor &highlightInk = QColor("#1e1e2e"),
                                   const QColor &highlightBackground = {},
                                   const QColor &codeBackground = {},
                                   const QColor &codeForeground = {});

    Q_INVOKABLE QString linkAt(qreal x, qreal y) const;

    // A list sits flush with the paragraphs around it, as OneNote's do: no
    // item has a vertical margin. The writer says so on every list
    // (qthtml/writer.py), but a list pasted from elsewhere brings Qt's 12px
    // above its first item and below its last, and Enter copies the split
    // item's margins, so this clears them as the items change. The repair
    // joins the triggering edit for undo and never reaches the note: the
    // reader ignores margins.
    Q_INVOKABLE void normalizeListMargins();

    // The dialect states prose line height and an image line's fixed distance
    // on every block it writes (qthtml/writer.py), but a block born outside
    // the writer — the first block of a note opened empty, or a paste from
    // another program — carries Qt's default instead, and drifts from the
    // form a re-render would give it. This restores that form, the same
    // way normalizeListMargins does: format-only, joined to the edit that
    // made the block, and never reaching the note (the reader ignores a
    // block's line height).
    Q_INVOKABLE void normalizeLineHeights();

    // Enter copies a code line's margins onto both halves. Keep the outer
    // margins on the run's first and last lines so editing cannot introduce
    // gaps inside the slab or remove its clearance from neighbouring text.
    Q_INVOKABLE void normalizeCodeMargins();

    // A block with no characters directly above a table takes no height:
    // Qt hides it — the same rule that hides the empty block Qt itself
    // puts over a document-opening table — so Enter at a list's end, or a
    // delete that bares the block, leaves the table drawn over the caret's
    // row, and no relayout brings the row back while the block stays empty
    // (measured on 6.11: markContentsDirty, a format edit and a page-size
    // round trip all left the table where it was; an empty block *below* a
    // table keeps its row). The dialect stores every deliberate blank as
    // one U+00A0 (qthtml/dialect.py), so such a block gets that filler
    // here — the form a re-render would give it. The write joins the edit
    // that bared the block, so undo stays one step, and the reader strips
    // a filler beside typed text, so it never reaches the note. Answers
    // with the filled position, for the caller to put the caret back in
    // front of the filler; -1 when every block already had its height.
    Q_INVOKABLE int fillEmptyBlocksBeforeTables();

signals:
    void contentChanged();
    void documentChanged();
    void linksChanged();
    void listIndentChanged();

private:
    // Counts a bracket in; the outermost one first notes the first
    // paragraph's character format, for endEditBlock to compare.
    void enterEditBlock(QTextDocument *doc);

    TextLinks *m_links;
    int m_linkRevision = 0;

    QQuickTextDocument *m_document = nullptr;
    QMetaObject::Connection m_contentConnection;
    int m_contentRevision = 0;
    qreal m_listIndent = 40;
    int m_editDepth = 0;
    QTextCharFormat m_firstBlockCharFormat;
};
