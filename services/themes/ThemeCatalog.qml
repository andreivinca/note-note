import QtQuick
import "../platform"
import "../processes"

Item {
  id: catalog
  property var descriptors: []
  property var specification: ({})
  property var entries: ({})
  property var diagnostics: []
  property int generation: 0
  ProcessRunner { id: runner }

  function load(items, callback) {
    var ticket = ++catalog.generation
    return runner.run({ command: ["python3", Platform.localPath(Qt.resolvedUrl("theme.py"))],
      timeoutMs: 15000, maxOutputBytes: 12 * 1024 * 1024,
      payload: JSON.stringify({ descriptors: items }) }, function(result) {
      if (ticket !== catalog.generation) {
        callback({ cancelled: true, error: "Theme catalog request was superseded." })
        return
      }
      if (!result.error) {
        catalog.specification = result.specification
        var entries = {}
        result.themes.forEach(function(entry) {
          entries[entry.descriptor.id] = entry
        })
        catalog.entries = entries
        catalog.diagnostics = result.diagnostics
        result.diagnostics.forEach(function(diagnostic) {
          console.warn("note-note themes:", diagnostic.id, diagnostic.message)
        })
      }
      callback(result)
    })
  }

  function initialize(id, callback) {
    return catalog.load(catalog.descriptors.filter(function(item) {
      return item.id === id || item.id === "org.note-note.appearance/system"
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
      if (a.id === "org.note-note.appearance/system") {
        return -1
      }
      if (b.id === "org.note-note.appearance/system") {
        return 1
      }
      return a.label.localeCompare(b.label) || a.id.localeCompare(b.id)
    })
  }
}
