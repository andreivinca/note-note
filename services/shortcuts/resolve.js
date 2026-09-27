.pragma library
.import "stroke.js" as Stroke

var priorities = { plugin: 100, application: 200, user: 300 }

var scopes = { application: ["workspace", "editor", "search", "page"],
  notes: ["workspace", "editor", "search"], editor: ["editor"], search: ["search"],
  page: ["page"], workspace: ["workspace"] }

function validateOverrides(value) {
  if (value === undefined) {
    return ""
  }
  if (!Array.isArray(value) || value.length > 512) {
    return "keybindings must be an array of at most 512 overrides"
  }
  var seen = Object.create(null)
  for (var i = 0; i < value.length; i++) {
    var entry = value[i]
    if (!entry || typeof entry !== "object" || Array.isArray(entry)
        || typeof entry.command !== "string" || entry.command.length > 256
        || !/^[a-z][a-z0-9.-]*\/[a-zA-Z][a-zA-Z0-9-]*$/.test(entry.command)
        || !Array.isArray(entry.keys) || entry.keys.length > 8) {
      return "Each keybinding needs a qualified command ID and a keys array (at most 8 keys): " + JSON.stringify(entry)
    }
    if (seen[entry.command]) {
      return "Duplicate keybinding override: " + entry.command
    }
    seen[entry.command] = true
    try {
      entry.keys.forEach(function(key) {
        var stroke = Stroke.parse(key)
        if (!Stroke.configurable(stroke) || Stroke.reserved(stroke)) {
          throw new Error("Use a modified key or function key; native editing shortcuts are reserved")
        }
      })
    } catch (error) {
      return entry.command + ": " + error.message
    }
  }
  return ""
}

// Compile only when registrations or settings change. A keystroke is one lookup.
function build(defaults, commands, contributions, tools, overrides) {
  var targets = Object.create(null), aliases = Object.create(null), candidates = [], diagnostics = []
  function target(id, kind, action, title, group, context, extra) {
    targets[id] = Object.assign({ id: id, kind: kind, action: action, title: title,
      group: group, contexts: scopes[context] || [], bindings: [] }, extra || {})
    aliases[id] = id
  }
  function add(id, key, context, priority, source) {
    try {
      var stroke = Stroke.parse(key), owner = targets[id]
      var contexts = context ? scopes[context] : owner.contexts
      if (!contexts || !contexts.length) {
        throw new Error("Unknown shortcut context")
      }
      if (priority !== priorities.application && (!Stroke.configurable(stroke) || Stroke.reserved(stroke))) {
        throw new Error("Reserved typing or native editing shortcut")
      }
      if (Stroke.reserved(stroke) && !owner.protected) {
        throw new Error("Reserved native editing shortcut")
      }
      candidates.push({ target: owner, stroke: stroke, contexts: contexts,
        priority: priority, source: source })
    } catch (error) {
      diagnostics.push(source + ": " + error.message)
    }
  }
  defaults.forEach(function(action) {
    target("app/" + action.id, "app", action.action || action.id, action.description, action.group,
      action.context, { repeatable: !!action.repeatable, parameters: action.parameters || {},
        protected: !!action.protected, workspaceAction: !!action.workspaceAction })
  })
  tools.forEach(function(tool) {
    if (!tool.isMenu) {
      target("tool/" + tool.toolId, "tool", tool.toolId, tool.label, "Editing", "editor")
    }
  })
  commands.forEach(function(command) {
    var appId = "app/" + command.workspaceAction
    if (command.workspaceAction && targets[appId] && targets[appId].workspaceAction) {
      aliases[command.id] = appId
    } else {
      // Commands without a declared binding start in notes; a declaration may narrow it.
      target(command.id, "command", command.id, command.title, "Commands", "notes")
    }
  })
  contributions.forEach(function(binding) {
    var owner = targets[binding.command]
    if (owner && owner.kind === "command") {
      owner.contexts = Array.from(new Set((owner.registeredContexts || []).concat(scopes[binding.context] || [])))
      owner.registeredContexts = owner.contexts
    }
  })
  var replacements = Object.create(null)
  var userBindings = overrides || []
  userBindings.forEach(function(entry) {
    var id = aliases[entry.command]
    if (!id) {
      return // Keep absent plugin overrides dormant until that plugin is loaded.
    }
    if (targets[id].protected) {
      diagnostics.push(entry.command + ": native editing bindings cannot be overridden")
      return
    }
    if (replacements[id]) {
      replacements[id] = { ambiguous: true }
      diagnostics.push(id + ": multiple overrides refer to this action; defaults retained")
    } else {
      replacements[id] = entry
    }
  })
  function replaced(id) {
    return replacements[id] && !replacements[id].ambiguous
  }
  defaults.forEach(function(action) {
    var id = "app/" + action.id
    if (!replaced(id)) {
      action.keys.forEach(function(key) { add(id, key, "", priorities.application, id) })
    }
  })
  tools.forEach(function(tool) {
    var id = "tool/" + tool.toolId, stroke = Stroke.fromQt(tool.shortcutKey, tool.shortcutModifiers)
    if (targets[id] && !replaced(id) && stroke) {
      if (Stroke.configurable(stroke)) {
        add(id, stroke.label, "editor", priorities.plugin, id)
      } else {
        diagnostics.push(id + ": typing keys cannot be editing shortcuts")
      }
    }
  })
  contributions.forEach(function(binding) {
    var id = aliases[binding.command]
    if (id && !replaced(id)) {
      var allowed = scopes[binding.context] || []
      if (allowed.some(function(context) { return targets[id].contexts.indexOf(context) < 0 })) {
        diagnostics.push(binding.command + ": shortcut context exceeds the action's context")
      } else {
        add(id, binding.key, binding.context, priorities.plugin, binding.command)
      }
    }
  })
  Object.keys(replacements).forEach(function(id) {
    if (replaced(id)) {
      replacements[id].keys.forEach(function(key) { add(id, key, "", priorities.user, id) })
    }
  })
  var buckets = Object.create(null), index = Object.create(null)
  candidates.forEach(function(binding) {
    var signature = binding.stroke.signature
    if (!buckets[signature]) {
      buckets[signature] = []
    }
    buckets[signature].push(binding)
  })
  Object.keys(buckets).forEach(function(signature) {
    var bucket = buckets[signature]
    bucket.forEach(function(binding) {
      var conflicts = bucket.filter(function(other) {
        return other.target.id !== binding.target.id && other.priority >= binding.priority
          && other.contexts.some(function(context) { return binding.contexts.indexOf(context) >= 0 })
      })
      if (conflicts.length) {
        diagnostics.push(binding.source + ": " + binding.stroke.label + " conflicts with "
          + conflicts.map(function(other) { return other.source }).join(", "))
        return
      }
      binding.contexts.forEach(function(context) {
        index[context + "/" + signature] = binding.target
      })
      if (!binding.target.bindings.some(function(existing) { return existing.signature === signature })) {
        binding.target.bindings.push(binding.stroke)
      }
    })
  })
  return { targets: targets, aliases: aliases, index: index, diagnostics: diagnostics }
}

function labels(compiled, id) {
  var target = compiled.targets[compiled.aliases[id]]
  return target ? target.bindings.map(function(binding) { return binding.label }) : []
}

function help(compiled) {
  var groups = Object.create(null)
  Object.keys(compiled.targets).forEach(function(id) {
    var target = compiled.targets[id], keys = labels(compiled, id)
    if (!keys.length) {
      return
    }
    if (!groups[target.group]) {
      groups[target.group] = []
    }
    groups[target.group].push(keys.join(" / ") + "   " + target.title)
  })
  var text = Object.keys(groups).map(function(group) { return group + "\n\n" + groups[group].join("\n") }).join("\n\n")
  if (compiled.diagnostics.length) {
    text += "\n\nShortcut conflicts\n\n" + compiled.diagnostics.join("\n")
  }
  return text
}
