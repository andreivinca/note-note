import QtQuick
import "app" as App
import "app/hosts/standalone" as Native

Window {
  visible: true
  width: 800
  height: 600
  Native.Backend { id: backend }
  App.Workspace { id: workspace; anchors.fill: parent }
  Component.onCompleted: {
    backend.install()
    workspace.initialize()
    workspace.open("{}")
  }
  Timer {
    property int attempts: 0
    interval: 50
    repeat: true
    running: true
    onTriggered: {
      attempts++
      if (attempts > 200) {
        console.error("FAIL! theme startup did not settle")
        Qt.exit(1)
        return
      }
      if (!workspace.providersLoaded || !workspace.themes.settled) {
        return
      }
      var id = backend.env("NOTE_NOTE_EXPECT_THEME")
      var color = backend.env("NOTE_NOTE_EXPECT_COLOR")
      var expected = color || workspace.themes.system["surface.background"]
      if (workspace.themes.committedThemeId !== id || workspace.themes.colors["surface.background"] !== expected) {
        return
      }
      console.error("<<<RESTART_DONE>>>")
      Qt.quit()
    }
  }
}
