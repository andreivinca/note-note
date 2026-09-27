.pragma library

function alpha(value, opacity) {
  var color = Qt.color(value)
  return Qt.rgba(color.r, color.g, color.b, opacity)
}

// Named recipes are application code, never expressions supplied by a theme.
var recipes = {
  root: function() { return "#000000" },
  alias: function(c) { return c[0] },
  raised: function(c) { return Qt.tint(c[0], alpha(c[1], 0.07)) },
  muted: function(c) { return alpha(c[0], 0.65) },
  inactiveText: function(c) { return alpha(c[0], 0.68) },
  disabled: function(c) { return alpha(c[0], 0.4) },
  border: function(c) { return alpha(c[0], 0.25) },
  focus: function(c) { return Qt.tint(c[0], alpha(c[1], 0.35)) },
  scrim: function() { return "#99000000" },
  selection: function(c) { return alpha(c[0], 0.2) },
  hover: function(c) { return alpha(c[0], 0.08) },
  pressed: function(c) { return alpha(c[1], 0.22) },
  selected: function(c) { return alpha(c[1], 0.18) },
  accentInk: function(c) { return Qt.tint(c[0], alpha(c[1], 0.6)) },
  input: function(c) { return Qt.tint(c[0], alpha(c[1], 0.08)) },
  inputBorder: function(c) { return Qt.tint(c[0], alpha(c[1], 0.18)) },
  placeholder: function(c) { return alpha(c[0], 0.45) },
  sidebar: function(c) { return Qt.tint(c[0], alpha(c[1], 0.018)) },
  titlebar: function(c) { return Qt.darker(c[0], 1.12) },
  textSelection: function(c) { return alpha(c[0], 0.35) },
  link: function(c) { return Qt.tint(c[0], alpha(c[1], 0.65)) },
  quoteInk: function(c) { return Qt.tint(c[0], alpha(c[1], 0.8)) },
  quoteBorder: function(c) { return alpha(c[0], 0.6) },
  code: function(c) { return Qt.darker(c[0], 1.16) },
  marker: function() { return "#f9e2af" },
  markerInk: function() { return "#1e1e2e" },
  error: function() { return "#d34747" },
  warning: function() { return "#c58b24" },
  success: function() { return "#448c59" },
  light: function(c) { return Qt.lighter(c[0], 1.5) },
  midlight: function(c) { return Qt.lighter(c[0], 1.15) },
  mid: function(c) { return Qt.darker(c[0], 1.3) },
  dark: function(c) { return Qt.darker(c[0], 1.7) },
  shadow: function() { return "#000000" }
}

function derive(token, palette) {
  var inputs = token.inputs.map(function(key) { return palette[key] })
  return recipes[token.recipe](inputs).toString()
}

function baseline(specification, raw, shellStyle) {
  var result = {}
  Object.keys(specification).forEach(function(key) {
    var token = specification[key]
    var supplied = token.systemRole ? raw[token.systemRole] : undefined
    result[key] = supplied !== undefined ? supplied.toString() : derive(token, result)
  })
  if (shellStyle && result["text.primary"]) {
    var foreground = result["text.primary"]
    var accent = result["accent.primary"]
    result["interaction.hover"] = shellStyle.hoverFillFor(foreground, accent).toString()
    result["interaction.pressed"] = shellStyle.pressedFillFor(foreground, accent).toString()
    result["interaction.selected"] = shellStyle.selectedFillFor(foreground, accent).toString()
    result["interaction.selectedForeground"] = shellStyle.selectedStateColor(foreground, accent).toString()
  }
  return result
}

function resolve(specification, system, colors) {
  var result = {}
  Object.keys(specification).forEach(function(key) {
    var value = colors[key]
    var token = specification[key]
    if (value === "system" || (value === undefined && token.recipe === "root")) {
      result[key] = system[key]
    } else if (value !== undefined) {
      result[key] = value
    } else {
      result[key] = derive(token, result)
    }
  })
  return result
}

function luminance(value) {
  var color = Qt.color(value)
  var parts = [color.r, color.g, color.b].map(function(channel) {
    return channel <= 0.04045 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4)
  })
  return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]
}

function contrastDiagnostics(specification, colors) {
  var warnings = []
  Object.keys(specification).forEach(function(key) {
    var pair = specification[key].pair
    if (!pair) {
      return
    }
    var foreground = Qt.color(colors[key])
    var background = Qt.color(colors[pair])
    if (foreground.a < 1 || background.a < 1) {
      return
    }
    var a = luminance(foreground), b = luminance(background)
    var ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
    if (ratio < 3) {
      warnings.push(key + " on " + pair + ": " + ratio.toFixed(1) + ":1 contrast")
    }
  })
  return warnings
}
