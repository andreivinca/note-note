// The document dialect as the native code reads it: the few constants and
// tests it shares with services/markdown/qthtml/dialect.py (the writer and
// the reader) and ui/Dialect.js (the editor's own tools). One number in three
// places, held together by tests/test_regressions.py.
#pragma once

#include <QChar>
#include <QString>
#include <QStringList>
#include <QTextBlockFormat>
#include <QTextCharFormat>

namespace NoteNoteDialect {

// A quote is the pair of margins at or past this; an indent sets the left
// one only.
constexpr qreal QUOTE_PX = 40;
// Prose line height, and the fixed distance beyond an image line's height.
constexpr qreal LINE_HEIGHT_PCT = 130;
constexpr qreal IMAGE_LINE_GAP_PX = 8;
// The clearance a code block's first and last lines carry outside the slab.
constexpr qreal CODE_MARGIN_PX = 20;
// A code line's text starts this far in, padded inside the slab.
constexpr qreal CODE_PAD_PX = 14;
// A heading is drawn bold; the author's bold inside one is heavier, so the
// reader can tell the two apart.
constexpr int BOLD_WEIGHT = 700;
constexpr int HEAVY_WEIGHT = 900;
// The size a heading of each level is written in, level 1 first; the last
// level also takes small capitals.
inline const QStringList HEADING_FONT_SIZE = {
    QStringLiteral("xx-large"), QStringLiteral("x-large"), QStringLiteral("large"),
    QStringLiteral("medium"), QStringLiteral("small"), QStringLiteral("small")};
inline const QString LAST_HEADING_VARIANT = QStringLiteral("small-caps");
// The toolbar's horizontal rule and empty two-by-two table, as the writer
// writes them (ui/tools/HorizontalRule.qml, InsertTable.qml): inserted
// through Qt's own HTML import, they are the blocks the reopened note has.
inline const QString RULE_HTML = QStringLiteral("<hr />");
inline const QString EMPTY_TABLE_HTML = QStringLiteral(
    "<table border=\"1\" cellspacing=\"0\" cellpadding=\"10\" style=\"margin-top:12px; margin-bottom:12px;\">"
    "<tr><td style=\"padding-top:6px;padding-bottom:6px\"><p style=\"line-height:130%;\"></p></td>"
    "<td style=\"padding-top:6px;padding-bottom:6px\"><p style=\"line-height:130%;\"></p></td></tr>"
    "<tr><td style=\"padding-top:6px;padding-bottom:6px\"><p style=\"line-height:130%;\"></p></td>"
    "<td style=\"padding-top:6px;padding-bottom:6px\"><p style=\"line-height:130%;\"></p></td></tr></table>");
// Markdown has no empty paragraph: a blank line is a paragraph holding this.
constexpr QChar BLANK_PARAGRAPH = QChar(0xa0);
// Nor a paragraph indent: a plain paragraph starts with this per level
// (docs/decisions.md, "Indent on plain text is non-breaking spaces").
inline const QString INDENT_TEXT = QString(4, BLANK_PARAGRAPH);
// The inline-code family, exactly: a note face whose name holds "mono" is
// prose (docs/engine-notes.md).
inline const QString MONO_FAMILY = QStringLiteral("monospace");

inline bool isQuote(const QTextBlockFormat &format)
{
    return format.leftMargin() >= QUOTE_PX && format.rightMargin() >= QUOTE_PX;
}

// A horizontal rule is a block holding no text, drawn as Qt's ruler.
inline bool isRule(const QTextBlockFormat &format)
{
    return format.hasProperty(QTextFormat::BlockTrailingHorizontalRulerWidth);
}

// A code block is a block background without a quote's margins.
inline bool isCodeBlock(const QTextBlockFormat &format)
{
    return format.background().style() != Qt::NoBrush && !isQuote(format);
}

// Inline code is a run whose families name the generic one.
inline bool isMonoFamily(const QTextCharFormat &format)
{
    for (const QString &family : format.font().families()) {
        if (family == MONO_FAMILY) {
            return true;
        }
    }
    return false;
}

}
