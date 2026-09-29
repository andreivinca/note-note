import NoteNote.Extensions 1.0

// A toolbar button with an editor shortcut. Its editor is the one every
// editing tool is given: this inserts text at the caret in one undo step.
// A code block's text is literal, so the button hides inside one.
Tool {
  toolId: "insertHello"
  label: "Insert hello"
  icon: "+"
  available: !editor.inCode
  shortcutKey: Qt.Key_H
  shortcutModifiers: Qt.ControlModifier | Qt.AltModifier

  function execute() {
    editor.insertHtml(editor.escapeHtml("Hello"))
  }
}
