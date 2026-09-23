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
  // The largest answer clipboard.py gives: an image of MAX_CLIPBOARD bytes
  // as base64 in its JSON envelope — more than a process may print by
  // default. The number is the staging policy's (services/clipboard/
  // clipboard.py, MAX_IMAGE_ANSWER), pinned there by tests/test_regressions.py.
  readonly property int clipboardAnswerBytes: 56 * 1024 * 1024
  // The system clipboard, one flavour at a time — "types", "text", "html"
  // or "image" — answered the way the native host answers it, so the
  // clipboard service (services/clipboard) has one caller's view of both.
  function readClipboard(format, callback) {
    processes.run({ command: ["python3", backend.dir + "/clipboard.py", format], timeoutMs: 60000,
                    maxOutputBytes: backend.clipboardAnswerBytes }, callback)
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
