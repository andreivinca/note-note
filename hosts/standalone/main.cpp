#include "application.h"

#include <QCommandLineParser>
#include <QGuiApplication>

int main(int argc, char *argv[])
{
    describeApplication();
    QGuiApplication app(argc, argv);
    QCommandLineParser parser;
    parser.setApplicationDescription(QStringLiteral("Local Markdown, OneNote, Sticky Notes and Notion in one workspace."));
    parser.addHelpOption();
    parser.addVersionOption();
    parser.addOption({QStringLiteral("data-dir"), QStringLiteral("Application resources directory."), QStringLiteral("directory")});
    parser.process(app);

    // A build-tree run says where the source tree is with --data-dir; an
    // installed one is found by its place (application.h, resolveDataDir).
    const QString dataDir = resolveDataDir(parser.value(QStringLiteral("data-dir")));
    if (dataDir.isEmpty()) {
        qCritical("The Note Note application resources could not be found; pass --data-dir.");
        return 1;
    }
    return runNoteNote(app, {dataDir, dataDir + QStringLiteral("/hosts/standalone/Main.qml"), true});
}
