import QtQuick
import "../../design"
import ".." as AppUi
import "../editing"

Tool {
  id: tool
  toolId: "link"
  label: "Insert link"
  icon: "󰌹"
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
      var range = tool.editor.selection()
      if (tool.editor.selectionInCode()) {
        tool.editor.typeInCode(range.from, range.to, "[" + text + "](" + url + ")")
      } else {
        tool.editor.insertHtml('<a href="' + tool.editor.escapeHtml(url) + '" style="-qt-foreground:none;">'
                               + tool.editor.escapeHtml(text) + "</a>")
      }
    })
  }

  panel: Component {
    ToolForm {
      id: form
      action: tool
      submitButton.objectName: "insertLink"
      cancelButton.objectName: "cancelLink"
      onSubmitted: tool.submit()
      Keys.onEscapePressed: tool.cancel()

      function focusInput() {
        if (tool.panelOpen) {
          var field = tool.linkText ? urlField : textField
          field.forceActiveFocus()
          field.cursorPosition = field.text.length
        }
      }

      Column {
        width: parent.width
        spacing: Style.spacing.sm
        Text {
          text: "Text"
          color: Util.alpha(form.foreground, 0.7)
          font.family: form.fontFamily
          font.pixelSize: Style.font.bodySmall
        }
        AppUi.ChromeTextField {
          id: textField
          objectName: "linkText"
          width: parent.width
          text: tool.linkText
          placeholderText: "Link text"
          Accessible.name: "Link text"
          foreground: form.foreground
          accent: tool.editor.accent
          font.family: form.fontFamily
          onTextEdited: tool.linkText = text
          Keys.onReturnPressed: tool.submit()
          Keys.onEnterPressed: tool.submit()
        }
      }
      Column {
        width: parent.width
        spacing: Style.spacing.sm
        Text {
          text: "URL"
          color: Util.alpha(form.foreground, 0.7)
          font.family: form.fontFamily
          font.pixelSize: Style.font.bodySmall
        }
        AppUi.ChromeTextField {
          id: urlField
          objectName: "linkUrl"
          width: parent.width
          text: tool.linkUrl
          placeholderText: "https://…"
          Accessible.name: "Link URL"
          foreground: form.foreground
          accent: tool.editor.accent
          font.family: form.fontFamily
          onTextEdited: tool.linkUrl = text
          Keys.onReturnPressed: tool.submit()
          Keys.onEnterPressed: tool.submit()
        }
      }
    }
  }
}
