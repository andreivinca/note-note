import QtQuick
import Quickshell
import "app/hosts/omarchy" as Omarchy
import "app/services/platform"
import "app/ui" as Ui
import "app/services/notes" as Notes
import "app/services/providers" as Providers
import "app/services/processes"
import "app/services/files"
import "app/plugins/org.note-note.local" as Local
import "app/plugins/org.note-note.onenote" as OneNote
import "app/plugins/org.note-note.sticky" as Sticky
import "app/plugins/org.note-note.notion" as Notion
import "app/services/microsoft" as Microsoft
import "app/services/notes/sidebar.js" as Sidebar
import "app/services/notes/ordering.js" as Ordering
import "app/services/providers/plan.js" as Plan
import "app/services/shortcuts" as Shortcuts
import "app/services/settings/settings.js" as Settings
import "app/ui/MarkdownBlocks.js" as Blocks
import "app/ui/Dialect.js" as Dialect
import "app/ui/editing/ToolbarSettings.js" as ToolbarSettings
import "app/tests" as Tests

ShellRoot {
  id: test
  Omarchy.Backend {
    id: backend
  }
  property var results: []
  property int processes: 0
  // What this run covers (tests/transition_selftest.py, --suite): "core" is
  // the controllers, providers and hosts here; any other suite is a group
  // of real-key editor scenarios, which EditorKeys runs by itself.
  readonly property string suite: Platform.env("NOTE_NOTE_TEST_SUITE")
  readonly property bool core: test.suite === "core"
  property bool localFinished: !test.core
  property bool watchFinished: !test.core
  property bool editorFinished: false
  property var appHost: null
  function hostOrderingCases() {
    var app = test.appHost
    var calls = [], complete = null
    var source = { id: "ordering", name: "Ordering", sections: [{ key: "s", name: "Notes", rows: [
      { kind: "note", path: "ordering:a", title: "A", reorder: { scope: "group", id: "a" } },
      { kind: "note", path: "ordering:b", title: "B", reorder: { scope: "group", id: "b" } }
    ] }], reorder: function(scope, ids, callback) {
      calls.push({ scope: scope, ids: ids })
      complete = callback
    } }
    app.providers = [source]
    app.activeSection = "ordering/s"
    app.filterText = ""
    app.rebuildRows()
    var group = app.rows[0].reorder
    var published = app.revision
    app.reorderItems(group, ["b", "a"])
    check("host sends opaque provider group and item IDs", calls.length === 1 && calls[0].scope === "group"
          && calls[0].ids.join(",") === "b,a")
    check("a pending order is published by rebuildRows, which keeps the list's scroll position",
          app.revision > published)
    check("pending order projects without mutating provider rows", app.rows[0].path === "ordering:b"
          && source.sections[0].rows[0].path === "ordering:a")
    app.rebuildRows()
    check("inventory refresh preserves an in-flight order", app.rows[0].path === "ordering:b")
    complete({ error: "write failed" })
    check("failed reorder returns to canonical rows and reports the error", app.rows[0].path === "ordering:a"
          && Object.keys(app.pendingReorders).length === 0 && app.statusText.indexOf("write failed") >= 0)
    complete({})
    check("reorder callback settles once", app.rows[0].path === "ordering:a")
    app.reorderItems(group, ["b", "b"])
    check("host rejects duplicate and partial order requests", calls.length === 1)
    // A drag while an order is saving: its order is sent as well and holds
    // the group, which only its own answer settles.
    app.reorderItems(group, ["b", "a"])
    var older = complete
    app.reorderItems(group, ["a", "b"])
    check("a drag while an order is saving sends the newer order as well", calls.length === 3
          && calls[2].ids.join(",") === "a,b" && app.rows[0].path === "ordering:a")
    older({ error: "older write failed" })
    check("an older order's failure neither settles the group nor is reported",
          Object.keys(app.pendingReorders).length === 1 && app.statusText.indexOf("older write failed") < 0)
    complete({})
    app.reorderItems(group, ["b", "a"])
    older = complete
    app.reorderItems(group, ["a", "b"])
    source.sections[0].rows.reverse()
    older({})
    app.rebuildRows()
    check("an older order's success leaves the newer order on screen", app.rows[0].path === "ordering:a"
          && Object.keys(app.pendingReorders).length === 1)
    source.sections[0].rows.reverse()
    complete({})
    check("successful reorder publishes provider canonical order", app.rows[0].path === "ordering:a"
          && Object.keys(app.pendingReorders).length === 0)
    var legacyCalls = []
    var legacy = { id: "legacy", name: "Legacy", canReorder: true, sections: [{ key: "notes", rows: [
      { kind: "note", path: "legacy:a", title: "A" }, { kind: "note", path: "legacy:b", title: "B" }
    ] }], setOrder: function(scope, paths) {
      legacyCalls.push({ scope: scope, paths: paths })
    } }
    app.providers = [legacy]
    app.activeSection = "legacy/notes"
    app.rebuildRows()
    app.reorderItems(app.rows[0].reorder, ["legacy:b", "legacy:a"])
    check("legacy providers retain optimistic ordering until their next update", app.rows[0].path === "legacy:b"
          && legacyCalls[0].scope === "notes" && legacyCalls[0].paths.join(",") === "legacy:b,legacy:a"
          && Object.keys(app.pendingReorders).length === 0)
    var retiring = Qt.createQmlObject('import QtQuick; QtObject { property string id: "retiring";'
      + ' property string name: "Retiring"; property var sections: [{ key: "s", name: "Notes", rows: ['
      + ' { kind: "note", path: "retiring:a", title: "A", reorder: { scope: "group", id: "a" } },'
      + ' { kind: "note", path: "retiring:b", title: "B", reorder: { scope: "group", id: "b" } }] }];'
      + ' property var settle: null; function reorder(scope, ids, callback) { settle = callback } }', test)
    app.providers = [retiring]
    app.activeSection = "retiring/s"
    app.rebuildRows()
    app.reorderItems(app.rows[0].reorder, ["b", "a"])
    var orphaned = retiring.settle
    app.retireProvider(retiring)
    check("retiring a provider releases the groups its unanswered writes held",
          Object.keys(app.pendingReorders).length === 0)
    orphaned({ error: "late answer" })
    check("a retired provider's late answer reports nothing", app.statusText.indexOf("late answer") < 0)
    app.providers = []
    app.rebuildRows()
  }
  // Review finding #13 through the workspace itself: hiding it and
  // summoning it again, and a close over the conflicted draft, clear the
  // notices — and leave the session's review over its note. The close does
  // not stop for the draft: it goes, and the workspace stays away. It starts
  // once the workspace has loaded its providers (hostConflict, below) and
  // follows the close as it settles, never waiting in a nested event loop,
  // which is no place to quit from (report).
  function hostConflictCases() {
    var app = test.appHost
    var saves = []
    var source = { id: "conflicted", name: "Conflicted", markdown: false, hasTitle: false, canDelete: true, sections: [],
      crumb: function(path) { return "Conflicted" },
      load: function(path, callback) { callback({ body: path }) },
      save: function(path, title, body, callback) { saves.push(callback) },
      remove: function(path, callback) { callback({}) },
      noteEdited: function(path) {},
      refresh: function() {},
      saveState: function() { return {} } }
    var state = function() { return JSON.parse(app.debugState()) }
    var reviewed = function() { return state().conflict && state().readOnly && app.dirty }
    app.providers = [source]
    app.open("{}")
    app.selectPath("conflicted:a")
    descendant(app, "noteEditor").restoreDocument({ title: "", body: "conflicted:a, edited", base: "" })
    app.onEdited()
    app.flushSave()
    saves.shift()({ error: "conflict", conflict: { id: "workspace", parts: [] } })
    check("a save conflict opens its review over the read-only note", reviewed(), app.debugState())
    app.dismiss()
    app.open("{}")
    check("hiding and summoning the workspace leaves the review and the read-only note", reviewed(), app.debugState())
    var closed = function() {
      app.readyToClose.disconnect(closed)
      // Once the close has settled.
      Qt.callLater(function() {
        check("a close goes over the conflicted draft without asking, and the workspace stays away",
              !app.opened && !app.closing, app.debugState())
        app.open("{}")
        check("opening the workspace again finds the review over the note", reviewed(), app.debugState())
        app.selectPath("conflicted:b")
        check("another note opens editable, out from under the review", !state().conflict && !state().readOnly)
        app.selectPath("conflicted:a")
        check("returning to the conflicted note reopens its review", reviewed(), app.debugState())
        app.requestDelete("conflicted:a")
        app.confirmDelete()
        check("deleting the conflicted note puts its review away", !state().conflict && app.currentPath === "")
        app.providers = []
        test.hostRowActionCases()
        test.hostCloseCases()
      })
    }
    app.readyToClose.connect(closed)
    app.requestClose()
  }
  // A row's action through the workspace: a rename asks for the new name in
  // the name dialog, which a write to the rows leaves standing; the action
  // holds the note still until the provider answers, and lets go of it
  // whatever the answer — an external provider may answer with nothing at
  // all. An item the provider disables is dimmed and cannot be chosen.
  // Follows the conflict cases.
  function hostRowActionCases() {
    var rowMenu = rowMenuFactory.createObject(test)
    rowMenu.row = { menu: [{ id: "open", title: "Open" }, { id: "wait", title: "Wait", enabled: false }] }
    check("a row menu item its provider disables is dimmed and cannot be chosen",
          rowMenu.count === 2 && rowMenu.itemAt(0).enabled && !rowMenu.itemAt(1).enabled
          && rowMenu.itemAt(1).contentItem.opacity < 1, "items: " + rowMenu.count)
    rowMenu.destroy()
    var app = test.appHost
    var saves = [], actions = []
    var source = { id: "rows", name: "Rows", markdown: false, hasTitle: false, canDelete: true, sections: [],
      crumb: function(path) { return "Rows" },
      load: function(path, callback) { callback({ body: path }) },
      save: function(path, title, body, callback) { saves.push(callback) },
      remove: function(path, callback) { callback({}) },
      noteEdited: function(path) {},
      refresh: function() {},
      saveState: function() { return {} },
      rowAction: function(path, id, value, callback) {
        actions.push({ path: path, id: id, value: value, callback: callback })
      } }
    var held = function() {
      return JSON.parse(app.debugState()).readOnly
    }
    var row = { provider: "rows", path: "dir:Plans", title: "Plans" }
    var rename = { id: "rename", title: "Rename", rename: true }
    app.providers = [source]
    app.selectPath("rows:Plans/a")
    descendant(app, "noteEditor").restoreDocument({ title: "", body: "rows:Plans/a, edited", base: "" })
    app.onEdited()
    var field = descendant(app, "promptField")
    app.chooseRowAction(row, rename)
    check("a rename asks for the row's new name in the name dialog, the field opening on the old one",
          !!app.promptPending && app.promptPending.message === "Rename “Plans”"
          && !!field && field.text === "Plans", JSON.stringify(app.promptPending))
    app.rebuildRows()
    check("a write to the rows leaves the name being asked for", !!app.promptPending)
    app.submitPrompt("Plans")
    check("the old name again renames nothing", !app.promptPending && actions.length === 0 && saves.length === 0)
    app.chooseRowAction(row, { id: "newSection", title: "New section", prompt: "Section name" })
    check("a name asked for something new opens on an empty field", !!field && field.text === "")
    app.cancelPrompt()
    app.chooseRowAction(row, rename)
    app.submitPrompt("Ideas")
    check("the new name reaches the provider while the note is held",
          actions.length === 1 && actions[0].value === "Ideas" && held(), app.debugState())
    saves.shift()({})
    actions.shift().callback()
    check("an action answered with nothing lets go of the note", !held(), app.debugState())
    app.runRowAction(row, { id: "delete" }, "")
    actions.shift().callback({ removed: ["rows:Plans/a"] })
    check("the open note its action removed is put away", app.currentPath === "" && !app.dirty, app.debugState())
    app.runRowAction(row, { id: "delete" }, "")
    check("and the workspace is free for the next action", actions.length === 1)
    actions.shift().callback({})
    app.providers = []
  }
  // A close puts the workspace away at once and waits for the writes still
  // out: opening it again meanwhile ends the close, and a write that fails
  // does not stop it. Follows the row action cases, and lets the run report
  // once it is done.
  function hostCloseCases() {
    var app = test.appHost
    var closer = closingProviderFactory.createObject(test)
    var quits = 0
    var quit = function() {
      quits++
    }
    // The second close: the order it waits for fails, and it goes anyway.
    var closed = function() {
      app.readyToClose.disconnect(closed)
      // Once the close has settled.
      Qt.callLater(function() {
        check("an order that fails while closing does not stop it: the process goes, the workspace stays away",
              quits === 1 && !app.opened && !app.closing, app.debugState())
        app.readyToClose.disconnect(quit)
        app.providers = []
        closer.destroy()
        test.processes--
      })
    }
    // The first close, ended by opening the workspace: once its writes have
    // answered, which would have finished it, the process is still wanted.
    var settled = function() {
      if (!app.writesSettled) {
        return
      }
      app.writesSettledChanged.disconnect(settled)
      Qt.callLater(function() {
        check("a close that was ended does not let the process go once its writes settle", quits === 0 && app.opened)
        app.readyToClose.connect(closed)
        app.reorderItems(group, ["b", "a"])
        app.requestClose()
        closer.settle({ error: "the order was lost" })
        closer.writeBusy = false
      })
    }
    app.readyToClose.connect(quit)
    app.providers = [closer]
    app.open("{}")
    app.activeSection = "closer/s"
    app.filterText = ""
    app.rebuildRows()
    var group = app.rows[0].reorder
    app.reorderItems(group, ["b", "a"])
    app.requestClose()
    check("a close puts the workspace away at once while an order is still being written",
          app.closing && !app.opened && quits === 0)
    app.open("{}")
    check("opening the workspace again ends the close", app.opened && !app.closing)
    app.writesSettledChanged.connect(settled)
    closer.writeBusy = false
    closer.settle({})
  }
  function hostSearchCases() {
    var app = test.appHost
    var source = { id: "cachetest", sections: [], replies: [], search: function(query, callback) { this.replies.push(callback) } }
    var other = { id: "othertest", sections: [], replies: [], search: function(query, callback) { this.replies.push(callback) } }
    app.providers = [source, other]
    app.filterText = "needle"
    app.runContentSearch()
    other.replies[0]({ paths: ["othertest:hit"] })
    app.invalidateContentSearch(source)
    app.refreshCachedSearch()
    source.replies[1]({ paths: ["cachetest:new"] })
    source.replies[0]({ paths: ["cachetest:old"] })
    check("cache refresh rejects an older answer to the same query",
          app.contentHits.cachetest["cachetest:new"] && !app.contentHits.cachetest["cachetest:old"])
    check("indexing refreshes only its provider", other.replies.length === 1 && app.contentHits.othertest["othertest:hit"])
    app.askProvider(source, "needle", app.searchSeq)
    app.setFilter("changed")
    source.replies[2]({ paths: ["cachetest:late"] })
    check("typing rejects in-flight cache search results", Object.keys(app.contentHits).length === 0)
    app.providers = []
    app.setFilter("")
  }
  // Two notebooks whose names hash to the same palette slot must not share a
  // colour; a colour the provider named is a brand and stays as given.
  function hostColourCases() {
    var app = test.appHost
    var local = { id: "local", name: "Notes", sections: [
      { key: "travel", name: "Travel", rows: [], footerActions: [] },
      { key: "projects", name: "Projects", rows: [], footerActions: [] },
      { key: "finance", name: "Finance", rows: [], footerActions: [] }] }
    var branded = { id: "branded", name: "Branded", sections: [
      { key: "s", name: "Branded", color: "#7719AA", rows: [], footerActions: [] }] }
    app.providers = [local, branded]
    app.activeSection = "local/travel"
    app.rebuildRows()
    var colours = app.tabs.map(function(tab) { return tab.color })
    check("notebooks with colliding names get distinct colours",
          colours.length === 4 && new Set(colours).size === 4, colours.join(","))
    check("a provider-named colour is kept as given", app.tabs[3].color === "#7719AA")
    app.providers = []
    app.rebuildRows()
  }
  function hostFooterCases() {
    var app = test.appHost
    var calls = []
    var first = { id: "first", name: "First", sections: [{ key: "s", name: "First", rows: [],
      footerActions: [{ path: "logout", title: "Sign out of first" }] }],
      action: function(id) { calls.push("first:" + id) } }
    var second = { id: "second", name: "Second", sections: [{ key: "s", name: "Second", rows: [],
      footerActions: [{ path: "logout", title: "Sign out of second" },
                      { path: "rename", title: "Name", inputPlaceholder: "Enter a name" }] }],
      action: function(id, value, section) {
        calls.push("second:" + id)
        if (id === "rename") {
          calls.push(value + ":" + section)
        }
      } }
    app.providers = [first, second]
    app.activeSection = "second/s"
    app.rebuildRows()
    check("host publishes the active provider footer", app.footerActions[0].title === "Sign out of second")
    check("footer clicks reach the active provider despite duplicate action ids",
          app.runAction("logout") && calls.join(",") === "second:logout")
    var staleAction = app.footerActions[0]
    app.runFooterAction(app.footerActions[1], "Travel")
    check("arbitrary provider input actions receive their value and section",
          calls.slice(-2).join(",") === "second:rename,Travel:s")
    calls = ["second:logout"]
    app.activeSection = "first/s"
    app.rebuildRows()
    app.runAction("logout")
    check("switching tabs switches footer action ownership", calls.join(",") === "second:logout,first:logout")
    check("a retired footer cannot invoke a different tab's matching action", !app.runFooterAction(staleAction, ""))
    var empty = { id: "empty", name: "Empty", sections: [],
      footerActions: [{ path: "first", title: "First notebook", inputPlaceholder: "Notebook name", shortcut: "newNotebook" }],
      action: function(id, value) { calls.push(id + ":" + value) } }
    app.providers = [empty]
    app.rebuildRows()
    check("providers without tabs can supply their first creation action",
          app.footerActions.length === 1 && app.footerActions[0].provider === "empty")
    app.runFooterAction(app.footerActions[0], "First")
    check("first-notebook input reaches its owning provider", calls[calls.length - 1] === "first:First")
    app.providers = []
    app.rebuildRows()
    check("removing providers clears footer actions", app.footerActions.length === 0 && !app.runAction("logout"))
  }
  function check(name, ok, detail) {
    test.results.push({ name: name, ok: !!ok, detail: detail || "" })
  }
  // The item under `item` whose objectName is `name`, or null.
  function descendant(item, name) {
    for (var i = 0; i < item.children.length; i++) {
      var child = item.children[i]
      if (child.objectName === name) {
        return child
      }
      var found = descendant(child, name)
      if (found) {
        return found
      }
    }
    return null
  }
  ProcessRunner { id: runner }
  // Only in the native harness, where an open workspace shows nothing: the
  // Omarchy host's windows follow `opened`, onto the desktop --host must
  // leave alone.
  Connections {
    id: hostConflict
    target: test.appHost
    enabled: Platform.env("NOTE_NOTE_TEST_STANDALONE") === "1"
    function onProvidersLoadedChanged() {
      test.processes++
      Qt.callLater(test.hostConflictCases)
    }
  }
  FileStore { id: files }
  Local.Provider { id: local; notesDir: Platform.env("NOTE_NOTE_TEST_DIR") }
  Tests.EditorKeys {
    id: editorKeys
    suite: test.suite
    onChecked: function(name, ok, detail) { test.check(name, ok, detail) }
    onFinished: {
      test.editorFinished = true
      if (test.reported) {
        Qt.callLater(Qt.quit)
      }
    }
  }

  QtObject {
    id: conversions
    property var reads: []
    property var renders: []
    property string highlight: "#f9e2af"
    property string highlightInk: "#1e1e2e"
    property string link: "#4282d7"
    property string codeChip: "transparent"
    function toMarkdown(html, callback) { reads.push(callback) }
    function toHtml(markdown, callback) { renders.push(callback) }
  }
  QtObject {
    id: clipboard
    property var callback: null
    function takeText(done) { callback = done }
    function takeHtml(done) { callback = done }
    function takeImage(done) { callback = done }
    function hasImage(done) { callback = done }
  }
  Shortcuts.KeybindingRegistry {
    id: editorBindings
    tools: editor.tools.actions
  }
  Ui.NoteEditor {
    id: editor
    keybindings: editorBindings
    width: 700
    height: 500
    hasNote: true
    markdown: conversions
    clipboard: clipboard
  }

  function show(text) {
    editor.restoreDocument({ title: "", body: "<p>" + text + "</p>", base: "" })
    editor.readOnly = false
  }
  function editorCases() {
    show("A")
    editor.withMarkdown(function(lines) { editor.replaceDoc(lines.join("\n"), 0) })
    show("B")
    conversions.reads.shift()("A", { ok: true, blocks: [0] })
    check("format conversion cannot cross note identity", conversions.renders.length === 0 && editor.plainText() === "B")

    show("A")
    editor.replaceDoc("formatted A", 0)
    show("B")
    conversions.renders.shift()("<p>formatted A</p>", true)
    check("replacement conversion cannot overwrite a different note", editor.plainText() === "B")

    show("original")
    editor.replaceDoc("formatted", 0)
    editor.edited() // a change to the current document invalidates its snapshot
    conversions.renders.shift()("<p>formatted</p>", true)
    check("replacement rejects a newer document revision", editor.plainText() === "original")

    show("caret")
    editor.withMarkdown(function() { test.check("stale selection applied", false) })
    editor.setCursorPosition(3)
    conversions.reads.shift()("caret", { ok: true, blocks: [0] })
    check("moving the caret leaves the document intact", editor.plainText() === "caret")

    ;[editor.paste, editor.pasteRich, editor.pastePlain].forEach(function(paste) {
      show("A")
      paste()
      show("B")
      clipboard.callback("clipboard text")
      check("clipboard reply belongs to its original note", editor.plainText() === "B")
    })
    show("A")
    editor.replaceDoc("valid", 0)
    conversions.renders.shift()("<p>valid</p>", true)
    check("an unchanged document accepts the requested edit", editor.plainText() === "valid")
    // The converter says which lines are a fenced block; the editor asks it.
    var fenced = { kinds: ["code", "code", "code", "code", "code", "text", "separator", "table", "table", "table"] }
    check("a fenced block is one run of code lines, fences included", Blocks.fences(fenced)[2].end === 4)
    check("snippets land after the entire code block", editor.blockEndLine(fenced, 2) === 4)
    check("a table is the run of its rows", editor.blockEndLine(fenced, 8) === 9
          && Blocks.tables(fenced).length === 1 && Blocks.tables(fenced)[0].start === 7)
  }

  QtObject {
    id: document
    property string title: ""
    property string body: ""
    property string documentBase: ""
    property var conversions: []
    property var conflictReview: null
    function cursorPosition() { return 0 }
    function setCursorPosition(position) {}
    function viewState() { return { cursor: 0, scroll: 0 } }
    function restoreViewState(state) {}
    function clearNotice() {}
    function showConflict(props) { conflictReview = props }
    function clearConflict() { conflictReview = null }
    function setNote(t, b, shown) {
      title = t
      body = b
      if (shown) {
        shown(true)
      }
    }
    function snapshotDocument() { return { title: title, body: body, base: documentBase } }
    function restoreDocument(snapshot) { title = snapshot.title; body = snapshot.body; documentBase = snapshot.base }
    function requestMarkdown(callback) { document.conversions.push(callback) }
  }
  QtObject {
    id: provider
    property string id: "test"
    property string name: "Test"
    property var loads: []
    property var saves: []
    property var deletions: []
    function remove(path, callback) { deletions.push(callback) }
    function load(path, callback) { loads.push(callback); return { cancel: function() {} } }
    function save(path, title, body, callback, options) {
      saves.push({ path: path, body: body, callback: callback, options: options })
    }
    function noteEdited(path) {}
  }

  Ui.MergeConflict {
    id: conflictPane
    width: 700
    height: 500
    conflict: ({ id: "conflict", parts: [
      { id: "body:0", field: "body", base: "original", local: "ours", remote: "theirs" }
    ] })
  }
  Notes.NoteSession {
    id: mergeSession
    editor: document
    providerFor: function(path) { return provider }
    versionFor: function(path) { return "1" }
    report: function(message) {}
  }
  function mergeCases() {
    provider.loads = []
    provider.saves = []
    mergeSession.selectPath("test:merge")
    provider.loads.shift()({ body: "original" })
    document.body = "ours"
    mergeSession.onEdited()
    mergeSession.flushSave()
    document.conversions.shift()("ours", true)
    provider.saves.shift().callback({ error: "conflict", conflict: conflictPane.conflict })
    check("conflict holds the draft and pauses saving", mergeSession.dirty && !mergeSession.writable && !!document.conflictReview)
    conflictPane.choose("body:0", "both")
    check("conflict view enables save after each choice", conflictPane.complete)
    document.conflictReview.resolve(conflictPane.choices)
    document.conversions.shift()("ours", true)
    var save = provider.saves.shift()
    check("resolution travels with the save snapshot", save.options.resolution.id === "conflict" &&
          save.options.resolution.choices["body:0"] === "both")
    save.callback({})
    check("resolved save releases the draft", !mergeSession.dirty && mergeSession.writable && !document.conflictReview)

    document.body = "older edit"
    mergeSession.onEdited()
    mergeSession.flushSave()
    document.conversions.shift()("older edit", true)
    document.body = "newer edit"
    mergeSession.onEdited()
    provider.saves.shift().callback({ error: "conflict", conflict: conflictPane.conflict })
    check("older conflict cannot decide text typed during a save", document.body === "newer edit" &&
          !document.conflictReview && mergeSession.writable && mergeSession.dirty)
    mergeSession.flushSave()
    document.conversions.shift()("newer edit", true)
    provider.saves.shift().callback({})

    document.body = "edit before leaving"
    mergeSession.onEdited()
    mergeSession.selectPath("test:away")
    document.conversions.shift()("edit before leaving", true)
    provider.loads.shift()({ body: "another note" })
    provider.saves.shift().callback({ error: "conflict", conflict: conflictPane.conflict })
    check("late conflict preserves the selected note", document.body === "another note" && !document.conflictReview)
    mergeSession.selectPath("test:merge")
    check("returning to a conflicted draft opens its review", document.body === "edit before leaving" &&
          !!document.conflictReview && !mergeSession.writable)
    mergeSession.cancelPendingSave("test:merge")
    mergeSession.dirty = false
    mergeSession.selectPath("test:recovery")
    provider.loads.shift()({ body: "recovered draft", recovered: true, conflict: conflictPane.conflict })
    check("recovery loads as unsaved and opens its conflict", mergeSession.dirty &&
          document.body === "recovered draft" && !!document.conflictReview)
    document.conflictReview.continueEditing()
    check("conflict can return to editable draft", mergeSession.writable && !document.conflictReview)
    mergeSession.cancelPendingSave("test:recovery")
    mergeSession.dirty = false
    mergeSession.currentPath = ""
    document.body = "B"
  }
  property var sessionReports: []
  Notes.NoteSession {
    id: session
    editor: document
    providerFor: function(path) { return provider }
    versionFor: function(path) { return "1" }
    report: function(message) { test.sessionReports.push(message) }
  }
  function sessionCases() {
    session.selectPath("test:A")
    session.selectPath("test:B")
    session.selectPath("test:A")
    provider.loads[2]({ body: "new A", view: "accepted-A" })
    provider.loads[0]({ body: "old A", view: "discarded-A" })
    provider.loads[1]({ body: "B", view: "discarded-B" })
    check("A to B to A rejects older documents and baseline tokens",
          document.body === "new A" && session.editingView === "accepted-A")
    session.onEdited()
    document.body = "unsaved A"
    session.selectPath("test:B")
    provider.loads[3]({ body: "B", view: "accepted-B" })
    document.conversions.shift()("unsaved A", true)
    check("a save retains its original note and body", provider.saves[0].path === "test:A" && provider.saves[0].body === "unsaved A")
    check("delayed conversion retains the captured editing baseline", provider.saves[0].options.view === "accepted-A")
    provider.saves.shift().callback({ error: "disk full" })
    session.selectPath("test:A")
    check("failed save draft and baseline survive switching away and back",
          document.body === "unsaved A" && session.dirty && session.editingView === "accepted-A")
    session.flushSave()
    document.conversions.shift()("unsaved A", true)
    provider.saves.shift().callback({ version: "2" })
    check("successful retry releases the retained draft", !session.drafts["test:A"] && !session.busy && session.loadedVersion === "2")
    test.sessionReports = []
    session.selectPath("test:C")
    provider.loads[4]({ body: "cut", editable: false, reason: "only part of it could be read" })
    check("a read-only load holds the editor and says the provider's reason",
          !session.writable && test.sessionReports.join("|") === "only part of it could be read")
    session.selectPath("test:A")
    provider.loads[5]({ body: "A again" })
    check("a writable load releases the editor again", session.writable && test.sessionReports.length === 1)
    session.reloadCurrent()
    session.selectPath("test:B")
    provider.loads[6]({ body: "late reload" })
    provider.loads[7]({ body: "B" })
    check("reload and selection share the same generation guard", document.body === "B")
    session.onEdited()
    test.sessionReports = []
    session.remove("test:B", function(result) {})
    provider.deletions.shift()({ error: "delete refused" })
    check("failed delete preserves the editable unsaved note", session.dirty && document.body === "B" && session.writable)
    check("the session reports a failed delete exactly once", test.sessionReports.join("|") === "Test: delete refused")
  }

  QtObject {
    id: titleProvider
    property var loads: []
    property var saves: []
    function load(path, callback) { loads.push(callback); return { cancel: function() {} } }
    function save(path, title, body, callback, options) { saves.push(callback) }
    function noteEdited(path) {}
  }
  Notes.NoteSession {
    id: titleSession
    editor: document
    providerFor: function(path) { return titleProvider }
    versionFor: function(path) { return "1" }
    report: function(message) {}
  }
  function unsavedTitleCases() {
    titleSession.selectPath("titles:a")
    titleProvider.loads.shift()({ title: "Listed", body: "text" })
    check("an unedited note shows its provider's title", !("titles:a" in titleSession.unsavedTitles))
    document.title = "Typed"
    titleSession.onEdited()
    check("a title being typed is the list's at once", titleSession.unsavedTitles["titles:a"] === "Typed")
    document.title = "Typed on"
    check("every keystroke of the title reaches the list", titleSession.unsavedTitles["titles:a"] === "Typed on")
    titleSession.selectPath("titles:b")
    document.conversions.shift()("text", true)
    titleProvider.loads.shift()({ title: "B", body: "b" })
    check("a note left with its save in flight keeps the typed title",
          titleSession.unsavedTitles["titles:a"] === "Typed on" && !("titles:b" in titleSession.unsavedTitles))
    titleProvider.saves.shift()({ error: "offline" })
    check("a failed save keeps the title it carried", titleSession.unsavedTitles["titles:a"] === "Typed on")
    titleSession.selectPath("titles:a")
    titleSession.flushSave()
    document.conversions.shift()("text", true)
    titleProvider.saves.shift()({})
    check("a landed save hands the title back to the provider", !("titles:a" in titleSession.unsavedTitles))
    titleSession.selectPath("")
  }

  QtObject {
    id: host
    property bool writesSettled: !session.busy
    property var config: ({ providers: { test: { enabled: true, notebookTabs: false } } })
    property var providerUrls: ({ test: "app/plugins/org.note-note.local/Provider.qml" })
    property string configPath: "unused-in-mock"
    property var providerState: ({})
    property var providers: [configured]
    property bool opened: false
    property int retired: 0
    property int forgotten: 0
    function providerById(id) { return configured }
    function providerOf(path) { return configured }
    function providerSnapshot() { return {} }
    function providerBusy(p) { return p.busy }
    function applyProviderSettings(p) { p.notebookTabs = config.providers.test.notebookTabs }
    function retireProvider(p) { retired++ }
    function forgetTabsOf(p) { forgotten++ }
    function addProvider(id) { return configured }
    function reorderProviders() {}
    function rebuildRows() {}
    function saveState() {}
  }
  QtObject {
    id: configured
    property var liveSettings: ["notebookTabs"]
    property bool notebookTabs: false
    property bool busy: false
    function rebuild() {}
    function refresh() {}
  }
  QtObject {
    id: configFiles
    property var callback: null
    property int writes: 0
    property string lastText: ""
    property bool busy: false
    property string revision: "test"
    function merge(value) { return value }
    function prepare(text, callback) {
      callback({ config: JSON.parse(text) })
    }
    function replace(text, revision, done) {
      writes++
      lastText = text
      callback = done
    }
  }
  Providers.ProviderLifecycle {
    id: lifecycle
    host: host
    session: session
    settings: configFiles
  }
  function lifecycleCases() {
    var result = null
    session.onEdited()
    document.body = "settings draft"
    lifecycle.apply(JSON.stringify({ providers: { test: { enabled: true, notebookTabs: true } } }), function(r) { result = r }, configFiles.revision)
    check("settings drain waits for document conversion", lifecycle.busy && configFiles.writes === 0)
    document.conversions.shift()("settings draft", true)
    lifecycle.tryCommit()
    check("settings drain waits for provider completion", configFiles.writes === 0)
    provider.saves.shift().callback({ error: "write failed" })
    lifecycle.tryCommit()
    check("failed save prevents teardown and config commit", result && result.error && host.retired === 0 && configFiles.writes === 0)
    check("failed settings transition keeps the editable draft", session.dirty && session.writable && !session.locked)

    result = null
    lifecycle.apply(JSON.stringify({ providers: { test: { enabled: true, notebookTabs: true } } }), function(r) { result = r }, configFiles.revision)
    document.conversions.shift()("settings draft", true)
    provider.saves.shift().callback({})
    lifecycle.tryCommit()
    check("config is not applied before file commit", host.config.providers.test.notebookTabs === false)
    configFiles.callback({ ok: true })
    check("presentation change updates the existing provider", result && result.ok && configured.notebookTabs && host.retired === 0)
    check("presentation change keeps the current note", session.currentPath === "test:B" && document.body === "settings draft")

    document.body = "settings draft, edited"
    session.onEdited()
    var conversions = document.conversions.length
    var appearanceConfig = { providers: host.config.providers, appearance: { theme: "example.colors/dark" } }
    lifecycle.apply(JSON.stringify(appearanceConfig), function(r) { result = r }, configFiles.revision)
    check("appearance-only settings never flush or lock a dirty note",
          session.dirty && !session.locked && session.writable && document.conversions.length === conversions)
    configFiles.callback({ ok: true })
    check("appearance settings preserve dirty document state", result.ok && session.dirty && host.retired === 0)
    session.flushSave()
    document.conversions.shift()("settings draft, edited", true)
    provider.saves.shift().callback({})

    lifecycle.apply(JSON.stringify({ providers: { test: { enabled: false } } }), function(r) { result = r }, configFiles.revision)
    configFiles.callback({ error: "permission denied" })
    check("failed config write leaves the running setup intact", result.error && host.retired === 0 && session.currentPath === "test:B")

    var layout = [["italic"], [{ dropdown: "insert", items: [
      { dropdown: "insertMonth", items: ["bold", "futureTool"] }
    ] }]]
    var toolbarConfig = { providers: host.config.providers, editor: { toolbar: layout } }
    lifecycle.apply(JSON.stringify(toolbarConfig), function(r) { result = r }, configFiles.revision)
    configFiles.callback({ error: "permission denied" })
    check("failed toolbar settings save preserves the active layout", result.error && !host.config.editor)
    lifecycle.apply(JSON.stringify(toolbarConfig), function(r) { result = r }, configFiles.revision)
    configFiles.callback({ ok: true })
    check("toolbar settings commit without replacing providers or losing the note",
          result.ok && host.retired === 0 && session.currentPath === "test:B"
          && JSON.stringify(host.config.editor.toolbar) === JSON.stringify(layout))
    check("saved toolbar order and future tool ids survive JSON reload",
          JSON.stringify(ToolbarSettings.editorDefaults(JSON.parse(configFiles.lastText).editor).toolbar) === JSON.stringify(layout))
    var previousWrites = configFiles.writes
    toolbarConfig.editor.toolbar = [["bold", { dropdown: "insert", items: ["bold"] }]]
    lifecycle.apply(JSON.stringify(toolbarConfig), function(r) { result = r }, configFiles.revision)
    check("invalid toolbar settings are rejected before writes or document locks",
          result.error && configFiles.writes === previousWrites && !session.locked
          && JSON.stringify(host.config.editor.toolbar) === JSON.stringify(layout))

    configured.busy = true
    lifecycle.apply(JSON.stringify({ providers: { test: { enabled: false } } }), function(r) { result = r }, configFiles.revision)
    var writes = configFiles.writes
    lifecycle.tryCommit()
    check("provider retirement waits for accepted mutations", host.retired === 0 && configFiles.writes === writes)
    configured.busy = false
    lifecycle.tryCommit()
    configFiles.callback({ ok: true })
    check("provider retires only after drain and confirmed settings write", host.retired === 1 && session.currentPath === "")
    check("a provider turned off gives up its tabs' places", host.forgotten === 1)
  }

  // Whether the editor may change the note (`writable`, which the host binds
  // the editor's read-only flag to) follows the session's own state, whatever
  // order a load, a delete, a save and a settings change finish in (review
  // finding #14): nothing puts back a flag saved before another finished.
  function editabilityCases() {
    provider.loads = []
    provider.saves = []
    provider.deletions = []
    var removed = null
    var removeOther = function() {
      session.remove("test:other", function(result) { removed = result })
    }
    session.selectPath("test:A")
    removeOther()
    provider.loads.shift()({ body: "A" })
    provider.deletions.shift()({})
    check("a note that loads while another is deleted is editable once the delete ends",
          !removed.error && !session.locked && session.writable)
    session.selectPath("test:B")
    removeOther()
    provider.deletions.shift()({})
    provider.loads.shift()({ body: "B" })
    check("a note that loads after a delete ended is editable", !session.locked && session.writable)
    session.selectPath("test:C")
    removeOther()
    provider.loads.shift()({ body: "C" })
    provider.deletions.shift()({ error: "refused" })
    check("a note that loads while a delete fails is editable once it has failed",
          !!removed.error && !session.locked && session.writable)
    session.selectPath("test:D")
    removeOther()
    provider.loads.shift()({ error: "unreachable" })
    provider.deletions.shift()({})
    check("a load that fails during a delete leaves its note read-only", session.loadFailed && !session.writable)
    session.selectPath("test:E")
    removeOther()
    provider.loads.shift()({ body: "E", editable: false, reason: "shared for reading" })
    provider.deletions.shift()({})
    check("a read-only document stays read-only when a delete ends", !session.locked && !session.writable)

    var conflict = { id: "held", parts: [] }
    session.selectPath("test:F")
    provider.loads.shift()({ body: "F" })
    document.body = "F edited"
    session.onEdited()
    session.flushSave()
    document.conversions.shift()("F edited", true)
    removeOther()
    provider.saves.shift().callback({ error: "conflict", conflict: conflict })
    provider.deletions.shift()({})
    check("a conflict that lands during a delete keeps its review and its read-only note",
          !session.locked && document.conflictReview && !session.writable)
    document.conflictReview.continueEditing()
    check("answering the review gives the note back", !document.conflictReview && session.writable && session.dirty)
    session.flushSave()
    document.conversions.shift()("F edited", true)
    provider.saves.shift().callback({})

    host.config = { providers: { test: { enabled: true, notebookTabs: false } } }
    var tabs = JSON.stringify({ providers: { test: { enabled: true, notebookTabs: true } } })
    var settled = null
    session.selectPath("test:G")
    lifecycle.apply(tabs, function(result) { settled = result }, configFiles.revision)
    provider.loads.shift()({ body: "G" })
    check("a provider-settings change refused during a load leaves the loaded note editable",
          !!settled.error && !session.locked && session.writable)
    document.body = "G edited"
    session.onEdited()
    lifecycle.apply(tabs, function(result) { settled = result }, configFiles.revision)
    document.conversions.shift()("G edited", true)
    provider.saves.shift().callback({ error: "conflict", conflict: conflict })
    lifecycle.tryCommit()
    check("a conflict that lands while settings drain keeps its review and its read-only note",
          !!settled.error && !session.locked && document.conflictReview && !session.writable)
    document.conflictReview.continueEditing()
    session.flushSave()
    document.conversions.shift()("G edited", true)
    provider.saves.shift().callback({})
    session.selectPath("")
  }

  // A local folder renamed and renamed back moves its notes there and back
  // (notePathChanged, replacePath): a path in use again is nobody's alias,
  // so the open note's saves and its folder's other notes find their files.
  function renameBackCases() {
    provider.loads = []
    provider.saves = []
    var move = function(from, to) {
      session.replacePath("test:" + from + "/n", "test:" + to + "/n", null)
      session.replacePath("test:" + from + "/m", "test:" + to + "/m", null)
    }
    session.selectPath("test:Plans/n")
    provider.loads.shift()({ body: "n" })
    move("Plans", "Ideas")
    move("Ideas", "Plans")
    check("a folder renamed back leaves its notes at their own paths",
          session.currentPath === "test:Plans/n" && session.resolvedPath("test:Plans/n") === "test:Plans/n"
          && session.resolvedPath("test:Ideas/m") === "test:Plans/m")
    document.body = "n edited"
    session.onEdited()
    session.flushSave()
    move("Plans", "Ideas")
    move("Ideas", "Plans")
    document.conversions.shift()("n edited", true)
    check("a save converting through a rename and back goes to the note's path",
          provider.saves.length === 1 && provider.saves[0].path === "test:Plans/n")
    provider.saves.shift().callback({})
    check("and settles, nothing left pending", !session.busy && !session.dirty && !session.drafts["test:Plans/n"])
    document.body = "n edited again"
    session.onEdited()
    session.flushSave()
    document.conversions.shift()("n edited again", true)
    check("the note's next save is sent as well", provider.saves.length === 1 && provider.saves[0].path === "test:Plans/n")
    provider.saves.shift().callback({})
    session.selectPath("test:Plans/m")
    check("another note of the folder opens at its own path", session.currentPath === "test:Plans/m" && session.loadingNote)
    provider.loads.shift()({ body: "m" })
    session.replacePath("test:Chain/a", "test:Chain/b", null)
    session.replacePath("test:Chain/b", "test:Chain/c", null)
    check("an old path follows its note through two renames", session.resolvedPath("test:Chain/a") === "test:Chain/c")
    session.selectPath("")
  }

  // What the provider holds (stored) is known for the open note alone: from
  // its load and its save landing. Another note's landing does not take its
  // place, and opening or deleting a note forgets it.
  function storedCases() {
    provider.loads = []
    provider.saves = []
    provider.deletions = []
    session.selectPath("test:S1")
    provider.loads.shift()({ body: "S1" })
    check("the open note's provider is known to hold what it loaded",
          !!session.stored && session.stored.path === "test:S1")
    document.body = "S1 edited"
    session.onEdited()
    session.selectPath("test:S2")
    check("opening another note forgets the first one's", session.stored === null)
    document.conversions.shift()("S1 edited", true)
    provider.loads.shift()({ body: "S2" })
    provider.saves.shift().callback({})
    check("a save landing for a note no longer open leaves the open note's",
          !!session.stored && session.stored.path === "test:S2" && session.stored.document.body === "S2")
    session.selectPath("test:S1")
    provider.loads.shift()({ body: "S1 edited" })
    session.onEdited()
    session.flushSave()
    check("a note typed back to what its provider holds sends no save", provider.saves.length === 0 && !session.dirty)
    session.remove("test:S1", function(result) {})
    check("a deleted note's is forgotten", session.stored === null)
    provider.deletions.shift()({})
    session.selectPath("")
  }

  function pureCases() {
    var proseFace = "<span style=\"font-family:'iA Writer Mono S'; font-weight:700;\">x</span>"
    var codeRun = "<span style=\"font-family:'DejaVu Sans Mono','monospace'; background-color:#222;\">x</span>"
    check("a note face whose name holds mono is prose", !Dialect.hasMonoFamily(proseFace))
    check("the generic family among fallbacks is code", Dialect.hasMonoFamily(codeRun))
    var chipped = "<span style=\"background-color:#2a2c3c;\">x</span>"
    var lit = "<span style=\"background-color:#F9E2AF; color:#111;\">x</span>" + chipped
    check("a code chip is not a highlight, another background is",
          !Dialect.hasHighlight(chipped, "#2a2c3c") && Dialect.hasHighlight(lit, "#2a2c3c"))
    check("a highlight comes off without the chip or the colour",
          Dialect.withoutBackground(lit, "#2a2c3c", true) === "<span style=\"color:#111;\">x</span>" + chipped
          && Dialect.withoutBackground(chipped, "#2a2c3c", false) === "<span style=\"\">x</span>")
    check("taking the code family out leaves every other declaration",
          Dialect.withoutMonoFamily(codeRun) === "<span style=\"background-color:#222;\">x</span>"
          && Dialect.withoutMonoFamily(proseFace) === proseFace)
    var tools = [
      { toolId: "bold", isMenu: false },
      { toolId: "italic", isMenu: false },
      { toolId: "insert", isMenu: true },
      { toolId: "newTool", isMenu: false }
    ]
    var layout = [["italic", "uninstalled"], [], [{ dropdown: "insert", items: ["bold", "future"] }]]
    var layoutBefore = JSON.stringify(layout)
    var resolved = ToolbarSettings.resolve(layout, tools)
    check("toolbar resolves ordered groups, dropdown members and omitted extensions",
          resolved.toolbar.map(function(entry) { return entry.tool.toolId }).join(",") === "italic,insert,newTool"
          && resolved.toolbar[1].group === 2 && resolved.toolbar[2].group === 3
          && resolved.menus.insert[0].toolId === "bold")
    check("toolbar resolution preserves user settings", JSON.stringify(layout) === layoutBefore)
    var nestedTools = tools.concat([
      { toolId: "insertMonth", isMenu: true },
      { toolId: "more", isMenu: true }
    ])
    var nested = [[{ dropdown: "insert", items: [
      { dropdown: "insertMonth", items: ["italic", { dropdown: "more", items: ["bold", "future"] }] }
    ] }]]
    var nestedBefore = JSON.stringify(nested)
    var nestedResolved = ToolbarSettings.resolve(nested, nestedTools)
    check("nested dropdowns preserve order and keep descendants off the toolbar",
          !ToolbarSettings.validate(nested)
          && nestedResolved.toolbar.map(function(entry) { return entry.tool.toolId }).join(",") === "insert,newTool"
          && nestedResolved.menus.insert[0].toolId === "insertMonth"
          && nestedResolved.menus.insertMonth.map(function(tool) { return tool.toolId }).join(",") === "italic,more"
          && nestedResolved.menus.more[0].toolId === "bold"
          && JSON.stringify(nested) === nestedBefore)
    var missingChild = ToolbarSettings.resolve(nested, tools)
    check("removing a submenu returns its descendants to the toolbar",
          missingChild.menus.insert.length === 0 && missingChild.toolbar.length === tools.length)
    var fallback = ToolbarSettings.resolve([[{ dropdown: "removedMenu", items: ["bold"] }]], tools)
    check("removing a dropdown tool returns its members to the toolbar", fallback.toolbar.length === tools.length)
    check("older settings get the full default layout",
          JSON.stringify(ToolbarSettings.editorDefaults().toolbar) === JSON.stringify(ToolbarSettings.defaults()))
    check("previous default toolbars upgrade to the new arrangement", ToolbarSettings.previousDefaults().every(function(layout) {
      return JSON.stringify(ToolbarSettings.editorDefaults({ toolbar: layout }).toolbar)
        === JSON.stringify(ToolbarSettings.defaults())
    }))
    check("a customized previous toolbar stays in its chosen arrangement",
          JSON.stringify(ToolbarSettings.editorDefaults({ toolbar: layout }).toolbar) === JSON.stringify(layout))
    check("explicit empty layouts and unknown editor settings survive default merging",
          ToolbarSettings.editorDefaults({ toolbar: [], future: 42 }).toolbar.length === 0
          && ToolbarSettings.editorDefaults({ future: 42 }).future === 42)
    var invalid = [null, {}, ["bold"], [[null]], [[""]], [[{ dropdown: "insert" }]],
      [["bold", "bold"]], [["bold", { dropdown: "insert", items: ["bold"] }]],
      [[{ dropdown: "insert", items: [{ dropdown: "nested", items: [null] }] }]],
      [[{ dropdown: "insert", items: [{ dropdown: "insert", items: [] }] }]],
      [["bold", { dropdown: "insert", items: [{ dropdown: "nested", items: ["bold"] }] }]]]
    check("toolbar validation rejects malformed entries and duplicates at any depth", invalid.every(function(value) {
      return !!ToolbarSettings.validate(value)
    }))
    check("toolbar validation permits empty groups and tools not installed yet", !ToolbarSettings.validate(layout))
    check("editor settings validation rejects invalid containers", [null, [], "invalid"].every(function(value) {
      return !!Settings.validate({ editor: value })
    }))
    var damaged = { providers: { local: { enabled: 0, notesDir: "/notes" }, sticky: "off" }, appearance: { theme: 7 },
      editor: { toolbar: ["bold"], future: 42 }, keybindings: [{ command: "app/newNote", keys: ["Ctrl+V"] }], unknown: [1] }
    var found = Settings.problems(damaged)
    var kept = Settings.usable(damaged, found)
    check("each invalid settings field is reported by itself", found.map(function(problem) {
      return problem.path.join(".")
    }).join(",") === "providers.local.enabled,providers.sticky,appearance.theme,editor.toolbar,keybindings", JSON.stringify(found))
    check("the valid rest of a damaged config stays in force", kept.providers.local.notesDir === "/notes"
          && kept.providers.local.enabled === undefined && kept.providers.sticky === undefined
          && kept.appearance.theme === undefined && kept.editor.future === 42 && kept.unknown[0] === 1
          && damaged.providers.sticky === "off")
    var merged = Settings.merge(kept, ["local", "sticky"], { local: { notesDir: "~/Notes" } })
    check("defaults fill only what a damaged config left out", merged.providers.local.notesDir === "/notes"
          && merged.providers.local.enabled === true && merged.providers.sticky.enabled === true
          && JSON.stringify(merged.editor.toolbar) === JSON.stringify(ToolbarSettings.defaults()) && merged.keybindings.length === 0)
    check("a Save names the first problem and accepts a valid config", Settings.validate(damaged) === found[0].message
          && !Settings.validate({}) && !!Settings.validate([]) && !!Settings.summary(found) && !Settings.summary([]))
    check("malformed toolbar defaults preserve unrelated editor settings",
          JSON.stringify(ToolbarSettings.editorDefaults({ toolbar: ["bold"], future: 42 }).toolbar) === JSON.stringify(ToolbarSettings.defaults())
          && ToolbarSettings.editorDefaults({ toolbar: ["bold"], future: 42 }).future === 42)
    var source = [{ id: "test", canReorder: true, sections: [{ key: "s", name: "Section", rows: [],
      footerActions: [{ path: "logout", title: "Sign out", inputPlaceholder: "Confirm", shortcut: "custom" }],
      notes: [{ kind: "note", path: "test:A", title: "Hidden note" }] }] }]
    var before = JSON.stringify(source)
    var model = Sidebar.build(source, "test/s", "hidden", {})
    check("sidebar search includes notes inside folded trees", model.rows.length === 1 && model.hits["test/s"] === 1)
    check("sidebar footer survives search without becoming a result", model.footerActions.length === 1 &&
          model.footerActions[0].path === "logout" && model.tabs[0].count === 1)
    check("sidebar preserves provider action ownership and input metadata",
          model.footerActions[0].provider === "test" && model.footerActions[0].section === "s"
          && model.footerActions[0].inputPlaceholder === "Confirm" && model.footerActions[0].shortcut === "custom")
    check("creation capability does not inject hardcoded footer buttons",
          Sidebar.build([{ id: "custom", canCreate: true, canCreateSection: true,
            sections: [{ key: "s", rows: [] }] }], "custom/s", "", {}).footerActions.length === 0)
    var logoutSearch = Sidebar.build(source, "test/s", "sign out", {})
    check("footer labels do not count as matching notes", logoutSearch.rows.length === 0 && logoutSearch.hits["test/s"] === 0)
    check("leaving a provider clears its footer", Sidebar.build(source, "other/s", "", {}).footerActions.length === 0)
    check("sidebar builder does not mutate provider input", JSON.stringify(source) === before)
    var today = new Date(2026, 8, 12, 14, 0).getTime()
    var flat = [
      { kind: "note", path: "old", modified: new Date(2026, 7, 1).getTime() },
      { kind: "note", path: "first", modified: today - 1000 },
      { kind: "note", path: "second", modified: today },
      { kind: "note", path: "unknown", modified: "invalid" },
      { kind: "new", path: "create" }
    ]
    var originalFlat = JSON.stringify(flat)
    var flatProvider = { id: "flat", sections: [{ key: "notes", rows: flat }] }
    var flatModel = Sidebar.build([flatProvider], "flat/notes", "", {})
    check("flat lists preserve provider order across modification dates",
          flatModel.rows.map(function(item) { return item.path }).join(",") === "old,first,second,unknown,create"
          && JSON.stringify(flat) === originalFlat)
    var hierarchy = [{ kind: "tree", path: "section" }].concat(flat)
    flatProvider.sections[0].rows = hierarchy
    var treeModel = Sidebar.build([flatProvider], "flat/notes", "", {})
    check("sidebar preserves provider hierarchies",
          treeModel.rows.map(function(item) { return item.path }).join(",") === "section,old,first,second,unknown,create")
    check("a tab key is spelt in one place and read back by the same",
          Sidebar.sectionKey({ id: "p" }, { key: "s/t" }) === "p/s/t"
          && Sidebar.providerIdOf("p/s/t") === "p" && Sidebar.ownKey("p/s/t") === "s/t")
    // The user dragged b/x first; a/z is not there just now, and a/y is new.
    var tabOrder = ["b/x", "a/z", "a/w"], present = ["a/w", "a/y", "b/x"]
    check("dragged tabs keep their order, and a tab the order does not name stands after its provider's last",
          Sidebar.arranged(tabOrder, present).join() === "b/x,a/w,a/y"
          && Sidebar.arranged(["a/w", "b/x"], present).join() === "a/w,a/y,b/x"
          && Sidebar.arranged([], present).join() === present.join())
    check("a tab whose provider the order does not name comes last",
          Sidebar.arranged(["b/x"], ["a/w", "a/y", "b/x"]).join() === "b/x,a/w,a/y")
    check("a drag places the tab before another or last, keeping the places of tabs not there",
          Sidebar.moved(tabOrder, present, "a/y", "b/x").join() === "a/y,b/x,a/z,a/w"
          && Sidebar.moved(tabOrder, present, "b/x", "").join() === "a/z,a/w,a/y,b/x")
    check("a provider turned off gives up its tabs' places, there or not",
          Sidebar.without(tabOrder, present, "a").join() === "b/x"
          && Sidebar.arranged(Sidebar.without([], present, "b"), present).join() === "a/w,a/y,b/x")
    check("modification captions accept numeric and ISO dates and reject invalid dates",
          Sidebar.timestamp(today) === today && Sidebar.timestamp(new Date(today).toISOString()) === today
          && Sidebar.timestamp("invalid") === 0)
    var noLive = function(id) { return [] }
    var tabsLive = function(id) { return ["notebookTabs"] }
    check("provider setting order does not cause replacement", Plan.plan(
      { providers: { a: { path: "x", enabled: true } } },
      { providers: { a: { enabled: true, path: "x" } } }, ["a"], noLive).length === 0)
    check("changing a resource requires replacement", Plan.plan(
      { providers: { a: { path: "x" } } }, { providers: { a: { path: "y" } } }, ["a"], noLive)[0].replace)
    var flip = Plan.plan({ providers: { a: { notebookTabs: false } } }, { providers: { a: { notebookTabs: true } } }, ["a"], tabsLive)
    check("a live setting the provider declares changes it in place", flip.length === 1 && flip[0].presentation && !flip[0].replace)
    check("the same key on a provider that did not declare it live replaces the instance",
          Plan.plan({ providers: { a: { notebookTabs: false } } }, { providers: { a: { notebookTabs: true } } }, ["a"], noLive)[0].replace)
    if (Platform.env("NOTE_NOTE_TEST_HOST") === "1" || Platform.env("NOTE_NOTE_TEST_STANDALONE") === "1") {
      var component = Qt.createComponent(Platform.env("NOTE_NOTE_TEST_STANDALONE") ? "app/Workspace.qml" : "app/hosts/omarchy/Notes.qml")
      check("the complete host component compiles", component.status === Component.Ready, component.errorString())
      if (component.status === Component.Ready) {
        test.appHost = component.createObject(test)
        check("the host instantiates with its real controllers", !!test.appHost)
        if (test.appHost) {
          test.appHost.initialize()
          var oldConfig = test.appHost.settings.merge({ providers: {} })
          check("host adds toolbar settings to older configuration", JSON.stringify(oldConfig.editor.toolbar) === JSON.stringify(ToolbarSettings.defaults()))
          var customConfig = test.appHost.settings.merge({ editor: { toolbar: layout, future: 42 } })
          check("host preserves custom toolbar order and unknown editor settings", JSON.stringify(customConfig.editor.toolbar) === layoutBefore && customConfig.editor.future === 42)
          var malformedConfig = test.appHost.settings.merge({ providers: { local: { enabled: false } }, editor: { toolbar: ["bold"] } })
          check("invalid toolbar at startup does not reset valid provider settings", !malformedConfig.providers.local.enabled
                && JSON.stringify(malformedConfig.editor.toolbar) === JSON.stringify(ToolbarSettings.defaults()))
          // A provider's defaults are its own: recorded off the instance and
          // shown in the config; only declared settings are assigned.
          var declared = { id: "declared", settings: ["a", "b"], a: 1, b: "two", c: 3 }
          test.appHost.recordProviderDefaults(declared)
          var filled = test.appHost.withProviderDefaults({ providers: { declared: { a: 9 } } }, "declared").providers.declared
          check("the config shows a provider's declared defaults under what the entry holds",
                JSON.stringify(filled) === JSON.stringify({ enabled: true, a: 9, b: "two" }))
          var hostConfig = test.appHost.config
          test.appHost.config = { providers: { declared: { enabled: false, a: 5, c: 7 } } }
          test.appHost.applyProviderSettings(declared)
          test.appHost.config = hostConfig
          check("only declared settings are assigned, enabled and the rest untouched",
                declared.a === 5 && declared.b === "two" && declared.c === 3)
        }
      }
    }
    check("shortcut dispatch and help use common definitions", editor.keybindings.match({ key: Qt.Key_N, modifiers: Qt.ControlModifier | Qt.ShiftModifier }, "workspace").action === "newNotebook" && editor.keybindings.helpText.indexOf("ctrl+shift+n") >= 0)

  }

  function processCase(name, options, expected, cancel) {
    test.processes++
    var calls = 0
    var handle = runner.run(options, function(result) {
      calls++
      check(name, expected(result), JSON.stringify(result))
      test.processes--
    })
    if (cancel) {
      handle.cancel()
      handle.cancel()
    }
    completionChecks.push(function() { check(name + " completes once", calls === 1) })
  }
  property var completionChecks: []
  function processCases() {
    processCase("UTF-8 survives byte-sized pipe writes", {
      command: ["python3", "-c", "import os,time; b='📝漢字'.encode(); [(os.write(1,bytes([v])),time.sleep(.002)) for v in b]"],
      raw: true
    }, function(result) {
      return result.text === "📝漢字"
    })
    processCase("process output is bounded before delivery", {
      command: ["python3", "-c", "print('x' * 4096)"],
      maxOutputBytes: 64
    }, function(result) {
      return result.error && result.error.indexOf("byte limit") >= 0
    })
    processCase("JSON process success", { command: ["python3", "-c", "import sys; print(sys.stdin.read())"], payload: '{"ok":true}' }, function(r) { return r.ok })
    processCase("process startup failure", { command: ["/note-note-command-does-not-exist"] }, function(r) { return !!r.error })
    processCase("nonzero process exit", { command: ["python3", "-c", "print('{}'); exit(3)"] }, function(r) { return !!r.error })
    processCase("malformed process output", { command: ["python3", "-c", "print('not json')"] }, function(r) { return !!r.error })
    processCase("process deadline", { command: ["python3", "-c", "import time; time.sleep(10)"], timeoutMs: 80 }, function(r) { return r.error === "operation timed out" })
    processCase("process cancellation", { command: ["python3", "-c", "import time; time.sleep(10)"] }, function(r) { return r.cancelled }, true)
  }

  function localCases() {
    local.watch(true)
    test.processes++
    local.load(local.pathOf(local.notesRoot + "/Large.md"), function(result) {
      check("oversized UTF-8 note is never returned as editable truncated text", !!result.error && !result.editable && result.body === undefined)
      test.processes--
    })
    local.createSection("Broken", function(result) {
      check("failed mkdir is reported without publishing a notebook", !!result.error && !local.notebooks.some(function(b) { return b.key === "Broken" }))
    })
    local.createSection("Work", function(result) {
      check("local section commit", !result.error, result.error)
      local.create("section:Work", function(created) {
        check("local create commit", !!created.path, created.error)
        var path = created.path, order = []
        var staged = "![](file://" + Platform.pasteDir + "/image.png)"
        local.save(path, "A", staged, function(saved) { order.push(1); check("image save commits", !saved.error, saved.error) })
        local.save(path, "B", "newest text", function(saved) {
          order.push(2)
          check("image and image-free saves are ordered", order.join(",") === "1,2")
          files.write(local.notesRoot + "/External.md", "---\ntitle: External changed\n---\nexternal content", function(result) {
            check("external edit fixture committed", !result.error)
            watchCheck.start()
          })
          local.load(path, function(loaded) {
            check("older staging cannot overwrite newer text", loaded.body === "newest text", JSON.stringify(loaded))
            local.save(path, "C", staged, function(answer) { order.push(3) })
            local.remove(path, function(removed) {
              check("delete waits for an active image save", !removed.error && order.join(",") === "1,2,3")
              local.load(path, function(missing) {
                check("delete cannot be undone by a late stage", !!missing.error)
                local.save(path, "stale", "stale", function(failed) {
                  check("failed write is reported", !!failed.error)
                  test.localFinished = true
                })
              })
            })
          })
        })
      })
    })
  }

  // Once, then quits — never under an editor scenario still running, which
  // waits on its events in a nested event loop: Quickshell, made to quit
  // there, destroys the shell under the scenario and starts it over. The
  // editor stops after that scenario, and the quit follows its end.
  property bool reported: false
  function report() {
    if (test.reported) {
      return
    }
    test.reported = true
    completion.stop()
    local.watch(false)
    console.log("<<<RESULT>>>" + JSON.stringify(test.results) + "<<<END>>>")
    if (editorKeys.running) {
      editorKeys.stop()
    } else {
      Qt.callLater(Qt.quit)
    }
  }
  QtObject {
    id: oneNoteAccount
    property bool configured: true
    property bool signedIn: true
    property bool loggingIn: false
    property bool filesRead: false
    property bool filesWrite: true
    property string account: "test"
    property string cacheSession: ""
    property var env: ({})
    property int logins: 0
    property int destructiveLogins: 0
    signal updated()
    signal signedOut()
    signal statusFailed(string error)
    function hasScope(scope) {
      return scope === "Notes.ReadWrite" || (scope === "Files.Read" && filesRead)
        || (scope === "Files.ReadWrite" && filesWrite)
    }
    function login() { logins++ }
    function relogin() { destructiveLogins++ }
  }
  OneNote.Provider { id: oneNote; ms: oneNoteAccount }
  // An account of its own, so switching it reaches no other provider.
  QtObject {
    id: stubAccount
    property bool configured: true
    property bool signedIn: true
    property bool loggingIn: false
    property string account: "test"
    property string cacheSession: ""
    property var env: ({})
    signal updated()
    signal signedOut()
    signal statusFailed(string error)
    function hasScope(scope) { return true }
  }
  Sticky.Provider {
    id: stickyStub
    ms: stubAccount
    script: Platform.env("NOTE_NOTE_TEST_ONENOTE_SCRIPT")
  }
  // A script's answer is for the account the request was made under: one
  // that lands after the account changed is refused (LaneProvider.qml).
  function laneProviderCases() {
    if (!Platform.env("NOTE_NOTE_TEST_ONENOTE_SCRIPT")) {
      return
    }
    test.processes++
    stickyStub.runScript(["list"], "", { done: function(result) {
      check("a script answer for another account is refused", result.error === "the signed-in account changed")
      stubAccount.cacheSession = ""
      stickyStub.runScript(["list"], "", { done: function(again) {
        check("a script answer for the same account is taken", !again.error && Array.isArray(again.sections))
        test.processes--
      } })
    } })
    stubAccount.cacheSession = "switched"
  }
  // Driven by a stand-in script: the listing lands first, in the order the
  // last pass left, and the pass that follows places the sections.
  OneNote.Provider {
    id: orderProvider
    ms: oneNoteAccount
    script: Platform.env("NOTE_NOTE_TEST_ONENOTE_SCRIPT")
  }
  function orderCases() {
    if (!Platform.env("NOTE_NOTE_TEST_ONENOTE_SCRIPT")) {
      return
    }
    var ids = function() {
      return orderProvider.onSections.map(function(section) { return section.id }).join(",")
    }
    var listed = ""
    var record = function() {
      if (listed === "" && orderProvider.onSections.length) {
        listed = ids()
      }
    }
    orderProvider.onSectionsChanged.connect(record)
    orderProvider.statusRequested.connect(function(text) {
      if (text.indexOf("section order") < 0) {
        return
      }
      orderProvider.onSectionsChanged.disconnect(record)
      check("the listing answers before the pass, in the order the last pass left", listed === "b,a")
      check("the pass places the sections and reports its warnings",
            ids() === "a,b" && text === "OneNote section order: N: placed by the pass")
      test.processes--
    })
    test.processes++
    orderProvider.refresh()
  }
  QtObject {
    id: immediateLane
    property int writeDepth: 0
    function enqueue(options, start, settled) {
      start({ done: function(result) { settled(result) } })
      return { cancel: function() {} }
    }
    function cancelOwner(owner) {}
  }
  OneNote.Provider {
    id: raceProvider
    ms: oneNoteAccount
    script: Platform.env("NOTE_NOTE_TEST_ONENOTE_RACE_SCRIPT")
  }
  property bool raceLoaded: false
  property bool raceLostInventory: false
  function listingRaceCases() {
    test.processes++
    raceProvider.updated.connect(function() {
      if (raceProvider.pages.length > 0) {
        test.raceLoaded = true
      } else if (test.raceLoaded) {
        test.raceLostInventory = true
      }
    })
    raceProvider.rq = immediateLane
    raceProvider.refresh()
    raceCheck.start()
  }
  Timer {
    id: raceCheck
    interval: 1500
    onTriggered: {
      check("an empty cached result cannot replace a newer network listing",
            test.raceLoaded && !test.raceLostInventory && raceProvider.pages.length === 1 && raceProvider.onNotebooks.length === 1)
      test.processes--
    }
  }
  Notes.NoteSession {
    id: oneNoteSession
    editor: document
    providerFor: function(path) { return oneNote }
    versionFor: function(path) { return "1" }
    report: function(message) {}
  }
  QtObject {
    id: mergeLane
    property var jobs: []
    property int depth: 0
    function enqueue(options, start, settled) {
      jobs.push({ options: options, start: start, settled: settled })
      return { cancel: function() {} }
    }
    function cancelOwner(owner) {}
  }
  // A provider whose order is written only when the test answers it.
  Component {
    id: closingProviderFactory
    QtObject {
      property string id: "closer"
      property string name: "Closer"
      property bool writeBusy: false
      property var settle: null
      property var sections: [{ key: "s", name: "Notes", rows: [
        { kind: "note", path: "closer:a", title: "A", reorder: { scope: "group", id: "a" } },
        { kind: "note", path: "closer:b", title: "B", reorder: { scope: "group", id: "b" } }] }]
      function reorder(scope, ids, callback) {
        writeBusy = true
        settle = callback
      }
      function refresh() {}
      function saveState() {
        return {}
      }
    }
  }
  // A lane that keeps what it is handed, for a test to start and answer in
  // its own order.
  QtObject {
    id: orderLane
    property var jobs: []
    function enqueue(options, start, settled) {
      orderLane.jobs.push({ options: options, start: start, settled: settled })
      return { cancel: function() {}, promote: function() {} }
    }
    function cancelOwner(owner) {}
  }
  Component { id: oneNoteFactory; OneNote.Provider {} }
  Component {
    id: creatingOneNoteFactory
    OneNote.Provider {
      property var commands: []
      function runScript(args, payload, ctx) {
        commands.push({ args: args, payload: payload, context: ctx })
      }
    }
  }
  Notes.NoteSession {
    id: creationSession
    property var source: null
    property var reports: []
    editor: document
    providerFor: function(path) { return creationSession.source }
    versionFor: function(path) { return "" }
    report: function(message) { creationSession.reports.push(message) }
  }
  // An account of its own, so signing it out reaches no other provider.
  QtObject {
    id: creationAccount
    property bool configured: true
    property bool signedIn: true
    property bool loggingIn: false
    property string account: "test"
    property string cacheSession: ""
    property var env: ({})
    signal updated()
    signal signedOut()
    signal statusFailed(string error)
    function hasScope(scope) { return scope === "Notes.ReadWrite" }
  }
  Component { id: localFactory; Local.Provider {} }
  Component { id: stickyFactory; Sticky.Provider {} }
  Component { id: notionFactory; Notion.Provider {} }
  Component { id: rowMenuFactory; Ui.RowMenu {} }

  // A lane that records what it is handed and lets the test answer it.
  QtObject {
    id: recordingLane
    property var jobs: []
    property int revision: 0
    function enqueue(job, run, done) { recordingLane.jobs.push({ job: job, done: done }) }
    function pendingFor(owner, writes) { return 0 }
    function cancelOwner(owner) {}
    function settle(answer) { recordingLane.jobs.shift().done(answer, { cancelled: answer === null }) }
  }
  QtObject {
    id: recordingAccount
    property bool configured: true
    property bool signedIn: true
    property bool loggingIn: false
    property string account: "test"
    property string cacheSession: ""
    property string grantedScope: "Mail.ReadWrite"
    property var env: ({})
    signal updated()
    signal signedOut()
    signal statusFailed(string error)
    function hasScope(scope) { return true }
    function refresh() {}
  }
  readonly property var recordingServices: ({
    requests: { queueFor: function(key, provider) { return recordingLane }, cancelOwner: function(owner) {} },
    microsoft: { create: function(owner, scopes, clientId) { return recordingAccount } }
  })

  // A remote provider's model follows the backend: a save changes the
  // stored note when the backend has taken it, a delete removes it when the
  // backend has, a cancelled delete is a failure, and a failed one leaves
  // the note where it was.
  Ui.NoteEditor { id: noticeEditor; visible: false; keybindings: editorBindings }
  // A clipboard that cannot be read: the editor says so instead of pasting
  // nothing in silence.
  QtObject {
    id: failingClipboard
    function hasImage(done) { done(true) }
    function takeImage(done) { done(null, "the clipboard image is too large") }
    function takeHtml(done) { done("", "the clipboard text is too large") }
    function takeText(done) { done("", "the clipboard text is too large") }
  }
  Ui.NoteEditor { id: pasteEditor; visible: false; keybindings: editorBindings; hasNote: true; canImages: true; clipboard: failingClipboard }
  function clipboardCases() {
    var said = []
    var record = function(text) { said.push(text) }
    pasteEditor.statusRequested.connect(record)
    pasteEditor.paste()
    pasteEditor.pastePlain()
    pasteEditor.statusRequested.disconnect(record)
    check("a clipboard that cannot be read is reported, not pasted in silence",
          said.join("|") === "the clipboard image is too large|the clipboard text is too large")
  }
  Ui.NoteEditor { id: staleInspectorEditor; visible: false; keybindings: editorBindings; inspectorUrl: Qt.resolvedUrl("app/tests/StaleInspector.qml") }
  // The native inspector is taken whole or not at all: the built module
  // speaks the editor's version, a module of another version is refused.
  function inspectorCases() {
    check("the built native inspector speaks the editor's version", noticeEditor.canColorText)
    check("a native inspector of another version is refused whole", !staleInspectorEditor.canColorText)
  }
  Component { id: blankView; Item {} }
  // A notice clears only itself: the serial it was shown under names it,
  // and a newer notice is left standing; a view carries its own title.
  function noticeCases() {
    var first = noticeEditor.showNotice("First", "text", "", [])
    var second = noticeEditor.showNotice("Second", "text", "", [])
    noticeEditor.clearNotice(first)
    check("clearing an older notice leaves the newer one", noticeEditor.showingNotice && noticeEditor.noticeTitle === "Second")
    noticeEditor.clearNotice(second)
    check("clearing the notice showing clears it", !noticeEditor.showingNotice && noticeEditor.noticeTitle === "")
    var view = noticeEditor.showView("Setup", blankView, {})
    check("a view carries its title and no notice text", noticeEditor.showingNotice && noticeEditor.noticeTitle === "Setup" && noticeEditor.noticeText === "")
    noticeEditor.clearNotice(view)
    check("a view clears by its serial too", !noticeEditor.showingNotice && noticeEditor.customView === null)
  }

  function remoteModelCases() {
    var sticky = stickyFactory.createObject(test, { services: test.recordingServices })
    sticky.notes = [{ id: "a", title: "", body: "old", modified: "1" }]
    sticky.rebuild()
    var answers = []
    sticky.save("sticky:a", "", "new", function(result) { answers.push(result) })
    check("a Sticky save leaves the model alone until the backend answers", sticky.notes[0].body === "old" && recordingLane.jobs.length === 1)
    recordingLane.settle({ error: "refused" })
    check("a failed Sticky save keeps the stored text", sticky.notes[0].body === "old" && answers[0].error === "refused")
    sticky.save("sticky:a", "", "new", function(result) { answers.push(result) })
    recordingLane.settle({ ok: true })
    check("a Sticky save that landed updates the stored text", sticky.notes[0].body === "new" && !answers[1].error)
    sticky.remove("sticky:a", function(result) { answers.push(result) })
    check("a Sticky delete keeps the note until the backend answers", sticky.notes.length === 1)
    recordingLane.settle(null)
    check("a cancelled Sticky delete is a failure and keeps the note", sticky.notes.length === 1 && /cancelled/.test(answers[2].error))
    sticky.remove("sticky:a", function(result) { answers.push(result) })
    recordingLane.settle({ ok: true })
    check("a Sticky delete that landed removes the note", sticky.notes.length === 0 && !answers[3].error)
    sticky.destroy()

    var notion = notionFactory.createObject(test, { services: test.recordingServices })
    notion.pages = [{ id: "p", title: "Old", parent: "", edited: "1" }]
    notion.bodies = ({ p: { title: "Old", body: "old", editable: true, version: "" } })
    notion.rebuild()
    var replies = []
    notion.save("notion:p", "New", "new", function(result) { replies.push(result) })
    check("a Notion save leaves the model alone until the backend answers", notion.pages[0].title === "Old" && notion.bodies.p.body === "old")
    recordingLane.settle({ error: "refused" })
    check("a failed Notion save keeps the stored page", notion.pages[0].title === "Old" && replies[0].error === "refused")
    notion.save("notion:p", "New", "new", function(result) { replies.push(result) })
    recordingLane.settle({ ok: true })
    check("a Notion save that landed updates the stored page", notion.pages[0].title === "New" && notion.bodies.p.body === "new")
    notion.remove("notion:p", function(result) { replies.push(result) })
    recordingLane.settle(null)
    check("a cancelled Notion delete is a failure and keeps the page", notion.pages.length === 1 && /cancelled/.test(replies[2].error))
    notion.remove("notion:p", function(result) { replies.push(result) })
    recordingLane.settle({ ok: true })
    check("a Notion delete that landed removes the page", notion.pages.length === 0 && !replies[3].error)
    notion.destroy()
  }
  Microsoft.Account {
    id: scopeAccount
    scopes: "offline_access User.Read Notes.ReadWrite Files.Read"
    optionalScopes: "Files.Read"
  }

  // A probe that cannot answer must leave the sign-in as it was and say so;
  // only an answer of "signed out" (or a sign-out) is the transition that
  // makes a provider throw its caches away. Each step's answer is chosen by
  // the stub through the account's owner (tests/transition_selftest.py).
  property bool accountFinished: !test.core
  property var accountEvents: []
  property var accountSteps: [
    { owner: "signed-in", expect: function() { return probeAccount.signedIn && probeAccount.account === "a" } },
    { owner: "garbage", expect: function() { return probeAccount.signedIn && test.accountEvents.slice(-1)[0] === "failed:the sign-in status could not be read" } },
    { owner: "error", expect: function() { return probeAccount.signedIn && test.accountEvents.slice(-1)[0] === "failed:boom" } },
    { owner: "signed-out", expect: function() { return !probeAccount.signedIn && test.accountEvents.slice(-1)[0] === "signedOut" } },
    { owner: "signed-out", expect: function() { return test.accountEvents.length === 3 } }
  ]
  property int accountStep: 0
  Microsoft.Account {
    id: probeAccount
    script: Platform.env("NOTE_NOTE_TEST_STATUS_SCRIPT")
    clientId: "test"
    onSignedOut: test.accountEvents.push("signedOut")
    onStatusFailed: function(error) { test.accountEvents.push("failed:" + error) }
    onUpdated: {
      var step = test.accountSteps[test.accountStep]
      test.check("account probe step " + test.accountStep + " (" + step.owner + ")", step.expect(), test.accountEvents.join(","))
      test.accountStep++
      if (test.accountStep < test.accountSteps.length) {
        probeAccount.owner = test.accountSteps[test.accountStep].owner
        probeAccount.refresh()
      } else {
        test.accountFinished = true
      }
    }
  }
  function accountCases() {
    if (!Platform.env("NOTE_NOTE_TEST_STATUS_SCRIPT")) {
      test.accountFinished = true
      return
    }
    probeAccount.owner = test.accountSteps[0].owner
    probeAccount.refresh()
  }
  function oneNoteCases() {
    var orderingSource = oneNoteFactory.createObject(test, { ms: oneNoteAccount })
    var orderingBook = "0-0000000000000001!1", orderingSection = "0-0000000000000001!2"
    orderingSource.onNotebooks = [{ id: orderingBook, name: "Book", userRole: "Owner" }]
    orderingSource.onSections = [{ id: orderingSection, name: "Section", notebookId: orderingBook }]
    orderingSource.expanded = [orderingSection]
    orderingSource.pages = [{ id: "a", sectionId: orderingSection, title: "A", clientId: "a", level: 0 },
                            { id: "child", sectionId: orderingSection, title: "Child", clientId: "child", level: 1 },
                            { id: "b", sectionId: orderingSection, title: "B", clientId: "b", level: 0 }]
    orderingSource.rebuild()
    check("OneNote sign-in asks for OneDrive write access and offers no page ordering toggle",
          orderingSource.microsoftScopes.indexOf("Files.ReadWrite") >= 0
          && orderingSource.accountActions(orderingBook).map(function(action) {
            return action.path
          }).join(",") === "newSection,logout")
    oneNoteAccount.filesWrite = false
    check("a sign-in without OneDrive write access asks to sign in again",
          orderingSource.accountRows().length === 1 && orderingSource.accountRows()[0].path === "login")
    check("OneNote page drags require OneDrive write access", !orderingSource.bookRows(orderingBook, 0)[1].reorder)
    orderingSource.action("login")
    check("signing in again keeps the account instead of signing out first",
          oneNoteAccount.logins === 1 && oneNoteAccount.destructiveLogins === 0)
    oneNoteAccount.filesWrite = true
    var orderingRows = orderingSource.bookRows(orderingBook, 0)
    check("OneNote declares section page groups and keeps subpage hierarchy",
          orderingRows[0].reorder === undefined && orderingRows[1].reorder.scope === "pages:" + orderingSection
          && orderingRows[1].reorder.descendants && !orderingRows[2].reorder && orderingRows[2].level === 2
          && orderingRows[3].reorder.scope === orderingRows[1].reorder.scope)
    check("a OneNote section offers Refresh, and rename and delete where its file can be written",
          orderingRows[0].menu.map(function(item) { return item.id }).join(",") === "refresh,rename,delete",
          JSON.stringify(orderingRows[0].menu))
    // What a startup listing does to a section the user worked in: its
    // stamp moved, so its pages are listed again.
    orderingSource.applyInventory({ sections: orderingSource.onSections, notebooks: orderingSource.onNotebooks,
                                    pages: orderingSource.pages, pendingSections: [orderingSection], pageListSerial: 1 })
    var relisted = orderingSource.bookRows(orderingBook, 0)[1].reorder
    check("a section whose pages are being listed again keeps its page drags",
          !!relisted && relisted.scope === "pages:" + orderingSection)
    // A first listing publishes its pages as they come: until it is done,
    // an order would leave out the ones still to come.
    orderingSource.applyInventory({ sections: orderingSource.onSections, notebooks: orderingSource.onNotebooks,
                                    pages: orderingSource.pages, pendingSections: [orderingSection],
                                    partialSections: [orderingSection], pageListSerial: 2 })
    check("a section listed only in part offers no page drags", !orderingSource.bookRows(orderingBook, 0)[1].reorder)
    orderingSource.applyInventory({ sections: orderingSource.onSections, notebooks: orderingSource.onNotebooks,
                                    pages: orderingSource.pages, pendingSections: [], pageListSerial: 3 })
    // A page order just written may not reach Graph for a few seconds, and
    // a listing meanwhile could bring the old one back.
    var settlesAt = {}
    settlesAt[orderingSection] = Date.now() / 1000 + 30
    orderingSource.applyInventory({ sections: orderingSource.onSections, notebooks: orderingSource.onNotebooks,
                                    pages: orderingSource.pages, pendingSections: [],
                                    sectionOrderSettlesAt: settlesAt, pageListSerial: 4 })
    var settlingRefresh = orderingSource.bookRows(orderingBook, 0)[0].menu[0]
    check("a section whose page order was just written offers Refresh disabled",
          settlingRefresh.id === "refresh" && settlingRefresh.enabled === false, JSON.stringify(settlingRefresh))
    orderingSource.applyInventory({ sections: orderingSource.onSections, notebooks: orderingSource.onNotebooks,
                                    pages: orderingSource.pages, pendingSections: [], pageListSerial: 5 })
    check("its Refresh comes back once the order has settled",
          orderingSource.bookRows(orderingBook, 0)[0].menu[0].enabled === true)
    orderingSource.pages[1].level = undefined
    check("a section listed before its pages carried their level offers no ordering",
          !orderingSource.pageOrderingAvailable(orderingSource.onSections[0]))
    orderingSource.pages[1].level = 1
    orderingSource.onNotebooks = [{ id: orderingBook, name: "Book", userRole: "Reader" }]
    check("read-only OneNote notebooks cannot expose reorder capabilities", !orderingSource.pageOrderingAvailable(orderingSource.onSections[0]))
    var readOnlyMenu = orderingSource.bookRows(orderingBook, 0)[0].menu
    check("a read-only notebook's OneNote section offers Refresh alone",
          readOnlyMenu.map(function(item) { return item.id }).join(",") === "refresh", JSON.stringify(readOnlyMenu))
    orderingSource.onNotebooks = [{ id: orderingBook, name: "Book", userRole: "Contributor" }]
    check("notebooks shared for editing expose reorder capabilities",
          orderingSource.pageOrderingAvailable(orderingSource.onSections[0]))
    var guidBook = "0-0000000000000001!s0123456789abcdef0123456789abcdef"
    orderingSource.onNotebooks = [{ id: guidBook, name: "Book", userRole: "Owner" },
                                  { id: guidBook.slice(0, -1), name: "Short", userRole: "Owner" }]
    check("notebooks OneDrive gave a GUID ID are personal and expose reorder capabilities",
          orderingSource.sectionFileWritable(guidBook) && !orderingSource.sectionFileWritable(guidBook.slice(0, -1)))
    orderingSource.destroy()
    // A drop is taken however soon it follows the last: a section's writes
    // run one at a time, a newer order replaces one still waiting, and each
    // is checked against the order the write before it left.
    var writer = creatingOneNoteFactory.createObject(test, { ms: oneNoteAccount })
    writer.rq = orderLane
    writer.onNotebooks = [{ id: orderingBook, name: "Book", userRole: "Owner" }]
    writer.onSections = [{ id: orderingSection, name: "Section", notebookId: orderingBook }]
    var parents = function(ids) {
      return ids.map(function(id) {
        return { id: id, sectionId: orderingSection, title: id.toUpperCase(), clientId: id, level: 0 }
      })
    }
    writer.pages = parents(["a", "b", "c"])
    orderLane.jobs = []
    var answers = []
    var drop = function(name, ids) {
      writer.reorder("pages:" + orderingSection, ids.map(function(id) {
        return writer.pathOf(id)
      }), function(result) {
        answers.push(name + ":" + (result.error || "saved"))
      })
    }
    var run = function(job) {
      job.start({ done: function(result) {
        job.settled(result, { superseded: false, cancelled: false })
      } })
    }
    drop("first", ["b", "a", "c"])
    var first = orderLane.jobs.shift()
    run(first)
    var written = JSON.parse(writer.commands[0].payload)
    check("a OneNote page order is a write keyed to its section, which a newer order can replace",
          first.options.key === "page-order:" + orderingSection && first.options.mode === "replace"
          && first.options.flush === true)
    check("a page order write is checked against the order OneNote is known to hold",
          written.expected.join(",") === "a,b,c" && written.order.join(",") === "b,a,c")
    drop("second", ["c", "b", "a"])
    check("a drop while the section's order is saving is taken, not refused",
          answers.length === 0 && orderLane.jobs.length === 1)
    drop("third", ["c", "a", "b"])
    orderLane.jobs.shift().settled(null, { superseded: true, cancelled: false })
    check("an order replaced while it waited answers as saved: the newer one holds all of it",
          answers.join(",") === "second:saved")
    writer.commands[0].context.done({ sections: writer.onSections, pages: parents(["b", "a", "c"]),
                                      pendingSections: [], pageListSerial: 1 })
    run(orderLane.jobs.shift())
    written = JSON.parse(writer.commands[1].payload)
    check("a queued page order write is checked against the order the write before it left",
          answers.join(",") === "second:saved,first:saved"
          && written.expected.join(",") === "b,a,c" && written.order.join(",") === "c,a,b")
    drop("fourth", ["a", "c", "b"])
    writer.commands[1].context.done({ error: "the answer was lost" })
    var rereads = function() {
      return orderLane.jobs.some(function(job) { return job.options.key === "pages:" + orderingSection })
    }
    check("an older write's failure leaves the section to the newer write behind it",
          answers[answers.length - 1] === "third:the answer was lost" && !rereads()
          && writer.pageOrderingAvailable(writer.onSections[0]))
    writer.pages = parents(["b", "a", "c", "d"])
    run(orderLane.jobs.shift())
    check("a write whose pages changed while it waited is refused, and the newest one's failure re-reads the section, which stays orderable",
          writer.commands.length === 2 && answers[answers.length - 1] === "fourth:The pages changed — try reordering again"
          && rereads() && writer.pageOrderingAvailable(writer.onSections[0]))
    // An order waits while OneNote has still to answer for a page being
    // made or deleted in its section. A page being made is in the order at
    // once, and is written under the ID OneNote gives it.
    orderLane.jobs = []
    writer.pages = parents(["a", "b"])
    var made = ""
    writer.create("section:" + orderingSection, function(result) { made = result.path })
    var creation = orderLane.jobs.shift()
    var orderIdOf = function(path) {
      var row = writer.bookRows(orderingBook, 0).filter(function(candidate) { return candidate.path === path })[0]
      return row && row.reorder ? row.reorder.id : ""
    }
    check("a page being made is in its section's order at once",
          creation.options.key === "create:section:" + orderingSection && orderIdOf(made) === made)
    var answered = answers.length
    drop("made", [writer.idOf(made), "a", "b"])
    check("an order naming a page being made waits for OneNote to make it",
          orderLane.jobs.length === 0 && answers.length === answered)
    creation.settled({ page: { id: "made", sectionId: orderingSection, title: "", modified: "1", clientId: "made", level: 0 },
                       note: { title: "", body: "", view: "made-base" }, pageListSerial: 2 })
    var madeOrder = orderLane.jobs.shift()
    run(madeOrder)
    written = JSON.parse(writer.commands[writer.commands.length - 1].payload)
    check("once made, the page is written in the order under its own ID, and its row keeps the order's name for it",
          madeOrder.options.key === "page-order:" + orderingSection
          && written.expected.join(",") === "a,b,made" && written.order.join(",") === "made,a,b"
          && orderIdOf(writer.pathOf("made")) === made)
    writer.commands[writer.commands.length - 1].context.done({ sections: writer.onSections,
      pages: parents(["made", "a", "b"]), pendingSections: [], pageListSerial: 3 })
    check("the made page's order settles with its write", answers[answers.length - 1] === "made:saved")
    writer.pages = parents(["a", "b", "c", "d"])
    var removal = null
    writer.remove(writer.pathOf("d"), function(result) { removal = result })
    var deletion = orderLane.jobs.shift()
    answered = answers.length
    drop("replaced", ["c", "b", "a"])
    drop("held", ["b", "a", "c"])
    check("an order asked for while a page of its section is deleted waits, and a newer one replaces it",
          removal.pending && orderLane.jobs.length === 0 && answers.slice(answered).join(",") === "replaced:saved")
    deletion.settled({ ok: true, pageListSerial: 4 })
    run(orderLane.jobs.shift())
    written = JSON.parse(writer.commands[writer.commands.length - 1].payload)
    check("once the page is deleted, the order is written without it",
          written.expected.join(",") === "a,b,c" && written.order.join(",") === "b,a,c")
    writer.commands[writer.commands.length - 1].context.done({ sections: writer.onSections,
      pages: parents(["b", "a", "c"]), pendingSections: [], pageListSerial: 5 })
    var failedDraft = ""
    writer.create("section:" + orderingSection, function(result) { failedDraft = result.path })
    orderLane.jobs.shift().settled({ error: "uncertain network response" })
    check("a draft OneNote could not make keeps its row, out of the section's order, which stays on",
          answers[answers.length - 1] === "held:saved" && !!writer.pageAt(failedDraft) && orderIdOf(failedDraft) === ""
          && writer.parentPageIds(orderingSection).join(",") === "b,a,c"
          && writer.pageOrderingAvailable(writer.onSections[0]))
    writer.remove(failedDraft, function(result) {})
    orderLane.jobs = []
    writer.destroy()
    var creations = []
    var creationHost = {
      currentPath: "local:/notes/Other/note.md", treeCursor: "",
      newNote: function(provider, target) { creations.push(provider + ":" + target) },
      newNotebook: function(name, provider) { creations.push(provider + ":" + name) }
    }
    var folders = localFactory.createObject(test, { host: creationHost })
    folders.rebuild()
    check("empty local provider supplies its first notebook action",
          folders.sections.length === 0 && folders.footerActions[0].inputPlaceholder === "Notebook name")
    folders.notebooks = [{ key: "Work", name: "Work" }, { key: "Other", name: "Other" }]
    folders.notes = [{ key: "Other", path: creationHost.currentPath, title: "Other note" }]
    folders.rebuild()
    folders.action("newNote", "", "Work")
    folders.action("newNotebook", "Travel", "Work")
    check("local creation actions retain the active notebook and submitted name",
          creations.join(",") === "local:section:Work,local:Travel")
    check("a local notebook tab supplies New Note, New section and New notebook",
          folders.sections[0].footerActions.map(function(action) { return action.path }).join(",") === "newNote,newSection,newNotebook")
    // A listing cut short keeps the model it had and writes no order from
    // what it did reach; a whole listing lifts both holds.
    var said = []
    folders.statusRequested.connect(function(text) { said.push(text) })
    var record = function(name) { return "N\tWork\t/notes/Work/" + name + ".md\t" + name + "\t\t1\t1" }
    folders.loadList(["D\tWork", record("one"), record("two"), "E\tcomplete"].join("\n") + "\n")
    check("a whole listing is trusted", folders.listingComplete && folders.notes.length === 2 && folders.orderWritable("Work"))
    // A name travels escaped and arrives as the file system has it: the
    // path is the note's identity, and the saved order names it the same way.
    folders.loadList(["D\tWork", "O\tWork\ttab\\there.md", record("one"), "N\tWork\t/notes/Work/tab\\there.md\ttab\\there\t\t1\t1", "E\tcomplete"].join("\n") + "\n")
    check("a listed name arrives exact, tab and all, and its saved order finds it",
          folders.notes.length === 2 && folders.notes[0].path === "local:/notes/Work/tab\there.md" && folders.notes[0].title === "tab\there")
    folders.loadList(["D\tWork", record("one"), "E\tpartial\tthe listing is larger than 10 bytes"].join("\n") + "\n")
    check("a partial listing keeps the notes already known", !folders.listingComplete && folders.notes.length === 2)
    folders.persistOrder("Work")
    check("no order is written from a partial listing",
          !folders.orderWritable("Work") && said[said.length - 1].indexOf("order was not saved") >= 0, said.join("|"))
    folders.loadList(["D\tWork", "X\tWork\tPermission denied", "D\tOther", record("three").replace(/Work/g, "Other"), "E\tcomplete"].join("\n") + "\n")
    check("an unreadable notebook keeps its order while the rest is trusted",
          folders.listingComplete && !folders.orderWritable("Work") && folders.orderWritable("Other"))
    folders.loadList(["D\tWork", "E\tcomplete"].join("\n").replace("E\tcomplete", "") + "\n")
    check("a listing without its last line changes nothing", said[said.length - 1].indexOf("ended before") >= 0 && folders.notes.length === 1)
    folders.destroy()

    // An account answer that is not "signed out" — a probe that failed, a
    // refresh — leaves the listing alone; only the sign-out transition
    // throws the listing away. Checked before another provider shares the
    // fake account below: a destroyed provider still hears signals until the
    // event loop reclaims it.
    oneNote.onSections = [{ id: "section", name: "Section", notebookId: "book", notebook: "Book" }]
    oneNote.pages = [{ id: "page", sectionId: "section", title: "Note" }]
    var messages = []
    var relay = function(text) { messages.push(text) }
    oneNote.statusRequested.connect(relay)
    oneNoteAccount.statusFailed("boom")
    oneNoteAccount.updated()
    check("a failed probe keeps OneNote's pages and says why",
          oneNote.pages.length === 1 && messages.join("|") === "OneNote: could not check the sign-in — boom")
    oneNoteAccount.signedIn = false
    oneNoteAccount.signedOut()
    oneNoteAccount.updated()
    check("the sign-out transition clears OneNote's pages", oneNote.pages.length === 0)
    oneNote.statusRequested.disconnect(relay)
    oneNoteAccount.signedIn = true
    oneNote.onSections = []
    var created = oneNoteFactory.createObject(test, {
      host: creationHost, ms: oneNoteAccount
    })
    check("OneNote search waits for inventory during dynamic provider startup",
          created && created.searchStatus("onenote") === "Preparing content search…")
    created.onSections = [{ id: "section", notebookId: "book" }, { id: "other", notebookId: "other-book" }]
    created.pages = []
    created.searchInventoryReady = true
    check("OneNote search scope follows the initialized inventory",
          JSON.stringify(created.searchSections("book")) === '["section"]')
    created.notebookTabs = true
    created.rebuild()
    // A new queue starts a listing of its own; the section's job is the one
    // keyed to a notebook.
    var lane = created.rq, queued = []
    created.rq = { enqueue: function(opts) { queued.push(opts.key) } }
    created.action("newSection", "Plans", "other-book")
    created.rq = lane
    var sectionJobs = queued.filter(function(key) { return key.indexOf("section:") === 0 })
    check("OneNote footer section creation targets its own notebook",
          sectionJobs.length === 1 && sectionJobs[0] === "section:other-book", JSON.stringify(queued))
    check("OneNote publishes section creation with its account footer and no New Note button",
          created.sections.every(function(section) {
            return section.footerActions.some(function(action) { return action.path === "newSection" })
                && section.footerActions.some(function(action) { return action.path === "logout" })
                && !section.footerActions.some(function(action) { return action.path === "newNote" })
          }))
    created.expanded = ["section", "other"]
    created.rebuild()
    check("OneNote New Note remains inside sections and New section is absent from the tree",
          created.sections.every(function(section) {
            return section.rows.some(function(row) { return row.kind === "new" && row.level === 1 })
                && !section.rows.some(function(row) { return row.path === "newSection" })
          }))
    created.notebookTabs = false
    created.rebuild()
    var bookRows = created.sections[0].rows.filter(function(row) { return row.kind === "tree" && row.level === 0 })
    check("the combined OneNote tab offers New section on each notebook's row, not in its footer",
          !created.sections[0].footerActions.some(function(action) { return action.path === "newSection" })
          && bookRows.map(function(row) { return row.path }).sort().join(",") === "book,other-book"
          && bookRows.every(function(row) {
            return row.menu.some(function(item) { return item.id === "newSection" && !!item.prompt })
          }), JSON.stringify(bookRows.map(function(row) { return row.path })))

    // A section shows as soon as it is asked for and leaves the list as soon
    // as it is deleted; OneNote's answer only settles what then stays.
    var jobs = []
    created.rq = { depth: 0, enqueue: function(opts, start, settled) {
      jobs.push({ key: opts.key, priority: opts.priority, settled: settled })
      return { cancel: function() {} }
    }, cancelOwner: function(owner) {} }
    // A section's job; a new queue starts a listing of its own besides.
    var sectionJob = function() {
      for (var i = 0; i < jobs.length; i++) {
        if (jobs[i].key.indexOf("section:") === 0) {
          return jobs.splice(i, 1)[0]
        }
      }
      return null
    }
    var queued = function(key) {
      return jobs.some(function(job) { return job.key === key })
    }
    var listedIds = function() {
      return created.onSections.map(function(section) { return section.id })
    }
    var rowPaths = function() {
      created.rebuild()
      return created.sections[0].rows.map(function(row) { return row.path })
    }
    var asked = null
    created.createSection("other-book", "Ideas", function(result) { asked = result })
    var draft = created.onSections.filter(function(section) { return section.name === "Ideas" })[0]
    check("a new OneNote section is listed before OneNote answers",
          !!asked && !asked.error && !!draft && rowPaths().indexOf(draft.id) >= 0 && queued("section:other-book"),
          JSON.stringify({ asked: asked, draft: draft, rows: rowPaths(), jobs: jobs.map(function(job) { return job.key }) }))
    var refused = null
    created.create("section:" + draft.id, function(result) { refused = result })
    check("a section still being created takes no page and has no menu",
          !!refused && String(refused.error).indexOf("still being created") >= 0
          && created.sectionMenu(draft).length === 0, JSON.stringify(refused))
    sectionJob().settled({ section: { id: "made", notebookId: "other-book", name: "Ideas" }, pageListSerial: 0 }, {})
    check("OneNote's answer puts the made section in the stand-in's place",
          listedIds().indexOf("made") >= 0 && listedIds().indexOf(draft.id) < 0 && rowPaths().indexOf("made") >= 0)
    var refreshed = null
    created.rowAction("made", "refresh", "", function(result) { refreshed = result })
    var refreshJob = jobs.filter(function(job) { return job.key === "pages:made" })[0]
    check("a OneNote section's Refresh lists its pages ahead of background work and lets the open note go at once",
          !!refreshed && !refreshed.error && !!refreshJob && refreshJob.priority === 0,
          JSON.stringify({ refreshed: refreshed, jobs: jobs.map(function(job) { return job.key }) }))
    if (refreshJob) {
      jobs.splice(jobs.indexOf(refreshJob), 1)
      refreshJob.settled(null)
    }
    created.createSection("other-book", "Broken", function(result) {})
    var broken = created.onSections.filter(function(section) { return section.name === "Broken" })[0]
    sectionJob().settled({ error: "refused" }, {})
    check("a section OneNote refuses leaves the list again", listedIds().indexOf(broken.id) < 0)

    created.pages = [{ id: "p1", sectionId: "made", title: "One" }, { id: "p2", sectionId: "made", title: "Two" }]
    var outcomes = []
    created.noteDeletionFinished.connect(function(path, result) {
      outcomes.push(path + ":" + (result.error || "ok"))
    })
    var answered = null
    created.rowAction("made", "delete", "", function(result) { answered = result })
    check("a deleted OneNote section leaves the list at once, its pages reported going",
          !!answered && answered.pending === true
          && answered.removed.join(",") === created.pathOf("p1") + "," + created.pathOf("p2")
          && rowPaths().indexOf("made") < 0 && queued("section:made"), JSON.stringify(answered))
    sectionJob().settled({ error: "the section is open elsewhere" }, {})
    check("a section OneNote keeps comes back, each page told the delete failed",
          rowPaths().indexOf("made") >= 0
          && outcomes.join(",") === created.pathOf("p1") + ":the section is open elsewhere," + created.pathOf("p2") + ":the section is open elsewhere",
          outcomes.join(","))
    outcomes = []
    created.rowAction("made", "delete", "", function(result) {})
    sectionJob().settled({ ok: true, pages: ["p1", "p2"], pageListSerial: 0 }, {})
    check("a section OneNote deletes is gone for good, each page told so",
          listedIds().indexOf("made") < 0 && rowPaths().indexOf("made") < 0
          && outcomes.join(",") === created.pathOf("p1") + ":ok," + created.pathOf("p2") + ":ok", outcomes.join(","))
    // A draft OneNote could not make goes with its section, and no listing brings it back.
    created.onSections = created.onSections.concat([{ id: "drafts", notebookId: "other-book", name: "Drafts" }])
    var failedDraft = { id: "draft-page", sectionId: "drafts", title: "Draft" }
    created.pendingPages = { "draft-page": { page: failedDraft, operations: [], error: "not made" } }
    created.pages = created.pages.concat([failedDraft])
    created.rowAction("drafts", "delete", "", function(result) {})
    sectionJob().settled({ ok: true, pages: [], pageListSerial: 0 }, {})
    created.applyInventory({ sections: created.onSections, notebooks: created.onNotebooks, pages: [], pageListSerial: 100 })
    check("a deleted section's drafts OneNote could not make go with it",
          Object.keys(created.pendingPages).length === 0
          && !created.pages.some(function(page) { return page.id === "draft-page" }), JSON.stringify(created.pages))
    created.rq = lane
    created.destroy()
    oneNote.notebookTabs = false
    oneNote.onSections = [{ id: "section", name: "Section", notebookId: "book", notebook: "Book" }]
    oneNote.pages = [{ id: "page", sectionId: "section", title: "Note" }]
    oneNote.rebuild()
    check("OneNote stays ready without Files.Read", oneNote.ready && oneNote.accountRows() === null)
    check("OneNote notes remain visible without Files.Read", oneNote.sections[0].notes.length === 1)
    check("OneNote keeps sign-out out of the scrolling tree",
          oneNote.sections[0].footerActions.some(function(action) { return action.path === "logout" }) &&
          !oneNote.sections[0].rows.some(function(row) { return row.path === "logout" }))
    oneNote.notebookTabs = true
    oneNote.rebuild()
    check("OneNote notebook tabs retain the account footer",
          oneNote.sections[0].key === "book" && oneNote.sections[0].footerActions.some(function(action) { return action.path === "logout" }))
    oneNote.notebookTabs = false
    oneNote.rebuild()
    check("losing Files.Read does not hide notes", oneNote.ready && oneNote.sections[0].notes.length === 1)
    check("OneNote sign-in includes OneDrive write access",
          oneNote.microsoftScopes.indexOf("Files.ReadWrite") >= 0 && oneNote.microsoftScopes.indexOf("Notes.ReadWrite") >= 0)
    check("optional initial consent stays optional during renewal",
          scopeAccount.loginScopes.indexOf("Files.Read") >= 0 && scopeAccount.env.NOTE_NOTE_MS_SCOPES.indexOf("Files.Read") < 0 &&
          scopeAccount.env.NOTE_NOTE_MS_OPTIONAL_SCOPES === "Files.Read")

    var previousExpansion = oneNote.expanded
    oneNote.onNotebooks = [{ id: "book", name: "Book", userRole: "Reader" }]
    oneNote.expanded = ["book", "section"]
    oneNote.rebuild()
    check("read-only shared notebooks keep their notes and omit creation actions",
          oneNote.sections[0].notes.length === 1 &&
          !oneNote.bookRows("book", 0).some(function(row) { return row.kind === "new" }) &&
          !oneNote.accountActions("book").some(function(action) { return action.path === "newSection" }) &&
          oneNote.createTargetFor("onenote:page") === "")
    var sharedBody = oneNote.cacheBody("onenote:page", { title: "Title", body: "Shared", view: "shared-view", editable: true })
    check("a cached shared page respects its notebook's read-only permission", !sharedBody.editable && !!sharedBody.reason)
    var sharedSave = null
    oneNote.save("onenote:page", "Title", "Attempted edit", function(result) { sharedSave = result }, {})
    check("read-only shared pages reject saves before queuing", !!sharedSave.error && oneNote.bodies.page.body === "Shared")
    oneNote.onNotebooks = []
    oneNote.expanded = previousExpansion
    oneNote.rebuild()

    var changed = 0
    var onChanged = function(path) { changed++ }
    oneNote.noteChanged.connect(onChanged)
    oneNote.rq = mergeLane
    check("OneNote starts listing when its lane becomes available",
          oneNote.listPending && mergeLane.jobs.length === 1 && mergeLane.jobs[0].options.key === "list")
    mergeLane.jobs.shift().settled({ sections: oneNote.onSections, pages: oneNote.pages, inventoryComplete: true })
    oneNote.cacheBody("onenote:page", { title: "Title", body: "original", view: "editor-base", editable: true })
    oneNoteSession.selectPath("onenote:page")
    var baseline = { view: oneNoteSession.editingView }
    oneNote.save("onenote:page", "Title", "first edit", function(r) {}, baseline)
    oneNote.save("onenote:page", "Title", "second edit", function(r) {}, baseline)
    oneNote.applyCheck("onenote:page", { title: "Title", body: "phone edit", editable: true })
    check("poll leaves an active OneNote editing baseline intact", oneNoteSession.editingView === "editor-base")
    changed = 0
    mergeLane.jobs.shift().settled({ title: "Title", body: "older merge", view: "old-result", merged: true })
    check("older save result cannot reload over a newer save", changed === 0)
    mergeLane.jobs.shift().settled({ title: "Title", body: "newer merge", view: "new-result", merged: true })
    check("successful merge has a separate future editing view", changed === 1 &&
          oneNote.bodies.page.view === "new-result" && oneNoteSession.editingView === "editor-base")
    oneNoteSession.reloadCurrent()
    check("baseline switches when the merged note is displayed", oneNoteSession.editingView === "new-result")
    changed = 0
    oneNote.save("onenote:page", "Title", "ordinary edit", function(r) {}, { view: oneNoteSession.editingView })
    mergeLane.jobs.shift().settled({ title: "Title", body: "ordinary edit", view: "ordinary-result", merged: false })
    check("ordinary autosave does not reload and clear undo", changed === 0)
    var conflictResult = null
    oneNote.save("onenote:page", "Title", "overlap", function(r) { conflictResult = r }, { view: oneNoteSession.editingView })
    mergeLane.jobs.shift().settled({ error: "conflict", conflict: conflictPane.conflict })
    check("OneNote passes structured conflicts to the host", conflictResult.conflict.id === "conflict")
    oneNoteSession.selectPath("onenote:race")
    oneNoteSession.selectPath("onenote:away")
    oneNoteSession.selectPath("onenote:race")
    var abandoned = mergeLane.jobs.shift()
    var away = mergeLane.jobs.shift()
    mergeLane.jobs.shift().settled({ title: "Title", body: "Displayed body", view: "displayed-view", editable: true })
    abandoned.settled({ title: "Title", body: "Unseen cloud body", view: "abandoned-view", editable: true })
    away.settled({ title: "Other", body: "Other body", view: "other-view", editable: true })
    check("discarded OneNote loads cannot replace the accepted document, baseline, or cache",
          document.body === "Displayed body" && oneNoteSession.editingView === "displayed-view" &&
          oneNote.bodies.race.view === "displayed-view")
    document.title = "Only a title edit"
    oneNoteSession.onEdited()
    oneNoteSession.flushSave()
    document.conversions.shift()("Displayed body", true)
    check("a title edit captures the displayed OneNote baseline", oneNoteSession.drafts["onenote:race"].view === "displayed-view")
    mergeLane.jobs.shift().settled({ title: document.title, body: "Displayed body", view: "saved-view", merged: false })
    oneNoteSession.currentPath = ""
    oneNote.noteChanged.disconnect(onChanged)
    oneNote.rq = null
  }
  function oneNoteCreationCases() {
    var source = creatingOneNoteFactory.createObject(test, { ms: oneNoteAccount })
    creationSession.source = source
    var deletionOutcomes = {}, statuses = []
    source.statusRequested.connect(function(text) { statuses.push(text) })
    source.notePathChanged.connect(function(previous, next, view) {
      creationSession.replacePath(previous, next, view)
    })
    source.noteDeletionFinished.connect(function(path, result) {
      deletionOutcomes[path] = result
      creationSession.finishDeletion(path, result)
    })
    source.onSections = [{ id: "s", name: "Section", notebookId: "n", notebook: "Notebook" },
                         { id: "other", name: "Other", notebookId: "n", notebook: "Notebook" }]
    var original = [{ id: "a", sectionId: "s", title: "A" }, { id: "b", sectionId: "s", title: "B" },
                    { id: "z", sectionId: "other", title: "Z" }]
    source.pages = original
    source.rq = mergeLane
    mergeLane.jobs.shift().settled({ sections: source.onSections, pages: original })
    var first = "", second = "", replies = 0
    source.create("section:s", function(result) {
      first = result.path
      replies++
    })
    source.create("section:s", function(result) {
      second = result.path
      replies++
    })
    check("OneNote creates two distinct editable drafts before any network response",
          replies === 2 && first && second && first !== second && mergeLane.jobs.length === 2)
    var firstId = source.idOf(first), secondId = source.idOf(second)
    check("OneNote drafts append at the end of their section in creation order",
          source.pages.map(function(page) { return page.id }).join(",") === "a,b," + firstId + "," + secondId + ",z")
    check("OneNote creation expands its destination immediately",
          source.expanded.indexOf("s") >= 0 && source.expanded.indexOf("n") >= 0)
    source.applyInventory({ sections: source.onSections, pages: original })
    check("a listing during creation retains both local drafts",
          source.pages.map(function(page) { return page.id }).join(",") === "a,b," + firstId + "," + secondId + ",z")
    creationSession.selectPath(first)
    check("a new OneNote draft opens without a remote page read",
          !creationSession.loadingNote && creationSession.writable && mergeLane.jobs.length === 2)
    document.title = "Typed immediately"
    document.body = "early content"
    creationSession.onEdited()
    creationSession.flushSave()
    document.conversions.shift()("early content", true)
    check("typing before creation retains the draft and waits to send its save",
          source.bodies[firstId].body === "early content" && creationSession.saveInFlight(first) && mergeLane.jobs.length === 2)
    creationSession.onEdited()
    creationSession.flushSave()
    document.conversions.shift()("early content", true)
    check("autosaves during a slow creation retain only the latest document",
          source.pendingPages[firstId].operations.length === 1 && creationSession.savesPending[first] === 1)
    var firstCreate = mergeLane.jobs.shift()
    var secondCreate = mergeLane.jobs.shift()
    check("remote creates share a section key to preserve their order",
          firstCreate.options.key === secondCreate.options.key && firstCreate.options.mode === "append")
    var sequence = creationSession.noteLoadSeq
    source.lastPages = { n: first }
    firstCreate.settled({ page: { id: "real-first", sectionId: "s", title: "", modified: "1" },
                          note: { title: "", body: "", view: "first-base" }, pageListSerial: 2 })
    check("remote creation transfers identity without reloading the editor",
          creationSession.currentPath === "onenote:real-first" && creationSession.noteLoadSeq === sequence &&
          document.title === "Typed immediately" && document.body === "early content" &&
          creationSession.editingView === "first-base")
    check("accepted saves and notebook memory follow the permanent page identity",
          creationSession.saveInFlight("onenote:real-first") && creationSession.drafts["onenote:real-first"] &&
          !creationSession.drafts[first] && source.lastPages.n === "onenote:real-first")
    var firstSave = mergeLane.jobs.shift()
    firstSave.start({ done: function(result) {} })
    check("the first save uses the remote ID and the new page's merge baseline",
          source.commands[0].args[0] === "update" && source.commands[0].args[1] === "real-first" &&
          JSON.parse(source.commands[0].payload).view === "first-base" &&
          JSON.parse(source.commands[0].payload).body === "early content")
    firstSave.settled({ title: "Typed immediately", body: "early content", view: "first-saved" })
    check("a save accepted under a draft ID finishes under the permanent ID",
          !creationSession.busy && !creationSession.drafts["onenote:real-first"])

    creationSession.selectPath(second)
    document.body = "conversion still running"
    creationSession.onEdited()
    creationSession.flushSave()
    secondCreate.settled({ page: { id: "real-second", sectionId: "s", title: "", modified: "2" },
                           note: { title: "", body: "", view: "second-base" }, pageListSerial: 3 })
    document.conversions.shift()("conversion still running", true)
    var lateSave = mergeLane.jobs.shift()
    lateSave.start({ done: function(result) {} })
    check("a conversion finishing after creation saves the new identity and baseline",
          source.commands[1].args[1] === "real-second" && JSON.parse(source.commands[1].payload).view === "second-base")
    lateSave.settled({ title: "", body: "conversion still running", view: "second-saved" })
    var synced = [original[0], original[1], { id: "real-first", sectionId: "s", title: "Typed immediately", modified: "1" },
                  { id: "real-second", sectionId: "s", title: "", modified: "2" }, original[2]]
    source.applyInventory({ sections: source.onSections, pages: original, pageListSerial: 1 })
    check("an obsolete listing cannot drop newly created pages", source.pages.length === 5)
    source.applyInventory({ sections: source.onSections, pages: synced, pageListSerial: 3 })
    check("OneNote page positions stay the same after sync",
          source.pages.map(function(page) { return page.id }).join(",") === "a,b,real-first,real-second,z")

    var failed = ""
    source.create("section:s", function(result) { failed = result.path })
    creationSession.selectPath(failed)
    document.body = "keep this on failure"
    creationSession.onEdited()
    creationSession.flushSave()
    document.conversions.shift()(document.body, true)
    statuses = []
    creationSession.reports = []
    mergeLane.jobs.shift().settled({ error: "uncertain network response" })
    check("failed creation keeps typed content editable and reports an unsaved draft",
          document.body === "keep this on failure" && creationSession.writable && creationSession.dirty &&
          !!creationSession.drafts[failed].error && !!source.pageAt(failed))
    check("a failed creation with a waiting save is reported once, by that save",
          statuses.length === 0 && creationSession.reports.length === 1 &&
          creationSession.reports[0] === creationSession.drafts[failed].error &&
          creationSession.reports[0].indexOf("uncertain network response") >= 0 &&
          creationSession.reports[0].indexOf("delete this draft") >= 0)
    creationSession.flushSave()
    document.conversions.shift()(document.body, true)
    check("a failed creation is never blindly replayed by autosave",
          mergeLane.jobs.length === 0 && creationSession.dirty && !creationSession.busy)
    var removed = null
    creationSession.remove(failed, function(result) { removed = result })
    check("a failed local draft can be deleted without contacting Microsoft", removed && !removed.error && !source.pageAt(failed))
    creationSession.selectPath("")

    var unattended = ""
    source.create("section:s", function(result) { unattended = result.path })
    statuses = []
    mergeLane.jobs.shift().settled({ error: "throttled" })
    check("a failed creation nobody waits on is said once on the status line",
          statuses.length === 1 && statuses[0].indexOf("throttled") >= 0)
    source.remove(unattended, function(result) {})

    var deleting = "", deleteResult = null
    source.create("section:s", function(result) { deleting = result.path })
    source.remove(deleting, function(result) { deleteResult = result })
    check("a draft disappears immediately when deleted during creation",
          deleteResult.pending && source.sections[0].notes.every(function(note) { return note.path !== deleting }))
    mergeLane.jobs.shift().settled(null)
    check("deleting an unsent creation removes its draft and settles the delete",
          deletionOutcomes[deleting] && !deletionOutcomes[deleting].error && !source.pageAt(deleting))

    var uncertain = "", uncertainDelete = null
    source.create("section:s", function(result) { uncertain = result.path })
    source.remove(uncertain, function(result) { uncertainDelete = result })
    mergeLane.jobs.shift().settled({ error: "Microsoft may have accepted the request" })
    check("an uncertain creation cannot be reported as a successful remote delete",
          uncertainDelete.pending && !!deletionOutcomes[uncertain].error && !!source.pageAt(uncertain) &&
          source.sections[0].notes.some(function(note) { return note.path === uncertain }))
    source.remove(uncertain, function(result) {})

    var racing = ""
    source.create("section:s", function(result) { racing = result.path })
    var racingCreate = mergeLane.jobs.shift()
    var deletion = null, discardedSave = 0
    source.save(racing, "Title", "text before delete", function(result) { discardedSave++ }, {})
    creationSession.selectPath(racing)
    creationSession.remove(racing, function(result) {
      deletion = result
      creationSession.selectPath("")
    })
    racingCreate.settled({ page: { id: "real-delete", sectionId: "s", title: "" },
                          note: { title: "", body: "", view: "delete-base" }, pageListSerial: 4 })
    var queuedDelete = mergeLane.jobs.shift()
    check("deleting during creation discards deferred saves and deletes the permanent page",
          discardedSave === 1 && queuedDelete.options.key === "page:real-delete" &&
          queuedDelete.options.mode === "replace" && mergeLane.jobs.length === 0)
    check("a pending deletion follows the permanent identity without locking the editor",
          !!creationSession.pendingDeletions["onenote:real-delete"] && !creationSession.locked)
    queuedDelete.settled({ pageListSerial: 5 })
    check("a draft deleted during creation cannot reappear after sync",
          deletion.pending && !deletionOutcomes["onenote:real-delete"].error && !source.pageAt(racing) && mergeLane.jobs.length === 0)
    check("the permanent delete releases its provisional recovery context", !creationSession.busy)

    creationSession.editor = editor
    var editorDraft = ""
    source.create("section:s", function(result) { editorDraft = result.path })
    creationSession.selectPath(editorDraft)
    editor.insertFormattedText(0, 0, "immediate typing", {})
    editor.setCursorPosition(5)
    var documentHtml = editor.documentHtml(), noteToken = editor.noteToken
    mergeLane.jobs.shift().settled({ page: { id: "real-editor", sectionId: "s", title: "" },
                                    note: { title: "", body: "", view: "editor-base" }, pageListSerial: 6 })
    check("the real editor retains its document and caret when creation finishes",
          editor.plainText() === "immediate typing" && editor.documentHtml() === documentHtml &&
          editor.cursorPosition() === 5 && editor.noteToken === noteToken)
    editor.undo()
    check("typing before remote creation remains undoable", editor.plainText() === "")
    editor.redo()
    check("typing before remote creation remains redoable", editor.plainText() === "immediate typing")
    creationSession.selectPath("")
    creationSession.editor = document
    source.destroy()
    creationSession.source = null
  }

  function oneNoteDeletionCases() {
    var source = creatingOneNoteFactory.createObject(test, { ms: oneNoteAccount })
    creationSession.source = source
    var completions = [], statuses = []
    source.statusRequested.connect(function(text) { statuses.push(text) })
    source.noteDeletionFinished.connect(function(path, result) {
      completions.push({ path: path, result: result })
      creationSession.finishDeletion(path, result)
    })
    source.onSections = [{ id: "s", name: "Section", notebookId: "n", notebook: "Notebook" },
                         { id: "other", name: "Other", notebookId: "n", notebook: "Notebook" }]
    source.expanded = ["s", "other"]
    var pages = ["a", "b", "c", "d"].map(function(id) {
      return { id: id, title: id.toUpperCase(), sectionId: "s", modified: "1" }
    }).concat([{ id: "x", title: "X", sectionId: "other", modified: "1" }])
    source.pages = pages
    source.rq = mergeLane
    mergeLane.jobs.shift().settled({ sections: source.onSections, pages: pages })
    pages.forEach(function(page) {
      source.cacheBody(source.pathOf(page.id), { title: page.title, body: "body " + page.id,
                       view: page.id + "-base", editable: true })
    })
    creationSession.selectPath("onenote:b")
    document.title = "Unsaved title"
    document.body = "unsaved text before deletion"
    creationSession.onEdited()
    var accepted = null, replies = 0
    creationSession.remove("onenote:b", function(result) {
      accepted = result
      replies++
      creationSession.selectPath("onenote:c")
    })
    check("OneNote deletion removes the row and opens the next note immediately",
          accepted.pending && replies === 1 && creationSession.currentPath === "onenote:c" &&
          source.sections[0].notes.map(function(note) { return note.path }).join(",") === "onenote:a,onenote:c,onenote:d,onenote:x")
    check("remote deletion drains in the background while the editor stays usable",
          creationSession.busy && !creationSession.locked && creationSession.writable && document.body === "body c" &&
          mergeLane.jobs.length === 1 && mergeLane.jobs[0].options.flush)
    var duplicate = null
    creationSession.reports = []
    creationSession.remove("onenote:b", function(result) { duplicate = result })
    check("a repeated delete cannot replace the original recovery document",
          !!duplicate.error && creationSession.pendingDeletions["onenote:b"].document.body === "unsaved text before deletion" &&
          mergeLane.jobs.length === 1)
    check("the session reports a refused delete once",
          creationSession.reports.join("|") === duplicate.error)
    // What a section delete taking the same note does (Workspace.runRowAction).
    creationSession.holdForDeletion("onenote:b")
    check("a section delete keeps the text a note's own delete still holds",
          creationSession.pendingDeletions["onenote:b"].document.body === "unsaved text before deletion"
          && creationSession.pendingDeletions["onenote:b"].unsaved)
    source.applyInventory({ sections: source.onSections, pages: pages })
    source.rebuild()
    check("refreshing during deletion does not bring its row back",
          source.sections[0].notes.every(function(note) { return note.path !== "onenote:b" }))
    statuses = []
    creationSession.reports = []
    mergeLane.jobs.shift().settled({ error: "delete refused" })
    check("a failed remote delete is reported once, by the session",
          statuses.length === 0 && creationSession.reports.join("|") === "OneNote: delete refused")
    check("a failed delete restores its original position without interrupting the current note",
          source.sections[0].notes.map(function(note) { return note.path }).join(",") === "onenote:a,onenote:b,onenote:c,onenote:d,onenote:x" &&
          creationSession.currentPath === "onenote:c" && document.body === "body c" && replies === 1 && !creationSession.busy)
    check("failed deletion retains the unsaved document and its editing baseline",
          creationSession.drafts["onenote:b"].document.body === "unsaved text before deletion" &&
          creationSession.drafts["onenote:b"].document.title === "Unsaved title" &&
          creationSession.drafts["onenote:b"].view === "b-base" && !!creationSession.failureFor(["onenote"]))
    creationSession.selectPath("onenote:b")
    check("reopening a restored note shows its unsaved text for editing",
          creationSession.dirty && creationSession.writable && document.body === "unsaved text before deletion")
    creationSession.flushSave()
    document.conversions.shift()(document.body, true)
    mergeLane.jobs.shift().settled({ title: document.title, body: document.body, view: "b-saved" })
    check("the restored note can be saved normally", !creationSession.busy && !creationSession.drafts["onenote:b"])
    creationSession.remove("onenote:b", function(result) {
      creationSession.selectPath("onenote:a")
    })
    source.applyInventory({ sections: source.onSections, pages: pages.filter(function(page) { return page.id !== "b" }) })
    mergeLane.jobs.shift().settled({ pageListSerial: 1 })
    source.applyInventory({ sections: source.onSections, pages: pages })
    source.rebuild()
    check("a successful deletion stays removed through stale listings and clears recovery state",
          !source.pageAt("onenote:b") && !source.bodies.b && !creationSession.busy &&
          !creationSession.pendingDeletions["onenote:b"])

    creationSession.remove("onenote:a", function(result) {
      creationSession.selectPath("onenote:d")
    })
    creationSession.remove("onenote:c", function(result) {})
    var deleteA = mergeLane.jobs.shift(), deleteC = mergeLane.jobs.shift()
    source.applyInventory({ sections: source.onSections, pages: [pages[3], pages[4]], pageListSerial: 1 })
    source.rebuild()
    check("several pending deletes remain hidden even when a listing omits them",
          source.sections[0].notes.map(function(note) { return note.path }).join(",") === "onenote:d,onenote:x")
    deleteC.settled({ error: "C refused" })
    deleteA.settled({ error: "A refused" })
    check("delete failures arriving out of order restore the original section order",
          source.sections[0].notes.map(function(note) { return note.path }).join(",") === "onenote:a,onenote:c,onenote:d,onenote:x" &&
          creationSession.currentPath === "onenote:d" && !creationSession.busy)
    var cancelled = null
    source.remove("onenote:c", function(result) { cancelled = result })
    mergeLane.jobs.shift().settled(null)
    check("a cancelled remote delete restores the note and reports failure",
          cancelled.pending && !!completions[completions.length - 1].result.error &&
          source.sections[0].notes.some(function(note) { return note.path === "onenote:c" }))
    check("each remote deletion has exactly one completion", completions.length === 5)
    var unlisted = null
    source.remove("onenote:unlisted", function(result) { unlisted = result })
    var unlistedDelete = mergeLane.jobs.shift()
    check("a page the listing has not reached is still deleted",
          unlisted.pending && unlistedDelete.options.key === "page:unlisted")
    unlistedDelete.settled({ error: "not found" })
    check("a failed delete of an unlisted page restores no row",
          !source.pageAt("onenote:unlisted") && completions[completions.length - 1].result.error === "not found")
    creationSession.selectPath("")
    creationSession.source = null
    source.destroy()
  }

  // A sign-out cancels a queued creation. The provisional page stays, so
  // the unsaved text the host keeps for it can still be reached and deleted
  // — otherwise it would refuse every close with no way to clear it.
  function oneNoteAccountChangeCases() {
    var source = creatingOneNoteFactory.createObject(test, { ms: creationAccount })
    creationSession.source = source
    source.noteDeletionFinished.connect(function(path, result) {
      creationSession.finishDeletion(path, result)
    })
    source.onSections = [{ id: "s", name: "Section", notebookId: "n", notebook: "Notebook" }]
    var listed = [{ id: "a", sectionId: "s", title: "A" }]
    source.pages = listed
    source.rq = mergeLane
    mergeLane.jobs.shift().settled({ sections: source.onSections, pages: listed })
    var draft = ""
    source.create("section:s", function(result) { draft = result.path })
    var creation = mergeLane.jobs.shift()
    creationSession.selectPath(draft)
    document.body = "typed before signing out"
    creationSession.onEdited()
    creationSession.flushSave()
    document.conversions.shift()(document.body, true)
    creationAccount.signedIn = false
    creationAccount.signedOut()
    creation.settled(null)
    check("signing out keeps a provisional page and its unsaved text reachable",
          source.pages.length === 1 && !!source.pageAt(draft) && !!creationSession.drafts[draft].error &&
          document.body === "typed before signing out")
    var discarded = null
    creationSession.remove(draft, function(result) { discarded = result })
    check("a draft whose creation the sign-out cancelled can still be deleted",
          discarded && !discarded.error && !source.pageAt(draft) && !creationSession.busy &&
          !creationSession.failureFor(["onenote"]))
    creationSession.selectPath("")
    creationSession.source = null
    source.destroy()
  }

  // The minute's poll asks OneDrive which sections changed, and checks the
  // open page and lists its section only while that section changed, or
  // while OneDrive cannot say.
  function oneNotePollCases() {
    var source = creatingOneNoteFactory.createObject(test, { ms: oneNoteAccount })
    source.onSections = [{ id: "s", name: "Section", notebookId: "n", notebook: "Notebook" }]
    source.pages = [{ id: "a", sectionId: "s", title: "A" }]
    source.rq = mergeLane
    mergeLane.jobs.shift().settled({ sections: source.onSections, pages: source.pages, inventoryComplete: true })
    var round = function(answer) {
      source.poll("onenote:a")
      source.poll("onenote:a")
      source.poll("onenote:a")
      var asked = mergeLane.jobs.shift()
      asked.settled(answer)
      var keys = mergeLane.jobs.map(function(job) { return job.options.key })
      while (mergeLane.jobs.length) {
        mergeLane.jobs.shift().settled(null)
      }
      return { asked: asked.options.key, keys: keys }
    }
    var changed = round({ tracked: ["s"], changed: ["s"] })
    check("the poll asks OneDrive which sections changed", changed.asked === "changes")
    check("a section OneDrive reports changed has its page checked and its pages listed",
          changed.keys.join() === "check:onenote:a,pages:s")
    check("a section that just changed is checked again while Graph catches up",
          round({ tracked: ["s"], changed: [] }).keys.join() === "check:onenote:a,pages:s")
    source.changedSections = { s: Date.now() - source.changeSettleMs - 1 }
    check("a quiet tracked section costs OneNote nothing", round({ tracked: ["s"], changed: [] }).keys.length === 0)
    check("a section OneDrive does not track is checked as before",
          round({ tracked: [], changed: [] }).keys.join() === "check:onenote:a,pages:s")
    source.pollTick = 0
    check("a failed round leaves the page checked as before",
          round({ error: "OneDrive did not list the changed files" }).keys.join() === "check:onenote:a,pages:s")
    check("a deferred round leaves the page checked as before",
          round({ deferred: true, retryAfter: 30 }).keys.join() === "check:onenote:a,pages:s")
    check("a cancelled round checks nothing", round(null).keys.length === 0)
    source.rq = null
    source.destroy()
  }

  // The cases about notes, which NOTE_NOTE_TEST_NOTES_ONLY runs alone.
  function noteCases() {
    unsavedTitleCases()
    sessionCases()
    mergeCases()
    lifecycleCases()
    editabilityCases()
    renameBackCases()
    storedCases()
    oneNoteCases()
    oneNoteCreationCases()
    oneNoteDeletionCases()
    oneNoteAccountChangeCases()
    oneNotePollCases()
  }

  Component.onCompleted: {
    backend.install()
    try {
      if (!test.core) {
        return
      }
      if (Platform.env("NOTE_NOTE_TEST_NOTES_ONLY")) {
        noteCases()
        report()
        return
      }
      editorCases()
      noteCases()
      pureCases()
      orderCases()
      listingRaceCases()
      laneProviderCases()
      processCases()
      localCases()
      remoteModelCases()
      noticeCases()
      inspectorCases()
      clipboardCases()
      accountCases()
    } catch (error) {
      check("test setup completed", false, error.message + " " + error.stack)
      report()
    }
  }
  Timer {
    id: completion
    interval: 250
    repeat: true
    running: true
    onTriggered: {
      if (test.localFinished && test.watchFinished && test.editorFinished && test.accountFinished && test.processes === 0 && (!test.appHost || test.appHost.providersLoaded)) {
        if (test.appHost) {
          test.check("host reads framed configuration at startup", test.appHost.configReady && test.appHost.providers.length === 0)
          test.hostSearchCases()
          test.hostFooterCases()
          test.hostColourCases()
          test.hostOrderingCases()
        }
        test.completionChecks.forEach(function(check) { check() })
        test.check("runner releases every process", runner.active === 0)
        test.report()
      }
    }
  }
  Timer {
    id: watchCheck
    interval: 1500
    onTriggered: {
      test.check("own saves do not hide external filesystem events",
                 local.notes.some(function(note) { return note.title === "External changed" }))
      test.watchFinished = true
    }
  }
  // The suite's deadline, which the runner sets inside its own limit for
  // the harness (tests/transition_selftest.py): what is unfinished is
  // reported, and the harness quits between two editor scenarios.
  Timer {
    interval: Number(Platform.env("NOTE_NOTE_TEST_DEADLINE_MS"))
    running: true
    onTriggered: {
      test.check("all asynchronous scenarios finished", false, JSON.stringify({
        suite: test.suite,
        local: test.localFinished,
        watcher: test.watchFinished,
        editor: test.editorFinished,
        scenario: editorKeys.running,
        processes: test.processes,
        host: !test.appHost || test.appHost.providersLoaded
      }))
      test.report()
    }
  }
}
