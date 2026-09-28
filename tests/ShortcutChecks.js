.pragma library
.import "../services/shortcuts/resolve.js" as Resolve
.import "../services/shortcuts/stroke.js" as Stroke
.import "../services/shortcuts/defaults.js" as Defaults

function run(verify) {
  var commands = [
    { id: "example.one/export", title: "Export" },
    { id: "example.two/send", title: "Send" },
    { id: "org.note-note.workspace/new-note", title: "New note", workspaceAction: "newNote" }
  ]
  function compile(bindings, overrides, tools) {
    return Resolve.build(Defaults.ACTIONS, commands, bindings || [], tools || [], overrides || [])
  }
  function binding(command, key, context) {
    return { command: command, key: key, context: context || "notes" }
  }
  function match(result, key, context) {
    var stroke = Stroke.parse(key)
    var target = result.index[(context || "workspace") + "/" + stroke.signature]
    return target ? target.id : ""
  }
  function label(result, id) {
    return Resolve.labels(result, id).join(" / ")
  }
  var base = compile()
  verify(match(base, "Ctrl+N") === "app/newNote", "app default executes by stable ID")
  verify(label(base, commands[2].id) === "ctrl+n", "workspace command inherits the app binding")
  verify(match(base, "Ctrl+S", "page") === "app/savePage" && !match(base, "Ctrl+S", "workspace"), "page scope")
  verify(match(base, "Ctrl+Shift+P", "page") === "app/commandPalette", "application scope includes settings")
  verify(match(base, "Down", "search") === "app/nextSearch" && !match(base, "Down", "editor"), "search arrows stay local")
  verify(Stroke.signature({ key: Qt.Key_Backtab, modifiers: Qt.ControlModifier }) === Stroke.parse("Ctrl+Shift+Tab").signature,
    "Qt Backtab normalizes to Shift+Tab")
  verify(Stroke.parse(" shift + Control + P ").label === "ctrl+shift+p", "normalization drives display")
  verify(Stroke.signature({ key: Qt.Key_N, modifiers: Qt.ControlModifier | Qt.GroupSwitchModifier }) === "", "AltGr is typing")
  var keys = [binding(commands[0].id, "Ctrl+Alt+E")]
  var plugin = compile(keys)
  verify(label(plugin, commands[0].id) === "ctrl+alt+e" && match(plugin, "Ctrl+Alt+E", "editor") === commands[0].id,
    "plugin registration drives label and dispatch")
  verify(!match(plugin, "Ctrl+Alt+E", "page"), "notes command stays out of Settings")
  verify(!label(Resolve.build(Defaults.ACTIONS, [], keys, [], []), commands[0].id), "unloaded command has no binding")
  var conflict = compile([binding(commands[0].id, "Ctrl+N")])
  verify(match(conflict, "Ctrl+N") === "app/newNote" && !label(conflict, commands[0].id) && conflict.diagnostics.length === 1,
    "app default wins over plugin default")
  var tied = [binding(commands[0].id, "Ctrl+Alt+E"), binding(commands[1].id, "Ctrl+Alt+E", "editor")]
  conflict = compile(tied)
  verify(!label(conflict, commands[0].id) && !label(conflict, commands[1].id) && conflict.diagnostics.length === 2,
    "overlapping plugin conflicts disable both complete bindings")
  verify(!match(compile(tied.slice().reverse()), "Ctrl+Alt+E", "editor"), "discovery order does not pick a winner")
  var separate = compile([binding(commands[0].id, "Ctrl+Alt+E", "page"), binding(commands[1].id, "Ctrl+Alt+E", "editor")])
  verify(match(separate, "Ctrl+Alt+E", "page") === commands[0].id && match(separate, "Ctrl+Alt+E", "editor") === commands[1].id,
    "non-overlapping scopes share a key")
  var changed = compile(keys, [{ command: commands[2].id, keys: ["Ctrl+Alt+N"] }])
  verify(!match(changed, "Ctrl+N") && match(changed, "Ctrl+Alt+N") === "app/newNote"
    && label(changed, commands[2].id) === "ctrl+alt+n", "alias overrides change action and label together")
  var unbound = compile(keys, [{ command: "app/search", keys: [] }])
  verify(!match(unbound, "Ctrl+K") && !match(unbound, "Ctrl+L") && !label(unbound, "app/search"), "unbind removes every default alias")
  changed = compile(keys, [{ command: commands[0].id, keys: ["Ctrl+N"] }])
  verify(match(changed, "Ctrl+N") === commands[0].id && !label(changed, commands[2].id)
    && !match(changed, "Ctrl+Alt+E"), "user binding wins over app and replaces plugin default")
  changed = compile(keys, [{ command: commands[0].id, keys: ["Ctrl+Alt+X"] }, { command: commands[1].id, keys: ["Ctrl+Alt+X"] }])
  verify(!match(changed, "Ctrl+Alt+X") && !match(changed, "Ctrl+Alt+E"), "equal user conflicts do not revive defaults")
  changed = compile([], [{ command: "app/newNote", keys: [] }, { command: commands[2].id, keys: ["Ctrl+Alt+N"] }])
  verify(match(changed, "Ctrl+N") === "app/newNote" && changed.diagnostics.length === 1, "ambiguous action aliases retain defaults")
  changed = compile([], [{ command: "missing.plugin/command", keys: ["Ctrl+N"] }])
  verify(match(changed, "Ctrl+N") === "app/newNote", "absent plugin override is dormant")
  var tools = [{ toolId: "bold", label: "Bold", shortcutKey: Qt.Key_B, shortcutModifiers: Qt.ControlModifier }]
  changed = compile([], [{ command: "tool/bold", keys: ["Ctrl+Alt+B"] }], tools)
  verify(!match(changed, "Ctrl+B", "editor") && match(changed, "Ctrl+Alt+B", "editor") === "tool/bold"
    && label(changed, "tool/bold") === "ctrl+alt+b", "tools use the same overrides and labels")
  verify(/ctrl\+alt\+b +Bold/.test(Resolve.help(changed)), "help uses effective tool binding")
  tools[0].shortcutKey = Qt.Key_S
  changed = compile([], [], tools)
  verify(match(changed, "Ctrl+S", "editor") === "tool/bold" && match(changed, "Ctrl+S", "page") === "app/savePage", "tool and page defaults coexist")
  tools[0].shortcutKey = Qt.Key_N
  changed = compile([], [], tools)
  verify(match(changed, "Ctrl+N", "editor") === "app/newNote" && !label(changed, "tool/bold"), "tools cannot displace app defaults")
  verify(!!Resolve.validateOverrides([{ command: "app/newNote", keys: ["Ctrl+V"] }]), "native paste is reserved")
  var invalidKeys = ["a", "Shift+A", "Ctrl+Ctrl+A", "Ctrl+", "constructor+N", "Ctrl+constructor", "Ctrl+F36"]
  invalidKeys.forEach(function(key) {
    verify(!!Resolve.validateOverrides([{ command: "app/newNote", keys: [key] }]), "reject invalid shortcut " + key)
  })
  verify(!Resolve.validateOverrides([{ command: "app/newNote", keys: ["F6", "Meta+Plus"] }]), "function and named punctuation keys supported")
  verify(!!Resolve.validateOverrides([{ command: "app/search", keys: [] }, { command: "app/search", keys: [] }]), "duplicate overrides rejected")
}
