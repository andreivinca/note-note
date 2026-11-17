#include "textblocks.h"
#include "textedits.h"

#include <QRegularExpression>
#include <QTextCursor>
#include <QTextDocument>
#include <QTextDocumentFragment>
#include <QTextTable>

#include <optional>

namespace {

// A heading to the dialect: Qt's heading tag, or text in a font size, which
// the reader takes for a heading before it looks for a quote
// (qthtml/reader.py, heading_level). Only headings are written sized.
bool isHeading(const QTextBlock &block)
{
    if (block.blockFormat().headingLevel() > 0) {
        return true;
    }
    for (QTextBlock::iterator it = block.begin(); !it.atEnd(); ++it) {
        if (it.fragment().charFormat().hasProperty(QTextFormat::FontSizeAdjustment)) {
            return true;
        }
    }
    return false;
}

// A paragraph as the writer makes one (qthtml/writer.py, block_style): a
// line height and nothing else, Qt storing no zero margin.
QTextBlockFormat paragraphFormat()
{
    QTextBlockFormat format;
    format.setLineHeight(NoteNoteDialect::LINE_HEIGHT_PCT, QTextBlockFormat::ProportionalHeight);
    return format;
}

// The formats a paragraph style gives a block: its block format, the
// block's own character format — what text typed into the emptied block
// takes — and its text's character format.
struct BlockStyle {
    QTextBlockFormat block;
    QTextCharFormat blockChar;
    QTextCharFormat text;
};

// A heading of `level`. Qt gives a heading tag margins and a block format of
// its own on import, so the style is read from Qt importing the writer's
// heading (qthtml/writer.py, heading) rather than restated here, and a
// heading made in place matches the note reopened.
BlockStyle headingStyle(int level)
{
    const QString variant = level == NoteNoteDialect::HEADING_FONT_SIZE.size()
        ? QStringLiteral(" font-variant:%1;").arg(NoteNoteDialect::LAST_HEADING_VARIANT) : QString();
    QTextDocument written;
    written.setHtml(QStringLiteral("<h%1 style=\"line-height:%2%;\"><span style=\"font-size:%3; font-weight:%4;%5\">x</span></h%1>")
                        .arg(level)
                        .arg(NoteNoteDialect::LINE_HEIGHT_PCT)
                        .arg(NoteNoteDialect::HEADING_FONT_SIZE.at(level - 1))
                        .arg(NoteNoteDialect::BOLD_WEIGHT)
                        .arg(variant));
    const QTextBlock block = written.begin();
    return {block.blockFormat(), block.charFormat(), block.begin().fragment().charFormat()};
}

// The text's character formats under its new level. A heading's own weight
// is bold, so the author's bold inside one is the heavy weight: bold text
// turned into a heading becomes heavy and the rest bold, and a heading
// turned back into a paragraph loses its bold and its heavy goes back to
// bold. The size and small capitals are the level's (`text`), none for a
// paragraph; every other format — italics, colour, links — stays.
void restyleText(const QTextBlock &block, bool wasHeading, int level, const QTextCharFormat &text)
{
    const int authorBold = wasHeading ? NoteNoteDialect::HEAVY_WEIGHT : NoteNoteDialect::BOLD_WEIGHT;
    // Taken first: a restyled fragment can merge with its neighbour, which
    // would leave an iterator over the block's fragments behind.
    QVector<QTextFragment> fragments;
    for (QTextBlock::iterator it = block.begin(); !it.atEnd(); ++it) {
        fragments.append(it.fragment());
    }
    for (const QTextFragment &fragment : fragments) {
        QTextCharFormat format = fragment.charFormat();
        const bool bold = format.fontWeight() >= authorBold;
        if (level > 0) {
            format.setFontWeight(bold ? NoteNoteDialect::HEAVY_WEIGHT : NoteNoteDialect::BOLD_WEIGHT);
        } else if (bold) {
            format.setFontWeight(NoteNoteDialect::BOLD_WEIGHT);
        } else {
            format.clearProperty(QTextFormat::FontWeight);
        }
        for (const int property : {int(QTextFormat::FontSizeAdjustment), int(QTextFormat::FontCapitalization)}) {
            if (text.hasProperty(property)) {
                format.setProperty(property, text.property(property));
            } else {
                format.clearProperty(property);
            }
        }
        QTextCursor cursor(block);
        cursor.setPosition(fragment.position());
        cursor.setPosition(fragment.position() + fragment.length(), QTextCursor::KeepAnchor);
        cursor.setCharFormat(format);
    }
}

// A code line, read from Qt importing the writer's code line
// (qthtml/writer.py, code) in the note's code background, as a heading is.
// Its margins are a first and last line's; normalizeCodeMargins keeps the
// run's.
BlockStyle codeStyle(const QString &background)
{
    QTextDocument written;
    written.setHtml(QStringLiteral("<p style=\"white-space:pre-wrap; margin-top:%1px; margin-bottom:%1px;"
                                   " margin-left:%2px; background-color:%3; font-family:'%4'; line-height:%5%;\">"
                                   "<span style=\"font-family:'%4';\">x</span></p>")
                        .arg(NoteNoteDialect::CODE_MARGIN_PX)
                        .arg(NoteNoteDialect::CODE_PAD_PX)
                        .arg(background, NoteNoteDialect::MONO_FAMILY)
                        .arg(NoteNoteDialect::LINE_HEIGHT_PCT));
    const QTextBlock block = written.begin();
    return {block.blockFormat(), block.charFormat(), block.begin().fragment().charFormat()};
}

// The paragraph a code line becomes, as the Markdown route makes it: the
// reader takes one filler off each end of the line (qthtml/reader.py,
// _code_line) and escapes it as a paragraph's text, four columns of leading
// whitespace or more becoming the dialect's indent and less dropped
// (mdtext.escape_line_start), and Qt reads the paragraph's HTML collapsing
// every other run of spaces and tabs. An empty line is a blank paragraph.
// Nothing for a line that route would lose — spaces alone too few to be
// an indent, which Markdown reads as the gap between blocks — or that holds
// any other space character, whose fate is the HTML import's.
std::optional<QString> paragraphText(QString line)
{
    const QChar filler = NoteNoteDialect::BLANK_PARAGRAPH;
    if (line.startsWith(filler)) {
        line.remove(0, 1);
    }
    if (line.endsWith(filler)) {
        line.chop(1);
    }
    if (line.isEmpty()) {
        return QString(filler);
    }
    for (const QChar c : line) {
        if (c.isSpace() && c != QLatin1Char(' ') && c != QLatin1Char('\t') && c != filler) {
            return std::nullopt;
        }
    }
    int lead = 0;
    int columns = 0;
    while (lead < line.size() && (line.at(lead) == QLatin1Char(' ') || line.at(lead) == QLatin1Char('\t'))) {
        columns = line.at(lead) == QLatin1Char('\t') ? (columns / 4 + 1) * 4 : columns + 1;
        ++lead;
    }
    static const QRegularExpression run(QStringLiteral("[ \t]+"));
    static const QRegularExpression trailing(QStringLiteral("[ \t]+$"));
    const QString rest = line.mid(lead).replace(run, QStringLiteral(" ")).remove(trailing);
    if (rest.isEmpty()) {
        return columns >= 4 ? std::optional<QString>(QString(filler)) : std::nullopt;
    }
    return (columns >= 4 ? QString(columns, filler) : QString()) + rest;
}

bool isCodeLine(const QTextBlock &block)
{
    return block.isValid() && NoteNoteDialect::isCodeBlock(block.blockFormat());
}

// The last block of the rule or code block holding `block`: a rule is a
// block of its own, a code block the run of code lines around it.
QTextBlock blockEnd(const QTextBlock &block)
{
    QTextBlock last = block;
    if (!isCodeLine(block)) {
        return last;
    }
    for (QTextBlock next = block.next(); isCodeLine(next) && TextEdits::sameContainer(last, next); next = next.next()) {
        last = next;
    }
    return last;
}

// The writer's `html` — a rule or a table — after the caret's block, past
// the whole code block the caret is in, as the Markdown route places it.
// Inserted at the end of that block, the fragment's own first block, empty,
// merges into it. After a list item the list splits round it, as two lists
// stand round a rule or table in Markdown; an empty line it follows takes
// the dialect's blank, as the line does in the note reopened, and Qt would
// hide an empty line above a table. When nothing follows, a paragraph goes
// in after it for the caret, as one would after a note that ends in a rule
// (stepPastBlock); Qt keeps an empty block after a table, which serves.
// Answers the caret: that paragraph when the note ends there, the same
// place otherwise. A caret in a table answers -1: there a table goes inside
// the cell and a rule after the table, which the Markdown route places.
int placeBlock(QTextDocument *doc, int position, const QString &html)
{
    const QTextBlock block = doc->findBlock(position);
    if (QTextCursor(block).currentTable()) {
        return -1;
    }
    const QTextBlock anchor = blockEnd(block);
    const bool atEnd = !anchor.next().isValid();
    QTextCursor cursor(doc);
    cursor.setPosition(anchor.position() + anchor.length() - 1);
    cursor.beginEditBlock();
    if (anchor.textList()) {
        TextEdits::splitListAfter(anchor);
    }
    if (anchor.text().isEmpty()) {
        cursor.insertText(QString(NoteNoteDialect::BLANK_PARAGRAPH));
    }
    cursor.insertFragment(QTextDocumentFragment::fromHtml(html));
    int caret = position;
    if (atEnd) {
        cursor.movePosition(QTextCursor::End);
        if (NoteNoteDialect::isRule(cursor.block().blockFormat())) {
            cursor.insertBlock(paragraphFormat(), QTextCharFormat());
        }
        caret = cursor.position();
    }
    cursor.endEditBlock();
    return caret;
}

// The block's quote margins come off. Cleared, not zeroed: a paragraph the
// writer makes stores no margin at all, and the block must match it.
void unquote(const QTextBlock &block)
{
    QTextBlockFormat format = block.blockFormat();
    format.clearProperty(QTextFormat::BlockLeftMargin);
    format.clearProperty(QTextFormat::BlockRightMargin);
    QTextCursor(block).setBlockFormat(format);
}

}

QVariantMap TextBlocks::toggleQuote(int from, int to)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || from < 0 || from > to || to >= doc->characterCount()) {
        return {};
    }
    const QVector<QTextBlock> blocks = TextEdits::selectedBlocks(doc, from, to);
    if (blocks.isEmpty()) {
        return {};
    }
    bool allQuoted = true;
    for (const QTextBlock &block : blocks) {
        if (isHeading(block) || QTextCursor(block).currentTable()) {
            return {};
        }
        allQuoted = allQuoted && NoteNoteDialect::isQuote(block.blockFormat());
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
        // A selection that is all quote loses it; a mixed one adopts it.
        if (allQuoted) {
            unquote(block);
            continue;
        }
        // A quote holds paragraphs only (qthtml/writer.py): an item leaves its list.
        if (block.textList()) {
            TextEdits::removeList(block);
        }
        QTextBlockFormat format = block.blockFormat();
        format.setLeftMargin(NoteNoteDialect::QUOTE_PX);
        format.setRightMargin(NoteNoteDialect::QUOTE_PX);
        QTextCursor cursor(block);
        cursor.setBlockFormat(format);
        // Qt omits an empty paragraph's margins from its HTML; the filler
        // keeps an empty quote line, as the writer keeps one on import.
        if (block.text().isEmpty()) {
            cursor.insertText(QString(NoteNoteDialect::BLANK_PARAGRAPH));
        }
    }
    transaction.endEditBlock();
    return {{"from", start.position()}, {"to", end.position()}};
}

bool TextBlocks::removeQuoteAtStart(int position)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || position < 0 || position >= doc->characterCount()) {
        return false;
    }
    const QTextBlock block = doc->findBlock(position);
    if (!NoteNoteDialect::isQuote(block.blockFormat()) || position != block.position()) {
        return false;
    }
    QTextCursor cursor(block);
    cursor.beginEditBlock();
    unquote(block);
    cursor.endEditBlock();
    return true;
}

bool TextBlocks::leaveEmptyQuote(int position)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || position < 0 || position >= doc->characterCount()) {
        return false;
    }
    const QTextBlock block = doc->findBlock(position);
    const QTextBlock next = block.next();
    if (!NoteNoteDialect::isQuote(block.blockFormat()) || !TextEdits::isEmptyBlock(block)
        || (next.isValid() && NoteNoteDialect::isQuote(next.blockFormat()))) {
        return false;
    }
    QTextCursor cursor(block);
    cursor.beginEditBlock();
    unquote(block);
    if (!block.text().isEmpty()) {
        // The filler that kept the empty line alive goes with the quote.
        cursor.setPosition(block.position() + block.length() - 1, QTextCursor::KeepAnchor);
        cursor.removeSelectedText();
    }
    cursor.endEditBlock();
    return true;
}

QVariantMap TextBlocks::setHeading(int from, int to, int level)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || from < 0 || from > to || to >= doc->characterCount()
        || level < 0 || level > NoteNoteDialect::HEADING_FONT_SIZE.size()) {
        return {};
    }
    const QVector<QTextBlock> blocks = TextEdits::selectedBlocks(doc, from, to);
    if (blocks.isEmpty()) {
        return {};
    }
    for (const QTextBlock &block : blocks) {
        if (QTextCursor(block).currentTable()) {
            return {};
        }
    }
    const BlockStyle heading = level > 0 ? headingStyle(level) : BlockStyle{paragraphFormat(), {}, {}};
    QTextCursor start(doc);
    start.setPosition(from);
    start.setKeepPositionOnInsert(true);
    QTextCursor end(doc);
    end.setPosition(to);
    end.setKeepPositionOnInsert(true);
    QTextCursor transaction(doc);
    transaction.beginEditBlock();
    for (const QTextBlock &block : blocks) {
        const bool wasHeading = isHeading(block);
        // A heading is a paragraph of its own: an item leaves its list, and
        // the level's block format replaces a quote's margins.
        if (block.textList()) {
            TextEdits::removeList(block);
        }
        QTextCursor cursor(block);
        cursor.setBlockFormat(heading.block);
        cursor.setBlockCharFormat(heading.blockChar);
        restyleText(block, wasHeading, level, heading.text);
        // Qt drops an empty heading's format from its HTML; the filler keeps
        // the line a heading to type into, as the writer keeps a blank line.
        if (level > 0 && block.text().isEmpty()) {
            cursor.insertText(QString(NoteNoteDialect::BLANK_PARAGRAPH), heading.text);
        }
    }
    transaction.endEditBlock();
    return {{"from", start.position()}, {"to", end.position()}};
}

int TextBlocks::stepPastBlock(int position, const QString &text)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || position < 0 || position >= doc->characterCount()) {
        return -1;
    }
    const QTextBlock block = doc->findBlock(position);
    if (!NoteNoteDialect::isRule(block.blockFormat()) && !isCodeLine(block)) {
        return -1;
    }
    const QTextBlock last = blockEnd(block);
    QTextCursor cursor(doc);
    cursor.setPosition(last.position() + last.length() - 1);
    cursor.beginEditBlock();
    cursor.insertBlock(paragraphFormat(), QTextCharFormat());
    cursor.insertText(text, QTextCharFormat());
    cursor.endEditBlock();
    return cursor.position();
}

int TextBlocks::leaveEmptyCode(int position)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || position < 0 || position >= doc->characterCount()) {
        return -1;
    }
    const QTextBlock block = doc->findBlock(position);
    if (!isCodeLine(block) || !TextEdits::isEmptyBlock(block) || blockEnd(block) != block) {
        return -1;
    }
    // The block's only line is the block: it stays, and the paragraph lands
    // after it, as Right at the note's end would put one.
    const QTextBlock previous = block.previous();
    if (!isCodeLine(previous) || !TextEdits::sameContainer(previous, block)) {
        return stepPastBlock(position, {});
    }
    QTextCursor cursor(block);
    cursor.beginEditBlock();
    cursor.setBlockFormat(paragraphFormat());
    cursor.setBlockCharFormat(QTextCharFormat());
    if (!block.text().isEmpty()) {
        // The filler that kept the empty line alive goes with the code.
        cursor.setPosition(block.position() + block.length() - 1, QTextCursor::KeepAnchor);
        cursor.removeSelectedText();
    }
    cursor.endEditBlock();
    return block.position();
}

int TextBlocks::insertRule(int position)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || position < 0 || position >= doc->characterCount()) {
        return -1;
    }
    return placeBlock(doc, position, NoteNoteDialect::RULE_HTML);
}

int TextBlocks::insertTable(int position)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || position < 0 || position >= doc->characterCount()) {
        return -1;
    }
    return placeBlock(doc, position, NoteNoteDialect::EMPTY_TABLE_HTML);
}

QVariantMap TextBlocks::makeCodeBlock(int from, int to, const QString &background)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || from < 0 || from > to || to >= doc->characterCount()) {
        return {};
    }
    const QTextBlock first = doc->findBlock(from);
    const QTextBlock last = doc->findBlock(to > from ? to - 1 : to);
    QVector<QTextBlock> blocks;
    for (QTextBlock block = first; block.isValid(); block = block.next()) {
        if (QTextCursor(block).currentTable() || block.textList() || isCodeLine(block)
            || NoteNoteDialect::isRule(block.blockFormat())
            || block.text().contains(QChar::ObjectReplacementCharacter)) {
            return {};
        }
        blocks.append(block);
        if (block == last) {
            break;
        }
    }
    const BlockStyle code = codeStyle(background);
    const QChar filler = NoteNoteDialect::BLANK_PARAGRAPH;
    const QTextBlock after = last.next();
    QTextCursor start(doc);
    start.setPosition(from);
    start.setKeepPositionOnInsert(true);
    QTextCursor end(doc);
    end.setPosition(to);
    end.setKeepPositionOnInsert(true);
    QTextCursor transaction(doc);
    transaction.beginEditBlock();
    for (const QTextBlock &block : blocks) {
        // A soft line break is a code line of its own.
        const QString text = block.text();
        for (int index = int(text.size()) - 1; index >= 0; --index) {
            if (text.at(index) == QChar::LineSeparator) {
                QTextCursor cursor(doc);
                cursor.setPosition(block.position() + index);
                cursor.setPosition(block.position() + index + 1, QTextCursor::KeepAnchor);
                cursor.removeSelectedText();
                cursor.insertBlock();
            }
        }
    }
    for (QTextBlock line = first; line.isValid() && line != after; line = line.next()) {
        QTextCursor cursor(line);
        cursor.setBlockFormat(code.block);
        cursor.setBlockCharFormat(code.blockChar);
        // Code is the line's visible text alone: its inline formats go, and
        // a filler a line ends in, which the Markdown route drops.
        if (line.text().size() > 1 && line.text().endsWith(filler)) {
            cursor.setPosition(line.position() + line.length() - 2);
            cursor.deleteChar();
        }
        cursor.setPosition(line.position());
        cursor.setPosition(line.position() + line.length() - 1, QTextCursor::KeepAnchor);
        cursor.setCharFormat(code.text);
        // The writer's filler keeps an empty code line alive.
        if (line.text().isEmpty()) {
            cursor.insertText(QString(filler), code.text);
        }
    }
    normalizeCodeMargins();
    transaction.endEditBlock();
    return {{"from", start.position()}, {"to", end.position()}};
}

QVariantMap TextBlocks::unmakeCodeBlock(int from, int to)
{
    QTextDocument *doc = m_document ? m_document->textDocument() : nullptr;
    if (!doc || from < 0 || from > to || to >= doc->characterCount()) {
        return {};
    }
    const QTextBlock held = doc->findBlock(from);
    if (!isCodeLine(held)) {
        return {};
    }
    QTextBlock first = held;
    while (isCodeLine(first.previous()) && TextEdits::sameContainer(first.previous(), first)) {
        first = first.previous();
    }
    const QTextBlock last = blockEnd(held);
    QVector<QTextBlock> lines;
    QStringList texts;
    for (QTextBlock line = first; line.isValid(); line = line.next()) {
        const std::optional<QString> text = paragraphText(line.text());
        if (!text) {
            return {};
        }
        lines.append(line);
        texts.append(*text);
        if (line == last) {
            break;
        }
    }
    // The selection keeps its lines and its place in them, as far as each
    // line's new text reaches.
    const QTextBlock fromLine = doc->findBlock(from);
    const QTextBlock toLine = doc->findBlock(to);
    const int fromOffset = from - fromLine.position();
    const int toOffset = to - toLine.position();
    QTextCursor transaction(doc);
    transaction.beginEditBlock();
    for (int index = 0; index < lines.size(); ++index) {
        const QTextBlock &line = lines.at(index);
        QTextCursor cursor(line);
        cursor.setBlockFormat(paragraphFormat());
        cursor.setBlockCharFormat(QTextCharFormat());
        cursor.setPosition(line.position());
        cursor.setPosition(line.position() + line.length() - 1, QTextCursor::KeepAnchor);
        if (line.text() == texts.at(index)) {
            cursor.setCharFormat(QTextCharFormat());
        } else {
            cursor.insertText(texts.at(index), QTextCharFormat());
        }
    }
    normalizeCodeMargins();
    transaction.endEditBlock();
    const auto within = [](const QTextBlock &line, int offset) {
        return line.position() + qMin(offset, line.length() - 1);
    };
    return {{"from", within(fromLine, fromOffset)}, {"to", within(toLine, toOffset)}};
}
