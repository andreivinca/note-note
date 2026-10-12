import QtQuick
import NoteNote.Native
import "app/hosts/standalone" as Native
import "app/plugins/org.note-note.onenote" as OneNote
import "app/services/platform"

// Use the real OneNote queue and process ownership with a slow synthetic
// read and delayed writes. No account or network request is involved. A
// close puts the window away at once. Another launch while its write is
// still out brings the window back and ends that close; the next close lets
// the process go once its write is done, the slow read notwithstanding.
Native.Main {
  id: window
  property var workspaceUnderTest: null
  property var providerUnderTest: null
  // "" until the first close, "reopened" once another launch has ended it,
  // "loaded" with the read and the last write out, "draining" once the close
  // the process ends with was asked for.
  property string phase: ""
  property int writesDone: 0
  property bool hiddenBeforeWrite: false

  Component {
    id: providerComponent
    OneNote.Provider {
      function runProcess(runner, args, payload, callback) {
        var delay = args[0] === "update" ? "1" : "30"
        return runner.run({ command: ["python3", "-c", "import time; time.sleep(" + delay + "); print('{}')"] }, callback)
      }
    }
  }

  function fail(message) {
    console.error("FAIL! " + message)
    Qt.exit(1)
  }

  function enqueueWrite() {
    var provider = window.providerUnderTest
    provider.rq.enqueue({ key: "accepted-write", owner: provider, flush: true }, function(ctx) {
      provider.runScript(["update"], "", ctx)
    }, function(result) {
      if (result && !result.error) {
        window.writesDone++
      }
    })
  }

  // The first close, ended by another launch while its write is still out.
  function reopenCase(workspace) {
    var provider = providerComponent.createObject(workspace, {
      host: workspace, services: { requests: workspace.services.requests }
    })
    window.providerUnderTest = provider
    workspace.providers = workspace.providers.concat([provider])
    window.enqueueWrite()
    window.close()
    if (window.visible || !workspace.closing) {
      window.fail("a close must put the window away at once")
      return
    }
    Desktop.activationRequested()
    if (!window.visible || workspace.closing) {
      window.fail("another launch must bring the window back and end the close")
      return
    }
    window.phase = "reopened"
  }

  // A slow read and one more write for the close the process ends with.
  function loadCase() {
    var provider = window.providerUnderTest
    provider.rq.enqueue({ key: "slow-read", owner: provider, priority: 1 }, function(ctx) {
      provider.runScript(["list"], "", ctx)
    }, function() {})
    window.enqueueWrite()
    window.phase = "loaded"
  }

  function closeCase() {
    window.phase = "draining"
    if (Platform.env("NOTE_NOTE_TEST_WM_CLOSE") === "1") {
      console.error("<<<WM_CLOSE_READY>>>")
    } else {
      window.close()
    }
  }

  onVisibleChanged: {
    if (!window.visible && window.phase === "draining" && window.writesDone === 1) {
      window.hiddenBeforeWrite = true
    }
  }

  Connections {
    target: window.workspaceUnderTest
    function onReadyToClose() {
      if (window.phase !== "draining") {
        window.fail("a close that another launch ended must not end the process")
        return
      }
      if (!window.hiddenBeforeWrite || window.writesDone !== 2 || !window.providerUnderTest.busy) {
        window.fail("a close must put the window away at once and drain the write while the slow read is still active")
        return
      }
      console.error("<<<CLOSE_DONE>>>")
    }
  }

  Timer {
    interval: 50
    running: true
    repeat: true
    onTriggered: {
      if (!window.workspaceUnderTest) {
        window.workspaceUnderTest = window.contentItem.children.find(function(child) {
          return child.objectName === "workspace"
        })
      }
      var workspace = window.workspaceUnderTest
      if (!workspace || !workspace.providersLoaded) {
        return
      }
      if (window.phase === "" && window.visible) {
        window.reopenCase(workspace)
      } else if (window.phase === "reopened" && window.writesDone === 1) {
        window.loadCase()
      } else if (window.phase === "loaded" && window.providerUnderTest.busy) {
        window.closeCase()
      }
    }
  }

  Timer {
    interval: 8000
    running: true
    onTriggered: {
      window.fail("the process did not exit once its write was done: phase " + window.phase)
    }
  }
}
