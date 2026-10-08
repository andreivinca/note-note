import QtQuick
import "../../design"
import "../../design/controls"
import "../../services/platform"
import ".." as AppUi
import "../editing"
import "Diacritics.js" as Diacritics

Tool {
  id: tool
  toolId: "diacritics"
  label: "Diacritics"
  icon: "á"
  // Literal text needs no provider-specific formatting capability.
  capability: ""
  panelPopup: true
  property var systemRegion: SystemRegion {}
  property string countryCode: systemRegion.countryCode
  // The timezone's country preselects a language until the user picks one.
  property string chosenLanguage: ""
  readonly property string language: chosenLanguage || Diacritics.regionLanguage(countryCode)
  readonly property var languages: Diacritics.languages()
  readonly property var alphabet: Diacritics.alphabet(language)
  readonly property var characters: alphabet ? Array.from(alphabet.lower + alphabet.upper) : []

  function execute() {
    openPanel()
  }

  function choose(character) {
    if (characters.indexOf(character) < 0) {
      return false
    }
    return submitPanel(function() {
      tool.editor.insertText(character)
    })
  }

  panel: Component {
    Item {
      id: picker
      implicitWidth: Style.space(260)
      implicitHeight: content.implicitHeight
      readonly property int columns: Math.max(1, Math.min(6, tool.alphabet ? tool.alphabet.lower.length : 6,
        Math.floor((width + Style.spacing.xs) / (Style.space(36) + Style.spacing.xs))))

      function focusInput() {
        if (!tool.panelOpen) {
          return
        }
        if (letters.count > 0) {
          letters.itemAt(0).forceActiveFocus()
        } else {
          languageField.forceActiveFocus()
        }
      }

      Column {
        id: content
        width: parent.width
        spacing: Style.spacing.sm

        AppUi.ChromeDropdown {
          id: languageField
          objectName: "diacriticsLanguage"
          width: parent.width
          label: "Language"
          options: tool.languages
          value: tool.language
          displayText: currentIndex < 0 ? "Choose a language" : currentText
          accent: tool.editor.accent
          fontFamily: tool.editor.fontFamily
          onSelected: function(value) {
            tool.chosenLanguage = value
          }
        }

        Grid {
          width: parent.width
          columns: picker.columns
          spacing: Style.spacing.xs

          Repeater {
            id: letters
            model: tool.characters
            delegate: Button {
              required property string modelData
              required property int index
              objectName: "diacritics-" + modelData
              width: (picker.width - (picker.columns - 1) * Style.spacing.xs) / picker.columns
              height: Style.space(36)
              text: modelData
              Accessible.name: "Insert " + modelData
              focusable: true
              foreground: Color.token("popup.foreground")
              accent: tool.editor.accent
              fontFamily: tool.editor.noteFontFamily
              fontSize: Math.round(Style.font.body * 1.4)
              onClicked: tool.choose(modelData)
              Keys.onReturnPressed: tool.choose(modelData)
              Keys.onEnterPressed: tool.choose(modelData)
              Keys.onPressed: function(event) {
                var next = index
                if (event.key === Qt.Key_Right) {
                  next++
                } else if (event.key === Qt.Key_Left) {
                  next--
                } else if (event.key === Qt.Key_Down) {
                  next += picker.columns
                } else if (event.key === Qt.Key_Up) {
                  next -= picker.columns
                } else {
                  return
                }
                if (next >= 0 && next < letters.count) {
                  letters.itemAt(next).forceActiveFocus()
                } else if (event.key === Qt.Key_Up) {
                  languageField.forceActiveFocus()
                }
                event.accepted = true
              }
            }
          }
        }
      }
      Connections {
        target: tool
        function onPanelOpenChanged() {
          if (!tool.panelOpen) {
            languageField.close()
          }
        }
      }
    }
  }
}
