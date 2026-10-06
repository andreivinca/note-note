import QtQuick
import "../../design"
import ".." as AppUi

Rectangle {
  id: group
  required property var registry
  required property var tools
  required property Item toolbar
  required property real toolbarOffsetX
  required property Component submenuComponent
  required property AppUi.ChromePopupStyle popupStyle
  required property real buttonHeight
  property bool panelOpen: false
  property bool separatorVisible: true
  property color surfaceColor: Color.token("toolbar.background")
  readonly property var editor: registry.editor
  property real panelPadding: Style.spacing.xs
  readonly property real naturalButtonHeight: {
    var tallest = 0
    for (var i = 0; i < toolsRow.children.length; i++) {
      tallest = Math.max(tallest, toolsRow.children[i].implicitHeight)
    }
    return tallest
  }
  readonly property var buttonMetrics: {
    var count = 0
    var width = 0
    for (var i = 0; i < toolsRow.children.length; i++) {
      var button = toolsRow.children[i]
      if (!button.modelData) {
        continue
      }
      if (registry.isVisible(button.modelData)) {
        width += button.width
        count++
      }
    }
    return { count: count, width: width + Math.max(0, count - 1) * toolsRow.spacing }
  }
  visible: buttonMetrics.count > 0
  implicitWidth: buttonMetrics.width + panelPadding * 2
  implicitHeight: buttonHeight + panelPadding * 2
  width: implicitWidth
  height: implicitHeight
  radius: Style.controlRadius + panelPadding

  Rectangle {
    visible: group.separatorVisible
    // Center the divider in the gap between this group and the next.
    x: group.width + group.toolbar.groupSpacing / 2 - width / 2
    y: group.panelPadding + (group.buttonHeight - height) / 2
    width: Style.spacing.hairline
    height: Style.space(18)
    color: Util.alpha(group.editor.foreground, 0.12)
  }

  Row {
    id: toolsRow
    x: group.panelPadding
    y: group.panelPadding
    height: group.buttonHeight
    spacing: Style.spacing.sm

    Repeater {
      id: buttons
      // Keep controls alive across capability/caret changes so hiding a
      // tool closes its popup without destroying the hovered control.
      model: group.tools
      delegate: Item {
        id: buttonSlot
        required property var modelData
        readonly property alias button: actionButton
        visible: group.registry.isVisible(modelData)
        implicitWidth: actionButton.implicitWidth
        implicitHeight: actionButton.implicitHeight
        width: actionButton.width
        height: group.buttonHeight

        AppUi.ChromeButton {
          id: actionButton
          readonly property var modelData: buttonSlot.modelData
          readonly property bool labeledMenu: modelData.isMenu && modelData.toolbarLabelVisible
          // Popups follow their button as the tools scroll or the editor resizes.
          readonly property real toolbarX: group.toolbarOffsetX + group.x + toolsRow.x + buttonSlot.x + x
          objectName: "editingTool-" + modelData.toolId
          enabled: group.editor.writable && (!modelData.isMenu || menu.rows.length > 0)
          // Dropdowns and icon buttons share the same face geometry.
          anchors.verticalCenter: parent.verticalCenter
          anchors.alignWhenCentered: false
          height: group.buttonHeight
          width: Math.max(implicitWidth, height)
          borderSpec: Border.none()
          // Labeled menus have the same rounded face as selected tools.
          surfaceColor: group.surfaceColor
          backgroundColor: labeledMenu ? selectedColor : "transparent"
          active: menu.opened || modelData.panelOpen
          selected: modelData.checked
          contentForeground: group.editor.foreground
          accent: group.editor.accent
          iconText: modelData.icon
          // A tooltip must not cover an open tool panel or menu.
          tooltipText: group.panelOpen || menu.opened ? "" : modelData.tooltip
          iconSize: Style.font.icon
          horizontalPadding: labeledMenu ? Style.space(12) : Style.spacing.sm
          // Match the inset created by centering an icon in a square tool button.
          leftPadding: iconText.length > 0 && (modelData.isMenu || modelData.panelPopup)
            ? Math.max(horizontalPadding + 1, (height - implicitIconWidth) / 2)
            : horizontalPadding + 1
          verticalPadding: Style.spacing.xxs
          spacing: !labeledMenu && (modelData.isMenu || modelData.panelPopup)
            ? Style.spacing.controlGap / 2 : Style.spacing.controlGap
          text: {
            if (labeledMenu) {
              return modelData.label + " 󰅀"
            }
            return modelData.isMenu || modelData.panelPopup ? "󰅀" : ""
          }
          opacity: enabled ? 1 : 0.45
          fontFamily: group.editor.fontFamily
          fontSize: Style.font.body
          onClicked: {
            if (modelData.isMenu) {
              if (menu.opened) {
                menu.close()
              } else {
                menu.open()
              }
            } else if (modelData.panelPopup && modelData.panelOpen) {
              modelData.cancelPanel()
            } else {
              group.registry.execute(modelData.toolId)
            }
          }
          onVisibleChanged: {
            if (!visible) {
              menu.close()
            }
          }
          Component.onDestruction: menu.close()

          ToolMenu {
            id: menu
            registry: group.registry
            tool: actionButton.modelData
            submenuComponent: group.submenuComponent
            maximumWidth: Math.max(0, group.toolbar.width - Style.spacing.sm * 2)
            popupStyle: group.popupStyle
            x: Math.max(Style.spacing.sm - actionButton.toolbarX,
              Math.min(0, group.toolbar.width - Style.spacing.sm - actionButton.toolbarX - width))
            y: buttonSlot.height - actionButton.y + group.panelPadding + Style.spacing.xxs
          }
        }
      }
    }
  }

  function buttonFor(id) {
    for (var i = 0; i < buttons.count; i++) {
      var slot = buttons.itemAt(i)
      if (slot && slot.modelData.toolId === id) {
        return slot.button
      }
    }
    return null
  }
}
