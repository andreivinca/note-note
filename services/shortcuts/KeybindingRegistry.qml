import QtQuick
import "defaults.js" as Defaults
import "resolve.js" as Resolve
import "stroke.js" as Stroke

QtObject {
  id: registry
  property var commands: []
  property var contributions: []
  property var tools: []
  property var overrides: []
  readonly property var compiled: Resolve.build(Defaults.ACTIONS, commands, contributions, tools, overrides)
  readonly property var diagnostics: compiled.diagnostics
  readonly property string helpText: Resolve.help(compiled)

  function match(event, context) {
    return compiled.index[context + "/" + Stroke.signature(event)] || null
  }

  function label(id) {
    return Resolve.labels(compiled, id)[0] || ""
  }

  function hint(id) {
    var text = label(id)
    return text ? " (" + text + ")" : ""
  }
}
