import QtQuick
import "../platform"
import "../processes"
import "../../design/resolve.js" as Resolve
import "system.js" as SystemTheme

// The theme files that were read and found valid, by theme ID. Reading is a
// helper's work (theme.py); which tokens a file may set is sent along.
Item {
  id: catalog
  property var descriptors: []
  property var entries: ({})
  property var diagnostics: []
  property int generation: 0
  ProcessRunner { id: runner }

  function publish(result) {
    var entries = {}
    result.themes.forEach(function(entry) {
      entries[entry.descriptor.id] = entry
    })
    result.diagnostics.forEach(function(diagnostic) {
      console.warn("note-note themes:", diagnostic.id, diagnostic.message)
    })
    catalog.diagnostics = result.diagnostics
    catalog.entries = entries
  }

  function load(items, callback) {
    var ticket = ++catalog.generation
    return runner.run({ command: ["python3", Platform.localPath(Qt.resolvedUrl("theme.py"))],
      timeoutMs: 15000, maxOutputBytes: 12 * 1024 * 1024,
      payload: JSON.stringify({ descriptors: items, tokens: Resolve.validationTable() }) }, function(result) {
      if (ticket !== catalog.generation) {
        callback({ cancelled: true, error: "Theme catalog request was superseded." })
        return
      }
      if (!result.error) {
        catalog.publish(result)
      }
      callback(result)
    })
  }

  function initialize(id, callback) {
    return catalog.load(catalog.descriptors.filter(function(item) {
      return item.id === id || item.id === SystemTheme.themeId
    }), callback)
  }

  function refresh(callback) {
    return catalog.load(catalog.descriptors, callback)
  }

  function list() {
    return Object.keys(catalog.entries).map(function(id) {
      var entry = catalog.entries[id]
      return { id: id, label: entry.value.name, detail: entry.descriptor.packageName }
    }).sort(function(a, b) {
      if (a.id === SystemTheme.themeId) {
        return -1
      }
      if (b.id === SystemTheme.themeId) {
        return 1
      }
      return a.label.localeCompare(b.label) || a.id.localeCompare(b.id)
    })
  }
}
