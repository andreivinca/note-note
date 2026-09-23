#include "textblocks.h"

#include <QImage>
#include <QPixmap>
#include <QTextLayout>
#include <QTextList>
#include <QTextTable>
#include <QUrl>

namespace {

void copyCellPadding(QTextTableCell cell, const QTextTableCellFormat &source)
{
    QTextTableCellFormat format = cell.format().toTableCellFormat();
    for (int property : {QTextFormat::TableCellTopPadding, QTextFormat::TableCellBottomPadding,
                         QTextFormat::TableCellLeftPadding, QTextFormat::TableCellRightPadding}) {
        if (source.hasProperty(property)) {
            format.setProperty(property, source.property(property));
        }
    }
    cell.setFormat(format);
}

// A neighbour past the document's ends is no block at all.
bool neighbourIsCode(const QTextBlock &block)
{
    return block.isValid() && NoteNoteDialect::isCodeBlock(block.blockFormat());
}

// The image file's own size, from the resource the document already
// loaded to paint it (the document caches these, so this is a lookup,
// not a read). Empty while a resource has not loaded — `images()` then
// reports natural 0 and the next pass sees it.
QSizeF naturalSize(QTextDocument *doc, const QTextImageFormat &format)
{
    const QVariant resource =
            doc->resource(QTextDocument::ImageResource, QUrl(format.name()));
    if (resource.canConvert<QImage>()) {
        return resource.value<QImage>().size();
    }
    if (resource.canConvert<QPixmap>()) {
        return resource.value<QPixmap>().size();
    }
    return QSizeF();
}

}

int TextBlocks::deletePreviousTable(int position)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || position <= 0 || position >= doc->characterCount()) {
        return -1;
    }
    QTextCursor cursor(doc);
    cursor.setPosition(position - 1);
    QTextTable *table = cursor.currentTable();
    if (!table || table->lastPosition() != position - 1) {
        return -1;
    }
    // Include both frame boundaries so Qt removes the table itself, not
    // just its cell contents. The exact end check keeps parent tables safe.
    cursor.beginEditBlock();
    cursor.setPosition(table->firstPosition() - 1);
    cursor.setPosition(position, QTextCursor::KeepAnchor);
    cursor.removeSelectedText();
    cursor.endEditBlock();
    return cursor.position();
}

QVariantMap TextBlocks::tableInfo(int position) const
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || position < 0 || position >= doc->characterCount()) {
        return {};
    }
    QTextCursor cursor(doc);
    cursor.setPosition(position);
    QTextTable *table = cursor.currentTable();
    if (!table) {
        return {};
    }
    const QTextTableCell cell = table->cellAt(cursor);
    return {{"row", cell.row()}, {"column", cell.column()},
            {"rows", table->rows()}, {"columns", table->columns()},
            {"cellStart", cell.firstCursorPosition().position()},
            {"cellEnd", cell.lastCursorPosition().position()}};
}

int TextBlocks::editTable(int position, const QString &operation, int index, int count)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || position < 0 || position >= doc->characterCount() || count < 1 || index < 0) {
        return -1;
    }
    QTextCursor cursor(doc);
    cursor.setPosition(position);
    QTextTable *table = cursor.currentTable();
    if (!table) {
        return -1;
    }
    const bool rows = operation == "insertRows" || operation == "removeRows";
    const bool columns = operation == "insertColumns" || operation == "removeColumns";
    const bool insert = operation == "insertRows" || operation == "insertColumns";
    const int size = rows ? table->rows() : table->columns();
    if ((!rows && !columns) || index > size || (!insert && (index + count > size || count >= size))) {
        return -1;
    }
    const QTextTableCell original = table->cellAt(cursor);
    const int originalRow = original.row();
    const int originalColumn = original.column();
    const QTextTableCellFormat padding = original.format().toTableCellFormat();
    cursor.beginEditBlock();
    if (operation == "insertRows") {
        table->insertRows(index, count);
    } else if (operation == "removeRows") {
        table->removeRows(index, count);
    } else if (operation == "insertColumns") {
        table->insertColumns(index, count);
    } else {
        table->removeColumns(index, count);
    }
    // Qt creates cells with only the table's uniform padding. Carry the
    // surrounding cell's per-side padding into the inserted rows/columns.
    if (insert) {
        const int firstRow = rows ? index : 0;
        const int lastRow = rows ? index + count : table->rows();
        const int firstColumn = columns ? index : 0;
        const int lastColumn = columns ? index + count : table->columns();
        for (int row = firstRow; row < lastRow; ++row) {
            for (int column = firstColumn; column < lastColumn; ++column) {
                copyCellPadding(table->cellAt(row, column), padding);
            }
        }
    }
    cursor.endEditBlock();
    // Deleting the first cell can leave Qt's cursor just before the table,
    // which belongs to the parent cell in a nested table. Keep editing this
    // table by landing in the nearest surviving cell instead.
    if (cursor.currentTable() != table) {
        cursor = table->cellAt(qMin(originalRow, table->rows() - 1),
                               qMin(originalColumn, table->columns() - 1)).firstCursorPosition();
    }
    return cursor.position();
}

int TextBlocks::appendTableRow(int position)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || position < 0 || position >= doc->characterCount()) {
        return -1;
    }
    QTextCursor cursor(doc);
    cursor.setPosition(position);
    QTextTable *table = cursor.currentTable();
    if (!table) {
        return -1;
    }
    const QTextTableCell cell = table->cellAt(cursor);
    const QTextBlock block = cursor.block();
    // A second Enter in the final cell's empty continuation adds a row to
    // this table, regardless of how many enclosing or preceding tables exist.
    if (cell.row() != table->rows() - 1 || cell.column() != table->columns() - 1
        || block.position() <= cell.firstCursorPosition().position()
        || block.position() + block.length() - 1 != cell.lastCursorPosition().position()
        || !block.text().trimmed().isEmpty()) {
        return -1;
    }
    cursor.beginEditBlock();
    cursor.setPosition(block.position() - 1);
    cursor.setPosition(block.position() + block.length() - 1, QTextCursor::KeepAnchor);
    cursor.removeSelectedText();
    const int row = table->rows();
    const QTextTableCellFormat padding = cell.format().toTableCellFormat();
    table->insertRows(row, 1);
    for (int column = 0; column < table->columns(); ++column) {
        copyCellPadding(table->cellAt(row, column), padding);
    }
    const int target = table->cellAt(row, 0).firstCursorPosition().position();
    cursor.endEditBlock();
    return target;
}


bool TextBlocks::setTextColor(int from, int to, const QString &color)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    const QColor ink(color);
    if (!doc || from < 0 || from >= to || to >= doc->characterCount() || (!color.isEmpty() && !ink.isValid())) {
        return false;
    }
    struct Run {
        int from;
        int to;
        QTextCharFormat format;
    };
    QVector<Run> runs;
    for (QTextBlock block = doc->findBlock(from); block.isValid() && block.position() < to; block = block.next()) {
        for (auto it = block.begin(); !it.atEnd(); ++it) {
            const QTextFragment fragment = it.fragment();
            const int start = qMax(from, fragment.position());
            const int end = qMin(to, fragment.position() + fragment.length());
            if (start >= end || fragment.charFormat().isImageFormat()) {
                continue;
            }
            QTextCharFormat format = fragment.charFormat();
            if (color.isEmpty()) {
                format.clearForeground();
            } else {
                format.setForeground(ink);
            }
            runs.append({start, end, format});
        }
    }
    QTextCursor cursor(doc);
    cursor.beginEditBlock();
    for (const Run &run : runs) {
        cursor.setPosition(run.from);
        cursor.setPosition(run.to, QTextCursor::KeepAnchor);
        cursor.setCharFormat(run.format);
    }
    cursor.endEditBlock();
    return !runs.isEmpty();
}


int TextBlocks::insertFormattedText(int from, int to, const QString &text, const QVariantMap &styles)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || from < 0 || from > to || to >= doc->characterCount()) {
        return -1;
    }
    QTextCursor cursor(doc);
    cursor.setPosition(from);
    cursor.setPosition(to, QTextCursor::KeepAnchor);
    QTextCharFormat format = cursor.charFormat();
    if (styles.contains("bold")) {
        format.setFontWeight(styles.value("bold").toBool() ? QFont::Bold : QFont::Normal);
    }
    if (styles.contains("italic")) {
        format.setFontItalic(styles.value("italic").toBool());
    }
    if (styles.contains("underline")) {
        format.setFontUnderline(styles.value("underline").toBool());
    }
    if (styles.contains("strikeout")) {
        format.setFontStrikeOut(styles.value("strikeout").toBool());
    }
    if (styles.contains("color")) {
        const QString color = styles.value("color").toString();
        if (color.isEmpty()) {
            format.clearForeground();
        } else {
            const QColor ink(color);
            if (!ink.isValid()) {
                return -1;
            }
            format.setForeground(ink);
        }
    }
    cursor.beginEditBlock();
    cursor.insertText(text, format);
    cursor.endEditBlock();
    return cursor.position();
}

TextBlocks::TextBlocks(QObject *parent) : QObject(parent), m_links(new TextLinks(this))
{
    connect(m_links, &TextLinks::linksChanged, this, [this]() {
        ++m_linkRevision;
        emit linksChanged();
    });
}

void TextBlocks::setDocument(QQuickTextDocument *document)
{
    if (document == m_document) {
        return;
    }
    m_document = document;
    m_links->setDocument(document ? document->textDocument() : nullptr);
    // A depth carried across documents would end blocks the new
    // document never began.
    m_editDepth = 0;
    emit documentChanged();
}

void TextBlocks::beginEditBlock(bool joinPrevious)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc) {
        return;
    }
    if (joinPrevious) {
        QTextCursor(doc).joinPreviousEditBlock();
    } else {
        QTextCursor(doc).beginEditBlock();
    }
    ++m_editDepth;
}

void TextBlocks::endEditBlock()
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || m_editDepth <= 0) {
        return;
    }
    QTextCursor(doc).endEditBlock();
    --m_editDepth;
}

int TextBlocks::deleteParagraphBoundary(int position)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || position < 0 || position >= doc->characterCount() - 1) {
        return -1;
    }
    const QTextBlock block = doc->findBlock(position);
    const QTextBlock next = block.next();
    if (!next.isValid()) {
        return -1;
    }
    const bool emptyParagraph = (block.text().isEmpty() || block.text() == QString(NoteNoteDialect::BLANK_PARAGRAPH))
            && !block.textList() && !NoteNoteDialect::isCodeBlock(block.blockFormat())
            && !block.blockFormat().hasProperty(QTextFormat::BlockTrailingHorizontalRulerWidth);
    QTextCursor cursor(doc);
    cursor.setPosition(position);
    if (!emptyParagraph && !cursor.atBlockEnd()) {
        return -1;
    }
    const QTextCursor following(next);
    // Paragraph deletion must not merge table cells or remove a frame's
    // required anchor paragraph. Qt handles those structural boundaries.
    if (cursor.currentTable() || cursor.currentFrame() != following.currentFrame()) {
        return -1;
    }
    cursor.beginEditBlock();
    if (emptyParagraph) {
        const QTextBlockFormat format = next.blockFormat();
        const QTextCharFormat characters = following.blockCharFormat();
        cursor.setPosition(block.position());
        cursor.setBlockFormat(format);
        cursor.setBlockCharFormat(characters);
        cursor.setPosition(next.position(), QTextCursor::KeepAnchor);
        cursor.removeSelectedText();
    } else {
        cursor.deleteChar();
    }
    cursor.endEditBlock();
    return cursor.position();
}

QVariantList TextBlocks::blocks() const
{
    QVariantList out;
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc) {
        return out;
    }
    for (QTextBlock block = doc->begin(); block.isValid(); block = block.next()) {
        const QTextBlockFormat format = block.blockFormat();
        QVariantMap entry;
        entry.insert(QStringLiteral("position"), block.position());
        entry.insert(QStringLiteral("end"), block.position() + qMax(0, block.length() - 1));
        entry.insert(QStringLiteral("marginLeft"), format.leftMargin());
        entry.insert(QStringLiteral("marginRight"), format.rightMargin());
        entry.insert(QStringLiteral("background"), format.background().style() != Qt::NoBrush);
        entry.insert(QStringLiteral("list"), block.textList() != nullptr);
        // A horizontal rule: Qt keeps it as an empty block wearing this
        // property, and the editor needs to know — a rule that ends the
        // note leaves the caret no position after it (escapeForward).
        entry.insert(QStringLiteral("rule"),
                     format.hasProperty(QTextFormat::BlockTrailingHorizontalRulerWidth));
        const QTextBlockFormat::MarkerType marker = format.marker();
        entry.insert(QStringLiteral("marker"),
                     marker == QTextBlockFormat::MarkerType::Checked         ? 2
                             : marker == QTextBlockFormat::MarkerType::Unchecked ? 1
                                                                                 : 0);
        out.append(entry);
    }
    return out;
}

QVariantList TextBlocks::images() const
{
    QVariantList out;
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc) {
        return out;
    }
    for (QTextBlock block = doc->begin(); block.isValid(); block = block.next()) {
        for (QTextBlock::iterator it = block.begin(); !it.atEnd(); ++it) {
            const QTextFragment fragment = it.fragment();
            if (!fragment.isValid() || !fragment.charFormat().isImageFormat()) {
                continue;
            }
            const QTextImageFormat format = fragment.charFormat().toImageFormat();
            const QSizeF natural = naturalSize(doc, format);
            qreal width = format.hasProperty(QTextFormat::ImageWidth) ? format.width() : 0;
            qreal height = format.hasProperty(QTextFormat::ImageHeight) ? format.height() : 0;
            if (width > 0 && height <= 0 && natural.width() > 0) {
                height = natural.height() * width / natural.width();
            } else if (height > 0 && width <= 0 && natural.height() > 0) {
                width = natural.width() * height / natural.height();
            }
            if (width <= 0 && height <= 0) {
                width = natural.width();
                height = natural.height();
            }
            const QTextLine line =
                    block.layout()->lineForTextPosition(fragment.position() - block.position());
            // A fragment can hold several adjacent copies of one image.
            for (int i = 0; i < fragment.length(); ++i) {
                QVariantMap entry;
                entry.insert(QStringLiteral("position"), fragment.position() + i);
                entry.insert(QStringLiteral("source"), format.name());
                entry.insert(QStringLiteral("width"), width);
                entry.insert(QStringLiteral("height"), height);
                entry.insert(QStringLiteral("naturalWidth"), natural.width());
                entry.insert(QStringLiteral("naturalHeight"), natural.height());
                entry.insert(QStringLiteral("ascent"), line.isValid() ? line.ascent() : height);
                out.append(entry);
            }
        }
    }
    return out;
}

bool TextBlocks::setImageWidth(int position, qreal width, bool join)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || width <= 0 || position < 0 || position >= doc->characterCount()) {
        return false;
    }
    QTextCursor cursor(doc);
    cursor.setPosition(position);
    cursor.setPosition(position + 1, QTextCursor::KeepAnchor);
    // charFormat() answers for the character before position(), which
    // with this selection is the image character itself.
    const QTextCharFormat current = cursor.charFormat();
    if (!current.isImageFormat()) {
        return false;
    }
    QTextImageFormat format = current.toImageFormat();
    format.setWidth(width);
    format.clearProperty(QTextFormat::ImageHeight);
    if (join) {
        cursor.joinPreviousEditBlock();
    } else {
        cursor.beginEditBlock();
    }
    cursor.setCharFormat(format);
    cursor.endEditBlock();
    return true;
}

int TextBlocks::insertPlainText(int from, int to, const QString &text)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || from < 0 || from > to || to >= doc->characterCount()) {
        return -1;
    }
    QTextCursor cursor(doc);
    cursor.setPosition(from);
    cursor.setPosition(to, QTextCursor::KeepAnchor);
    cursor.insertText(text);
    return cursor.position();
}

void TextBlocks::normalizeLinks()
{
    TextLinks::normalizeAnchors(m_document ? m_document->textDocument() : nullptr);
}

void TextBlocks::configureLinks(const QColor &colour, bool plainText, const QColor &quoteInk, const QColor &highlightInk)
{
    m_links->configure(colour, plainText, quoteInk, highlightInk);
}

QString TextBlocks::linkAt(qreal x, qreal y) const
{
    return m_links->linkAt(QPointF(x, y));
}

void TextBlocks::normalizeListMargins()
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc) {
        return;
    }
    for (QTextBlock block = doc->begin(); block.isValid(); block = block.next()) {
        QTextList *list = block.textList();
        if (!list) {
            continue;
        }
        const bool nested = list->format().indent() > 1;
        const int item = list->itemNumber(block);
        const qreal top = !nested && item == 0 ? 12 : 0;
        const qreal bottom = !nested && item == list->count() - 1 ? 12 : 0;
        QTextBlockFormat format = block.blockFormat();
        if (format.topMargin() == top && format.bottomMargin() == bottom) {
            continue;
        }
        format.setTopMargin(top);
        format.setBottomMargin(bottom);
        QTextCursor cursor(block);
        cursor.joinPreviousEditBlock();
        cursor.setBlockFormat(format);
        cursor.endEditBlock();
    }
}

void TextBlocks::normalizeLineHeights()
{
    constexpr qreal percent = NoteNoteDialect::LINE_HEIGHT_PCT;
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc) {
        return;
    }
    for (QTextBlock block = doc->begin(); block.isValid(); block = block.next()) {
        QTextBlockFormat format = block.blockFormat();
        if (format.lineHeightType() == QTextBlockFormat::ProportionalHeight
            && qFuzzyCompare(format.lineHeight(), percent)) {
            continue;
        }
        format.setLineHeight(percent, QTextBlockFormat::ProportionalHeight);
        QTextCursor cursor(block);
        cursor.joinPreviousEditBlock();
        cursor.setBlockFormat(format);
        cursor.endEditBlock();
    }
}

void TextBlocks::normalizeCodeMargins()
{
    constexpr qreal codeMargin = NoteNoteDialect::CODE_MARGIN_PX;
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc) {
        return;
    }
    for (QTextBlock block = doc->begin(); block.isValid(); block = block.next()) {
        if (!NoteNoteDialect::isCodeBlock(block.blockFormat())) {
            continue;
        }
        const qreal top = neighbourIsCode(block.previous()) ? 0 : codeMargin;
        const qreal bottom = neighbourIsCode(block.next()) ? 0 : codeMargin;
        QTextBlockFormat format = block.blockFormat();
        if (format.topMargin() == top && format.bottomMargin() == bottom) {
            continue;
        }
        format.setTopMargin(top);
        format.setBottomMargin(bottom);
        QTextCursor cursor(block);
        cursor.joinPreviousEditBlock();
        cursor.setBlockFormat(format);
        cursor.endEditBlock();
    }
}

int TextBlocks::fillEmptyBlocksBeforeTables()
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc) {
        return -1;
    }
    int filled = -1;
    for (QTextBlock block = doc->begin(); block.isValid(); block = block.next()) {
        const QTextBlock following = block.next();
        if (block.length() > 1 || !following.isValid()) {
            continue;
        }
        QTextCursor cursor(block);
        QTextTable *table = QTextCursor(following).currentTable();
        // Leaving a nested table also changes currentTable(), but its
        // last cell is not an empty paragraph above the parent table.
        if (!table || table == cursor.currentTable()
                || following.position() != table->firstPosition()) {
            continue;
        }
        cursor.joinPreviousEditBlock();
        cursor.insertText(QString(NoteNoteDialect::BLANK_PARAGRAPH));
        cursor.endEditBlock();
        if (filled < 0) {
            filled = block.position();
        }
    }
    return filled;
}
