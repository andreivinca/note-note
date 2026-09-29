import QtQuick
import QtQuick.Controls as QQC
import "../../design"
import "../../design/controls"
import ".." as AppUi

Item {
  id: bar
  required property var registry
  property color background: Color.menu.background
  property color fill: Color.token("toolbar.background")
  property bool toolsVisible: true
  readonly property real groupPadding: Style.spacing.xs
  readonly property real popupMargin: Style.spacing.lg
  // Buttons and dividers share the first row's center. Its height
  // includes both levels of padding and grows with the tallest control.
  readonly property real rowHeight: Math.max(Style.space(44),
    toolFlow.buttonHeight + 2 * (groupPadding + Style.spacing.sm))
  readonly property var editor: registry.editor
  readonly property bool panelOpen: registry.panelOpen
  readonly property var visibleGroupIndexes: {
    var visible = []
    var groups = registry.toolbarGroups
    for (var i = 0; i < groups.length; i++) {
      if (groups[i].tools.some(function(tool) {
        return registry.isVisible(tool)
      })) {
        visible.push(i)
      }
    }
    return visible
  }
  readonly property int lastVisibleGroupIndex: visibleGroupIndexes.length > 0
    ? visibleGroupIndexes[visibleGroupIndexes.length - 1] : -1
  readonly property bool lastGroupAlignsRight: {
    var group = registry.toolbarGroups[lastVisibleGroupIndex]
    return group ? group.tools.length === 1 && group.tools[0].isMenu : false
  }
  // The final menu sits apart from the tool groups, so it has no divider before it.
  readonly property int separatorLimitIndex: lastGroupAlignsRight && visibleGroupIndexes.length > 1
    ? visibleGroupIndexes[visibleGroupIndexes.length - 2] : lastVisibleGroupIndex
  height: visible ? Math.max(rowHeight, strip.implicitHeight) + Style.spacing.hairline : 0

  AppUi.ChromePopupStyle {
    id: chromePopupStyle
  }

  Component {
    id: submenuFactory
    ToolMenu {
      registry: bar.registry
      submenuComponent: submenuFactory
      maximumWidth: toolFlow.width
      popupStyle: chromePopupStyle
    }
  }

  Rectangle {
    anchors.fill: parent
    color: bar.fill
  }

  Column {
    id: strip
    width: parent.width
    padding: Style.spacing.sm
    topPadding: (bar.rowHeight - toolFlow.buttonHeight) / 2 - bar.groupPadding
    bottomPadding: topPadding
    spacing: padding

    Flow {
      id: toolFlow
      visible: bar.toolsVisible
      width: parent.width - parent.leftPadding - parent.rightPadding
      spacing: Style.spacing.lg
      // All groups share the tallest button's height, including text-only
      // dropdowns whose labels are shorter than the icon glyphs.
      readonly property real buttonHeight: {
        var tallest = Style.space(28)
        for (var i = 0; i < children.length; i++) {
          var group = children[i]
          if (group.naturalButtonHeight) {
            tallest = Math.max(tallest, group.naturalButtonHeight)
          }
        }
        return tallest
      }
      Repeater {
        id: groups
        model: bar.registry.toolbarGroups
        delegate: ToolBarGroup {
          required property int index
          required property var modelData
          objectName: "editingToolGroup-" + modelData.id
          registry: bar.registry
          tools: modelData.tools
          toolbarFlow: toolFlow
          submenuComponent: submenuFactory
          popupStyle: chromePopupStyle
          buttonHeight: toolFlow.buttonHeight
          panelPadding: bar.groupPadding
          panelOpen: bar.panelOpen
          separatorVisible: index < bar.separatorLimitIndex
          alignRight: index === bar.lastVisibleGroupIndex && bar.lastGroupAlignsRight
          precedingWidth: {
            var used = 0
            for (var i = 0; i < toolFlow.children.length; i++) {
              var group = toolFlow.children[i]
              if (group.modelData && group.index < index && group.visible) {
                used += group.implicitWidth + toolFlow.spacing
              }
            }
            return used
          }
          color: "transparent"
        }
      }
    }

    Repeater {
      model: bar.registry.actions
      delegate: Loader {
        required property var modelData
        width: strip.width - strip.leftPadding - strip.rightPadding
        // Panels keep their controls while closed. Closing from a control's
        // signal must not destroy that control while its handler is running.
        active: !!modelData.panel && !modelData.panelPopup
        visible: !modelData.panelPopup && modelData.panelOpen && bar.registry.canExecute(modelData)
        sourceComponent: modelData.panel
      }
    }
  }

  function menuContains(tool, id) {
    if (tool.toolId === id) {
      return true
    }
    if (!tool.isMenu) {
      return false
    }
    return bar.registry.menuTools(tool.toolId).some(function(child) {
      return bar.menuContains(child, id)
    })
  }

  function popupX(id, popupWidth) {
    for (var i = 0; i < groups.count; i++) {
      var group = groups.itemAt(i)
      var button = group ? group.buttonFor(id) : null
      if (!button && group) {
        for (var j = 0; j < group.tools.length; j++) {
          if (bar.menuContains(group.tools[j], id)) {
            button = group.buttonFor(group.tools[j].toolId)
            break
          }
        }
      }
      if (button) {
        return Math.max(popupMargin, Math.min(button.toolbarX + popupMargin, bar.width - popupWidth - popupMargin))
      }
    }
    return Math.max(popupMargin, strip.leftPadding)
  }

  Repeater {
    model: bar.registry.actions
    delegate: Loader {
      required property var modelData
      active: !!modelData.panel && modelData.panelPopup
      sourceComponent: Component {
        Item {
          objectName: "editingPopupHolder-" + modelData.toolId
          QQC.Popup {
            id: popup
            palette: ControlPalette {}
            readonly property var tool: modelData
            parent: bar
            objectName: "editingPopup-" + tool.toolId
            popupType: QQC.Popup.Item
            width: Math.min(implicitWidth, Math.max(0, bar.width - 2 * bar.popupMargin))
            x: bar.popupX(tool.toolId, width)
            y: bar.height + bar.popupMargin
            padding: chromePopupStyle.padding + Border.width(chromePopupStyle.borderSpec)
            focus: true
            visible: tool.panelOpen && bar.registry.canExecute(tool)
            closePolicy: QQC.Popup.CloseOnEscape | QQC.Popup.CloseOnPressOutside
            onOpened: {
              var panel = contentItem.item
              if (panel && typeof panel.focusInput === "function") {
                panel.focusInput()
              }
            }
            onClosed: {
              if (tool.panelOpen) {
                tool.cancelPanel()
              }
            }
            background: BorderSurface {
              color: chromePopupStyle.fill
              borderSpec: chromePopupStyle.borderSpec
              radius: chromePopupStyle.radius
            }
            contentItem: Loader {
              sourceComponent: popup.tool.panel
            }
          }
        }
      }
    }
  }

  Rectangle {
    anchors.bottom: parent.bottom
    width: parent.width
    height: Style.spacing.hairline
    color: Util.alpha(bar.editor.foreground, 0.1)
  }
}
