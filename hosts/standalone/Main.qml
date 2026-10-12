import QtQuick
import QtQuick.Controls
import NoteNote.Native
import "../.." as App
import "../../design"

ApplicationWindow {
  id: window
  title: "Note Note"
  width: 1120
  height: 760
  minimumWidth: 760
  minimumHeight: 480
  // On screen while the workspace is open, as the Omarchy host's windows
  // are: a close puts the window away at once, and the process stays until
  // what the workspace accepted has answered (requestClose). Shown first
  // once the theme the settings name is known, found or not, so the window
  // never opens in one theme and changes to another.
  visible: workspace.opened && workspace.themes.settled
  color: workspace.background
  palette: ControlPalette {}

  Backend {
    id: backend
  }
  App.Workspace {
    id: workspace
    objectName: "workspace"
    anchors.fill: parent
    onDismissRequested: requestClose()
    onReadyToClose: {
      // The providers are going: a launch from here on is not shown here,
      // and waits for this process to exit instead.
      Desktop.leave()
      workspace.releaseProviders()
      // Exits rather than quits: a quit first asks the window to close, and
      // a close of this window is the workspace's, which has just finished.
      Qt.callLater(function() {
        Qt.exit(0)
      })
    }
  }
  // The workspace closes, not the window: its close puts the window away
  // through `visible`.
  onClosing: function(event) {
    event.accepted = false
    workspace.requestClose()
  }
  Connections {
    target: Desktop
    // Another launch. Opening the workspace ends a close still writing in
    // the background, and the window comes forward.
    function onActivationRequested() {
      if (!workspace.opened) {
        workspace.open("{}")
      }
      if (window.visibility === Window.Minimized) {
        window.showNormal()
      }
      window.raise()
      window.requestActivate()
    }
  }
  Component.onCompleted: {
    backend.install()
    workspace.initialize()
    workspace.open("{}")
  }
}
