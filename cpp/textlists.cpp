#include "textblocks.h"

#include <QTextList>
#include <QTextTable>

namespace {

void appendBlocks(QVector<QTextBlock> &blocks, QTextDocument *doc, int from, int through)
{
    const QTextBlock last = doc->findBlock(through);
    for (QTextBlock block = doc->findBlock(from); block.isValid(); block = block.next()) {
        const QTextBlockFormat format = block.blockFormat();
        if (!NoteNoteDialect::isCodeBlock(format)
            && !format.hasProperty(QTextFormat::BlockTrailingHorizontalRulerWidth)) {
            blocks.append(block);
        }
        if (block == last) {
            break;
        }
    }
}

QVector<QTextBlock> selectedBlocks(QTextDocument *doc, int from, int to)
{
    QVector<QTextBlock> blocks;
    QTextCursor selection(doc);
    selection.setPosition(from);
    selection.setPosition(to, QTextCursor::KeepAnchor);
    if (!selection.hasComplexSelection()) {
        appendBlocks(blocks, doc, from, to > from ? to - 1 : to);
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
            appendBlocks(blocks, doc, cell.firstCursorPosition().position(), cell.lastCursorPosition().position());
        }
    }
    return blocks;
}

bool matchesStyle(const QTextBlock &block, const QString &style)
{
    const QTextList *list = block.textList();
    if (!list) {
        return false;
    }
    const bool checkbox = block.blockFormat().marker() != QTextBlockFormat::MarkerType::NoMarker;
    if (style == "todo") {
        return checkbox;
    }
    const bool ordered = list->format().style() <= QTextListFormat::ListDecimal;
    return !checkbox && (style == "ol" ? ordered : !ordered);
}

bool sameContainer(const QTextBlock &left, const QTextBlock &right)
{
    const QTextCursor a(left);
    const QTextCursor b(right);
    if (a.currentFrame() != b.currentFrame()) {
        return false;
    }
    const QTextTable *table = a.currentTable();
    return !table || table->cellAt(a) == table->cellAt(b);
}

QTextList *adjacentList(const QTextBlock &block, const QTextBlock &neighbour,
                       const QTextListFormat &format, const QString &style)
{
    if (!neighbour.isValid() || !sameContainer(block, neighbour) || !matchesStyle(neighbour, style)) {
        return nullptr;
    }
    QTextList *list = neighbour.textList();
    if (list->format().style() != format.style() || list->format().indent() != format.indent()) {
        return nullptr;
    }
    return list;
}

void removeList(const QTextBlock &block)
{
    block.textList()->remove(block);
    QTextBlockFormat format = block.blockFormat();
    // QTextList::remove turns the list indent into a paragraph indent.
    // Leaving the list restores an ordinary paragraph at the same position.
    format.setIndent(0);
    format.setMarker(QTextBlockFormat::MarkerType::NoMarker);
    format.setTopMargin(12);
    format.setBottomMargin(12);
    QTextCursor(block).setBlockFormat(format);
}

}

QVariantMap TextBlocks::toggleList(int from, int to, const QString &style)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || from < 0 || from > to || to >= doc->characterCount()
        || (style != "todo" && style != "ul" && style != "ol")) {
        return {};
    }
    const QVector<QTextBlock> blocks = selectedBlocks(doc, from, to);
    bool remove = true;
    for (const QTextBlock &block : blocks) {
        remove = remove && matchesStyle(block, style);
    }
    if (blocks.isEmpty()) {
        return {};
    }
    QTextCursor start(doc);
    start.setPosition(from);
    start.setKeepPositionOnInsert(true);
    QTextCursor end(doc);
    end.setPosition(to);
    end.setKeepPositionOnInsert(true);
    QTextCursor transaction(doc);
    transaction.beginEditBlock();
    for (const QTextBlock &block : blocks) {
        if (remove) {
            removeList(block);
            continue;
        }
        QTextListFormat format;
        format.setStyle(style == "ol" ? QTextListFormat::ListDecimal : QTextListFormat::ListDisc);
        format.setIndent(block.textList() ? block.textList()->format().indent() : 1);
        QTextBlockFormat paragraph = block.blockFormat();
        const bool checked = paragraph.marker() == QTextBlockFormat::MarkerType::Checked;
        paragraph.setIndent(0);
        paragraph.setMarker(style == "todo"
            ? (checked ? QTextBlockFormat::MarkerType::Checked : QTextBlockFormat::MarkerType::Unchecked)
            : QTextBlockFormat::MarkerType::NoMarker);
        QTextCursor cursor(block);
        cursor.setBlockFormat(paragraph);

        QTextList *list = adjacentList(block, block.previous(), format, style);
        if (!list) {
            list = adjacentList(block, block, format, style);
        }
        if (list) {
            list->add(block);
        } else {
            list = cursor.createList(format);
        }
        // Qt omits an empty cell's list when exporting HTML. Keep the same
        // invisible item content that the Markdown writer uses on import.
        if (block.text().isEmpty()) {
            cursor.insertText(QString(NoteNoteDialect::BLANK_PARAGRAPH));
        }
        // Bridge a paragraph inserted between compatible lists. Moving blocks
        // individually keeps a list in another cell or at another depth intact.
        for (QTextBlock next = block.next(); next.isValid(); next = next.next()) {
            QTextList *following = adjacentList(block, next, format, style);
            if (!following || following == list) {
                break;
            }
            list->add(next);
        }
    }
    transaction.endEditBlock();
    return {{"from", start.position()}, {"to", end.position()}};
}

bool TextBlocks::removeListAtStart(int position)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || position < 0 || position >= doc->characterCount()) {
        return false;
    }
    const QTextBlock block = doc->findBlock(position);
    if (!block.textList() || position != block.position()) {
        return false;
    }
    QTextCursor cursor(block);
    cursor.beginEditBlock();
    removeList(block);
    cursor.endEditBlock();
    return true;
}

bool TextBlocks::leaveEmptyList(int position)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || position < 0 || position >= doc->characterCount()) {
        return false;
    }
    const QTextBlock block = doc->findBlock(position);
    if (!block.textList() || (!block.text().isEmpty()
        && block.text() != QString(NoteNoteDialect::BLANK_PARAGRAPH))) {
        return false;
    }
    QTextCursor cursor(block);
    cursor.beginEditBlock();
    removeList(block);
    if (!block.text().isEmpty()) {
        cursor.setPosition(block.position() + block.length() - 1, QTextCursor::KeepAnchor);
        cursor.removeSelectedText();
    }
    cursor.endEditBlock();
    return true;
}
