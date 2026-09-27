.pragma library
.import "../../ui/editing/ToolbarSettings.js" as ToolbarSettings
.import "../shortcuts/resolve.js" as Shortcuts

var systemTheme = "org.note-note.appearance/system"

function defaults(ids, providerDefaults) {
  var providers = {}
  ids.forEach(function(id) {
    providers[id] = Object.assign({ enabled: true }, providerDefaults[id] || {})
  })
  return { editor: ToolbarSettings.editorDefaults(), providers: providers,
           appearance: { theme: systemTheme }, plugins: {}, keybindings: [] }
}

function merge(parsed, ids, providerDefaults) {
  var base = defaults(ids, providerDefaults)
  var providers = Object.assign({}, parsed.providers || {})
  ids.forEach(function(id) {
    providers[id] = Object.assign({}, base.providers[id], providers[id] || {})
  })
  return Object.assign({}, parsed, {
    providers: providers,
    editor: ToolbarSettings.editorDefaults(parsed.editor),
    appearance: Object.assign({}, base.appearance, parsed.appearance || {}),
    plugins: Object.assign({}, parsed.plugins || {}),
    keybindings: parsed.keybindings || []
  })
}

function validate(config) {
  if (!config || typeof config !== "object" || Array.isArray(config)) {
    return "The settings must be a JSON object"
  }
  var groups = ["providers", "editor", "appearance", "plugins"]
  for (var i = 0; i < groups.length; i++) {
    var entry = config[groups[i]]
    if (entry !== undefined && (!entry || typeof entry !== "object" || Array.isArray(entry))) {
      return groups[i] + " must be an object"
    }
  }
  var theme = config.appearance && config.appearance.theme
  if (theme !== undefined && (typeof theme !== "string" || !/^[a-z][a-z0-9.-]*\/[a-z][a-z0-9-]*$/.test(theme))) {
    return "appearance.theme must be a qualified theme ID"
  }
  return Shortcuts.validateOverrides(config.keybindings) || ToolbarSettings.validateConfig(config)
}
