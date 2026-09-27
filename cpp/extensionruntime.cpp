#include "extensionruntime.h"

#include <QFileInfo>
#include <QQmlEngine>

bool ExtensionRuntime::install(const QUrl &directory)
{
    QQmlEngine *engine = qmlEngine(this);
    if (!engine || !directory.isLocalFile() || !QFileInfo(directory.toLocalFile()).isDir()) {
        return false;
    }
    engine->addImportPath(directory.toLocalFile());
    return true;
}
