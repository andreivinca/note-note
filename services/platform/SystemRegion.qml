import QtQuick
import "../processes"

// IANA timezone data identifies the region even when the UI uses English.
Item {
  id: region
  readonly property string script: Platform.localPath(Qt.resolvedUrl("region.py"))
  property string timeZone: ""
  property string countryCode: ""
  property bool ready: false
  property string error: ""
  property bool started: false
  ProcessRunner { id: runner }

  function detect() {
    if (!Platform.backend || started) {
      return
    }
    started = true
    runner.run({ command: ["python3", region.script], timeoutMs: 5000 }, function(result) {
      region.timeZone = result.timeZone || ""
      region.countryCode = result.countryCode || ""
      region.ready = true
      region.error = result.error || ""
      if (result.error) {
        console.warn("note-note: could not detect the system timezone:", result.error)
      }
    })
  }
  Connections {
    target: Platform
    function onBackendChanged() {
      region.detect()
    }
  }
  Component.onCompleted: region.detect()
}
