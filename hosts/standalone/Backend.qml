import QtQuick
import NoteNote.Native
import "../../services/platform"
import "../../design" as Design

// The desktop executable as the workspace's host: QProcess, storage under
// the application's own directories, and the clipboard through QClipboard.
Item {
  id: backend
  readonly property string storageName: "notenote"
  readonly property string configName: "notenote"
  readonly property string accountConfig: "notenote/accounts.json"
  readonly property url textInspectorUrl: Qt.resolvedUrl("TextInspector.qml")
  readonly property Component processComponent: Component {
    NativeProcess {}
  }
  function env(name) {
    return Desktop.env(name)
  }
  function copyText(text) {
    Desktop.copyText(text)
  }
  // The system clipboard, one flavour at a time — "types", "text", "html"
  // or "image" — read here and now; the callback keeps the same shape the
  // Omarchy host answers through a process.
  function readClipboard(format, callback) {
    callback(Desktop.clipboard(format))
  }
  function install() {
    Design.Color.systemTheme = SystemTheme
    Platform.backend = backend
  }
}
