import QtQuick
import "../../design"
import "resolve.js" as Resolve

Item {
  id: theme
  property var catalog: null
  property bool supportsCustom: false
  property string committedThemeId: "org.note-note.appearance/system"
  property var committedColors: null
  property string previewId: ""
  property var previewSession: null
  property int generation: 0
  property int revision: 0
  property var colors: ({})
  property var diagnostics: []
  function adoptCommitted() {
    var entry = catalog.entries[theme.committedThemeId]
    var supported = theme.supportsCustom || theme.committedThemeId === "org.note-note.appearance/system"
    theme.committedColors = entry && supported ? entry.value.colors : null
  }
  onSupportsCustomChanged: {
    if (catalog) {
      theme.adoptCommitted()
    }
  }
  Connections {
    target: theme.catalog
    function onEntriesChanged() {
      theme.adoptCommitted()
      if (theme.previewId && !theme.catalog.entries[theme.previewId]) {
        theme.previewId = ""
      }
    }
  }
  readonly property var system: Resolve.baseline(catalog ? catalog.specification : {}, Color.raw, Style.source)
  readonly property var candidate: previewId && catalog.entries[previewId] ? catalog.entries[previewId].value.colors : committedColors
  readonly property var resolved: candidate ? Resolve.resolve(catalog.specification, system, candidate) : system
  onResolvedChanged: {
    if (JSON.stringify(resolved) !== JSON.stringify(colors)) {
      colors = resolved
      revision++
      diagnostics = Resolve.contrastDiagnostics(catalog.specification, colors)
    }
  }

  function setCommitted(id, callback) {
    theme.committedThemeId = id
    var ticket = ++theme.generation
    function install(result) {
      if (ticket !== theme.generation) {
        return
      }
      var entry = catalog.entries[id]
      theme.adoptCommitted()
      if (!entry) {
        console.warn("note-note themes:", id, "unavailable; using System for this session")
      }
      if (callback) {
        callback(result)
      }
    }
    if (catalog.entries[id]) {
      install({ ok: true })
    } else {
      catalog.initialize(id, install)
    }
  }

  function beginPreview() {
    if (theme.previewSession) {
      theme.previewSession.cancel()
    }
    var session = {
      preview: function(id) {
        if (theme.previewSession !== session) {
          return false
        }
        theme.previewId = id && catalog.entries[id] ? id : ""
        return !id || !!catalog.entries[id]
      },
      cancel: function() {
        if (theme.previewSession === session) {
          theme.previewId = ""
          theme.previewSession = null
        }
      },
      commit: function(id) {
        if (theme.previewSession !== session) {
          return
        }
        theme.setCommitted(id)
        session.cancel()
      }
    }
    theme.previewSession = session
    return session
  }
}
