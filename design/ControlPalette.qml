import QtQuick

Palette {
  window: Color.background
  windowText: Color.foreground
  base: Color.token("control.base", Color.raw.base || Color.background)
  alternateBase: Color.token("control.alternateBase", Color.raw.alternateBase || Color.background)
  text: Color.token("control.text", Color.raw.text || Color.foreground)
  button: Color.token("button.background", Color.raw.button || Color.background)
  buttonText: Color.token("button.foreground", Color.raw.buttonText || Color.foreground)
  highlight: Color.token("control.highlight", Color.raw.highlight || Color.accent)
  highlightedText: Color.token("control.highlightedText", Color.raw.highlightedText || Color.foreground)
  toolTipBase: Color.token("tooltip.background", Color.raw.toolTipBase || Color.background)
  toolTipText: Color.token("tooltip.foreground", Color.raw.toolTipText || Color.foreground)
  link: Color.token("editor.link", Color.raw.link || Color.accent)
  linkVisited: Color.token("editor.linkVisited", Color.raw.linkVisited || Color.accent)
  light: Color.token("control.light", Color.raw.light || Color.background)
  midlight: Color.token("control.midlight", Color.raw.midlight || Color.background)
  mid: Color.token("control.mid", Color.raw.mid || Color.background)
  dark: Color.token("control.dark", Color.raw.dark || Color.background)
  shadow: Color.token("control.shadow", Color.raw.shadow || "#000000")
  accent: Color.accent
  placeholderText: Color.token("control.placeholderText", Color.raw.placeholderText || Color.foreground)
  disabled.text: Color.token("control.disabledText", Color.raw.disabledText || Color.foreground)
  disabled.buttonText: Color.token("button.disabledForeground", Color.raw.disabledButtonText || Color.foreground)
  disabled.windowText: Color.token("text.disabled", Color.raw.disabledWindowText || Color.foreground)
}
