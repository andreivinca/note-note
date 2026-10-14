import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "ol"
  label: "Numbered list"
  icon: "󰉻"
  splitMenu: true
  toolbarLabelVisible: false
  available: !editor.inCode
  shortcutKey: Qt.Key_Slash
  shortcutModifiers: Qt.ControlModifier

  function execute() {
    editor.toggleListStyle("ol")
  }

  options: [
    Tool {
      editor: tool.editor
      toolId: "numberDecimal"
      capability: "listStyles"
      label: "1, 2, 3  Numbers"
      available: tool.available && editor.canStyleLists
      function execute() {
        editor.setListStyle("decimal")
      }
    },
    Tool {
      editor: tool.editor
      toolId: "numberLowerAlpha"
      capability: "listStyles"
      label: "a, b, c  Lowercase letters"
      available: tool.available && editor.canStyleLists
      function execute() {
        editor.setListStyle("lower-alpha")
      }
    },
    Tool {
      editor: tool.editor
      toolId: "numberUpperAlpha"
      capability: "listStyles"
      label: "A, B, C  Uppercase letters"
      available: tool.available && editor.canStyleLists
      function execute() {
        editor.setListStyle("upper-alpha")
      }
    },
    Tool {
      editor: tool.editor
      toolId: "numberUpperRoman"
      capability: "listStyles"
      label: "I, II, III  Roman numerals"
      available: tool.available && editor.canStyleLists
      function execute() {
        editor.setListStyle("upper-roman")
      }
    },
    Tool {
      editor: tool.editor
      toolId: "numberLowerRoman"
      capability: "listStyles"
      label: "i, ii, iii  Lowercase Roman numerals"
      available: tool.available && editor.canStyleLists
      function execute() {
        editor.setListStyle("lower-roman")
      }
    }
  ]
}
