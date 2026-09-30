.pragma library
.import "tokens.js" as Tokens

// How a colour nothing supplies is made from the colours it depends on, and
// how a theme is laid over the host's own colours. tokens.js says which
// recipe each token uses and what it reads.

function alpha(value, opacity) {
  var color = Qt.color(value)
  return Qt.rgba(color.r, color.g, color.b, opacity)
}

// Pale desktop palettes need stronger secondary ink than dark palettes.
// Keep disabled controls separate: this is for readable, available content.
function secondaryOpacity(background, opacity) {
  return luminance(background) > 0.5 ? Math.max(opacity, 0.85) : opacity
}

// Named recipes are application code, never expressions supplied by a theme.
// A recipe's parameters are its token's `inputs`, in order.
var recipes = {
  // A colour only the host can give. Black is what is left when it does not.
  root: function() { return "#000000" },
  alias: function(source) { return source },
  activeTabBackground: function(selection, background, foreground) {
    return luminance(background) > 0.5 ? Qt.tint(selection, alpha(foreground, 0.06)) : selection
  },
  raised: function(background, foreground) { return Qt.tint(background, alpha(foreground, 0.07)) },
  muted: function(foreground) { return alpha(foreground, 0.65) },
  inactiveText: function(foreground) { return alpha(foreground, 0.68) },
  disabled: function(foreground) { return alpha(foreground, 0.4) },
  border: function(foreground) { return alpha(foreground, 0.25) },
  focus: function(surface, foreground) { return Qt.tint(surface, alpha(foreground, 0.35)) },
  scrim: function() { return "#99000000" },
  selection: function(accent) { return alpha(accent, 0.2) },
  input: function(surface, foreground) { return Qt.tint(surface, alpha(foreground, 0.08)) },
  inputBorder: function(surface, foreground) { return Qt.tint(surface, alpha(foreground, 0.18)) },
  placeholder: function(foreground) { return alpha(foreground, 0.45) },
  sidebar: function(background, foreground) { return Qt.tint(background, alpha(foreground, 0.05)) },
  titlebar: function(background) { return Qt.darker(background, 1.12) },
  textSelection: function(accent) { return alpha(accent, 0.35) },
  link: function(foreground, accent) { return Qt.tint(foreground, alpha(accent, 0.65)) },
  quoteInk: function(background, foreground) { return Qt.tint(background, alpha(foreground, 0.8)) },
  quoteBorder: function(accent) { return alpha(accent, 0.6) },
  code: function(background) { return Qt.darker(background, 1.16) },
  marker: function() { return "#f9e2af" },
  markerInk: function() { return "#1e1e2e" },
  error: function() { return "#d34747" },
  light: function(background) { return Qt.lighter(background, 1.5) },
  midlight: function(background) { return Qt.lighter(background, 1.15) },
  mid: function(background) { return Qt.darker(background, 1.3) },
  dark: function(background) { return Qt.darker(background, 1.7) },
  shadow: function() { return "#000000" }
}

function derive(name, palette) {
  var token = Tokens.specification[name]
  if (token.recipe === "root") {
    console.warn("note-note themes: the host supplies no", token.systemRole, "colour for", name)
  }
  var inputs = token.inputs.map(function(key) {
    return palette[key]
  })
  return recipes[token.recipe].apply(null, inputs).toString()
}

// What "system" means: every token from the host's own roles, and from its
// recipe where the host has no role for it.
function baseline(hostRoles) {
  var result = {}
  Object.keys(Tokens.specification).forEach(function(name) {
    var token = Tokens.specification[name]
    var supplied = hostRoles[token.systemRole]
    result[name] = supplied === undefined ? derive(name, result) : supplied.toString()
    if (supplied === undefined && ["muted", "inactiveText", "placeholder"].indexOf(token.recipe) >= 0) {
      var opacity = Qt.color(result[name]).a
      result[name] = alpha(result[name], secondaryOpacity(result["surface.background"], opacity)).toString()
    }
  })
  return result
}

// A theme over the system: what it states is used, "system" is the system's
// colour whatever else the theme changed, and what it leaves out follows the
// colours it did set.
function resolve(system, colors) {
  var result = {}
  Object.keys(Tokens.specification).forEach(function(name) {
    var value = colors[name]
    var rooted = Tokens.specification[name].recipe === "root"
    if (value === "system" || (value === undefined && rooted)) {
      result[name] = system[name]
    } else {
      result[name] = value === undefined ? derive(name, result) : value
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

// Pairs a reader would struggle with. A diagnostic, never a correction: what
// a theme states is what is shown.
function contrastDiagnostics(colors) {
  var warnings = []
  Object.keys(Tokens.specification).forEach(function(name) {
    var pair = Tokens.specification[name].pair
    if (!pair) {
      return
    }
    var foreground = Qt.color(colors[name])
    var background = Qt.color(colors[pair])
    if (foreground.a < 1 || background.a < 1) {
      return
    }
    var a = luminance(foreground), b = luminance(background)
    var ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
    if (ratio < 3) {
      warnings.push(name + " on " + pair + ": " + ratio.toFixed(1) + ":1 contrast")
    }
  })
  return warnings
}

// The part of the specification a theme file is checked against.
function validationTable() {
  var table = {}
  Object.keys(Tokens.specification).forEach(function(name) {
    table[name] = { overlay: Tokens.specification[name].overlay }
  })
  return table
}
