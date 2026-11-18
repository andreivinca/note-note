import QtQuick
import "../editing"

Tool {
  id: tool
  toolId: "table"
  label: "Insert a table"
  icon: "󰓫"

  // What a host without the native helper inserts, and what goes inside a
  // table cell; the helper inserts the writer's own rendering of it
  // elsewhere (cpp/dialect.h, EMPTY_TABLE_HTML).
  readonly property string markdown: "|  |  |\n|---|---|\n|  |  |"

  function execute() {
    if (!editor.insertEmptyTable()) {
      editor.insertTable(markdown)
    }
  }
}
