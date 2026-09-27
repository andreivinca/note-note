import QtQuick
import "../platform"
import "../processes"

Item {
  id: catalog
  property var commands: []
  property var keybindings: []
  property var themes: []
  property var providers: []
  property var packages: []
  property var diagnostics: []
  property bool ready: false
  readonly property string script: Platform.localPath(Qt.resolvedUrl("manifest.py"))
  signal loaded()
  ProcessRunner { id: runner }

  function load(settings) {
    runner.run({ command: ["python3", catalog.script], timeoutMs: 15000, maxOutputBytes: 8 * 1024 * 1024,
      payload: JSON.stringify({ builtinRoot: Platform.localPath(Qt.resolvedUrl("../../plugins")),
        userRoot: Platform.configDir + "/plugins", themesRoot: Platform.configDir + "/themes",
        legacyRoot: Platform.providersDir, settings: settings }) }, function(result) {
      catalog.commands = result.commands || []
      catalog.keybindings = result.keybindings || []
      catalog.themes = result.themes || []
      catalog.providers = result.providers || []
      catalog.packages = result.packages || []
      catalog.diagnostics = result.diagnostics || []
      if (result.error) {
        catalog.diagnostics = [{ stage: "discovery", message: result.error }]
      }
      catalog.diagnostics.forEach(function(diagnostic) {
        console.warn("note-note plugins:", diagnostic.packageId || diagnostic.path || "catalog", diagnostic.message)
      })
      catalog.ready = true
      catalog.loaded()
    })
  }

  function readResource(descriptor, path, json, callback) {
    return runner.run({ command: ["python3", catalog.script], timeoutMs: 10000, maxOutputBytes: 2 * 1024 * 1024,
      payload: JSON.stringify({ operation: "resource", root: descriptor.root, path: path, json: json }) }, callback)
  }
}
