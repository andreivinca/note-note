import QtQuick

// The theme as Qt's own controls ask for it: one palette, role by role.
Palette {
  window: Colors.background
  windowText: Colors.foreground
  base: Colors.token("control.base")
  alternateBase: Colors.token("control.alternateBase")
  text: Colors.token("control.text")
  button: Colors.token("button.background")
  buttonText: Colors.token("button.foreground")
  highlight: Colors.token("control.highlight")
  highlightedText: Colors.token("control.highlightedText")
  toolTipBase: Colors.token("tooltip.background")
  toolTipText: Colors.token("tooltip.foreground")
  link: Colors.token("control.link")
  linkVisited: Colors.token("control.linkVisited")
  light: Colors.token("control.light")
  midlight: Colors.token("control.midlight")
  mid: Colors.token("control.mid")
  dark: Colors.token("control.dark")
  shadow: Colors.token("control.shadow")
  accent: Colors.accent
  placeholderText: Colors.token("control.placeholderText")
  disabled.text: Colors.token("control.disabledText")
  disabled.buttonText: Colors.token("button.disabledForeground")
  disabled.windowText: Colors.token("text.disabled")
}
