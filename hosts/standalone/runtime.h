#pragma once

#include <QObject>
#include <QVariantMap>

class DesktopRuntime : public QObject
{
    Q_OBJECT

public:
    explicit DesktopRuntime(QObject *parent = nullptr) : QObject(parent) {}
    Q_INVOKABLE QString env(const QString &name) const;
    Q_INVOKABLE void copyText(const QString &text);
    Q_INVOKABLE QVariantMap clipboard(const QString &format) const;
    // The application is on its way out: from now on another launch is not
    // shown here, and waits for this process to exit instead.
    Q_INVOKABLE void leave();
    // Another launch asks for the window; says whether it was shown, which
    // it never is once the application has left.
    bool activate();

signals:
    void activationRequested();

private:
    bool m_leaving = false;
};
