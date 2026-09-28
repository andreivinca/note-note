.pragma library
.import "stroke.js" as Stroke

// Which key runs what, where: the application's defaults, what packages
// contribute and what the user's settings say instead, compiled into one
// lookup. The key grammar is stroke.js's.

var priorities = { plugin: 100, application: 200, user: 300 }

var scopes = { application: ["workspace", "editor", "search", "page"],
  notes: ["workspace", "editor", "search"], editor: ["editor"], search: ["search"],
  page: ["page"], workspace: ["workspace"] }

var maxOverrides = 512
var maxKeys = 8

// ---- the user's overrides, as the settings hold them ---------------------

function overrideProblem(entry) {
  if (!entry || typeof entry !== "object" || Array.isArray(entry)
      || typeof entry.command !== "string" || entry.command.length > 256
      || !/^[a-z][a-z0-9.-]*\/[a-zA-Z][a-zA-Z0-9-]*$/.test(entry.command)
      || !Array.isArray(entry.keys) || entry.keys.length > maxKeys) {
    return "Each keybinding needs a qualified command ID and a keys array (at most " + maxKeys + " keys): "
      + JSON.stringify(entry)
  }
  for (var i = 0; i < entry.keys.length; i++) {
    try {
      var stroke = Stroke.parse(entry.keys[i])
      if (!Stroke.configurable(stroke) || Stroke.reserved(stroke)) {
        return entry.command + ": Use a modified key or function key; native editing shortcuts are reserved"
      }
    } catch (error) {
      return entry.command + ": " + error.message
    }
  }
  return ""
}

function validateOverrides(value) {
  if (value === undefined) {
    return ""
  }
  if (!Array.isArray(value) || value.length > maxOverrides) {
    return "keybindings must be an array of at most " + maxOverrides + " overrides"
  }
  var seen = Object.create(null)
  for (var i = 0; i < value.length; i++) {
    var problem = overrideProblem(value[i])
    if (problem) {
      return problem
    }
    if (seen[value[i].command]) {
      return "Duplicate keybinding override: " + value[i].command
    }
    seen[value[i].command] = true
  }
  return ""
}

// ---- compiling -----------------------------------------------------------
// `state` is the compilation in progress: `targets` by ID, `aliases` from
// every ID a caller may use to the target it means, the `candidates` offered
// so far and the `diagnostics` for what could not be used.

function addTarget(state, id, kind, action, title, group, context, extra) {
  state.targets[id] = Object.assign({ id: id, kind: kind, action: action, title: title,
    group: group, contexts: scopes[context] || [], bindings: [] }, extra || {})
  state.aliases[id] = id
}

function addTargets(state, defaults, tools, commands) {
  defaults.forEach(function(action) {
    addTarget(state, "app/" + action.id, "app", action.action || action.id, action.description, action.group,
      action.context, { repeatable: !!action.repeatable, parameters: action.parameters || {},
        protected: !!action.protected, workspace: !!action.workspace })
  })
  tools.forEach(function(tool) {
    if (!tool.isMenu) {
      addTarget(state, "tool/" + tool.toolId, "tool", tool.toolId, tool.label, "Editing", "editor")
    }
  })
  commands.forEach(function(command) {
    var host = state.targets["app/" + command.workspaceAction]
    if (command.workspaceAction && host && host.workspace) {
      // The command and the application's own action are one thing to bind.
      state.aliases[command.id] = host.id
    } else {
      // Commands without a declared binding start in notes; a declaration may narrow it.
      addTarget(state, command.id, "command", command.id, command.title, "Commands", "notes")
    }
  })
}

// A command runs where its package's bindings say, all of them together.
function declareContexts(state, contributions) {
  var declared = Object.create(null)
  contributions.forEach(function(binding) {
    var owner = state.targets[binding.command]
    if (owner && owner.kind === "command") {
      declared[owner.id] = (declared[owner.id] || []).concat(scopes[binding.context] || [])
    }
  })
  Object.keys(declared).forEach(function(id) {
    state.targets[id].contexts = Array.from(new Set(declared[id]))
  })
}

// What the user's settings put in place of a target's defaults, by target.
function replacementsFor(state, overrides) {
  var replacements = Object.create(null)
  overrides.forEach(function(entry) {
    var id = state.aliases[entry.command]
    if (!id) {
      return // Keep absent plugin overrides dormant until that plugin is loaded.
    }
    if (state.targets[id].protected) {
      state.diagnostics.push(entry.command + ": native editing bindings cannot be overridden")
      return
    }
    if (replacements[id]) {
      replacements[id] = { ambiguous: true }
      state.diagnostics.push(id + ": multiple overrides refer to this action; defaults retained")
    } else {
      replacements[id] = entry
    }
  })
  Object.keys(replacements).forEach(function(id) {
    if (replacements[id].ambiguous) {
      delete replacements[id]
    }
  })
  return replacements
}

// Why this stroke cannot be offered for the target, or nothing.
function refusal(owner, stroke, contexts, priority) {
  if (!contexts || !contexts.length) {
    return "Unknown shortcut context"
  }
  if (priority !== priorities.application && (!Stroke.configurable(stroke) || Stroke.reserved(stroke))) {
    return "Reserved typing or native editing shortcut"
  }
  if (Stroke.reserved(stroke) && !owner.protected) {
    return "Reserved native editing shortcut"
  }
  return ""
}

function offer(state, id, key, context, priority, source) {
  var stroke
  try {
    stroke = Stroke.parse(key)
  } catch (error) {
    state.diagnostics.push(source + ": " + error.message)
    return
  }
  var owner = state.targets[id]
  var contexts = context ? scopes[context] : owner.contexts
  var reason = refusal(owner, stroke, contexts, priority)
  if (reason) {
    state.diagnostics.push(source + ": " + reason)
    return
  }
  state.candidates.push({ target: owner, stroke: stroke, contexts: contexts, priority: priority, source: source })
}

function offerDefaults(state, defaults, replacements) {
  defaults.forEach(function(action) {
    var id = "app/" + action.id
    if (!replacements[id]) {
      action.keys.forEach(function(key) {
        offer(state, id, key, "", priorities.application, id)
      })
    }
  })
}

function offerTools(state, tools, replacements) {
  tools.forEach(function(tool) {
    var id = "tool/" + tool.toolId, stroke = Stroke.fromQt(tool.shortcutKey, tool.shortcutModifiers)
    if (!state.targets[id] || replacements[id] || !stroke) {
      return
    }
    if (Stroke.configurable(stroke)) {
      offer(state, id, stroke.label, "editor", priorities.plugin, id)
    } else {
      state.diagnostics.push(id + ": typing keys cannot be editing shortcuts")
    }
  })
}

function offerContributions(state, contributions, replacements) {
  contributions.forEach(function(binding) {
    var id = state.aliases[binding.command]
    if (!id || replacements[id]) {
      return
    }
    var contexts = state.targets[id].contexts
    var outside = (scopes[binding.context] || []).some(function(context) {
      return contexts.indexOf(context) < 0
    })
    if (outside) {
      state.diagnostics.push(binding.command + ": shortcut context exceeds the action's context")
    } else {
      offer(state, id, binding.key, binding.context, priorities.plugin, binding.command)
    }
  })
}

function offerReplacements(state, replacements) {
  Object.keys(replacements).forEach(function(id) {
    replacements[id].keys.forEach(function(key) {
      offer(state, id, key, "", priorities.user, id)
    })
  })
}

function overlapping(a, b) {
  return a.contexts.some(function(context) {
    return b.contexts.indexOf(context) >= 0
  })
}

// A candidate is bound unless another target's candidate of the same or a
// higher priority wants the same stroke where it would be pressed.
function bind(state) {
  var sharing = Object.create(null)
  state.candidates.forEach(function(binding) {
    var signature = binding.stroke.signature
    if (!sharing[signature]) {
      sharing[signature] = []
    }
    sharing[signature].push(binding)
  })
  var index = Object.create(null)
  state.candidates.forEach(function(binding) {
    var signature = binding.stroke.signature
    var rivals = sharing[signature].filter(function(other) {
      return other.target.id !== binding.target.id
        && other.priority >= binding.priority && overlapping(other, binding)
    })
    if (rivals.length) {
      state.diagnostics.push(binding.source + ": " + binding.stroke.label + " conflicts with "
        + rivals.map(function(other) { return other.source }).join(", "))
      return
    }
    binding.contexts.forEach(function(context) {
      index[context + "/" + signature] = binding.target
    })
    var known = binding.target.bindings.some(function(existing) {
      return existing.signature === signature
    })
    if (!known) {
      binding.target.bindings.push(binding.stroke)
    }
  })
  return index
}

// Compile only when registrations or settings change. A keystroke is one lookup.
function build(defaults, commands, contributions, tools, overrides) {
  var state = { targets: Object.create(null), aliases: Object.create(null), candidates: [], diagnostics: [] }
  addTargets(state, defaults, tools, commands)
  declareContexts(state, contributions)
  var replacements = replacementsFor(state, overrides || [])
  offerDefaults(state, defaults, replacements)
  offerTools(state, tools, replacements)
  offerContributions(state, contributions, replacements)
  offerReplacements(state, replacements)
  return { targets: state.targets, aliases: state.aliases, index: bind(state), diagnostics: state.diagnostics }
}

function labels(compiled, id) {
  var target = compiled.targets[compiled.aliases[id]]
  return target ? target.bindings.map(function(binding) { return binding.label }) : []
}

function padded(text, width) {
  return text + " ".repeat(Math.max(0, width - text.length))
}

// The help page: every bound action under its group, keys in one column.
function help(compiled) {
  var rows = Object.keys(compiled.targets).map(function(id) {
    return { group: compiled.targets[id].group, keys: labels(compiled, id).join(" / "), title: compiled.targets[id].title }
  }).filter(function(row) {
    return row.keys.length > 0
  })
  var width = rows.reduce(function(widest, row) {
    return Math.max(widest, row.keys.length)
  }, 0)
  var groups = Object.create(null)
  rows.forEach(function(row) {
    groups[row.group] = (groups[row.group] || []).concat("  " + padded(row.keys, width) + "   " + row.title)
  })
  var text = Object.keys(groups).map(function(group) {
    return group + "\n\n" + groups[group].join("\n")
  }).join("\n\n")
  if (compiled.diagnostics.length) {
    text += "\n\nShortcuts that could not be used\n\n" + compiled.diagnostics.join("\n")
  }
  return text
}
