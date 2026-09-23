#pragma once

#include <QString>

class QGuiApplication;

// The application as both executables run it: the product (main.cpp), with
// its own window and one instance per user, and the test harness
// (tests/harness_main.cpp), with a QML file of the test's choosing over the
// same runtime, types and resources. What differs is said here; everything
// else is one function.
struct Launch {
    QString dataDir;        // the resources: Workspace.qml and everything beside it
    QString entry;          // the QML file to load
    bool singleInstance;    // take the activation lock and socket
};

// Where the resources are: as requested, else next to the executable (an
// archive keeps that when it is moved), else the configured prefix (an
// executable copied elsewhere). Empty when no candidate holds Workspace.qml.
QString resolveDataDir(const QString &requested);

int runNoteNote(QGuiApplication &app, const Launch &launch);
