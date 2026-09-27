#pragma once

#include <QObject>
#include <QUrl>
#include <QtQml/qqmlregistration.h>

// The shell shares a QML engine: register only the application's public module
// root, without changing the process environment or any desktop palette.
class ExtensionRuntime : public QObject
{
    Q_OBJECT
    QML_ELEMENT
public:
    using QObject::QObject;
    Q_INVOKABLE bool install(const QUrl &directory);
};
