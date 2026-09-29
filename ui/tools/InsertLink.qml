import QtQuick
import "../../design"
import ".." as AppUi
import "../editing"

Tool {
  id: tool
  toolId: "link"
  label: "Insert link"
  icon: "󰌹"
  available: !editor.inCode
  panelPopup: true
  property string linkText: ""
  property string linkUrl: "https://"

  function execute() {
    if (!editor.acceptsInline()) {
      return
    }
    linkText = editor.selection().text
    linkUrl = "https://"
    openPanel()
  }

  function cancel() {
    cancelPanel()
  }

  function submit() {
    var url = linkUrl.trim()
    var text = linkText.trim() || url
    if (!url) {
      cancelPanel()
      return
    }
    submitPanel(function() {
      tool.editor.insertHtml('<a href="' + tool.editor.escapeHtml(url) + '" style="-qt-foreground:none;">'
                             + tool.editor.escapeHtml(text) + "</a>")
    })
  }

  panel: Component {
    ToolForm {
      id: form
      action: tool
      submitButton.objectName: "insertLink"
      onSubmitted: tool.submit()
      Keys.onEscapePressed: tool.cancel()

      function focusInput() {
        if (tool.panelOpen) {
          var field = tool.linkText ? urlField : textField
          field.forceActiveFocus()
          field.cursorPosition = field.text.length
        }
      }

      AppUi.ChromeTextField {
        id: textField
        objectName: "linkText"
        width: parent.width
        text: tool.linkText
        iconText: "󰦨"
        placeholderText: "Link text"
        Accessible.name: "Link text"
        accent: tool.editor.accent
        font.family: form.fontFamily
        onTextEdited: tool.linkText = text
        Keys.onReturnPressed: tool.submit()
        Keys.onEnterPressed: tool.submit()
      }
      AppUi.ChromeTextField {
        id: urlField
        objectName: "linkUrl"
        width: parent.width
        text: tool.linkUrl
        iconText: "󰖟"
        placeholderText: "https://…"
        Accessible.name: "Link URL"
        accent: tool.editor.accent
        font.family: form.fontFamily
        onTextEdited: tool.linkUrl = text
        Keys.onReturnPressed: tool.submit()
        Keys.onEnterPressed: tool.submit()
      }
    }
  }
}
