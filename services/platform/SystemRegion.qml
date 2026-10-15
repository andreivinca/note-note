import QtQuick
import "../processes"

// IANA timezone data identifies the region even when the UI uses English.
// It is detected the first time something asks for it, not at startup.
Item {
  id: region
  readonly property string script: Platform.localPath(Qt.resolvedUrl("region.py"))
  property string timeZone: ""
  property string countryCode: ""
  property bool ready: false
  property string error: ""
  property bool started: false
  property var waiting: []
  ProcessRunner { id: runner }

  // Calls `callback` once the region is known: at once when it is, else
  // when the detection this starts, or one already running, answers.
  function whenReady(callback) {
    if (region.ready) {
      callback()
      return
    }
    region.waiting = region.waiting.concat([callback])
    if (region.started) {
      return
    }
    region.started = true
    runner.run({ command: ["python3", region.script], timeoutMs: 5000 }, function(result) {
      region.timeZone = result.timeZone || ""
      region.countryCode = result.countryCode || ""
      region.ready = true
      region.error = result.error || ""
      if (result.error) {
        console.warn("note-note: could not detect the system timezone:", result.error)
      }
      var waiting = region.waiting
      region.waiting = []
      waiting.forEach(function(callback) {
        callback()
      })
    })
  }
}
