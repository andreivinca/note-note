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
  property var moves: []
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
      // Kept as the host keeps it: the tab taken out and put back before
      // `before`, or last.
      onMoved: function(key, before) {
        window.moves = window.moves.concat([key + ">" + before])
        var moving = sections.find(function(section) { return section.key === key })
        var rest = sections.filter(function(section) { return section.key !== key })
        var at = before ? rest.findIndex(function(section) { return section.key === before }) : rest.length
        rest.splice(at, 0, moving)
        sections = rest
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

    function order() {
      return tabs.sections.map(function(section) { return section.key }).join()
    }

    // Takes hold of a tab's face and carries it across the rail to `toX`,
    // waiting there for `hold` ms before letting go.
    function drag(key, toX, hold) {
      var from = box(tab(key))
      var x = from.x + from.width / 2, y = from.y + tabs.faceHeight / 2
      mousePress(rail, x, y)
      for (var i = 1; i <= 12; i++) {
        mouseMove(rail, x + (toX - x) * i / 12, y, -1, Qt.LeftButton)
      }
      if (hold) {
        wait(hold)
      }
      mouseRelease(rail, toX, y)
      wait(50)
    }

    function checkDragging() {
      select("middle")
      var count = window.activations
      window.moves = []
      var right = box(tab("right"))
      drag("left", right.x + right.width * 0.75)
      equal(window.moves.join(), "left>", "a tab dragged past the last one goes last")
      equal(order(), "middle,right,left", "the strip shows the order it is given back")
      equal(window.activations, count, "a drag is not a click")

      var middle = box(tab("middle"))
      drag("left", middle.x + middle.width * 0.25)
      equal(window.moves.join(), "left>,left>middle", "a tab dragged before the first one goes first")
      equal(order(), "left,middle,right", "the tabs are back in their first order")

      var left = box(tab("left"))
      drag("left", left.x + left.width / 2 + 3)
      equal(window.moves.length, 2, "a drag that ends where it began moves nothing")
      equal(window.activations, count + 1, "a press that hardly moves is a click")

      // Held beyond either end of the row, a dragged tab stops at the last
      // slot or the first, and let go where it began it moves nothing.
      var held = box(tab("middle"))
      var hx = held.x + held.width / 2, hy = held.y + tabs.faceHeight / 2
      var far = tabs.width - 2, near = 2
      var dragged = tab("middle")
      mousePress(rail, hx, hy)
      for (var step = 1; step <= 12; step++) {
        mouseMove(rail, hx + (far - hx) * step / 12, hy, -1, Qt.LeftButton)
      }
      tryVerify(function() {
        return dragged.x > 0 && Math.abs(dragged.mapToItem(dragged.parent, 0, 0).x - dragged.x) < 0.5
      }, 1000, "a tab held past the end stops at the last slot")
      for (step = 1; step <= 12; step++) {
        mouseMove(rail, far + (near - far) * step / 12, hy, -1, Qt.LeftButton)
      }
      tryVerify(function() {
        return dragged.x === 0 && Math.abs(dragged.mapToItem(dragged.parent, 0, 0).x) < 0.5
      }, 1000, "a tab held before the start stops at the first slot")
      for (step = 1; step <= 6; step++) {
        mouseMove(rail, near + (hx - near) * step / 6, hy, -1, Qt.LeftButton)
      }
      mouseRelease(rail, hx, hy)
      equal(window.moves.length, 2, "a tab carried to both ends and back moves nothing")
      equal(order(), "left,middle,right", "the order stays")

      // The sections change under the drag: the tabs are built again and
      // the drag has nothing left to drop.
      var start = box(tab("left"))
      var x = start.x + start.width / 2, y = start.y + tabs.faceHeight / 2
      mousePress(rail, x, y)
      for (var i = 1; i <= 6; i++) {
        mouseMove(rail, x + i * 20, y, -1, Qt.LeftButton)
      }
      check(tabs.dragTab !== null, "the tab is being dragged")
      tabs.sections = tabs.sections.slice()
      mouseRelease(rail, x + 120, y)
      check(tabs.dragTab === null, "a new set of tabs ends the drag")
      equal(window.moves.length, 2, "a drag whose tabs were built again moves nothing")
      equal(order(), "left,middle,right", "the order stays")
    }

    // An overflowing strip scrolls under a tab held at its end, rather than
    // flicking away under the one being dragged.
    function checkDraggingAcross() {
      tabs.width = 320
      select("left")
      tryVerify(function() {
        return box(tab("left")).x - tabs.tabRadius >= -0.5
      }, 1000, "the strip starts at its first tab")
      window.moves = []
      drag("left", rail.x + tabs.width - 4, 1500)
      equal(window.moves.join(), "left>", "a tab held at the end scrolls the strip to the last place")
      equal(order(), "middle,right,left", "the overflowing strip shows the new order")
      tabs.width = 920
      var middle = box(tab("middle"))
      drag("left", middle.x + middle.width * 0.25)
      equal(order(), "left,middle,right", "the tabs are back in their first order")
    }

    function run() {
      for (var size of [11, 13, 20]) {
        tabs.fontSize = size
        select("middle")
        checkNeighbor("left", -1)
        checkNeighbor("right", 1)
        checkScrolling()
        checkDragging()
        checkDraggingAcross()
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
