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
// TextLinks colours and locates URLs without changing the document, and
// clears inherited anchors from empty paragraphs.
// The edit-block brackets (beginEditBlock/
// endEditBlock) write nothing at all: they fence the editor's own strokes
// into one undo step.
//
// The module is OPTIONAL. It is built locally (`sh cpp/build.sh`) against
// the system Qt and loaded by a directory import (ui/NativeBlocks.qml);
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
    static constexpr int Version = 1;

public:
    Q_INVOKABLE int insertFormattedText(int from, int to, const QString &text, const QVariantMap &styles);
    Q_INVOKABLE bool setTextColor(int from, int to, const QString &color);
    Q_INVOKABLE QVariantMap tableInfo(int position) const;
    Q_INVOKABLE int editTable(int position, const QString &operation, int index, int count);
    Q_INVOKABLE int appendTableRow(int position);
    Q_INVOKABLE int deletePreviousTable(int position);

    explicit TextBlocks(QObject *parent = nullptr);

    int linkRevision() const { return m_linkRevision; }
    int version() const { return Version; }

    QQuickTextDocument *document() const { return m_document; }
    void setDocument(QQuickTextDocument *document);

    // The editor's tools edit in strokes — highlight inserts the restyled
    // copy and then removes the original; a block tool removes the whole
    // document and inserts the rewrite — and Qt's undo stack records every
    // stroke on its own, so ctrl+z used to surface a tool's intermediate
    // states. These brackets make the strokes one transaction: each edit
    // between them, whoever makes it (the QML insert/remove and the
    // normalize joins alike), lands in a single undo step. It is the same
    // QTextCursor edit block setImageWidth uses, document-global, so a
    // throwaway cursor is enough. The depth guard keeps a stray end from
    // underflowing Qt's counter — the QML side brackets in try/finally
    // (NoteEditor.atomic), so depth here never outlives a tool.
    Q_INVOKABLE void beginEditBlock(bool joinPrevious = false);
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
    // item's task-list state — 0 none, 1 an unchecked box, 2 a checked one;
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
                                   const QColor &highlightInk = QColor("#1e1e2e"));

    Q_INVOKABLE QString linkAt(qreal x, qreal y) const;

    // Qt gives an outer list 12px above its first item and below its last,
    // with zero between items. Nested lists (indent > 1) have zero margins
    // throughout. Enter copies the split item's margins, so restore this
    // imported form as the items change. The repair joins the triggering
    // edit for undo and never reaches the note: the reader ignores margins.
    Q_INVOKABLE void normalizeListMargins();

    // The dialect states its line height on every block it writes
    // (qthtml/writer.py), but a block born outside the writer — the first
    // block of a note opened empty, or blocks a paste brings in from
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
    void documentChanged();
    void linksChanged();

private:
    TextLinks *m_links;
    int m_linkRevision = 0;

    QQuickTextDocument *m_document = nullptr;
    int m_editDepth = 0;
};
