.pragma library
.import "../../ui/editing/ToolbarSettings.js" as ToolbarSettings
.import "../shortcuts/resolve.js" as Shortcuts
.import "../themes/system.js" as SystemTheme

// What a settings field may hold is stated here and nowhere else: the file
// helper (config_io.py) checks only that the text is strict JSON.

function isObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value)
}

function defaults(ids, providerDefaults) {
  var providers = {}
  ids.forEach(function(id) {
    providers[id] = Object.assign({ enabled: true }, providerDefaults[id] || {})
  })
  return { editor: ToolbarSettings.editorDefaults(), providers: providers,
           appearance: { theme: SystemTheme.themeId }, plugins: {}, keybindings: [] }
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

function entryProblems(config, group, report) {
  Object.keys(config[group]).forEach(function(id) {
    var entry = config[group][id]
    if (!isObject(entry)) {
      report([group, id], group + "." + id + " must be an object")
    } else if (entry.enabled !== undefined && typeof entry.enabled !== "boolean") {
      report([group, id, "enabled"], group + "." + id + ".enabled must be true or false")
    }
  })
}

// Every part of the settings that cannot be used, as { path, message }. A
// problem names the smallest part that is wrong, so the rest stays in force.
function problems(config) {
  var found = []
  function report(path, message) {
    found.push({ path: path, message: message })
  }
  var groups = ["providers", "editor", "appearance", "plugins"]
  groups.forEach(function(group) {
    if (config[group] !== undefined && !isObject(config[group])) {
      report([group], group + " must be an object")
    }
  })
  var registries = ["providers", "plugins"]
  registries.forEach(function(group) {
    if (isObject(config[group])) {
      entryProblems(config, group, report)
    }
  })
  var theme = isObject(config.appearance) ? config.appearance.theme : undefined
  if (theme !== undefined && (typeof theme !== "string" || !theme)) {
    report(["appearance", "theme"], "appearance.theme must be a theme ID")
  }
  var toolbar = isObject(config.editor) ? config.editor.toolbar : undefined
  var toolbarError = toolbar === undefined ? "" : ToolbarSettings.validate(toolbar)
  if (toolbarError) {
    report(["editor", "toolbar"], toolbarError)
  }
  var bindingError = Shortcuts.validateOverrides(config.keybindings)
  if (bindingError) {
    report(["keybindings"], bindingError)
  }
  return found
}

// What an explicit Save must satisfy: the first problem, or nothing.
function validate(config) {
  if (!isObject(config)) {
    return "The settings must be a JSON object"
  }
  var found = problems(config)
  return found.length ? found[0].message : ""
}

// The settings with each problem's part left out, for the defaults to fill.
function usable(config, found) {
  var result = JSON.parse(JSON.stringify(config))
  found.forEach(function(problem) {
    var owner = result
    for (var i = 0; i < problem.path.length - 1; i++) {
      owner = owner[problem.path[i]]
    }
    delete owner[problem.path[problem.path.length - 1]]
  })
  return result
}

// One line for a status message or a page notice.
function summary(found) {
  if (!found.length) {
    return ""
  }
  var more = found.length > 1 ? " (and " + (found.length - 1) + " more)" : ""
  return found[0].message + more + "; the default is used until the settings are corrected"
}
