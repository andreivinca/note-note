// What the native block edits share, inside the module: textlists.cpp
// (list membership) and textparagraphs.cpp (quotes, headings, code, rules
// and tables) both act on the paragraphs a selection covers, and a
// paragraph style takes an item out of its list first. Not a QML type.
#pragma once

#include <QTextBlock>
#include <QTextDocument>
#include <QVector>

namespace TextEdits {

// The paragraphs a selection covers, with an exclusive selection end: a
// rectangular table selection is the cells inside the rectangle. Code
// lines and rules are never among them — no block tool restyles those.
QVector<QTextBlock> selectedBlocks(QTextDocument *doc, int from, int to);

// The block leaves its list as a plain paragraph, its text and table cell
// kept; the items after it keep their numbering in a list of their own.
void removeList(const QTextBlock &block);

// The items after `item` in its list become a list of their own, keeping
// their numbers: what is put between them then stands between two lists.
void splitListAfter(const QTextBlock &item);

// The two blocks are in one frame and, in a table, one cell: list
// membership and a code block's run of lines never cross that boundary.
bool sameContainer(const QTextBlock &left, const QTextBlock &right);

// Nothing in it, or only the filler that keeps an empty block alive in Qt's
// HTML (NoteNoteDialect::BLANK_PARAGRAPH).
bool isEmptyBlock(const QTextBlock &block);

}
