#include "textblocks.h"
#include "textedits.h"

#include <QRegularExpression>
#include <QTextDocumentFragment>
#include <QTextList>
#include <QTextTable>

#include <memory>
#include <optional>

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

bool isCheckbox(const QTextBlock &block)
{
    return block.blockFormat().marker() != QTextBlockFormat::MarkerType::NoMarker;
}

bool hasStyle(const QTextBlock &block, ListStyle style)
{
    const QTextList *list = block.textList();
    if (!list) {
        return false;
    }
    if (style.checkbox) {
        return isCheckbox(block);
    }
    return !isCheckbox(block) && list->format().style() == style.marker;
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

bool allChecked(const QVector<QTextBlock> &blocks)
{
    for (const QTextBlock &block : blocks) {
        if (block.blockFormat().marker() != QTextBlockFormat::MarkerType::Checked) {
            return false;
        }
    }
    return true;
}

enum class ToggleAction { Apply, Check, Remove };

// What a toggle does to the selected paragraphs: a style comes off
// paragraphs that all have it already, and a mixed selection adopts it. A
// checkbox goes OneNote's way and is checked before it comes off.
ToggleAction toggleAction(const QVector<QTextBlock> &blocks, ListStyle style)
{
    if (!allHaveStyle(blocks, style)) {
        return ToggleAction::Apply;
    }
    if (style.checkbox && !allChecked(blocks)) {
        return ToggleAction::Check;
    }
    return ToggleAction::Remove;
}

void check(const QTextBlock &block)
{
    QTextBlockFormat format = block.blockFormat();
    format.setMarker(QTextBlockFormat::MarkerType::Checked);
    QTextCursor(block).setBlockFormat(format);
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

// The list of an earlier item the block can join: the nearest one at its
// level or above, past any deeper items. List membership never crosses a
// table cell.
QTextList *earlierList(const QTextBlock &block, const QTextListFormat &format, ListStyle style)
{
    for (QTextBlock previous = block.previous(); previous.isValid() && TextEdits::sameContainer(block, previous);
         previous = previous.previous()) {
        const QTextList *list = previous.textList();
        if (!list || list->format().indent() <= format.indent()) {
            return listOf(previous, format, style);
        }
    }
    return nullptr;
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
        if (!TextEdits::sameContainer(block, next) || !next.textList()) {
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

// An item joins the list of an earlier item it continues unless
// `joinEarlier` is false: then it starts a list of its own in `format`.
void applyList(const QTextBlock &block, ListStyle style, const QTextListFormat &format, bool joinEarlier = true)
{
    // Taken before removeList clears it.
    const auto marker = markerFor(block, style);
    // A QTextList holds items of one level and style: an item moving above
    // its list, or taking another style at its level, leaves it first.
    const QTextList *previous = block.textList();
    if (previous && (format.indent() < previous->format().indent()
        || (format.indent() == previous->format().indent() && format.style() != previous->format().style()))) {
        TextEdits::removeList(block);
    }
    QTextBlockFormat paragraph = block.blockFormat();
    paragraph.setIndent(0);
    paragraph.setMarker(marker);
    QTextCursor cursor(block);
    cursor.setBlockFormat(paragraph);

    QTextList *list = joinEarlier ? earlierList(block, format, style) : nullptr;
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

// A list typed the Markdown way: the editing tool it belongs to (ui/tools),
// the style's name (styleNamed) and the number its first item counts from.
struct TypedList {
    QString tool;
    QString style;
    int start = 1;
};

// The list a paragraph's text asks for when Space follows it: "1." or "1)"
// numbers from that number, "a." and "A." letter from that letter, "-" and
// "*" bullet, "[]" and "[ ]" check.
std::optional<TypedList> typedList(const QString &text)
{
    static const QRegularExpression number(QStringLiteral("^([1-9][0-9]{0,8})[.)]$"));
    static const QRegularExpression letter(QStringLiteral("^([a-zA-Z])[.)]$"));
    static const QRegularExpression bullet(QStringLiteral("^[-*]$"));
    static const QRegularExpression checkbox(QStringLiteral("^\\[ ?\\]$"));
    if (const QRegularExpressionMatch match = number.match(text); match.hasMatch()) {
        return TypedList{QStringLiteral("ol"), QStringLiteral("decimal"), match.captured(1).toInt()};
    }
    if (const QRegularExpressionMatch match = letter.match(text); match.hasMatch()) {
        const QChar first = match.captured(1).at(0);
        const bool lower = first.isLower();
        const int start = first.toLower().unicode() - 'a' + 1;
        return TypedList{QStringLiteral("ol"), QLatin1String(lower ? "lower-alpha" : "upper-alpha"), start};
    }
    if (bullet.match(text).hasMatch()) {
        return TypedList{QStringLiteral("ul"), QStringLiteral("disc")};
    }
    if (checkbox.match(text).hasMatch()) {
        return TypedList{QStringLiteral("todo"), QStringLiteral("todo")};
    }
    return std::nullopt;
}

// The typed list a Space at `position` would start: the paragraph's text in
// front of the caret asks for one, and nothing but an empty paragraph's
// filler follows it. Code, rules and list items take the Space as text.
std::optional<TypedList> typedListAt(const QTextDocument *doc, int position)
{
    const QTextBlock block = doc->findBlock(position);
    const QTextBlockFormat format = block.blockFormat();
    if (!block.isValid() || block.textList() || NoteNoteDialect::isCodeBlock(format)
        || NoteNoteDialect::isRule(format)) {
        return std::nullopt;
    }
    const int offset = position - block.position();
    const QString after = block.text().mid(offset);
    if (!after.isEmpty() && after != QString(NoteNoteDialect::BLANK_PARAGRAPH)) {
        return std::nullopt;
    }
    return typedList(block.text().left(offset));
}

// A plain paragraph takes one level more or less of the indent Markdown
// keeps, as the Markdown tools give it (ui/tools/Indent.qml, Outdent.qml).
void indentParagraph(const QTextBlock &block, int direction)
{
    QTextCursor cursor(block);
    if (direction > 0) {
        cursor.insertText(NoteNoteDialect::INDENT_TEXT);
    } else if (block.text().startsWith(NoteNoteDialect::INDENT_TEXT)) {
        cursor.movePosition(QTextCursor::NextCharacter, QTextCursor::KeepAnchor, int(NoteNoteDialect::INDENT_TEXT.size()));
        cursor.removeSelectedText();
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

namespace {

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


QVariantMap TextBlocks::toggleList(int from, int to, const QString &styleName, bool toggle)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    const std::optional<ListStyle> style = styleNamed(styleName);
    if (!doc || !style || from < 0 || from > to || to >= doc->characterCount()) {
        return {};
    }
    const QVector<QTextBlock> blocks = TextEdits::selectedBlocks(doc, from, to);
    if (blocks.isEmpty()) {
        return {};
    }
    const ToggleAction action = toggle ? toggleAction(blocks, *style) : ToggleAction::Apply;
    QTextCursor start(doc);
    start.setPosition(from);
    start.setKeepPositionOnInsert(true);
    QTextCursor end(doc);
    end.setPosition(to);
    end.setKeepPositionOnInsert(true);
    QTextCursor transaction(doc);
    transaction.beginEditBlock();
    for (const QTextBlock &block : blocks) {
        switch (action) {
        case ToggleAction::Apply:
            applyList(block, *style, listFormat(block, *style));
            break;
        case ToggleAction::Check:
            check(block);
            break;
        case ToggleAction::Remove:
            TextEdits::removeList(block);
            break;
        }
    }
    transaction.endEditBlock();
    return {{"from", start.position()}, {"to", end.position()}};
}

QVariantMap TextBlocks::typedListAt(int position) const
{
    const QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || position < 0 || position >= doc->characterCount()) {
        return {};
    }
    const std::optional<TypedList> typed = ::typedListAt(doc, position);
    if (!typed) {
        return {};
    }
    return {{"tool", typed->tool}, {"style", typed->style}, {"start", typed->start}};
}

int TextBlocks::startTypedList(int position)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || position < 0 || position >= doc->characterCount()) {
        return -1;
    }
    const std::optional<TypedList> typed = ::typedListAt(doc, position);
    if (!typed) {
        return -1;
    }
    // The Space is typed on its own, so undoing the list leaves the text as
    // it was typed, Space and all.
    beginEditBlock(position);
    QTextCursor typing(doc);
    typing.setPosition(position);
    typing.insertText(QStringLiteral(" "));
    endEditBlock();

    beginEditBlock(position + 1);
    const QTextBlock block = doc->findBlock(position);
    QTextCursor caret(doc);
    caret.setPosition(block.position());
    caret.setPosition(position + 1, QTextCursor::KeepAnchor);
    caret.removeSelectedText();
    caret.setKeepPositionOnInsert(true);
    const ListStyle style = *styleNamed(typed->style);
    QTextListFormat format = listFormat(block, style);
    format.setStart(typed->start);
    // A number that does not continue the list just above starts its own.
    const QTextList *earlier = earlierList(block, format, style);
    const bool continues = !earlier || !isNumbered(style.marker)
        || earlier->format().start() + earlier->count() == typed->start;
    applyList(block, style, format, continues);
    endEditBlock();
    return caret.position();
}

bool TextBlocks::indentBlocks(int from, int to, int direction, bool cycleStyles)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || from < 0 || from > to || to >= doc->characterCount()
        || (direction != 1 && direction != -1)) {
        return false;
    }
    const QVector<QTextBlock> blocks = TextEdits::selectedBlocks(doc, from, to);
    if (blocks.isEmpty()) {
        return false;
    }
    bool hasList = false;
    for (const QTextBlock &block : blocks) {
        if (block.textList()) {
            hasList = true;
            break;
        }
    }
    QTextCursor transaction(doc);
    transaction.beginEditBlock();
    for (const QTextBlock &block : blocks) {
        QTextList *list = block.textList();
        if (!list) {
            // A cell's paragraph moves with the list items beside it only:
            // a Markdown table row holds no indent of its own.
            if (hasList || !QTextCursor(block).currentTable()) {
                indentParagraph(block, direction);
            }
            continue;
        }
        const int indent = list->format().indent() + direction;
        if (indent < 1) {
            TextEdits::removeList(block);
            continue;
        }
        ListStyle style{list->format().style(), isCheckbox(block)};
        if (cycleStyles && !style.checkbox) {
            style.marker = styleAtDepth(style.marker, indent);
        }
        // An item moving to a level an earlier item of its list holds takes
        // that item's marker, even one chosen from the dropdown: its parent's
        // when it returns to that level, its sibling's when it joins it.
        for (QTextBlock previous = block.previous(); previous.isValid() && TextEdits::sameContainer(block, previous);
             previous = previous.previous()) {
            const QTextList *earlier = previous.textList();
            if (!earlier || earlier->format().indent() < indent) {
                break;
            }
            if (earlier->format().indent() == indent) {
                const bool sameFamily = style.checkbox || isNumbered(earlier->format().style()) == isNumbered(style.marker);
                if (isCheckbox(previous) == style.checkbox && sameFamily) {
                    style.marker = earlier->format().style();
                }
                break;
            }
        }
        QTextListFormat format;
        format.setStyle(style.marker);
        format.setIndent(indent);
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
    for (const QTextBlock &block : TextEdits::selectedBlocks(projected.get(), from, to)) {
        if (block.textList()) {
            TextEdits::removeList(block);
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
    TextEdits::removeList(block);
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
    if (!block.textList() || !TextEdits::isEmptyBlock(block)) {
        return false;
    }
    QTextCursor cursor(block);
    cursor.beginEditBlock();
    TextEdits::removeList(block);
    if (!block.text().isEmpty()) {
        // The filler that kept the empty item alive goes with the list.
        cursor.setPosition(block.position() + block.length() - 1, QTextCursor::KeepAnchor);
        cursor.removeSelectedText();
    }
    cursor.endEditBlock();
    return true;
}
