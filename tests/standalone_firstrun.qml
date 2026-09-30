import QtQuick
import "app/hosts/standalone" as Native

// A first run: no config file yet. The workspace writes one once the
// providers have recorded their defaults (Workspace.loadProviders), and the
// selftest reads the file back.
Native.Main {
  id: window
  property bool starterSelected: false
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
      var local = workspace.providerById("local")
      if (!local || !local.notes.length) {
        return
      }
      if (workspace.tabs[0].key !== "local/Notes" || workspace.activeKey() !== "local/Notes"
          || local.notes[0].title !== "Getting started") {
        console.error("FAIL! First run must show the local Notes tab and Getting started note")
        Qt.exit(1)
        return
      }
      if (!window.starterSelected) {
        window.starterSelected = true
        workspace.choosePath(local.notes[0].path)
        return
      }
      if (workspace.currentPath !== local.notes[0].path || workspace.loadingNote) {
        return
      }
      if (workspace.loadFailed) {
        console.error("FAIL! The Getting started note must load")
        Qt.exit(1)
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
