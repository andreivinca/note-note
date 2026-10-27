import QtQuick
import ".." as AppUi

// Input tools share one popover, the card every form popup has: the tool's
// icon and name, its fields, and a footer that says how to finish beside the
// one action. Escape or a click outside cancels, as it does for every popup.
AppUi.PopupForm {
  required property Tool action
  iconText: action.icon
  title: action.label
  hint: "Enter to insert · Esc to cancel"
  confirmText: "Insert"
  fontFamily: action.editor.fontFamily
  accent: action.editor.accent
}
