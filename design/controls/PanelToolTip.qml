import QtQuick
import QtQuick.Controls as Controls
import ".."

Controls.ToolTip {
  id: tip
  property color panelForeground: Colors.token("tooltip.foreground")
  property color panelBackground: Colors.token("tooltip.background")
  property color panelBorder: Colors.menu.border
  property string fontFamily: Style.font.family
  property real fontSize: Style.font.bodySmall
  delay: 400
  background: Rectangle {
    color: tip.panelBackground
    border.color: tip.panelBorder
    radius: Style.cornerRadius
  }
  contentItem: Text {
    text: tip.text
    textFormat: Text.PlainText
    color: tip.panelForeground
    font.family: tip.fontFamily
    font.pixelSize: tip.fontSize
  }
}
