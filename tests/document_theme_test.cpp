#include "../cpp/textlinks.h"

#include <QSignalSpy>
#include <QTest>
#include <QTextBlock>
#include <QTextCursor>
#include <QTextLayout>

class DocumentThemeTest : public QObject
{
    Q_OBJECT
private slots:
    void displayDoesNotEditContent()
    {
        QTextDocument document;
        document.setHtml(QStringLiteral(
            "<p>ordinary <span style='background-color:#f9e2af'>marker</span> "
            "<span style='font-family:monospace'>code</span> "
            "<span style='color:#112233'>authored</span></p>"
            "<p style='margin-left:40px;margin-right:40px'>quote "
            "<a href='https://example.org' style='-qt-foreground:none'>link</a></p>"
            "<table><tr><td>cell<table><tr><td>nested</td></tr></table></td></tr></table>"));
        TextLinks highlighter;
        highlighter.setDocument(&document);
        QTextCursor cursor(&document);
        cursor.movePosition(QTextCursor::End);
        cursor.insertText(QStringLiteral(" pending"));
        cursor.setPosition(3);
        cursor.setPosition(9, QTextCursor::KeepAnchor);
        const QString html = document.toHtml();
        const int undoSteps = document.availableUndoSteps();
        QSignalSpy contentChanges(&document, &QTextDocument::contentsChange);
        const bool modified = document.isModified();
        for (int i = 0; i < 8; ++i) {
            highlighter.configure(QColor("#aabbcc"), false, QColor("#667788"), QColor("#000000"),
                                  QColor(i % 2 ? "#66aaee" : "#eeaa66"), QColor("#223344"), QColor("#eeeeee"));
            QCOMPARE(document.toHtml(), html);
            QCOMPARE(document.availableUndoSteps(), undoSteps);
            QCOMPARE(contentChanges.count(), 0);
            QCOMPARE(document.isModified(), modified);
            QCOMPARE(cursor.anchor(), 3);
            QCOMPARE(cursor.position(), 9);
        }
        const QTextBlock first = document.begin();
        const int marker = first.text().indexOf(QStringLiteral("marker"));
        const int code = first.text().indexOf(QStringLiteral("code"));
        const int author = first.text().indexOf(QStringLiteral("authored"));
        bool markerPainted = false;
        bool codePainted = false;
        for (const auto &range : first.layout()->formats()) {
            if (range.start <= marker && range.start + range.length > marker) {
                markerPainted = range.format.background().color() == QColor("#66aaee");
            }
            if (range.start <= code && range.start + range.length > code) {
                codePainted = range.format.background().color() == QColor("#223344");
            }
            if (range.start <= author && range.start + range.length > author) {
                QCOMPARE(range.format.foreground().style(), Qt::NoBrush);
            }
        }
        QVERIFY(markerPainted);
        QVERIFY(codePainted);
        document.undo();
        QVERIFY(!document.toPlainText().endsWith(QStringLiteral(" pending")));
        document.redo();
        QCOMPARE(document.toHtml(), html);
        QSignalSpy changes(&document, &QTextDocument::contentsChanged);
        cursor.insertText(QStringLiteral("new edit"));
        QVERIFY(changes.count() > 0);
        QVERIFY(document.toHtml() != html);
    }
};

QTEST_MAIN(DocumentThemeTest)
#include "document_theme_test.moc"
