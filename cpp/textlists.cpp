#include "textblocks.h"

#include <QTextDocumentFragment>
#include <QTextList>
#include <QTextTable>

#include <memory>
#include <optional>

namespace {

struct ListStyle {
    QTextListFormat::Style marker;
    bool checkbox = false;
};

// The names the editing tools know the styles by (ui/tools).
std::optional<ListStyle> styleNamed(const QString &name)
{
    if (name == QLatin1String("todo")) {
        return ListStyle{QTextListFormat::ListDisc, true};
    }
    if (name == QLatin1String("ul") || name == QLatin1String("disc")) {
        return ListStyle{QTextListFormat::ListDisc};
    }
    if (name == QLatin1String("circle")) {
        return ListStyle{QTextListFormat::ListCircle};
    }
    if (name == QLatin1String("square")) {
        return ListStyle{QTextListFormat::ListSquare};
    }
    if (name == QLatin1String("ol") || name == QLatin1String("decimal")) {
        return ListStyle{QTextListFormat::ListDecimal};
    }
    if (name == QLatin1String("lower-alpha")) {
        return ListStyle{QTextListFormat::ListLowerAlpha};
    }
    if (name == QLatin1String("upper-alpha")) {
        return ListStyle{QTextListFormat::ListUpperAlpha};
    }
    if (name == QLatin1String("upper-roman")) {
        return ListStyle{QTextListFormat::ListUpperRoman};
    }
    if (name == QLatin1String("lower-roman")) {
        return ListStyle{QTextListFormat::ListLowerRoman};
    }
    return std::nullopt;
}

bool isNumbered(QTextListFormat::Style style)
{
    switch (style) {
    case QTextListFormat::ListDecimal:
    case QTextListFormat::ListLowerAlpha:
    case QTextListFormat::ListUpperAlpha:
    case QTextListFormat::ListLowerRoman:
    case QTextListFormat::ListUpperRoman:
        return true;
    default:
        return false;
    }
}

QTextListFormat::Style styleAtDepth(QTextListFormat::Style style, int depth)
{
    const QVector<QTextListFormat::Style> bullets = {
        QTextListFormat::ListDisc, QTextListFormat::ListCircle, QTextListFormat::ListSquare
    };
    const QVector<QTextListFormat::Style> numbers = {
        QTextListFormat::ListDecimal, QTextListFormat::ListLowerAlpha,
        QTextListFormat::ListLowerRoman
    };
    const auto &cycle = isNumbered(style) ? numbers : bullets;
    return cycle[(depth - 1) % cycle.size()];
}

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

bool hasStyle(const QTextBlock &block, ListStyle style)
{
    const QTextList *list = block.textList();
    if (!list) {
        return false;
    }
    const bool checkbox = block.blockFormat().marker() != QTextBlockFormat::MarkerType::NoMarker;
    if (style.checkbox) {
        return checkbox;
    }
    return !checkbox && list->format().style() == style.marker;
}

bool allHaveStyle(const QVector<QTextBlock> &blocks, ListStyle style)
{
    for (const QTextBlock &block : blocks) {
        if (!hasStyle(block, style)) {
            return false;
        }
    }
    return true;
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

// The list a block is an item of, when it is one of the style and depth asked for.
QTextList *listOf(const QTextBlock &block, const QTextListFormat &format, ListStyle style)
{
    if (!block.isValid() || !hasStyle(block, style)) {
        return nullptr;
    }
    QTextList *list = block.textList();
    if (list->format().style() != format.style() || list->format().indent() != format.indent()) {
        return nullptr;
    }
    return list;
}

// A neighbour's list the block can join: list membership never crosses a
// table cell.
QTextList *neighbouringList(const QTextBlock &block, const QTextBlock &neighbour,
                            const QTextListFormat &format, ListStyle style)
{
    const bool forward = neighbour.position() > block.position();
    for (QTextBlock next = neighbour; next.isValid() && sameContainer(block, next);
         next = forward ? next.next() : next.previous()) {
        const QTextList *list = next.textList();
        if (!list || list->format().indent() <= format.indent()) {
            return listOf(next, format, style);
        }
    }
    return nullptr;
}

void removeList(const QTextBlock &block)
{
    QTextList *list = block.textList();
    const int index = list->itemNumber(block);
    QVector<QTextBlock> following;
    if (index > 0) {
        for (int item = index + 1; item < list->count(); ++item) {
            following.append(list->item(item));
        }
    }
    QTextListFormat suffixFormat = list->format();
    suffixFormat.setStart(suffixFormat.start() + index);
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
    if (!following.isEmpty()) {
        QTextList *suffix = QTextCursor(following.first()).createList(suffixFormat);
        for (const QTextBlock &item : following) {
            suffix->add(item);
        }
    }
}

QTextListFormat listFormat(const QTextBlock &block, ListStyle style)
{
    QTextListFormat format;
    format.setStyle(style.marker);
    format.setIndent(block.textList() ? block.textList()->format().indent() : 1);
    return format;
}

// A checkbox keeps the state it has; any other style has no marker.
QTextBlockFormat::MarkerType markerFor(const QTextBlock &block, ListStyle style)
{
    if (!style.checkbox) {
        return QTextBlockFormat::MarkerType::NoMarker;
    }
    const bool checked = block.blockFormat().marker() == QTextBlockFormat::MarkerType::Checked;
    return checked ? QTextBlockFormat::MarkerType::Checked : QTextBlockFormat::MarkerType::Unchecked;
}

// Bridge a paragraph inserted between compatible lists. Moving blocks
// individually keeps a list in another cell or at another depth intact.
void joinFollowing(QTextList *list, const QTextBlock &block, const QTextListFormat &format, ListStyle style)
{
    for (QTextBlock next = block.next(); next.isValid(); next = next.next()) {
        if (!sameContainer(block, next) || !next.textList()) {
            return;
        }
        if (next.textList()->format().indent() > format.indent()) {
            continue;
        }
        QTextList *following = listOf(next, format, style);
        if (!following || following == list) {
            return;
        }
        list->add(next);
    }
}

void applyList(const QTextBlock &block, ListStyle style, const QTextListFormat &format)
{
    const auto marker = markerFor(block, style);
    const QTextList *previous = block.textList();
    if (previous && (format.indent() < previous->format().indent()
        || (format.indent() == previous->format().indent() && format.style() != previous->format().style()))) {
        removeList(block);
    }
    QTextBlockFormat paragraph = block.blockFormat();
    paragraph.setIndent(0);
    paragraph.setMarker(marker);
    QTextCursor cursor(block);
    cursor.setBlockFormat(paragraph);

    QTextList *list = neighbouringList(block, block.previous(), format, style);
    if (!list) {
        list = listOf(block, format, style);
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
    joinFollowing(list, block, format, style);
}

bool isEmptyItem(const QTextBlock &block)
{
    return block.text().isEmpty() || block.text() == QString(NoteNoteDialect::BLANK_PARAGRAPH);
}

}

QVariantMap TextBlocks::toggleList(int from, int to, const QString &styleName, bool toggle)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    const std::optional<ListStyle> style = styleNamed(styleName);
    if (!doc || !style || from < 0 || from > to || to >= doc->characterCount()) {
        return {};
    }
    const QVector<QTextBlock> blocks = selectedBlocks(doc, from, to);
    if (blocks.isEmpty()) {
        return {};
    }
    // A selection that is the style already loses it; a mixed one adopts it.
    const bool remove = toggle && allHaveStyle(blocks, *style);
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
        } else {
            applyList(block, *style, listFormat(block, *style));
        }
    }
    transaction.endEditBlock();
    return {{"from", start.position()}, {"to", end.position()}};
}

bool TextBlocks::indentBlocks(int from, int to, int direction, bool cycleStyles)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || from < 0 || from > to || to >= doc->characterCount()
        || (direction != 1 && direction != -1)) {
        return false;
    }
    const QVector<QTextBlock> blocks = selectedBlocks(doc, from, to);
    bool hasList = false;
    for (const QTextBlock &block : blocks) {
        if (block.textList()) {
            hasList = true;
            break;
        }
    }
    if (!hasList) {
        return false;
    }
    QTextCursor transaction(doc);
    transaction.beginEditBlock();
    for (const QTextBlock &block : blocks) {
        QTextList *list = block.textList();
        if (!list) {
            QTextBlockFormat format = block.blockFormat();
            if (!NoteNoteDialect::isQuote(format)) {
                format.setLeftMargin(qMax(0.0, format.leftMargin() + direction * NoteNoteDialect::INDENT_PX));
                QTextCursor(block).setBlockFormat(format);
            }
            continue;
        }
        const int indent = list->format().indent() + direction;
        if (indent < 1) {
            removeList(block);
            continue;
        }
        const bool checkbox = block.blockFormat().marker() != QTextBlockFormat::MarkerType::NoMarker;
        ListStyle style{list->format().style(), checkbox};
        if (cycleStyles && !checkbox) {
            style.marker = styleAtDepth(style.marker, indent);
        }
        QTextListFormat format;
        format.setStyle(style.marker);
        format.setIndent(indent);
        // Returning to a parent's level returns to its chosen marker, even
        // when that level began with a style selected from the dropdown.
        if (direction < 0) {
            for (QTextBlock previous = block.previous(); previous.isValid() && sameContainer(block, previous);
                 previous = previous.previous()) {
                const QTextList *parent = previous.textList();
                if (!parent || parent->format().indent() < indent) {
                    break;
                }
                if (parent->format().indent() == indent) {
                    const bool parentCheckbox = previous.blockFormat().marker() != QTextBlockFormat::MarkerType::NoMarker;
                    if (parentCheckbox == checkbox && (checkbox || isNumbered(parent->format().style()) == isNumbered(style.marker))) {
                        style.marker = parent->format().style();
                        format.setStyle(style.marker);
                    }
                    break;
                }
            }
        }
        applyList(block, style, format);
    }
    transaction.endEditBlock();
    return true;
}

QString TextBlocks::paragraphsForBlocks(int from, int to) const
{
    const QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || from < 0 || from > to || to >= doc->characterCount()) {
        return {};
    }
    const std::unique_ptr<QTextDocument> projected(doc->clone());
    for (const QTextBlock &block : selectedBlocks(projected.get(), from, to)) {
        if (block.textList()) {
            removeList(block);
        }
    }
    QTextCursor selection(projected.get());
    selection.select(QTextCursor::Document);
    return QTextDocumentFragment(selection).toHtml();
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
    if (!block.textList() || !isEmptyItem(block)) {
        return false;
    }
    QTextCursor cursor(block);
    cursor.beginEditBlock();
    removeList(block);
    if (!block.text().isEmpty()) {
        // The filler that kept the empty item alive goes with the list.
        cursor.setPosition(block.position() + block.length() - 1, QTextCursor::KeepAnchor);
        cursor.removeSelectedText();
    }
    cursor.endEditBlock();
    return true;
}
