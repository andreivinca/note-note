pragma Singleton
import QtQuick

QtObject {
  id: style
  property var source: null
  readonly property int cornerRadius: source ? source.cornerRadius : 6
  readonly property int gapsOut: source ? source.gapsOut : 12
  readonly property string fontFamily: source ? source.fontFamily : Qt.application.font.family
  readonly property var font: source ? source.font : desktopFont
  readonly property var spacing: source ? source.spacing : desktopSpacing
  readonly property color hoverFill: hoverFillFor(Color.foreground, Color.accent)
  readonly property color selectionFill: Util.alpha(Color.accent, 0.35)
  property QtObject desktopFont: QtObject {
    readonly property string family: style.fontFamily
    readonly property string menuFamily: style.fontFamily
    readonly property int baseSize: 14
    readonly property int caption: 11
    readonly property int bodySmall: 12
    readonly property int body: 14
    readonly property int subtitle: 15
    readonly property int title: 16
    readonly property int displayLarge: 32
    readonly property int iconSmall: 14
    readonly property int icon: 18
    readonly property int iconLarge: 22
  }
  property QtObject desktopSpacing: QtObject {
    readonly property int xxs: 2
    readonly property int xs: 4
    readonly property int sm: 8
    readonly property int md: 12
    readonly property int lg: 16
    readonly property int xxxl: 32
    readonly property int hairline: 1
    readonly property int controlGap: 6
    readonly property int controlHeight: 32
    readonly property int controlPaddingX: 10
    readonly property int panelPadding: 20
    readonly property int popupRowHeight: 32
  }
  function space(value) {
    return source ? source.space(value) : value
  }
  function hoverFillFor(foreground, accent) {
    return source ? source.hoverFillFor(foreground, accent) : Util.alpha(foreground, 0.08)
  }
  function pressedFillFor(foreground, accent) {
    return source ? source.pressedFillFor(foreground, accent) : Util.alpha(accent, 0.22)
  }
  function selectedFillFor(foreground, accent) {
    return source ? source.selectedFillFor(foreground, accent) : Util.alpha(accent, 0.18)
  }
  function hoverStateColor(foreground, accent) {
    return source ? source.hoverStateColor(foreground, accent) : foreground
  }
  function selectedStateColor(foreground, accent) {
    return source ? source.selectedStateColor(foreground, accent) : Qt.tint(foreground, Util.alpha(accent, 0.6))
  }
}
