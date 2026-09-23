import QtQuick
import Quickshell
import "../../services/platform"
import "../../services/processes"
import "../../design" as Design
import qs.Commons as Shell

// The Omarchy shell as the workspace's host: Quickshell processes, storage
// under the shell's own directories, and the clipboard through wl-paste.
Item {
  id: backend
  readonly property string storageName: "omarchy"
  readonly property string configName: "omarchy/note-note"
  readonly property string accountConfig: "omarchy/note-note.json"
  // The native text inspector, when the user has built it (cpp/build.sh).
  readonly property url textInspectorUrl: Qt.resolvedUrl("TextInspector.qml")
  readonly property Component processComponent: Component {
    ProcessBackend {}
  }
  readonly property string dir: Platform.localPath(Qt.resolvedUrl(".")).replace(/\/$/, "")
  function env(name) {
    return Quickshell.env(name)
  }
  function copyText(text) {
    processes.run({ command: ["wl-copy"], payload: text, raw: true }, function(result) {
      if (result.error) {
        console.warn("note-note: could not copy to the clipboard")
      }
    })
  }
  // The system clipboard, one flavour at a time — "types", "text", "html"
  // or "image" — answered the way the native host answers it, so the
  // clipboard service (services/clipboard) has one caller's view of both.
  function readClipboard(format, callback) {
    processes.run({ command: ["python3", backend.dir + "/clipboard.py", format], timeoutMs: 60000 }, callback)
  }
  ProcessRunner {
    id: processes
  }
  function install() {
    Platform.backend = backend
    Design.Style.source = Shell.Style
    Design.Color.source = Shell.Color
  }
}
