import QtQuick
import QtTest
import "app/ui" as Ui
import "app/services/notes/ordering.js" as Ordering
import "app/services/notes/sidebar.js" as Sidebar

Window {
  id: window
  visible: true
  width: 360
  height: 620
  property int commits: 0
  property var lastGroup: null
  property var lastIds: []

  Ui.NoteList {
    id: list
    anchors.fill: parent
    sections: [{ key: "custom/tab", name: "Notes", count: 4 }]
    activeKey: "custom/tab"
    fontFamily: "sans-serif"
    onReorderFinished: function(group, ids) {
      window.commits++
      window.lastGroup = group
      window.lastIds = ids
      list.model = Ordering.apply(list.model, group, ids)
    }
  }

  TestCase {
    id: checks
    name: "Ordering"
    when: false

    function check(condition, message) {
      if (!condition) {
        throw new Error(message)
      }
    }

    function paths(rows) {
      return rows.map(function(row) {
        return row.path
      }).join(",")
    }

    function item(kind, path, level, scope, descendants) {
      return { kind: kind, path: path, title: path, level: level,
               reorder: scope === undefined ? null : { scope: scope, id: path, descendants: !!descendants } }
    }

    function publish(rows) {
      list.pendingReorders = ({})
      list.filtering = false
      list.model = Sidebar.build([{ id: "custom", canReorder: false,
        sections: [{ key: "tab", rows: rows }] }], "custom/tab", "", {}).rows
      wait(100)
    }

    function row(path) {
      var result = findChild(list, "noteRow-" + path)
      check(!!result, "visible row exists: " + path)
      return result
    }

    function drag(from, to) {
      var source = row(from), target = row(to)
      var start = source.mapToItem(window.contentItem, 70, source.height / 2)
      var end = target.mapToItem(window.contentItem, 70, target.height / 2)
      mousePress(window.contentItem, start.x, start.y, Qt.LeftButton)
      mouseMove(window.contentItem, start.x, start.y + 14, 20)
      wait(30)
      mouseMove(window.contentItem, end.x, end.y, 20)
      wait(40)
      mouseRelease(window.contentItem, end.x, end.y, Qt.LeftButton)
      wait(160)
    }

    function flat() {
      return [item("tree", "section-a", 0), item("note", "a", 1, "a"), item("note", "b", 1, "a"),
              item("tree", "section-b", 0), item("note", "c", 1, "b"), item("note", "d", 1, "b")]
    }

    function run() {
      publish(flat())
      check(list.model[1].reorder.scope === "a" && !("fixed" in list.model[1]),
            "explicit provider groups work without a global reorder flag")
      var legacy = Sidebar.build([{ id: "legacy", canReorder: true, sections: [{ key: "tab", rows: [
        { kind: "note", path: "implied" }, { kind: "note", path: "declined", reorder: null },
        { kind: "note", path: "pinned", fixed: true }] }] }], "legacy/tab", "", {}).rows
      check(legacy[0].reorder.scope === "tab" && legacy[1].reorder === null && legacy[2].reorder === null,
            "an explicit null descriptor opts a row out of the legacy canReorder group")
      var snapshot = JSON.stringify(list.model), group = list.model[1].reorder
      check(Ordering.apply(list.model, group, ["b", "b"]) === null, "duplicate IDs are rejected")
      check(Ordering.apply(list.model, group, ["a"]) === null, "partial groups are rejected")
      check(Ordering.apply(list.model, group, ["b", "c"]) === null, "foreign IDs are rejected")
      check(JSON.stringify(list.model) === snapshot, "validation leaves canonical rows untouched")
      drag("a", "b")
      check(window.commits === 1 && window.lastGroup.scope === "a" && window.lastIds.join(",") === "b,a",
            "drag commits exactly one provider group")
      check(paths(list.model) === "section-a,b,a,section-b,c,d", "other sections retain their order")

      publish(flat())
      drag("a", "c")
      check(window.commits === 1 && paths(list.visualRows()) === "section-a,a,b,section-b,c,d",
            "dropping on another group cannot move a note between sections")

      list.pendingReorders = ({})
      var pending = ({})
      pending[Ordering.key(list.model[1].reorder)] = true
      list.pendingReorders = pending
      drag("a", "b")
      check(window.commits === 1, "a pending group refuses another drag")

      publish([item("tree", "first", 0, "sections", true), item("note", "child-a", 1, "first"),
               item("note", "child-b", 1, "first"), item("tree", "second", 0, "sections", true),
               item("note", "child-c", 1, "second")])
      var expected = "second,child-c,first,child-a,child-b"
      check(paths(Ordering.apply(list.model, list.model[0].reorder, ["second", "first"])) === expected,
            "provider-defined tree reorders preserve entire child blocks")
      drag("first", "second")
      check(window.commits === 2 && paths(list.model) === expected,
            "tree rows and descendants use the same drag interaction")

      publish(flat())
      var source = row("a"), target = row("b")
      var start = source.mapToItem(window.contentItem, 70, source.height / 2)
      var end = target.mapToItem(window.contentItem, 70, target.height / 2)
      mousePress(window.contentItem, start.x, start.y, Qt.LeftButton)
      mouseMove(window.contentItem, start.x, start.y + 14, 20)
      mouseMove(window.contentItem, end.x, end.y, 20)
      wait(30)
      keyClick(Qt.Key_Escape)
      mouseRelease(window.contentItem, end.x, end.y, Qt.LeftButton)
      wait(100)
      check(window.commits === 2 && paths(list.visualRows()) === "section-a,a,b,section-b,c,d",
            "Escape cancels a drag without writing its temporary order")

      var longRows = []
      for (var i = 0; i < 30; i++) {
        longRows.push(item("note", "long-" + i, 0, "long"))
      }
      publish(longRows)
      source = row("long-0")
      start = source.mapToItem(window.contentItem, 70, source.height / 2)
      mousePress(window.contentItem, start.x, start.y, Qt.LeftButton)
      mouseMove(window.contentItem, start.x, start.y + 14, 20)
      mouseMove(window.contentItem, start.x, window.height - 25, 20)
      wait(250)
      check(list.scrollOffset() > 0, "dragging near the viewport edge scrolls a long section")
      mouseRelease(window.contentItem, start.x, window.height - 25, Qt.LeftButton)
      wait(100)

      publish(longRows)
      list.setScrollOffset(0)
      wait(50)
      source = row("long-1")
      target = row("long-5")
      start = source.mapToItem(window.contentItem, 70, source.height / 2)
      end = target.mapToItem(window.contentItem, 70, target.height / 2)
      var fastCommits = window.commits
      // The button held, as on a real drag: the list flicks only then.
      mousePress(window.contentItem, start.x, start.y, Qt.LeftButton)
      mouseMove(window.contentItem, end.x, end.y, 0, Qt.LeftButton)
      wait(30)
      mouseMove(window.contentItem, end.x, end.y + 2, 0, Qt.LeftButton)
      wait(30)
      mouseRelease(window.contentItem, end.x, end.y + 2, Qt.LeftButton)
      wait(160)
      check(list.scrollOffset() === 0 && window.commits === fastCommits + 1
            && window.lastIds.indexOf("long-1") > window.lastIds.indexOf("long-4"),
            "a fast drag on a draggable row reorders instead of scrolling the list")

      publish([item("note", "pinned-a", 0, "pinned"), item("action", "fixed", 0),
               item("note", "pinned-b", 0, "pinned")])
      source = row("pinned-a")
      target = row("pinned-b")
      start = source.mapToItem(window.contentItem, 70, source.height / 2)
      end = target.mapToItem(window.contentItem, 70, target.height / 2)
      mousePress(window.contentItem, start.x, start.y, Qt.LeftButton)
      mouseMove(window.contentItem, start.x, start.y + 14, 20)
      mouseMove(window.contentItem, end.x, end.y, 20)
      wait(30)
      check(paths(list.visualRows()) === "pinned-b,fixed,pinned-a", "fixed rows keep their slots during a drag")
      mouseRelease(window.contentItem, end.x, end.y, Qt.LeftButton)
      wait(100)

      publish(flat())
      list.filtering = true
      wait(100)
      check(list.visualRows().length === 0, "filtered results cannot be reordered")
      console.log("<<<ORDERING_DONE>>>")
      Qt.exit(0)
    }
  }

  Timer {
    interval: 200
    running: true
    onTriggered: {
      try {
        checks.run()
      } catch (error) {
        console.error("FAIL!", error.message)
        Qt.exit(1)
      }
    }
  }
}
