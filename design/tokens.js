.pragma library

// Every colour the application has a name for, and the only list of them.
//
//   recipe      how the colour is derived from `inputs` when nothing supplies
//               it (design/resolve.js)
//   inputs      the tokens that recipe reads, in its order; each stands
//               earlier in this list, which is therefore the order colours
//               are resolved in
//   systemRole  the host role that supplies the colour when a theme says
//               "system"; without one, or on a host that has no such role,
//               the recipe does
//   overlay     the colour may be translucent
//   pair        the background it has to be readable on
var specification = {
  "surface.background": { recipe: "root", inputs: [], systemRole: "background", overlay: false },
  "text.primary": { recipe: "root", inputs: [], systemRole: "foreground", overlay: false, pair: "surface.background" },
  "accent.primary": { recipe: "root", inputs: [], systemRole: "accent", overlay: false, pair: "surface.background" },
  "surface.raised": { recipe: "raised", inputs: ["surface.background", "text.primary"], overlay: false },
  "text.secondary": { recipe: "muted", inputs: ["text.primary"], overlay: true, pair: "surface.background" },
  "text.disabled": { recipe: "disabled", inputs: ["text.primary"], systemRole: "disabledWindowText", overlay: true, pair: "surface.background" },
  "border.default": { recipe: "border", inputs: ["text.primary"], systemRole: "border", overlay: true },
  "border.focus": { recipe: "focus", inputs: ["surface.raised", "text.primary"], overlay: false },
  "overlay.scrim": { recipe: "scrim", inputs: [], systemRole: "scrim", overlay: true },
  "selection.background": { recipe: "selection", inputs: ["accent.primary"], systemRole: "selectedBackground", overlay: true },
  "selection.foreground": { recipe: "alias", inputs: ["accent.primary"], systemRole: "selectedText", overlay: false, pair: "selection.background" },
  "input.background": { recipe: "input", inputs: ["surface.raised", "text.primary"], overlay: false },
  "input.foreground": { recipe: "alias", inputs: ["text.primary"], overlay: false, pair: "input.background" },
  "input.border": { recipe: "inputBorder", inputs: ["surface.raised", "text.primary"], overlay: false },
  "input.placeholder": { recipe: "placeholder", inputs: ["text.primary"], overlay: true, pair: "input.background" },
  "button.background": { recipe: "alias", inputs: ["surface.raised"], systemRole: "button", overlay: false },
  "button.foreground": { recipe: "alias", inputs: ["text.primary"], systemRole: "buttonText", overlay: false, pair: "button.background" },
  "button.disabledForeground": { recipe: "disabled", inputs: ["text.primary"], systemRole: "disabledButtonText", overlay: true, pair: "button.background" },
  "popup.background": { recipe: "alias", inputs: ["surface.raised"], overlay: false },
  "popup.foreground": { recipe: "alias", inputs: ["text.primary"], systemRole: "popupText", overlay: false, pair: "popup.background" },
  "popup.border": { recipe: "inputBorder", inputs: ["popup.background", "text.primary"], overlay: false },
  "tooltip.background": { recipe: "alias", inputs: ["surface.background"], systemRole: "toolTipBase", overlay: false },
  "tooltip.foreground": { recipe: "alias", inputs: ["text.primary"], systemRole: "toolTipText", overlay: false, pair: "tooltip.background" },
  "sidebar.background": { recipe: "sidebar", inputs: ["surface.background", "text.primary"], overlay: false },
  "sidebar.foreground": { recipe: "alias", inputs: ["text.primary"], overlay: false, pair: "sidebar.background" },
  "tab.activeBackground": { recipe: "activeTabBackground", inputs: ["selection.background", "surface.background", "text.primary"], overlay: true },
  "tab.activeForeground": { recipe: "alias", inputs: ["selection.foreground"], overlay: false, pair: "tab.activeBackground" },
  "tab.inactiveForeground": { recipe: "inactiveText", inputs: ["text.primary"], overlay: true, pair: "surface.background" },
  "titlebar.background": { recipe: "alias", inputs: ["sidebar.background"], overlay: false },
  "statusbar.background": { recipe: "alias", inputs: ["surface.background"], overlay: false },
  "statusbar.foreground": { recipe: "alias", inputs: ["text.primary"], overlay: false, pair: "statusbar.background" },
  "editor.background": { recipe: "alias", inputs: ["surface.background"], overlay: false },
  "toolbar.background": { recipe: "alias", inputs: ["editor.background"], overlay: false },
  "editor.foreground": { recipe: "alias", inputs: ["text.primary"], overlay: false, pair: "editor.background" },
  "editor.selectionBackground": { recipe: "textSelection", inputs: ["accent.primary"], overlay: true },
  "editor.selectionForeground": { recipe: "alias", inputs: ["editor.foreground"], overlay: false, pair: "editor.selectionBackground" },
  "editor.link": { recipe: "link", inputs: ["editor.foreground", "accent.primary"], overlay: false, pair: "editor.background" },
  "editor.quoteForeground": { recipe: "quoteInk", inputs: ["editor.background", "editor.foreground"], overlay: false, pair: "editor.background" },
  "editor.quoteBorder": { recipe: "quoteBorder", inputs: ["accent.primary"], overlay: true },
  "editor.codeBackground": { recipe: "code", inputs: ["editor.background"], overlay: false },
  "editor.codeForeground": { recipe: "alias", inputs: ["editor.foreground"], overlay: false, pair: "editor.codeBackground" },
  "editor.inlineCodeBackground": { recipe: "code", inputs: ["editor.background"], overlay: false },
  "editor.highlightBackground": { recipe: "marker", inputs: [], overlay: false },
  "editor.highlightForeground": { recipe: "markerInk", inputs: [], overlay: false, pair: "editor.highlightBackground" },
  "status.error": { recipe: "error", inputs: [], systemRole: "urgent", overlay: false, pair: "surface.background" },
  "palette.background": { recipe: "alias", inputs: ["popup.background"], overlay: false },
  "palette.foreground": { recipe: "alias", inputs: ["popup.foreground"], overlay: false, pair: "palette.background" },
  "palette.selectionBackground": { recipe: "alias", inputs: ["selection.background"], overlay: true },
  "palette.selectionForeground": { recipe: "alias", inputs: ["selection.foreground"], overlay: false, pair: "palette.selectionBackground" },
  "control.base": { recipe: "alias", inputs: ["input.background"], systemRole: "base", overlay: false },
  "control.text": { recipe: "alias", inputs: ["input.foreground"], systemRole: "text", overlay: false },
  "control.alternateBase": { recipe: "alias", inputs: ["surface.raised"], systemRole: "alternateBase", overlay: false },
  "control.highlight": { recipe: "alias", inputs: ["selection.background"], systemRole: "highlight", overlay: true },
  "control.highlightedText": { recipe: "alias", inputs: ["selection.foreground"], systemRole: "highlightedText", overlay: false },
  "control.light": { recipe: "light", inputs: ["surface.background"], systemRole: "light", overlay: false },
  "control.midlight": { recipe: "midlight", inputs: ["surface.background"], systemRole: "midlight", overlay: false },
  "control.mid": { recipe: "mid", inputs: ["surface.background"], systemRole: "mid", overlay: false },
  "control.dark": { recipe: "dark", inputs: ["surface.background"], systemRole: "dark", overlay: false },
  "control.shadow": { recipe: "shadow", inputs: [], systemRole: "shadow", overlay: false },
  "control.placeholderText": { recipe: "placeholder", inputs: ["text.primary"], systemRole: "placeholderText", overlay: true },
  "control.disabledText": { recipe: "disabled", inputs: ["text.primary"], systemRole: "disabledText", overlay: true },
  "control.link": { recipe: "alias", inputs: ["editor.link"], systemRole: "link", overlay: false },
  "control.linkVisited": { recipe: "alias", inputs: ["control.link"], systemRole: "linkVisited", overlay: false }
}
