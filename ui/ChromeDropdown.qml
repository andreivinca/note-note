import QtQuick
import QtQuick.Controls as QQC
import "../design"
import "../design/controls" as Controls

// A choice field with the same surface and dimensions as ChromeTextField.
Controls.Dropdown {
  id: control
  foreground: controlStyle.text
  fontFamily: Style.font.menuFamily
  implicitHeight: Math.max(controlStyle.height, implicitContentHeight + topPadding + bottomPadding)
  leftPadding: Style.spacing.controlPaddingX + controlStyle.borderWidth
  rightPadding: leftPadding + indicator.width + Style.spacing.controlGap
  topPadding: Style.spacing.xs + controlStyle.borderWidth
  bottomPadding: topPadding
  hoverEnabled: true
  Accessible.name: label

  ChromeControlStyle {
    id: controlStyle
  }
  ChromePopupStyle {
    id: popupStyle
  }

  contentItem: Text {
    text: control.displayText
    textFormat: Text.PlainText
    font: control.font
    color: control.foreground
    verticalAlignment: Text.AlignVCenter
    elide: Text.ElideRight
  }
  indicator: Text {
    x: control.width - width - control.leftPadding
    y: (control.height - height) / 2
    text: "󰅀"
    font.family: Style.font.family
    font.pixelSize: Style.font.iconSmall
    color: Style.secondaryText(control.foreground, 0.65)
  }
  background: Rectangle {
    radius: controlStyle.radius
    color: controlStyle.fill
    border.width: controlStyle.borderWidth
    border.color: control.activeFocus ? controlStyle.focusBorderColor : controlStyle.borderColor
  }

  delegate: QQC.ItemDelegate {
    id: option
    required property var modelData
    required property int index
    width: ListView.view.width
    implicitHeight: Math.max(popupStyle.rowHeight, implicitContentHeight + topPadding + bottomPadding)
    text: modelData.label
    font: control.font
    highlighted: control.highlightedIndex === index
    hoverEnabled: true
    leftPadding: popupStyle.horizontalPadding
    rightPadding: leftPadding
    topPadding: popupStyle.verticalPadding
    bottomPadding: topPadding
    contentItem: Text {
      text: option.text
      textFormat: Text.PlainText
      font: option.font
      color: popupStyle.text
      elide: Text.ElideRight
      verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
      radius: popupStyle.rowRadius
      color: option.highlighted ? Style.hoverFillFor(popupStyle.text, control.accent) : "transparent"
    }
  }
  popup: QQC.Popup {
    y: control.height + Style.spacing.xs
    width: control.width
    implicitHeight: contentItem.implicitHeight + topPadding + bottomPadding
    height: Math.min(implicitHeight, Math.max(0, control.Window.height - 2 * margins))
    margins: Style.spacing.lg
    padding: popupStyle.padding + Border.width(popupStyle.borderSpec)
    popupType: QQC.Popup.Item
    closePolicy: QQC.Popup.CloseOnEscape | QQC.Popup.CloseOnPressOutsideParent
    contentItem: ListView {
      implicitHeight: contentHeight
      model: control.delegateModel
      currentIndex: control.highlightedIndex
      highlightMoveDuration: 0
      clip: true
      boundsBehavior: Flickable.StopAtBounds
      QQC.ScrollIndicator.vertical: QQC.ScrollIndicator {}
    }
    background: Controls.BorderSurface {
      color: popupStyle.fill
      radius: popupStyle.radius
      borderSpec: popupStyle.borderSpec
    }
  }
}
