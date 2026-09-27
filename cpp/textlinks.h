#pragma once

#include <QColor>
#include <QSyntaxHighlighter>
#include <QTextDocument>
#include <QTimer>

// Theme ink for links, quotes and highlights is display-only. Authored text
// colors take precedence. The document's text, character
// advances, anchor formats and undo history stay unchanged.
class TextLinks : public QSyntaxHighlighter
{
    Q_OBJECT

public:
    explicit TextLinks(QObject *parent = nullptr);
    void configure(const QColor &colour, bool plainText, const QColor &quoteInk, const QColor &highlightInk,
                   const QColor &highlightBackground = {}, const QColor &codeBackground = {},
                   const QColor &codeForeground = {});
    QString linkAt(const QPointF &point) const;
    static void normalizeAnchors(QTextDocument *document);

signals:
    void linksChanged();

protected:
    void highlightBlock(const QString &text) override;

private:
    QTimer m_notifyLinks;
    QColor m_colour;
    QColor m_quoteInk;
    QColor m_highlightInk;
    QColor m_highlightBackground;
    QColor m_codeBackground;
    QColor m_codeForeground;
    bool m_plainText = false;
};
