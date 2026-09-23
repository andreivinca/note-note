import QtQuick
import ".."

Rectangle {
  property var borderSpec: Border.none()
  property real padding: 0
  property real topPadding: padding
  property real rightPadding: padding
  property real bottomPadding: padding
  property real leftPadding: padding
  readonly property real contentTopInset: Border.width(borderSpec) + topPadding
  readonly property real contentRightInset: Border.width(borderSpec) + rightPadding
  readonly property real contentBottomInset: Border.width(borderSpec) + bottomPadding
  readonly property real contentLeftInset: Border.width(borderSpec) + leftPadding
  border.width: Border.width(borderSpec)
  border.color: borderSpec ? borderSpec.color : "transparent"
}
