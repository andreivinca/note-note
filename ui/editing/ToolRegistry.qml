import QtQuick
import Qt.labs.folderlistmodel
import "../../services/shortcuts/stroke.js" as Stroke
import "ToolbarSettings.js" as ToolbarSettings

Item {
  id: registry
  required property var editor
  required property var keybindings
  // The application's own tools, one QML file each.
  property url directory: Qt.resolvedUrl("../tools")
  // The tools plugin packages contribute (services/extensions/manifest.py),
  // or null while the plugin catalog is still being read: the registry
  // loads once it knows every tool.
  property var contributions: []
  property var layout: ToolbarSettings.defaults()
  readonly property alias ready: registryState.ready
  // Whether the tools on hand are the ones the sources name now.
  readonly property bool upToDate: registryState.ready && registryState.loadedDirectory === directory
    && registryState.loadedContributions === contributions
  readonly property alias errors: registryState.errors
  readonly property alias tools: registryState.tools
  readonly property bool panelOpen: actions.some(function(tool) {
    return tool.panelOpen
  })
  readonly property var actions: tools.reduce(function(result, tool) {
    return result.concat(registry.definitions(tool))
  }, [])
  readonly property var placement: ToolbarSettings.resolve(layout, tools)
  readonly property var toolbarGroups: {
    var groups = []
    for (var i = 0; i < placement.toolbar.length; i++) {
      var entry = placement.toolbar[i]
      var group = groups[groups.length - 1]
      if (!group || group.id !== entry.group) {
        group = { id: entry.group, tools: [] }
        groups.push(group)
      }
      group.tools.push(entry.tool)
    }
    return groups
  }
  readonly property var topLevelTools: placement.toolbar.map(function(entry) {
    return entry.tool
  })
  readonly property var toolbarTools: topLevelTools.filter(function(tool) {
    return registry.isVisible(tool)
  })
  onLayoutChanged: {
    if (ready) {
      closePanels()
    }
  }
  onContributionsChanged: reload.restart()

  QtObject {
    id: registryState
    property bool ready: false
    property url loadedDirectory: ""
    property var loadedContributions: null
    property var errors: []
    property var tools: []
  }

  FolderListModel {
    id: files
    // The directory the rows are of. `folder` changes at once, while the
    // model goes on listing the previous one, still Ready, until it has
    // read the new one and turns Ready again.
    property url listed: ""
    folder: registry.directory
    nameFilters: ["*.qml"]
    showDirs: false
    showDotAndDotDot: false
    sortField: FolderListModel.Name
    onStatusChanged: {
      if (status === FolderListModel.Ready) {
        listed = folder
        reload.restart()
      }
    }
    onCountChanged: reload.restart()
  }

  Timer {
    id: reload
    interval: 0
    onTriggered: {
      if (files.status === FolderListModel.Ready && files.listed === registry.directory && registry.contributions) {
        registry.loadTools()
      }
    }
  }

  function definitions(tool) {
    return [tool].concat(Array.from(tool.options))
  }

  // Every file a tool comes from: the application's directory first, then
  // the packages'. `id` is the one a manifest gives the tool, if any.
  function sources() {
    var result = []
    for (var i = 0; i < files.count; i++) {
      result.push({ url: files.get(i, "fileUrl"), builtin: true, id: "" })
    }
    return result.concat(contributions.map(function(descriptor) {
      return { url: descriptor.url, builtin: descriptor.builtin, id: descriptor.id }
    }))
  }

  // One tool made from its file, or null with the reason in diagnostics.
  function create(source, diagnostics) {
    var component = Qt.createComponent(source.url, Component.PreferSynchronous)
    if (component.status !== Component.Ready) {
      diagnostics.push(String(source.url) + ": " + component.errorString())
      component.destroy()
      return null
    }
    var tool = component.createObject(registry, { editor: registry.editor })
    component.destroy()
    var reason = ""
    if (!tool || tool.apiVersion !== 1 || !tool.toolId || !tool.label || !tool.options
        || typeof tool.execute !== "function") {
      reason = "expected an editing Tool with an id and label"
    } else if (source.id && tool.toolId !== source.id) {
      reason = "its toolId is not " + source.id + ", the ID its manifest gives it"
    }
    if (reason) {
      diagnostics.push(String(source.url) + ": " + reason)
      if (tool) {
        tool.destroy()
      }
      return null
    }
    return { tool: tool, builtin: source.builtin }
  }

  // How many tools claim each action ID: all of them, and the application's
  // own, its built-in packages included.
  function claims(candidates) {
    var result = Object.create(null)
    candidates.forEach(function(candidate) {
      definitions(candidate.tool).forEach(function(definition) {
        var claim = result[definition.toolId] || (result[definition.toolId] = { all: 0, builtin: 0 })
        claim.all++
        if (candidate.builtin) {
          claim.builtin++
        }
      })
    })
    return result
  }

  function definitionError(tool, claim, builtin) {
    if (tool.apiVersion !== 1 || !tool.toolId || !tool.label || typeof tool.execute !== "function") {
      return "expected an editing Tool with an id and label"
    }
    // The application's tools keep their IDs against a package's; among
    // equals nobody wins.
    if (builtin && claim.builtin > 1) {
      return "duplicate tool id"
    }
    if (!builtin && claim.all > 1) {
      return "duplicate or reserved tool id"
    }
    if (tool.shortcutKey && (tool.isMenu || !Stroke.fromQt(tool.shortcutKey, tool.shortcutModifiers))) {
      return "a shortcut needs a supported key and an executable tool"
    }
    return ""
  }

  function loadTools() {
    // Discover once per set of sources. Updating source files takes effect
    // on app restart; do not destroy tool instances underneath pending
    // conversions.
    if (upToDate) {
      return
    }
    registry.closePanels()
    var previous = registryState.tools
    registryState.tools = []
    registryState.ready = false
    var diagnostics = []
    var candidates = sources().map(function(source) {
      return registry.create(source, diagnostics)
    }).filter(function(candidate) {
      return candidate !== null
    })
    candidates.sort(function(a, b) {
      return a.tool.toolId.localeCompare(b.tool.toolId)
    })
    var claimed = claims(candidates)
    var accepted = []
    for (var j = 0; j < candidates.length; j++) {
      var candidate = candidates[j]
      var reason = ""
      var candidateEntries = definitions(candidate.tool)
      for (var c = 0; !reason && c < candidateEntries.length; c++) {
        var definition = candidateEntries[c]
        reason = c > 0 && definition.isMenu ? "tool options must be executable"
          : definitionError(definition, claimed[definition.toolId], candidate.builtin)
      }
      if (reason) {
        diagnostics.push(candidate.tool.toolId + ": " + reason)
        candidate.tool.destroy()
        continue
      }
      candidateEntries.forEach(function(entry) {
        entry.keybindings = Qt.binding(function() { return registry.keybindings })
      })
      accepted.push(candidate.tool)
    }
    registryState.errors = diagnostics
    registryState.tools = accepted
    registryState.loadedDirectory = directory
    registryState.loadedContributions = contributions
    registryState.ready = true
    for (var k = 0; k < previous.length; k++) {
      previous[k].destroy()
    }
    for (var d = 0; d < diagnostics.length; d++) {
      console.warn("Editing tool skipped: " + diagnostics[d])
    }
  }

  function find(id) {
    for (var i = 0; i < actions.length; i++) {
      if (actions[i].toolId === id) {
        return actions[i]
      }
    }
    return null
  }

  function menuTools(id) {
    var menu = find(id)
    var rows = menu && menu.options.length > 0 ? Array.from(menu.options) : (placement.menus[id] || [])
    return rows.filter(function(tool) {
      return registry.isVisible(tool) && (!tool.isMenu || registry.menuTools(tool.toolId).length > 0)
    })
  }

  function groupFor(id) {
    for (var i = 0; i < placement.toolbar.length; i++) {
      if (placement.toolbar[i].tool.toolId === id) {
        return placement.toolbar[i].group
      }
    }
    return -1
  }

  function isVisible(tool) {
    if (!tool || !tool.available) {
      return false
    }
    if (tool.options.length > 0) {
      return Array.from(tool.options).some(function(option) {
        return registry.isVisible(option)
      })
    }
    return tool.isMenu || editor.supports(tool.capability)
  }

  function canExecute(tool) {
    if (!upToDate || !tool || tool.isMenu || !editor.writable || !isVisible(tool)) {
      return false
    }
    return true
  }

  function execute(id) {
    var tool = find(id)
    if (!canExecute(tool)) {
      return false
    }
    closePanels(tool)
    tool.execute()
    return true
  }

  function handleShortcut(event) {
    var binding = keybindings.match(event, "editor")
    if (!binding || binding.kind !== "tool") {
      return false
    }
    if (!event.isAutoRepeat) {
      execute(binding.action)
    }
    // Consume disabled actions too, so native formatting cannot bypass capabilities.
    return true
  }

  function closePanels(except) {
    for (var i = 0; i < actions.length; i++) {
      if (actions[i] !== except) {
        actions[i].panelOpen = false
      }
    }
  }

  Connections {
    target: registry.editor
    function onNoteTokenChanged() {
      registry.closePanels()
    }
    function onWritableChanged() {
      if (!registry.editor.writable) {
        registry.closePanels()
        registry.editor.clearPending()
      }
    }
    function onEnabledToolsChanged() {
      registry.closePanels()
      registry.editor.clearPending()
    }
  }
}
