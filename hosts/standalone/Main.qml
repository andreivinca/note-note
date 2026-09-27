import QtQuick
import QtQuick.Controls
import NoteNote.Native
import "../.." as App
import "../../design"

ApplicationWindow {
  id: window
  property bool closeAccepted: false
  title: "Note Note"
  width: 1120
  height: 760
  minimumWidth: 760
  minimumHeight: 480
  visible: true
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
      workspace.releaseProviders()
      window.closeAccepted = true
      window.close()
      Qt.callLater(function() {
        Qt.quit()
      })
    }
  }
  onClosing: function(event) {
    event.accepted = window.closeAccepted
    if (!event.accepted) {
      workspace.requestClose()
    }
  }
  Connections {
    target: Desktop
    function onActivationRequested() {
      if (window.visibility === Window.Minimized) {
        window.showNormal()
      } else {
        window.show()
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
