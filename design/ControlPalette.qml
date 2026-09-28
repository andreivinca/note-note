import QtQuick

// The theme as Qt's own controls ask for it: one palette, role by role.
Palette {
  window: Color.background
  windowText: Color.foreground
  base: Color.token("control.base")
  alternateBase: Color.token("control.alternateBase")
  text: Color.token("control.text")
  button: Color.token("button.background")
  buttonText: Color.token("button.foreground")
  highlight: Color.token("control.highlight")
  highlightedText: Color.token("control.highlightedText")
  toolTipBase: Color.token("tooltip.background")
  toolTipText: Color.token("tooltip.foreground")
  link: Color.token("control.link")
  linkVisited: Color.token("control.linkVisited")
  light: Color.token("control.light")
  midlight: Color.token("control.midlight")
  mid: Color.token("control.mid")
  dark: Color.token("control.dark")
  shadow: Color.token("control.shadow")
  accent: Color.accent
  placeholderText: Color.token("control.placeholderText")
  disabled.text: Color.token("control.disabledText")
  disabled.buttonText: Color.token("button.disabledForeground")
  disabled.windowText: Color.token("text.disabled")
}
