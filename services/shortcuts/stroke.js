.pragma library

var modifierMask = Qt.ControlModifier | Qt.AltModifier | Qt.ShiftModifier | Qt.MetaModifier
var modifiers = { ctrl: Qt.ControlModifier, control: Qt.ControlModifier, alt: Qt.AltModifier,
  shift: Qt.ShiftModifier, meta: Qt.MetaModifier, super: Qt.MetaModifier }
var names = {
  esc: Qt.Key_Escape, escape: Qt.Key_Escape, tab: Qt.Key_Tab,
  enter: Qt.Key_Return, return: Qt.Key_Return, numenter: Qt.Key_Enter,
  space: Qt.Key_Space, backspace: Qt.Key_Backspace, delete: Qt.Key_Delete, insert: Qt.Key_Insert,
  home: Qt.Key_Home, end: Qt.Key_End, pageup: Qt.Key_PageUp, pagedown: Qt.Key_PageDown,
  up: Qt.Key_Up, down: Qt.Key_Down, left: Qt.Key_Left, right: Qt.Key_Right,
  plus: Qt.Key_Plus, minus: Qt.Key_Minus, comma: Qt.Key_Comma, period: Qt.Key_Period,
  slash: Qt.Key_Slash, backslash: Qt.Key_Backslash, bracketleft: Qt.Key_BracketLeft,
  bracketright: Qt.Key_BracketRight, equal: Qt.Key_Equal
}

function fromQt(key, flags) {
  if (key === Qt.Key_Backtab) {
    key = Qt.Key_Tab
    flags |= Qt.ShiftModifier
  }
  flags &= modifierMask
  var name = ""
  if ((key >= Qt.Key_A && key <= Qt.Key_Z) || (key >= Qt.Key_0 && key <= Qt.Key_9)) {
    name = String.fromCharCode(key).toLowerCase()
  } else if (key >= Qt.Key_F1 && key <= Qt.Key_F35) {
    name = "f" + (key - Qt.Key_F1 + 1)
  } else {
    name = Object.keys(names).find(function(candidate) { return names[candidate] === key }) || ""
  }
  if (!name) {
    return null
  }
  var parts = []
  if (flags & Qt.ControlModifier) {
    parts.push("ctrl")
  }
  if (flags & Qt.AltModifier) {
    parts.push("alt")
  }
  if (flags & Qt.ShiftModifier) {
    parts.push("shift")
  }
  if (flags & Qt.MetaModifier) {
    parts.push("meta")
  }
  parts.push(name)
  return { key: key, modifiers: flags, signature: key + ":" + flags, label: parts.join("+") }
}

function parse(value) {
  if (typeof value !== "string" || value.length > 64) {
    throw new Error("A shortcut must be a string of at most 64 characters.")
  }
  var parts = value.toLowerCase().split("+").map(function(part) { return part.trim() })
  var name = parts.pop(), flags = 0
  parts.forEach(function(part) {
    var flag = Object.prototype.hasOwnProperty.call(modifiers, part) ? modifiers[part] : 0
    if (!flag || (flags & flag)) {
      throw new Error("Invalid or repeated shortcut modifier: " + part)
    }
    flags |= flag
  })
  var key = Object.prototype.hasOwnProperty.call(names, name) ? names[name] : undefined
  if (/^[a-z0-9]$/.test(name)) {
    key = name.toUpperCase().charCodeAt(0)
  } else if (/^f([1-9]|[12][0-9]|3[0-5])$/.test(name)) {
    key = Qt.Key_F1 + Number(name.slice(1)) - 1
  } else if (name === "backtab") {
    key = Qt.Key_Tab
    flags |= Qt.ShiftModifier
  }
  var result = fromQt(key, flags)
  if (!result) {
    throw new Error("Unknown shortcut key: " + name)
  }
  return result
}

function configurable(stroke) {
  return !!(stroke.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier))
    || (stroke.key >= Qt.Key_F1 && stroke.key <= Qt.Key_F35)
}

function reserved(stroke) {
  return ["ctrl+a", "ctrl+c", "ctrl+x", "ctrl+v", "ctrl+shift+v", "ctrl+z", "ctrl+shift+z", "ctrl+y",
    "ctrl+insert", "shift+insert", "shift+delete"].indexOf(stroke.label) >= 0
}

function signature(event) {
  if (event.modifiers & Qt.GroupSwitchModifier) {
    return ""
  }
  var key = event.key, flags = event.modifiers & modifierMask
  if (key === Qt.Key_Backtab) {
    key = Qt.Key_Tab
    flags |= Qt.ShiftModifier
  }
  return key + ":" + flags
}
