import QtQuick
import "../platform"
import "../processes"

Item {
  id: catalog
  property var commands: []
  property var keybindings: []
  property var themes: []
  property var providers: []
  property var diagnostics: []
  // What went wrong, as opposed to what is merely switched off.
  readonly property var problems: diagnostics.filter(function(diagnostic) {
    return diagnostic.level !== "note"
  })
  // One line for a status message or the palette's foot.
  readonly property string problemSummary: {
    if (!problems.length) {
      return ""
    }
    var first = problems[0]
    var more = problems.length > 1 ? " (and " + (problems.length - 1) + " more)" : ""
    return catalog.nameOf(first) + ": " + first.message + more
  }
  property bool ready: false
  readonly property string script: Platform.localPath(Qt.resolvedUrl("manifest.py"))
  signal loaded()
  ProcessRunner { id: runner }

  function nameOf(diagnostic) {
    return diagnostic.packageId || String(diagnostic.path || "").split("/").pop() || "the plugin catalog"
  }

  function load(settings) {
    runner.run({ command: ["python3", catalog.script], timeoutMs: 15000, maxOutputBytes: 8 * 1024 * 1024,
      payload: JSON.stringify({ builtinRoot: Platform.localPath(Qt.resolvedUrl("../../plugins")),
        userRoot: Platform.configDir + "/plugins", themesRoot: Platform.configDir + "/themes",
        legacyRoot: Platform.providersDir, settings: settings }) }, function(result) {
      catalog.commands = result.commands || []
      catalog.keybindings = result.keybindings || []
      catalog.themes = result.themes || []
      catalog.providers = result.providers || []
      catalog.diagnostics = result.error ? [{ stage: "discovery", level: "error", message: result.error }]
        : result.diagnostics || []
      catalog.diagnostics.forEach(function(diagnostic) {
        console.warn("note-note plugins:", catalog.nameOf(diagnostic), diagnostic.message)
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
