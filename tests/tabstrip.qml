import QtQuick
import QtTest
import "app/ui" as Ui

Window {
  id: window
  visible: true
  width: 960
  height: 180
  color: tabs.activeBackground
  property int activations: 0
  property string lastActivated: ""
  readonly property real pixelRatio: Screen.devicePixelRatio

  Rectangle {
    id: rail
    width: tabs.width
    height: tabs.railHeight
    color: tabs.background

    Ui.TabStrip {
      id: tabs
      anchors.bottom: parent.bottom
      width: 920
      height: implicitHeight
      fontFamily: "sans-serif"
      fontSize: 13
      background: "#505060"
      activeBackground: "#161c28"
      activeForeground: "white"
      inactiveForeground: "white"
      activeKey: "middle"
      sections: [
        { key: "left", name: "Ideas" },
        { key: "middle", name: "A notebook with a long name that needs to elide" },
        { key: "right", name: "Shared library", logo: Qt.resolvedUrl("app/plugins/org.note-note.notion/logo.svg") }
      ]
      onActivated: function(key) {
        window.activations++
        window.lastActivated = key
        activeKey = key
      }
    }
  }

  TestCase {
    id: checks
    name: "TabStrip"
    when: false

    function check(condition, message) {
      if (!condition) {
        throw new Error(message)
      }
    }

    function equal(actual, expected, message) {
      if (actual !== expected) {
        throw new Error(message + ": " + actual + " != " + expected)
      }
    }

    function tab(key) {
      var item = findChild(tabs, "notebookTab-" + key)
      check(item !== null, "tab exists: " + key)
      return item
    }

    function box(item) {
      var point = item.mapToItem(rail, tabs.tabRadius, 0)
      return { x: point.x, y: point.y, width: item.faceWidth, height: item.height }
    }

    function placements() {
      return tabs.sections.map(function(section) {
        var bounds = box(tab(section.key))
        return [bounds.x, bounds.width]
      })
    }

    function select(key) {
      mouseMove(window.contentItem, 0, window.height - 1)
      tabs.activeKey = key
      wait(160)
    }

    function expectPixel(image, x, y, color, message) {
      var scale = window.pixelRatio
      var px = Math.floor(x * scale)
      var py = Math.floor(y * scale)
      var difference = Math.max(Math.abs(image.red(px, py) - color.r * 255),
        Math.abs(image.green(px, py) - color.g * 255),
        Math.abs(image.blue(px, py) - color.b * 255))
      check(difference < 20, message + " at " + x + ", " + y + ": " + image.pixel(px, py))
    }

    function checkNeighbor(key, side) {
      select("middle")
      var active = box(tab("middle"))
      var neighbor = tab(key)
      var inactive = box(neighbor)
      var gap = side > 0 ? inactive.x - active.x - active.width
        : active.x - inactive.x - inactive.width
      check(gap > 0 && gap < tabs.tabRadius, "neighboring faces have a compact gap")
      mouseMove(neighbor, neighbor.width / 2, tabs.faceHeight / 2)
      wait(160)
      var image = grabImage(window.contentItem)

      // Along each shoulder, the rail separates the painted curves on
      // both sides of the gap, rather than either tab painting over it.
      var radius = tabs.selectedRadius
      var centerX = side > 0 ? active.x + active.width + radius : active.x - radius
      var centerY = rail.height - radius
      var hoverRadius = tabs.tabRadius - tabs.bottomInset
      var hoverCenterX = side > 0 ? inactive.x + hoverRadius
        : inactive.x + inactive.width - hoverRadius
      var hoverCenterY = rail.height - tabs.bottomInset - hoverRadius
      for (var angle of [20, 40, 60]) {
        var radians = angle * Math.PI / 180
        var cosine = Math.cos(radians)
        var sine = Math.sin(radians)
        expectPixel(image, centerX - side * (radius + 1) * cosine,
          centerY + (radius + 1) * sine, tabs.activeBackground, "selected shoulder")
        expectPixel(image, hoverCenterX - side * (hoverRadius - 1) * cosine,
          hoverCenterY + (hoverRadius - 1) * sine, tabs.activeBackground, "hover corner")
        var selectedX = centerX - side * radius * cosine
        var selectedY = centerY + radius * sine
        var hoverX = hoverCenterX - side * hoverRadius * cosine
        var hoverY = hoverCenterY + hoverRadius * sine
        expectPixel(image, (selectedX + hoverX) / 2, (selectedY + hoverY) / 2,
          tabs.background, "clear curve gap")
      }

      // The selected shoulder reaches into the neighbor's rectangular
      // slot. A click on that painted shoulder must belong to the selected tab.
      var shoulderX = side > 0 ? active.x + active.width + radius / 3
        : active.x - radius / 3
      var count = window.activations
      mouseClick(rail, shoulderX, rail.height - 1)
      equal(window.activations, count + 1, "painted shoulder accepts clicks")
      equal(window.lastActivated, "middle", "shoulder does not activate its neighbor")

      count = window.activations
      var gapX = side > 0 ? active.x + active.width + gap / 2 : active.x - gap / 2
      mouseClick(rail, gapX, active.y + radius + 1)
      equal(window.activations, count, "empty rail does not activate either tab")

      var before = placements()
      mouseClick(neighbor, neighbor.width / 2, tabs.faceHeight / 2)
      equal(window.lastActivated, key, "hover face selects its own notebook")
      equal(JSON.stringify(placements()), JSON.stringify(before), "selection keeps face widths and positions")
    }

    function checkScrolling() {
      tabs.width = 320
      select("right")
      function fullyVisible(key) {
        var bounds = box(tab(key))
        return bounds.x - tabs.tabRadius >= -0.5
          && bounds.x + bounds.width + tabs.tabRadius <= tabs.width + 0.5
      }
      tryVerify(function() {
        return fullyVisible("right")
      }, 1000, "last selected tab includes its shoulder at the overflow edge")
      var beforeWheel = box(tab("left")).x
      mouseWheel(tabs, tabs.width / 2, tabs.height / 2, 0, 120)
      tryVerify(function() {
        return box(tab("left")).x > beforeWheel
      }, 1000, "vertical wheel scrolls the narrow strip horizontally")
      select("left")
      tryVerify(function() {
        return fullyVisible("left")
      }, 1000, "first selected tab includes its shoulder")
      select("right")
      tabs.width = 260
      tryVerify(function() {
        return fullyVisible("right")
      }, 1000, "resizing reveals the entire selected tab")
      tabs.width = 920
    }

    function run() {
      for (var size of [11, 13, 20]) {
        tabs.fontSize = size
        select("middle")
        checkNeighbor("left", -1)
        checkNeighbor("right", 1)
        checkScrolling()
      }
      console.error("<<<TABSTRIP_DONE>>>")
      Qt.quit()
    }
  }

  Timer {
    interval: 100
    running: true
    onTriggered: {
      try {
        checks.run()
      } catch (error) {
        console.error("FAIL!", error.message, error.stack)
        Qt.exit(1)
      }
    }
  }
}
