pragma Singleton
import QtQuick

QtObject {
  id: colors
  // The plugin supplies shell colors directly. The standalone resolver
  // chooses desktop sources before falling back to application colors.
  property var source: null
  property var systemTheme: null
  property var theme: null
  readonly property var resolved: systemTheme ? systemTheme.colors : null
  property SystemPalette system: SystemPalette {
    colorGroup: SystemPalette.Active
  }
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
    return { background: system.window, foreground: system.windowText, accent: system.highlight,
      urgent: "#d34747", border: Util.alpha(system.windowText, 0.25), scrim: "#99000000",
      selectedBackground: Util.alpha(system.highlight, 0.2), selectedText: system.highlight }
  }
  function token(name, fallback) {
    return theme && theme.colors[name] !== undefined ? theme.colors[name] : fallback
  }
  readonly property color background: token("surface.background", raw.background)
  readonly property color foreground: token("text.primary", raw.foreground)
  readonly property color accent: token("accent.primary", raw.accent)
  readonly property color urgent: token("status.error", raw.urgent)
  readonly property QtObject menu: QtObject {
    readonly property color background: colors.background
    readonly property color text: colors.foreground
    readonly property color border: colors.token("border.default", colors.raw.border)
    readonly property color scrim: colors.token("overlay.scrim", colors.raw.scrim)
    readonly property color selectedBackground: colors.token("selection.background", colors.raw.selectedBackground)
    readonly property color selectedText: colors.token("selection.foreground", colors.raw.selectedText)
  }
  readonly property QtObject popups: QtObject {
    readonly property color text: colors.token("popup.foreground", colors.raw.popupText || colors.foreground)
  }
}
