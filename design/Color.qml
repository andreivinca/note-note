pragma Singleton
import QtQuick
import "resolve.js" as Resolve

QtObject {
  id: colors
  // The plugin supplies shell colors directly. The standalone resolver
  // chooses desktop sources before falling back to application colors.
  property var source: null
  property var systemTheme: null
  // The theme service in force, once a workspace has one. Until then, and
  // in anything built without a workspace, the colours are the system's.
  property var theme: null
  readonly property var resolved: systemTheme ? systemTheme.colors : null
  property SystemPalette system: SystemPalette {
    colorGroup: SystemPalette.Active
  }
  // The host's own roles, by the names tokens.js knows them under. A role a
  // host does not have is left out, and the token's recipe takes its place.
  readonly property var raw: {
    if (source) {
      return { background: source.menu.background, foreground: source.menu.text,
        accent: source.accent, urgent: source.urgent, border: source.menu.border,
        scrim: source.menu.scrim, selectedBackground: source.menu.selectedBackground,
        selectedText: source.menu.selectedText, popupText: source.popups.text }
    }
    if (resolved) {
      return resolved
    }
    return { background: system.window, foreground: system.windowText, accent: system.highlight }
  }
  // Every token as the host alone colours it: what "system" means.
  readonly property var baseline: Resolve.baseline(raw)
  readonly property var tokens: theme ? theme.colors : baseline

  function token(name) {
    return tokens[name]
  }
  readonly property color background: token("surface.background")
  readonly property color foreground: token("text.primary")
  readonly property color accent: token("accent.primary")
  readonly property color urgent: token("status.error")
  readonly property QtObject menu: QtObject {
    readonly property color background: colors.background
    readonly property color text: colors.foreground
    readonly property color border: colors.token("border.default")
    readonly property color scrim: colors.token("overlay.scrim")
    readonly property color selectedBackground: colors.token("selection.background")
    readonly property color selectedText: colors.token("selection.foreground")
  }
  readonly property QtObject popups: QtObject {
    readonly property color text: colors.token("popup.foreground")
  }
}
