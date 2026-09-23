import QtQuick
import "app/hosts/standalone" as Native

// A first run: no config file yet. The workspace writes one once the
// providers have recorded their defaults (Workspace.loadProviders), and the
// selftest reads the file back.
Native.Main {
  id: window
  Timer {
    id: startup
    interval: 100
    running: true
    repeat: true
    onTriggered: {
      var workspace = window.contentItem.children.find(function(child) {
        return child.objectName === "workspace"
      })
      if (!workspace || !workspace.providersLoaded || workspace.configUnwritten) {
        return
      }
      startup.stop()
      finish.start()
    }
  }
  Timer {
    id: finish
    interval: 1000
    onTriggered: {
      console.error("<<<FIRSTRUN_DONE>>>")
      window.close()
    }
  }
}
