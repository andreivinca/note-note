import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import ".."

Controls.AbstractButton {
  id: button
  property string iconText: ""
  property string tooltipText: ""
  property bool selected: false
  property bool active: false
  property bool focusable: false
  property bool bordered: false
  property color foreground: Color.foreground
  property color backgroundColor: "transparent"
  property color accent: Color.accent
  property color hoverColor: Style.hoverFillFor(foreground, accent)
  property color pressedColor: Style.pressedFillFor(foreground, accent)
  property color selectedColor: Style.selectedFillFor(foreground, accent)
  property color selectedForeground: Style.selectedStateColor(foreground, accent)
  readonly property color contentColor: selected || active ? selectedForeground : foreground
  property string fontFamily: Style.font.family
  property real fontSize: Style.font.body
  property real iconSize: Style.font.icon
  horizontalPadding: Style.spacing.controlPaddingX
  verticalPadding: Style.spacing.xs
  property real radius: Style.cornerRadius
  property var borderSpec: bordered || activeFocus ? Border.flat(Util.alpha(foreground, 0.4), 1) : Border.none()
  signal rightClicked()

  leftPadding: horizontalPadding + 1
  rightPadding: horizontalPadding + 1
  topPadding: verticalPadding + 1
  bottomPadding: verticalPadding + 1
  implicitWidth: implicitContentWidth + leftPadding + rightPadding
  implicitHeight: implicitContentHeight + topPadding + bottomPadding
  hoverEnabled: true
  focusPolicy: focusable ? Qt.StrongFocus : Qt.NoFocus
  Accessible.name: text || tooltipText
  opacity: enabled ? 1 : 0.5

  background: BorderSurface {
    radius: button.radius
    borderSpec: button.borderSpec
    color: button.down ? button.pressedColor
      : button.hovered || button.activeFocus ? button.hoverColor
      : button.selected || button.active ? button.selectedColor
      : button.backgroundColor
    Behavior on color {
      ColorAnimation {
        duration: 120
      }
    }
  }
  contentItem: Item {
    implicitWidth: contentRow.implicitWidth
    implicitHeight: contentRow.implicitHeight

    RowLayout {
      id: contentRow
      x: (parent.width - width) / 2
      anchors.verticalCenter: parent.verticalCenter
      anchors.alignWhenCentered: false
      spacing: Style.spacing.controlGap

      Item {
        visible: button.iconText.length > 0
        implicitWidth: iconGlyph.implicitWidth
        implicitHeight: iconGlyph.implicitHeight
        Layout.alignment: Qt.AlignVCenter

        TextMetrics {
          id: iconMetrics
          font: iconGlyph.font
          text: iconGlyph.text
        }

        // Center the visible glyph within its font spacing box, keeping
        // button sizes and icon-to-label spacing independent of bearings.
        Text {
          id: iconGlyph
          x: (parent.width - iconMetrics.tightBoundingRect.width) / 2
            - iconMetrics.tightBoundingRect.x
          y: (parent.height - iconMetrics.tightBoundingRect.height) / 2
            - baselineOffset - iconMetrics.tightBoundingRect.y
          text: button.iconText
          textFormat: Text.PlainText
          color: button.contentColor
          font.family: button.fontFamily
          font.pixelSize: button.iconSize
          renderType: Text.NativeRendering
        }
      }
      Text {
        visible: button.text.length > 0
        text: button.text
        textFormat: Text.PlainText
        color: button.contentColor
        font.family: button.fontFamily
        font.pixelSize: button.fontSize
        Layout.alignment: Qt.AlignVCenter
      }
    }
  }
  Controls.ToolTip.visible: hovered && tooltipText.length > 0
  Controls.ToolTip.text: tooltipText
  Controls.ToolTip.delay: 400
  HoverHandler {
    cursorShape: Qt.PointingHandCursor
  }
  TapHandler {
    acceptedButtons: Qt.RightButton
    onTapped: button.rightClicked()
  }
}
