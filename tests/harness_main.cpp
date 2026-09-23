// The test harness executable: the application's runtime, types and
// resources under a QML file of the test's choosing, without the one
// instance per user the product takes. Built with BUILD_TESTING, never
// installed — the product binary carries no test entry.
#include "../hosts/standalone/application.h"

#include <QCommandLineParser>
#include <QGuiApplication>

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    QCommandLineParser parser;
    parser.setApplicationDescription(QStringLiteral("Note Note test harness: runs a QML harness over the application."));
    parser.addHelpOption();
    parser.addOption({QStringLiteral("data-dir"), QStringLiteral("Application resources directory."), QStringLiteral("directory")});
    parser.addOption({QStringLiteral("qml"), QStringLiteral("The QML harness to run."), QStringLiteral("file")});
    parser.process(app);

    const QString dataDir = resolveDataDir(parser.value(QStringLiteral("data-dir")));
    if (dataDir.isEmpty()) {
        qCritical("The Note Note application resources could not be found; pass --data-dir.");
        return 1;
    }
    if (!parser.isSet(QStringLiteral("qml"))) {
        qCritical("Pass the QML harness to run with --qml.");
        return 1;
    }
    return runNoteNote(app, {dataDir, parser.value(QStringLiteral("qml")), false});
}
