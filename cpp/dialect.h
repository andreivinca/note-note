// The document dialect as the native code reads it: the few constants and
// tests it shares with services/markdown/qthtml/dialect.py (the writer and
// the reader) and ui/Dialect.js (the editor's own tools). One number in three
// places, held together by tests/test_regressions.py.
#pragma once

#include <QChar>
#include <QString>
#include <QTextBlockFormat>
#include <QTextCharFormat>

namespace NoteNoteDialect {

// A quote is the pair of margins at or past this; an indent sets the left
// one only.
constexpr qreal QUOTE_PX = 40;
// Every block's line height, in percent of the font's.
constexpr qreal LINE_HEIGHT_PCT = 130;
// Markdown has no empty paragraph: a blank line is a paragraph holding this.
constexpr QChar BLANK_PARAGRAPH = QChar(0xa0);
// The inline-code family, exactly: a note face whose name holds "mono" is
// prose (docs/engine-notes.md).
inline const QString MONO_FAMILY = QStringLiteral("monospace");

inline bool isQuote(const QTextBlockFormat &format)
{
    return format.leftMargin() >= QUOTE_PX && format.rightMargin() >= QUOTE_PX;
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
