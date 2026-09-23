import "../platform"
import "../processes"
import QtQuick

// The clipboard, for pasting into a note: its image, and its text for the
// plain paste.
//
// The host reads the system clipboard (Platform.backend.readClipboard:
// QClipboard in the native host, wl-paste in the Omarchy host); the policy
// is here. A picture is staged and scaled by clipboard.py, the same for
// both hosts, and pasted files stay in the cache until the note is saved
// into its provider.
Item {
  id: root

  readonly property string dir: Platform.localPath(Qt.resolvedUrl(".")).replace(/\/$/, "")
  readonly property string script: dir + "/clipboard.py"
  readonly property string stagingDir: Platform.pasteDir

  // Every answer below is callback(value, error): the value, or its empty
  // form when the clipboard holds nothing of the kind — the ordinary case,
  // not a failure — and `error` set, in the user's words, when the
  // clipboard could not be read or the picture could not be staged, for
  // the editor to say rather than paste nothing in silence.

  // Does the clipboard hold a picture?  callback(true|false)
  // Cheap: it only asks the compositor what types are on offer.
  function hasImage(callback) {
    Platform.backend.readClipboard("types", function(result) { callback(!!(result && result.image)) })
  }

  // The clipboard's image, written into the staging directory:
  // callback({ path, mime, bytes }), or callback(null) with no image on offer.
  function takeImage(callback) {
    Platform.backend.readClipboard("image", function(result) {
      if (!result || result.error) {
        callback(null, result ? result.error : "the clipboard could not be read")
        return
      }
      if (!result.data) {
        callback(null)
        return
      }
      runner.run({ command: ["python3", root.script, "stage", root.stagingDir],
                   payload: JSON.stringify(result), timeoutMs: 60000 },
                 function(staged) {
        if (!staged || staged.error || !staged.path) {
          callback(null, staged && staged.error ? staged.error : "the picture could not be staged")
          return
        }
        callback(staged)
      })
    })
  }

  // The clipboard's text, whatever flavour it is on offer in:
  // callback(string), "" when the clipboard holds no text at all.
  function takeText(callback) {
    Platform.backend.readClipboard("text", function(result) { root.answer(callback, result, "text") })
  }

  // The clipboard's HTML flavour, for the editor's own paste (see
  // clipboard.py, clipboard_html).  callback(string) — "" when none is on
  // offer, which sends the paste down Qt's own path.
  function takeHtml(callback) {
    Platform.backend.readClipboard("html", function(result) { root.answer(callback, result, "html") })
  }

  function answer(callback, result, key) {
    if (!result || result.error) {
      callback("", result ? result.error : "the clipboard could not be read")
      return
    }
    callback(result[key] || "")
  }

  ProcessRunner { id: runner }
}
