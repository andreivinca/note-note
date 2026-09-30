import QtQuick
import "../../design"
import "../../design/resolve.js" as Resolve
import "system.js" as SystemTheme

// Which theme is in force, and what it makes of every colour. The selection
// is the settings' to keep; a preview is a look that ends with its session.
Item {
  id: theme
  property var catalog: null
  property bool supportsCustom: false
  property string committedThemeId: SystemTheme.themeId
  property var committedColors: null
  property string previewId: ""
  property var previewSession: null
  property int generation: 0
  // Whether the theme the settings name has been looked for, found or not.
  // Until then the colours are the system's.
  property bool settled: false
  // Counts the palettes published, so one can be told from the next.
  property int revision: 0
  // Every token, always: a palette is replaced whole, never filled in.
  property var colors: Color.baseline
  property var diagnostics: []
  readonly property var system: Color.baseline
  readonly property var candidate: previewId && catalog.entries[previewId]
    ? catalog.entries[previewId].value.colors : committedColors
  readonly property bool followsSystem: !candidate || Object.keys(candidate).every(function(key) {
    return candidate[key] === "system"
  })
  readonly property var resolved: candidate ? Resolve.resolve(system, candidate) : system
  onResolvedChanged: theme.publish()
  Component.onCompleted: theme.publish()
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

  function publish() {
    if (theme.revision > 0 && JSON.stringify(theme.resolved) === JSON.stringify(theme.colors)) {
      return
    }
    theme.colors = theme.resolved
    theme.revision++
    theme.diagnostics = Resolve.contrastDiagnostics(theme.colors)
  }

  // A host without native display styling cannot recolour a note's own
  // marks, so it keeps the theme that follows the desktop.
  function supports(id) {
    return theme.supportsCustom || id === SystemTheme.themeId
  }

  function adoptCommitted() {
    var entry = catalog.entries[theme.committedThemeId]
    theme.committedColors = entry && theme.supports(theme.committedThemeId) ? entry.value.colors : null
  }

  // The themes as a picker lists them: which one is in force, and which
  // this host cannot show.
  function choices() {
    return catalog.list().map(function(item) {
      var supported = theme.supports(item.id)
      return Object.assign({}, item, {
        detail: item.detail + (item.id === theme.committedThemeId ? " · Current" : ""),
        enabled: supported,
        reason: supported ? "" : "Custom themes require the native display helper. Build it and restart."
      })
    })
  }

  function setCommitted(id) {
    theme.committedThemeId = id
    var ticket = ++theme.generation
    function install(result) {
      if (ticket !== theme.generation) {
        return
      }
      theme.adoptCommitted()
      theme.settled = true
      if (result.error) {
        console.warn("note-note themes:", id, "could not be loaded:", result.error)
      } else if (!catalog.entries[id]) {
        console.warn("note-note themes:", id, "unavailable; using System for this session")
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
        var shown = !!id && !!catalog.entries[id] && theme.supports(id)
        theme.previewId = shown ? id : ""
        return !id || shown
      },
      cancel: function() {
        if (theme.previewSession === session) {
          theme.previewId = ""
          theme.previewSession = null
        }
      },
      // The selection is the settings' to keep; the theme in force follows
      // them. Ending the preview here only hands the look over without a gap.
      commit: function(id) {
        if (theme.previewSession !== session) {
          return
        }
        if (theme.committedThemeId !== id) {
          theme.setCommitted(id)
        }
        session.cancel()
      }
    }
    theme.previewSession = session
    return session
  }
}
