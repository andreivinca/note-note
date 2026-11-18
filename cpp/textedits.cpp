#include "textedits.h"

#include "dialect.h"

#include <QTextCursor>
#include <QTextList>
#include <QTextTable>

namespace {

// A selected range starting at `from` holds nothing of two blocks around a
// table. One is the block before it, when the range starts at the table's
// opening mark, which is that block's last character: Qt widens a selection
// crossing into a table to take the whole table from there. The other is
// the empty block Qt keeps after every table, outside its frame, which is
// no paragraph of the note until something is typed into it.
bool holdsNothing(const QTextBlock &block, int from)
{
    const QTextBlock next = block.next();
    const QTextTable *opening = next.isValid() ? QTextCursor(next).currentTable() : nullptr;
    if (opening && from > block.position() && from == block.position() + block.length() - 1
        && from == opening->firstPosition() - 1) {
        return true;
    }
    const QTextBlock previous = block.previous();
    const QTextTable *closing = previous.isValid() ? QTextCursor(previous).currentTable() : nullptr;
    return closing && block.text().isEmpty() && block.position() == closing->lastPosition() + 1;
}

// The paragraphs from `from` through `through` a block tool restyles: never
// a code line or a rule, nor in a `range` a block it holds nothing of.
void appendBlocks(QVector<QTextBlock> &blocks, QTextDocument *doc, int from, int through, bool range)
{
    const QTextBlock last = doc->findBlock(through);
    for (QTextBlock block = doc->findBlock(from); block.isValid(); block = block.next()) {
        const QTextBlockFormat format = block.blockFormat();
        if (!NoteNoteDialect::isCodeBlock(format)
            && !NoteNoteDialect::isRule(format)
            && !(range && holdsNothing(block, from))) {
            blocks.append(block);
        }
        if (block == last) {
            break;
        }
    }
}

// The list's items from `first` on, as a list of their own counting from
// `start`: Qt exports a paragraph between two items of one list inside it.
void moveToOwnList(QTextList *list, int first, int start)
{
    QVector<QTextBlock> following;
    for (int item = first; item < list->count(); ++item) {
        following.append(list->item(item));
    }
    if (following.isEmpty()) {
        return;
    }
    QTextListFormat format = list->format();
    format.setStart(start);
    QTextList *suffix = QTextCursor(following.first()).createList(format);
    for (const QTextBlock &item : following) {
        suffix->add(item);
    }
}

}

QVector<QTextBlock> TextEdits::selectedBlocks(QTextDocument *doc, int from, int to)
{
    QVector<QTextBlock> blocks;
    QTextCursor selection(doc);
    selection.setPosition(from);
    selection.setPosition(to, QTextCursor::KeepAnchor);
    if (!selection.hasComplexSelection()) {
        appendBlocks(blocks, doc, from, to > from ? to - 1 : to, to > from);
        return blocks;
    }
    // Qt exposes a rectangular table selection as the *starts* of its
    // first and last cells. Include the last cell and exclude cells outside
    // the rectangle, rather than interpreting those positions as text bounds.
    int firstRow, rows, firstColumn, columns;
    selection.selectedTableCells(&firstRow, &rows, &firstColumn, &columns);
    const QTextTable *table = selection.currentTable();
    for (int row = firstRow; row < firstRow + rows; ++row) {
        for (int column = firstColumn; column < firstColumn + columns; ++column) {
            const QTextTableCell cell = table->cellAt(row, column);
            appendBlocks(blocks, doc, cell.firstCursorPosition().position(), cell.lastCursorPosition().position(), true);
        }
    }
    return blocks;
}

void TextEdits::splitListAfter(const QTextBlock &item)
{
    QTextList *list = item.textList();
    const int index = list->itemNumber(item);
    moveToOwnList(list, index + 1, list->format().start() + index + 1);
}

void TextEdits::removeList(const QTextBlock &block)
{
    QTextList *list = block.textList();
    const int index = list->itemNumber(block);
    const int start = list->format().start() + index;
    list->remove(block);
    QTextBlockFormat format = block.blockFormat();
    // QTextList::remove turns the list indent into a paragraph indent and
    // leaves the item's margins. An ordinary paragraph has neither: the
    // converter states every paragraph's vertical margins as zero
    // (services/markdown/qthtml/writer.py, block_style), and a paragraph
    // that left a list must not be spaced differently until the note reloads.
    format.setIndent(0);
    format.setMarker(QTextBlockFormat::MarkerType::NoMarker);
    format.setTopMargin(0);
    format.setBottomMargin(0);
    QTextCursor(block).setBlockFormat(format);
    // Qt otherwise exports the freed paragraph inside the old list. Give
    // the following items their own list, retaining their current numbering.
    if (index > 0) {
        moveToOwnList(list, index, start);
    }
}

bool TextEdits::sameContainer(const QTextBlock &left, const QTextBlock &right)
{
    const QTextCursor a(left);
    const QTextCursor b(right);
    if (a.currentFrame() != b.currentFrame()) {
        return false;
    }
    const QTextTable *table = a.currentTable();
    return !table || table->cellAt(a) == table->cellAt(b);
}

bool TextEdits::isEmptyBlock(const QTextBlock &block)
{
    return block.text().isEmpty() || block.text() == QString(NoteNoteDialect::BLANK_PARAGRAPH);
}
