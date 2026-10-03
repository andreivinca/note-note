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
  readonly property real groupSpacing: Style.spacing.lg
  readonly property real popupMargin: Style.spacing.lg
  // Buttons and dividers share the first row's center. Its height
  // includes both levels of padding and grows with the tallest control.
  readonly property real rowHeight: Math.max(Style.space(44),
    toolRail.buttonHeight + 2 * (groupPadding + Style.spacing.sm))
  readonly property var editor: registry.editor
  readonly property bool panelOpen: registry.panelOpen
  readonly property var insertTool: registry.topLevelTools.find(function(tool) {
    return tool.toolId === "insert" && tool.isMenu
  }) || null
  readonly property var scrollableGroups: registry.toolbarGroups.map(function(group) {
    return { id: group.id, tools: group.tools.filter(function(tool) {
      return tool !== bar.insertTool
    }) }
  }).filter(function(group) {
    return group.tools.length > 0
  })
  readonly property var visibleGroupIndexes: {
    var visible = []
    var groups = scrollableGroups
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
  height: visible ? Math.max(rowHeight, strip.implicitHeight) + Style.spacing.hairline : 0

  AppUi.ChromePopupStyle {
    id: chromePopupStyle
  }

  Component {
    id: submenuFactory
    ToolMenu {
      registry: bar.registry
      submenuComponent: submenuFactory
      maximumWidth: toolRail.width
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
    topPadding: (bar.rowHeight - toolRail.buttonHeight) / 2 - bar.groupPadding
    bottomPadding: topPadding
    spacing: padding

    Item {
      id: toolRail
      visible: bar.toolsVisible
      width: parent.width - parent.leftPadding - parent.rightPadding
      height: buttonHeight + bar.groupPadding * 2
      // All groups share the tallest button's height, including text-only
      // dropdowns whose labels are shorter than the icon glyphs.
      readonly property real buttonHeight: {
        var tallest = Style.space(32)
        for (var i = 0; i < groups.count; i++) {
          var group = groups.itemAt(i)
          if (group) {
            tallest = Math.max(tallest, group.naturalButtonHeight)
          }
        }
        return Math.max(tallest, insertGroup.naturalButtonHeight)
      }

      Flickable {
        id: toolViewport
        objectName: "editingToolViewport"
        width: Math.max(0, toolRail.width - (insertGroup.visible ? insertGroup.width + bar.groupSpacing : 0))
        height: parent.height
        contentWidth: toolRow.width
        contentHeight: height
        flickableDirection: Flickable.HorizontalFlick
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentWidth > width
        clip: true
        onWidthChanged: clampScroll()
        onContentWidthChanged: clampScroll()

        function clampScroll() {
          contentX = Math.max(0, Math.min(contentX, Math.max(0, contentWidth - width)))
        }

        // Match the notebook tabs: both wheel axes move the tools sideways.
        WheelHandler {
          target: null
          acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
          onWheel: function(event) {
            var delta = (event.pixelDelta.x !== 0 || event.pixelDelta.y !== 0)
              ? (event.pixelDelta.x + event.pixelDelta.y) * 3
              : ((event.angleDelta.x + event.angleDelta.y) / 120) * Style.space(56)
            toolViewport.contentX = Math.max(0, Math.min(toolViewport.contentX - delta,
              Math.max(0, toolViewport.contentWidth - toolViewport.width)))
          }
        }

        Row {
          id: toolRow
          height: parent.height
          spacing: bar.groupSpacing

          Repeater {
            id: groups
            model: bar.scrollableGroups
            delegate: ToolBarGroup {
              required property int index
              required property var modelData
              objectName: "editingToolGroup-" + modelData.id
              registry: bar.registry
              surfaceColor: bar.fill
              tools: modelData.tools
              toolbar: bar
              toolbarOffsetX: strip.x + toolRail.x + toolViewport.x - toolViewport.contentX
              submenuComponent: submenuFactory
              popupStyle: chromePopupStyle
              buttonHeight: toolRail.buttonHeight
              panelPadding: bar.groupPadding
              panelOpen: bar.panelOpen
              separatorVisible: index < bar.lastVisibleGroupIndex
              color: "transparent"
            }
          }
        }
      }

      Rectangle {
        anchors.left: toolViewport.left
        height: toolViewport.height
        width: Math.min(Style.space(18), toolViewport.width / 2)
        visible: toolViewport.contentX > 0
        gradient: Gradient {
          orientation: Gradient.Horizontal
          GradientStop {
            position: 0
            color: Util.alpha(bar.fill, 0.95)
          }
          GradientStop {
            position: 1
            color: "transparent"
          }
        }
      }

      Rectangle {
        anchors.right: toolViewport.right
        height: toolViewport.height
        width: Math.min(Style.space(18), toolViewport.width / 2)
        visible: toolViewport.contentX < toolViewport.contentWidth - toolViewport.width - 1
        gradient: Gradient {
          orientation: Gradient.Horizontal
          GradientStop {
            position: 0
            color: "transparent"
          }
          GradientStop {
            position: 1
            color: Util.alpha(bar.fill, 0.95)
          }
        }
      }

      ToolBarGroup {
        id: insertGroup
        objectName: "editingInsertGroup"
        anchors.right: parent.right
        registry: bar.registry
        surfaceColor: bar.fill
        tools: bar.insertTool ? [bar.insertTool] : []
        toolbar: bar
        toolbarOffsetX: strip.x + toolRail.x
        submenuComponent: submenuFactory
        popupStyle: chromePopupStyle
        buttonHeight: toolRail.buttonHeight
        panelPadding: bar.groupPadding
        panelOpen: bar.panelOpen
        separatorVisible: false
        color: "transparent"
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
    for (var i = 0; i <= groups.count; i++) {
      var group = i < groups.count ? groups.itemAt(i) : insertGroup
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
