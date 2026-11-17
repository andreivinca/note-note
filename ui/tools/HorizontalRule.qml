import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "rule"
  label: "Horizontal rule"
  icon: "󰍴"

  // What a host without the native helper inserts; the helper inserts the
  // writer's own rendering of it (cpp/dialect.h, RULE_HTML).
  readonly property string markdown: "---"

  function execute() {
    editor.insertRule(markdown)
  }
}
