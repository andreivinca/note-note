.pragma library

// A key with its modifiers, as the application spells and compares it.
var modifierMask = Qt.ControlModifier | Qt.AltModifier | Qt.ShiftModifier | Qt.MetaModifier
var modifiers = { ctrl: Qt.ControlModifier, control: Qt.ControlModifier, alt: Qt.AltModifier,
  shift: Qt.ShiftModifier, meta: Qt.MetaModifier, super: Qt.MetaModifier }
var names = {
  esc: Qt.Key_Escape, escape: Qt.Key_Escape, tab: Qt.Key_Tab, backtab: Qt.Key_Backtab,
  enter: Qt.Key_Return, return: Qt.Key_Return, numenter: Qt.Key_Enter,
  space: Qt.Key_Space, backspace: Qt.Key_Backspace, delete: Qt.Key_Delete, insert: Qt.Key_Insert,
  home: Qt.Key_Home, end: Qt.Key_End, pageup: Qt.Key_PageUp, pagedown: Qt.Key_PageDown,
  up: Qt.Key_Up, down: Qt.Key_Down, left: Qt.Key_Left, right: Qt.Key_Right,
  plus: Qt.Key_Plus, minus: Qt.Key_Minus, comma: Qt.Key_Comma, period: Qt.Key_Period,
  slash: Qt.Key_Slash, backslash: Qt.Key_Backslash, bracketleft: Qt.Key_BracketLeft,
  bracketright: Qt.Key_BracketRight, equal: Qt.Key_Equal
}
// Native document operations: undo and redo pass through the editor's
// transaction handler, and the clipboard keys are the text control's own.
var reservedLabels = ["ctrl+a", "ctrl+c", "ctrl+x", "ctrl+v", "ctrl+shift+v", "ctrl+z", "ctrl+shift+z", "ctrl+y",
  "ctrl+insert", "shift+insert", "shift+delete"]

// Qt reports Shift+Tab as Backtab, with the Shift flag or without it.
function normalized(key, flags) {
  if (key === Qt.Key_Backtab) {
    return { key: Qt.Key_Tab, flags: (flags | Qt.ShiftModifier) & modifierMask }
  }
  return { key: key, flags: flags & modifierMask }
}

function signatureOf(pressed) {
  return pressed.key + ":" + pressed.flags
}

function nameOf(key) {
  if ((key >= Qt.Key_A && key <= Qt.Key_Z) || (key >= Qt.Key_0 && key <= Qt.Key_9)) {
    return String.fromCharCode(key).toLowerCase()
  }
  if (key >= Qt.Key_F1 && key <= Qt.Key_F35) {
    return "f" + (key - Qt.Key_F1 + 1)
  }
  return Object.keys(names).find(function(candidate) {
    return names[candidate] === key
  }) || ""
}

function fromQt(key, flags) {
  var pressed = normalized(key, flags)
  var name = nameOf(pressed.key)
  if (!name) {
    return null
  }
  var parts = []
  if (pressed.flags & Qt.ControlModifier) {
    parts.push("ctrl")
  }
  if (pressed.flags & Qt.AltModifier) {
    parts.push("alt")
  }
  if (pressed.flags & Qt.ShiftModifier) {
    parts.push("shift")
  }
  if (pressed.flags & Qt.MetaModifier) {
    parts.push("meta")
  }
  parts.push(name)
  return { key: pressed.key, modifiers: pressed.flags, signature: signatureOf(pressed), label: parts.join("+") }
}

function keyNamed(name) {
  if (/^[a-z0-9]$/.test(name)) {
    return name.toUpperCase().charCodeAt(0)
  }
  if (/^f([1-9]|[12][0-9]|3[0-5])$/.test(name)) {
    return Qt.Key_F1 + Number(name.slice(1)) - 1
  }
  return Object.prototype.hasOwnProperty.call(names, name) ? names[name] : undefined
}

function parse(value) {
  if (typeof value !== "string" || value.length > 64) {
    throw new Error("A shortcut must be a string of at most 64 characters.")
  }
  var parts = value.toLowerCase().split("+").map(function(part) {
    return part.trim()
  })
  var name = parts.pop(), flags = 0
  parts.forEach(function(part) {
    var flag = Object.prototype.hasOwnProperty.call(modifiers, part) ? modifiers[part] : 0
    if (!flag || (flags & flag)) {
      throw new Error("Invalid or repeated shortcut modifier: " + part)
    }
    flags |= flag
  })
  var result = fromQt(keyNamed(name), flags)
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
  return reservedLabels.indexOf(stroke.label) >= 0
}

function signature(event) {
  if (event.modifiers & Qt.GroupSwitchModifier) {
    return ""
  }
  return signatureOf(normalized(event.key, event.modifiers))
}
