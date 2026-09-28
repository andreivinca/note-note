import QtQuick
import QtTest
import "app" as App
import "app/hosts/standalone" as Native
import "app/services/processes"
import "app/design"
import "app/design/resolve.js" as Resolve
import "app/design/tokens.js" as Tokens
import "app/services/themes/system.js" as SystemTheme
import "app/ui/commands/matching.js" as Matching
import "app/tests/ShortcutChecks.js" as ShortcutChecks

Window {
  id: window
  visible: true
  width: 1000
  height: 740
  color: workspace.background
  Native.Backend { id: backend }
  ProcessRunner { id: runner }
  App.Workspace {
    id: workspace
    anchors.fill: parent
  }
  Component.onCompleted: {
    backend.install()
    workspace.initialize()
    workspace.open("{}")
  }

  TestCase {
    id: checks
    name: "Extensions"
    when: false

    function request(options) {
      var answer = null
      runner.run(options, function(result) { answer = result })
      tryVerify(function() { return answer !== null }, 10000)
      return answer
    }

    function openThemePicker() {
      workspace.commandUi.open(null)
      workspace.commands.execute("org.note-note.appearance/select-theme", {})
      tryVerify(function() { return workspace.commandUi.choosing }, 10000)
      verify(!workspace.commandUi.busy)
    }

    function select(id) {
      var index = workspace.commandUi.matches.findIndex(function(item) { return item.id === id })
      verify(index >= 0, "missing choice " + id)
      workspace.commandUi.currentIndex = index
      workspace.commandUi.preview()
    }

    function capture(path) {
      if (!path) {
        return
      }
      var captured = false
      wait(100)
      workspace.grabToImage(function(result) {
        verify(result.saveToFile(path))
        captured = true
      })
      tryVerify(function() { return captured }, 5000)
    }

    function workspaceCommand(name) {
      return workspace.commands.list().find(function(item) {
        return item.id === "org.note-note.workspace/" + name
      })
    }

    function invokeWorkspaceCommand(name) {
      workspace.commandUi.open(window.activeFocusItem)
      select("org.note-note.workspace/" + name)
      verify(workspace.commandUi.current.enabled, name + ": " + workspace.commandUi.current.reason)
      workspace.commandUi.accept()
      tryVerify(function() { return !workspace.commands.busy && !workspace.commandUi.opened }, 10000)
    }

    function focusInside(item) {
      var focused = window.activeFocusItem
      while (focused && focused !== item) {
        focused = focused.parent
      }
      return focused === item
    }

    function saveBindings(bindings) {
      var config = JSON.parse(JSON.stringify(workspace.config))
      config.keybindings = bindings
      var answer = null
      workspace.applySettingsJson(JSON.stringify(config), function(result) { answer = result }, workspace.settings.revision)
      tryVerify(function() { return answer !== null }, 10000)
      if (answer.error) {
        throw new Error("Save keybindings: " + answer.error)
      }
    }

    function checkShortcutRebinding(editor) {
      var provider = workspace.providerById("local"), collapsed = workspace.listCollapsed
      var noteCount = provider.notes.length, originalPath = workspace.currentPath
      function unchanged(stage) {
        if (workspace.dirty) {
          throw new Error(stage + " unexpectedly changed the note")
        }
      }
      editor.focusEditor()
      keyClick(Qt.Key_G, Qt.ControlModifier | Qt.AltModifier)
      tryVerify(function() { return workspace.commandUi.choosing }, 10000)
      compare(workspace.commandUi.title, "Greeting")
      workspace.commandUi.requestClose()
      verify(focusInside(editor), "shortcut-launched picker restores editor focus")
      unchanged("default plugin shortcut")

      workspace.commandUi.open(window.activeFocusItem)
      select("org.note-note.workspace/new-note")
      saveBindings([
        { command: "app/newNote", keys: ["Ctrl+Alt+N"] },
        { command: "app/toggleList", keys: ["Ctrl+Alt+E"] },
        { command: "app/search", keys: ["Ctrl+Alt+K"] },
        { command: "app/savePage", keys: ["Ctrl+Alt+S"] },
        { command: "org.example.greeting/greet", keys: ["F6"] },
        { command: "tool/bold", keys: ["Ctrl+Alt+B"] }
      ])
      compare(workspace.providerById("local"), provider, "binding-only save keeps the provider instance")
      compare(workspace.commandUi.current.id, "org.note-note.workspace/new-note")
      compare(workspace.commandUi.current.shortcut, "ctrl+alt+n", "open palette refreshes labels")
      compare(workspace.shortcuts.label("app/search"), "ctrl+alt+k")
      compare(editor.tools.find("bold").shortcutLabel, "ctrl+alt+b")
      verify(workspace.shortcuts.helpText.indexOf("ctrl+alt+b") >= 0)
      workspace.commandUi.requestClose()
      unchanged("saving bindings")
      editor.focusEditor()
      keyClick(Qt.Key_E, Qt.ControlModifier)
      unchanged("old toggle shortcut")
      compare(workspace.listCollapsed, collapsed, "old shortcut no longer toggles")
      keyClick(Qt.Key_E, Qt.ControlModifier | Qt.AltModifier)
      compare(workspace.listCollapsed, !collapsed)
      keyClick(Qt.Key_E, Qt.ControlModifier | Qt.AltModifier)
      compare(workspace.listCollapsed, collapsed)
      unchanged("rebound toggle")
      verify(!workspace.handleShortcut({ key: Qt.Key_G, modifiers: Qt.ControlModifier | Qt.AltModifier }),
        "old plugin shortcut returns to native input handling")
      verify(!workspace.commands.busy && !workspace.commandUi.opened, "old plugin key no longer executes")
      keyClick(Qt.Key_F6)
      tryVerify(function() { return workspace.commandUi.choosing }, 10000)
      workspace.commandUi.requestClose()
      verify(focusInside(editor))
      workspace.openPage("settings")
      keyClick(Qt.Key_F6)
      verify(!workspace.commands.busy && !workspace.commandUi.opened, "notes binding cannot execute on Settings")
      var page = workspace.currentPage(), savedRevision = workspace.settings.revision
      verify(page.actionTooltip.indexOf("ctrl+alt+s") >= 0)
      keyClick(Qt.Key_S, Qt.ControlModifier)
      compare(workspace.settings.revision, savedRevision, "old save key does not run the page action")
      keyClick(Qt.Key_S, Qt.ControlModifier | Qt.AltModifier)
      tryVerify(function() { return page.noticeText.indexOf("Saved.") === 0 }, 10000)
      workspace.closePage()
      unchanged("page isolation")
      saveBindings([{ command: "org.example.greeting/greet", keys: [] }, { command: "app/newNote", keys: [] }])
      compare(workspaceCommand("new-note").shortcut, "")
      editor.focusEditor()
      keyClick(Qt.Key_N, Qt.ControlModifier)
      unchanged("unbound new note")
      wait(100)
      compare(workspace.providerById("local").notes.length, noteCount)
      compare(workspace.currentPath, originalPath)
      verify(!workspace.handleShortcut({ key: Qt.Key_G, modifiers: Qt.ControlModifier | Qt.AltModifier }))
      verify(!workspace.commandUi.opened && !workspace.commands.busy)
      saveBindings([])
      compare(workspaceCommand("new-note").shortcut, "ctrl+n")
      compare(editor.tools.find("bold").shortcutLabel, "ctrl+b")
    }

    function checkWorkspaceCommands(editor) {
      ShortcutChecks.run(function(value, message) { verify(value, message) })
      var provider = workspace.providerById("local")
      var originalPath = workspace.currentPath
      var initialCount = provider.notes.length
      compare(workspaceCommand("new-note").shortcut, "ctrl+n")
      compare(workspaceCommand("new-notebook").shortcut, "ctrl+shift+n")
      compare(workspaceCommand("delete-note").shortcut, "ctrl+d")
      compare(workspaceCommand("toggle-sidebar").shortcut, "ctrl+e")
      compare(workspaceCommand("open-settings").shortcut, "")

      var screenshot = backend.env("NOTE_NOTE_TEST_SCREENSHOT")
      if (screenshot) {
        workspace.commandUi.open(window.activeFocusItem)
        select("org.note-note.workspace/new-note")
        capture(screenshot.replace(/\.png$/, "-workspace.png"))
        workspace.commandUi.requestClose()
      }

      editor.focusEditor()
      var collapsed = workspace.listCollapsed
      invokeWorkspaceCommand("toggle-sidebar")
      compare(workspace.listCollapsed, !collapsed)
      verify(editor.bodyFocused, "palette handoff restores focus before toggling the sidebar")
      keyClick(Qt.Key_E, Qt.ControlModifier)
      compare(workspace.listCollapsed, collapsed)

      // Even an external command without workspace metadata goes through the
      // API's validation. A canceled invocation cannot perform a late action.
      workspace.commandUi.open(window.activeFocusItem)
      workspace.commands.execute("org.example.greeting/greet", {})
      tryVerify(function() { return workspace.commandUi.choosing }, 10000)
      var context = workspace.commandApi.contextFor(workspace.commands.active)
      verify(!!context.workspace.invoke("missingAction").error)
      workspace.deleteConfirmOpen = true
      verify(!!context.workspace.invoke("toggleList").error)
      compare(workspace.listCollapsed, collapsed)
      workspace.deleteConfirmOpen = false
      workspace.commandUi.requestClose()
      verify(!!context.workspace.invoke("toggleList").error)
      compare(workspace.listCollapsed, collapsed)

      workspace.commandUi.open(window.activeFocusItem)
      workspace.commands.execute("org.example.greeting/greet", {})
      tryVerify(function() { return workspace.commandUi.choosing }, 10000)
      context = workspace.commandApi.contextFor(workspace.commands.active)
      verify(context.workspace.invoke("toggleList").ok)
      verify(!!context.workspace.invoke("toggleList").error, "one accepted handoff per command")
      compare(workspace.listCollapsed, !collapsed)
      workspace.commands.cancel()
      keyClick(Qt.Key_E, Qt.ControlModifier)
      compare(workspace.listCollapsed, collapsed)

      invokeWorkspaceCommand("open-settings")
      compare(workspace.page, "settings")
      var page = workspace.currentPage()
      verify(focusInside(page), "closing the palette must not steal focus from Settings")
      keyClick(Qt.Key_Space)
      verify(page.dirty)
      var dirtySettings = page.savedText
      invokeWorkspaceCommand("open-settings")
      verify(page.dirty, "reopening Settings preserves unsaved edits")
      compare(page.savedText, dirtySettings)
      for (var name of ["new-note", "new-notebook", "delete-note", "toggle-sidebar"]) {
        verify(!workspaceCommand(name).enabled, name + " must not act on hidden notes")
      }
      // Execution rechecks availability even if called directly with a stale entry.
      workspace.commandUi.open(window.activeFocusItem)
      workspace.commands.execute("org.note-note.workspace/new-note", {})
      verify(workspace.commandUi.message.indexOf("Return to your notes") >= 0)
      compare(provider.notes.length, initialCount)
      workspace.commandUi.requestClose()
      workspace.closePage()

      // Creation uses the normal save path for a dirty note before opening the new one.
      editor.focusEditor()
      editor.setCursorPosition(editor.plainText().length)
      keyClick(Qt.Key_X)
      var originalBody = null
      editor.requestMarkdown(function(body, ok) {
        verify(ok)
        originalBody = body
      })
      tryVerify(function() { return originalBody !== null }, 5000)
      verify(workspace.dirty)
      invokeWorkspaceCommand("new-note")
      tryVerify(function() {
        return workspace.currentPath !== originalPath && !workspace.loadingNote && provider.notes.length === initialCount + 1
      }, 10000)
      var createdPath = workspace.currentPath
      tryVerify(function() { return !workspace.saveInFlight(originalPath) }, 10000)
      var loaded = null
      provider.load(originalPath, function(result) { loaded = result })
      tryVerify(function() { return loaded !== null }, 10000)
      compare(loaded.body.trim(), originalBody.trim())
      verify(focusInside(editor), "the new note receives focus")

      invokeWorkspaceCommand("delete-note")
      verify(workspace.deleteConfirmOpen)
      compare(workspace.deletePath, createdPath)
      compare(provider.notes.length, initialCount + 1)
      keyClick(Qt.Key_Escape)
      verify(!workspace.deleteConfirmOpen)
      verify(provider.notes.some(function(note) { return note.path === createdPath }))
      invokeWorkspaceCommand("delete-note")
      keyClick(Qt.Key_Right)
      keyClick(Qt.Key_Return)
      tryVerify(function() {
        return !workspace.deleteConfirmOpen && !provider.notes.some(function(note) { return note.path === createdPath })
      }, 10000)

      workspace.selectPath("")
      verify(!workspaceCommand("delete-note").enabled)
      verify(workspaceCommand("new-note").enabled, "creation does not require an open note")
      workspace.choosePath(originalPath)
      tryVerify(function() { return !workspace.loadingNote }, 10000)

      workspace.setFilter("Theme")
      workspace.listCollapsed = true
      invokeWorkspaceCommand("new-notebook")
      compare(workspace.filterText, "")
      verify(!workspace.listCollapsed)
      var input = findChild(workspace, "footerAction-local-newNotebook")
      verify(input.editing && focusInside(input), "the existing notebook name field keeps focus")
      keyClick(Qt.Key_Escape)
      verify(!input.editing)
      verify(!provider.notebooks.some(function(book) { return book.key === "Commandbook" }))
      invokeWorkspaceCommand("new-notebook")
      for (var letter of "Commandbook") {
        keyClick(letter)
      }
      keyClick(Qt.Key_Return)
      tryVerify(function() {
        return provider.notes.some(function(note) {
          return note.path === workspace.currentPath && note.key === "Commandbook"
        }) && !workspace.loadingNote
      }, 10000)
      verify(focusInside(editor))
      tryVerify(function() { return workspace.writesSettled }, 10000)
    }

    function run() {
      // Before anything was read from disk the colours are whole: the system's.
      compare(Object.keys(workspace.themes.colors).length, Object.keys(Tokens.specification).length)
      tryVerify(function() { return workspace.providersLoaded && workspace.themes.settled && !workspace.settings.busy }, 10000)
      compare(workspace.catalog.commands.length, 7)
      compare(workspace.catalog.problemSummary, "")
      var spec = Tokens.specification, resolvedSoFar = {}
      Object.keys(spec).forEach(function(key) {
        var recipe = Resolve.recipes[spec[key].recipe]
        verify(typeof recipe === "function", key + " names a recipe")
        compare(recipe.length, spec[key].inputs.length, key + " gives its recipe what it reads")
        verify(spec[key].inputs.every(function(input) { return resolvedSoFar[input] }), key + " follows its inputs")
        verify(!spec[key].pair || !!spec[spec[key].pair], key + " is paired with a token")
        resolvedSoFar[key] = true
      })
      var shipped = workspace.themes.catalog.entries[SystemTheme.themeId].value.colors
      compare(Object.keys(shipped).sort().join(), Object.keys(spec).sort().join(), "System states every token")
      verify(Object.keys(shipped).every(function(key) { return shipped[key] === "system" }))
      var system = workspace.themes.system
      compare(JSON.stringify(workspace.themes.colors), JSON.stringify(system))
      verify(Object.keys(system).every(function(key) { return /^#[0-9a-f]{6,8}$/i.test(system[key]) }),
        "every token resolves to a colour")
      var partial = Resolve.resolve(system, { "surface.background": "#181a20", "text.primary": "#ffffff", "editor.foreground": "system" })
      compare(partial["surface.background"], "#181a20")
      compare(partial["editor.foreground"], system["editor.foreground"])
      verify(partial["surface.raised"] !== system["surface.raised"])
      var matched = Matching.filter([{ id: "a", label: "Alpha", keywords: ["hello"] }, { id: "b", label: "Hello" }], "HELLO", "a")
      compare(matched.items[0].id, "b")
      compare(matched.items[matched.index].id, "a")

      tryVerify(function() { return workspace.rows.some(function(row) { return row.kind === "note" }) }, 10000)
      workspace.choosePath(workspace.rows.find(function(row) { return row.kind === "note" }).path)
      tryVerify(function() { return !!workspace.currentPath && !workspace.loadingNote }, 10000)
      var editor = findChild(workspace, "noteEditor")
      verify(editor.canColorText)
      checkShortcutRebinding(editor)
      var area = editor.tools.editor.textArea
      verify(!workspace.dirty, "clean before selection")
      var before = area.text
      area.select(2, 7)
      var start = area.selectionStart, end = area.selectionEnd
      var revision = workspace.settings.revision
      verify(!workspace.dirty, "clean before picker")
      openThemePicker()
      verify(!workspace.dirty, "clean before preview")
      select("org.example.colors/midnight")
      compare(workspace.themes.colors["surface.background"], "#181A20")
      compare(area.text, before)
      compare(area.selectionStart, start)
      compare(area.selectionEnd, end)
      verify(!workspace.dirty)
      compare(workspace.settings.revision, revision)
      var screenshot = backend.env("NOTE_NOTE_TEST_SCREENSHOT")
      capture(screenshot)
      workspace.commandUi.requestClose()
      compare(JSON.stringify(workspace.themes.colors), JSON.stringify(system))
      verify(!workspace.commands.busy)

      openThemePicker()
      keyClick(Qt.Key_Z)
      keyClick(Qt.Key_Z)
      compare(workspace.commandUi.matches.length, 0)
      compare(JSON.stringify(workspace.themes.colors), JSON.stringify(system))
      mouseClick(workspace, 5, workspace.height - 5)
      verify(!workspace.commandUi.opened)

      editor.focusEditor()
      keyClick(Qt.Key_P, Qt.ControlModifier | Qt.ShiftModifier)
      verify(workspace.commandUi.opened)
      var query = findChild(workspace.commandUi, "commandQuery")
      for (var letter of "Color Theme") {
        keyClick(letter)
      }
      compare(workspace.commandUi.matches.length, 1)
      var results = findChild(workspace.commandUi, "commandResults")
      // A one-result palette must fit the whole row above its footer.
      tryVerify(function() {
        var choice = findChild(results, "commandChoice-org.note-note.appearance/select-theme")
        if (!choice || choice.height <= 0) {
          return false
        }
        var top = choice.mapToItem(results, 0, 0).y
        return top >= 0 && top + choice.height <= results.height + 0.5
      })
      capture(screenshot ? screenshot.replace(/\.png$/, "-commands.png") : "")
      keyClick(Qt.Key_Escape)
      verify(!workspace.commandUi.opened)
      verify(editor.bodyFocused)

      openThemePicker()
      select("org.example.colors/midnight")
      workspace.commandUi.accept()
      workspace.commandUi.accept()
      tryVerify(function() { return !workspace.commands.busy && !workspace.settings.busy }, 10000)
      compare(workspace.config.appearance.theme, "org.example.colors/midnight")
      verify(workspace.settings.revision !== revision)
      compare(area.text, before)
      verify(!workspace.dirty)

      workspace.commandUi.open(null)
      workspace.commands.execute("org.example.greeting/greet", {})
      tryVerify(function() { return workspace.commandUi.choosing && workspace.commandUi.title === "Greeting" }, 10000)
      var hello = findChild(workspace, "commandChoice-hello")
      verify(hello !== null)
      mouseClick(hello, hello.width / 2, hello.height / 2)
      verify(workspace.statusText === "Hello!" || workspace.statusText === "Salut!")
      verify(!workspace.commands.busy)

      workspace.openPage("settings")
      var page = workspace.currentPage()
      page.focusBody()
      keyClick(Qt.Key_Space)
      verify(page.dirty)
      workspace.commandUi.open(null)
      var themeCommand = workspace.commands.list().find(function(item) { return item.id === "org.note-note.appearance/select-theme" })
      verify(!themeCommand.enabled)
      workspace.commandUi.requestClose()
      workspace.closePage()

      // A clean Settings buffer follows a theme commit and adopts its revision.
      workspace.openPage("settings")
      var cleanPage = workspace.currentPage()
      openThemePicker()
      select("org.note-note.appearance/system")
      workspace.commandUi.accept()
      tryVerify(function() { return !workspace.commands.busy }, 10000)
      compare(JSON.parse(cleanPage.savedText).appearance.theme, "org.note-note.appearance/system")
      openThemePicker()
      select("org.example.colors/midnight")
      workspace.commandUi.accept()
      tryVerify(function() { return !workspace.commands.busy }, 10000)
      verify(!cleanPage.dirty)
      compare(cleanPage.configRevision, workspace.settings.revision)
      compare(JSON.parse(cleanPage.savedText).appearance.theme, "org.example.colors/midnight")
      workspace.closePage()

      openThemePicker()
      select("org.note-note.appearance/system")
      var foreign = request({ command: ["python3", "-c", "import sys,json; p=sys.argv[1]; d=json.load(open(p)); d['foreign']=True; open(p,'w').write(json.dumps(d)); print('{}')", workspace.configPath] })
      verify(!foreign.error)
      workspace.commandUi.accept()
      tryVerify(function() { return workspace.settings.stale && !workspace.settings.busy }, 10000)
      verify(workspace.commandUi.opened)
      compare(workspace.themes.colors["surface.background"], "#181A20")
      workspace.commandUi.requestClose()
      verify(!workspace.commands.busy)

      // A later ordinary keystroke must still edit and save the note.
      editor.focusEditor()
      editor.setCursorPosition(editor.plainText().length)
      keyClick(Qt.Key_X)
      verify(workspace.dirty)
      workspace.flushSave()
      tryVerify(function() { return !workspace.dirty && !workspace.saveInFlight(workspace.currentPath) }, 10000)
      checkWorkspaceCommands(editor)
    }
  }

  Timer {
    interval: 100
    running: true
    onTriggered: {
      try {
        checks.run()
        console.error("<<<EXTENSIONS_DONE>>>")
        Qt.quit()
      } catch (error) {
        console.error("FAIL!", error.message, error.stack)
        console.error("Command UI:", workspace.commandUi.message, workspace.commandUi.title)
        Qt.exit(1)
      }
    }
  }
}
