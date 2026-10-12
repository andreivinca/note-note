#include "application.h"

#include "processbackend.h"
#include "runtime.h"
#include "../../cpp/textblocks.h"
#include "theme/desktoptheme.h"

#include <QDir>
#include <QFileInfo>
#include <QFontDatabase>
#include <QGuiApplication>
#include <QImageReader>
#include <QLocalServer>
#include <QLocalSocket>
#include <QLockFile>
#include <QProcess>
#include <QQmlApplicationEngine>
#include <QQuickStyle>
#include <QStandardPaths>

QString resolveDataDir(const QString &requested)
{
    QString dataDir = requested;
    if (dataDir.isEmpty()) {
        dataDir = QDir(QCoreApplication::applicationDirPath()).absoluteFilePath(QStringLiteral(NOTE_NOTE_DATA_FROM_BIN));
        if (!QFileInfo::exists(dataDir + QStringLiteral("/Workspace.qml"))) {
            dataDir = QStringLiteral(NOTE_NOTE_INSTALL_DATA_DIR);
        }
    }
    return QFileInfo::exists(dataDir + QStringLiteral("/Workspace.qml")) ? dataDir : QString();
}

void describeApplication()
{
    QCoreApplication::setApplicationName(QStringLiteral("note-note"));
    QCoreApplication::setOrganizationDomain(QStringLiteral("andreivinca.github.io"));
    QCoreApplication::setApplicationVersion(QStringLiteral(NOTE_NOTE_VERSION));
}

namespace {

// Asks the instance already running to show its window, and says whether it
// did: it answers once it has, and one on its way out answers nothing.
bool activateRunningInstance(const QString &path)
{
    QLocalSocket client;
    client.connectToServer(path);
    return client.waitForConnected(2000) && client.waitForReadyRead(2000)
        && client.read(1) == QByteArrayLiteral("1");
}

}

int runNoteNote(QGuiApplication &app, const Launch &launch)
{
    QGuiApplication::setDesktopFileName(QStringLiteral("io.github.andreivinca.note-note"));
    QGuiApplication::setQuitOnLastWindowClosed(false);
    QImageReader::setAllocationLimit(128);
    QQuickStyle::setStyle(QStringLiteral("Basic"));

    DesktopRuntime runtime;
    const int symbols = QFontDatabase::addApplicationFont(launch.dataDir + QStringLiteral("/assets/fonts/nerd-symbols/SymbolsNerdFont-Regular.ttf"));
    for (const QString &family : QFontDatabase::applicationFontFamilies(symbols)) {
        QFontDatabase::addApplicationFallbackFontFamily(QChar::Script_Common, family);
    }
    QLocalServer server;
    const QString instancePath = QStandardPaths::writableLocation(QStandardPaths::RuntimeLocation) + QStringLiteral("/note-note");
    QLockFile instanceLock(instancePath + QStringLiteral(".lock"));
    if (launch.singleInstance) {
        if (!instanceLock.tryLock()) {
            // Another instance runs, and shows its window. One on its way out
            // does not: this launch waits for it to exit, and the lock with
            // it, and then runs itself.
            if (activateRunningInstance(instancePath)) {
                return 0;
            }
            if (!instanceLock.tryLock(10000)) {
                qCritical("The running Note Note instance could not be reached.");
                return 1;
            }
        }
        QLocalServer::removeServer(instancePath);
        server.setSocketOptions(QLocalServer::UserAccessOption);
        if (!server.listen(instancePath)) {
            qCritical("Could not create the application activation socket.");
            return 1;
        }
        QObject::connect(&server, &QLocalServer::newConnection, &runtime, [&server, &runtime]() {
            while (server.hasPendingConnections()) {
                QLocalSocket *connection = server.nextPendingConnection();
                // The answer the launch waits for: its window is shown.
                if (runtime.activate()) {
                    connection->write("1");
                    connection->flush();
                }
                connection->disconnectFromServer();
                connection->deleteLater();
            }
        });
    }

    DesktopTheme theme;
    qmlRegisterSingletonInstance("NoteNote.Native", 1, 0, "SystemTheme", &theme);
    qmlRegisterType<ProcessBackend>("NoteNote.Native", 1, 0, "NativeProcess");
    qmlRegisterType<TextBlocks>("NoteNote.Native", 1, 0, "TextBlocks");
    qmlRegisterSingletonInstance("NoteNote.Native", 1, 0, "Desktop", &runtime);
    QQmlApplicationEngine engine;
    engine.addImportPath(launch.dataDir + QStringLiteral("/extensions"));
    QObject::connect(&engine, &QQmlApplicationEngine::exit, &app, &QCoreApplication::exit);
    QObject::connect(&engine, &QQmlApplicationEngine::objectCreationFailed, &app, []() {
        QCoreApplication::exit(1);
    }, Qt::QueuedConnection);
    engine.load(QUrl::fromLocalFile(QFileInfo(launch.entry).absoluteFilePath()));
    const int result = app.exec();
    // A launch from here on finds no socket and waits for the lock, which
    // goes with this process.
    server.close();
    qDeleteAll(engine.rootObjects());
    // Only cancelled transports are reparented to the application. Reap any
    // final acknowledgements after the UI event loop has already stopped.
    for (QProcess *process : app.findChildren<QProcess *>(Qt::FindDirectChildrenOnly)) {
        if (process->state() != QProcess::NotRunning) {
            process->waitForFinished(1000);
        }
    }
    return result;
}
