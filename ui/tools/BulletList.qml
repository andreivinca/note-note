import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "ul"
  label: "Bullet list"
  icon: "󰉹"
  splitMenu: true
  toolbarLabelVisible: false
  available: !editor.inCode
  shortcutKey: Qt.Key_Period
  shortcutModifiers: Qt.ControlModifier

  function execute() {
    editor.toggleListStyle("ul")
  }

  options: [
    Tool {
      editor: tool.editor
      toolId: "bulletDisc"
      capability: "ul"
      label: "●  Filled circle"
      available: tool.available && editor.canStyleLists
      function execute() {
        editor.setListStyle("disc")
      }
    },
    Tool {
      editor: tool.editor
      toolId: "bulletCircle"
      capability: "ul"
      label: "○  Hollow circle"
      available: tool.available && editor.canStyleLists
      function execute() {
        editor.setListStyle("circle")
      }
    },
    Tool {
      editor: tool.editor
      toolId: "bulletSquare"
      capability: "ul"
      label: "◾  Square"
      available: tool.available && editor.canStyleLists
      function execute() {
        editor.setListStyle("square")
      }
    }
  ]
}
