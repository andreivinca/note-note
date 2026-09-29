import QtQuick
import QtQuick.Layouts
import "../../design"
import "../../ui" as AppUi
import "../../ui/editing"
import "Calendar.js" as Calendar

Tool {
  id: tool
  toolId: "customMonth"
  label: "Insert custom month"
  icon: "󰃭"
  panelPopup: true
  capability: "table"
  property int selectedMonth: 0
  property string yearText: ""
  property var calendarLocale: Qt.locale()
  readonly property bool valid: /^[0-9]{1,4}$/.test(yearText)
    && Calendar.validMonth(Number(yearText), selectedMonth)
  readonly property var months: {
    var options = []
    for (var month = 0; month < 12; month++) {
      options.push({ value: String(month), label: calendarLocale.standaloneMonthName(month, Locale.LongFormat) })
    }
    return options
  }

  function execute() {
    var today = new Date()
    calendarLocale = Qt.locale()
    selectedMonth = today.getMonth()
    yearText = String(today.getFullYear())
    openPanel()
  }

  function submit() {
    if (!valid) {
      return false
    }
    return submitPanel(function() {
      tool.editor.insertTable(Calendar.markdown(Number(tool.yearText), tool.selectedMonth, tool.calendarLocale))
    })
  }

  panel: Component {
    ToolForm {
      id: form
      objectName: "customMonthPanel"
      action: tool
      submitButton.objectName: "insertCustomMonth"
      submitButton.enabled: tool.valid
      message: tool.valid ? "" : "Enter a year from 1 to 9999."
      onSubmitted: tool.submit()
      Keys.onEscapePressed: tool.cancelPanel()

      function focusInput() {
        if (tool.panelOpen) {
          yearField.forceActiveFocus()
          yearField.selectAll()
        }
      }

      RowLayout {
        width: parent.width
        spacing: Style.spacing.md
        AppUi.ChromeDropdown {
          id: monthField
          objectName: "customMonthMonth"
          Layout.fillWidth: true
          Layout.preferredWidth: Style.space(180)
          Layout.minimumWidth: 0
          label: "Month"
          options: tool.months
          value: String(tool.selectedMonth)
          accent: tool.editor.accent
          fontFamily: form.fontFamily
          onSelected: function(value) {
            tool.selectedMonth = Number(value)
          }
        }
        AppUi.ChromeTextField {
          id: yearField
          objectName: "customMonthYear"
          Layout.preferredWidth: Style.space(80)
          text: tool.yearText
          placeholderText: "Year"
          Accessible.name: "Year"
          validator: IntValidator { bottom: 1; top: 9999 }
          maximumLength: 4
          inputMethodHints: Qt.ImhDigitsOnly
          accent: tool.editor.accent
          font.family: form.fontFamily
          onTextEdited: tool.yearText = text
          Keys.onReturnPressed: tool.submit()
          Keys.onEnterPressed: tool.submit()
        }
      }
      Connections {
        target: tool
        function onPanelOpenChanged() {
          if (!tool.panelOpen) {
            monthField.close()
          }
        }
      }
    }
  }
}
