# Commands and keybindings

A command is an entry in the command palette (Ctrl+Shift+P). It either names
one of the app's workspace actions, or points at a QML **handler** that the
app creates when the command runs. A package with a handler command is
executable code: it starts disabled until the user enables it.

## Manifest entry

```json
"commands": [
  {
    "id": "greet",
    "title": "Choose a greeting",
    "category": "Example",
    "keywords": ["hello", "salut"],
    "requires": ["hasDocument"],
    "handler": "Greeting.qml"
  }
]
```

| Field | Rule |
|---|---|
| `id` | local ID, unique among the package's commands; qualified as `<package-id>/<id>` |
| `title` | required, what the palette shows |
| `category` | optional; shown and searched |
| `keywords` | optional, at most 32 strings of at most 64 characters; searched, not shown |
| `requires` | optional, at most 16 of `hasDocument` (a note is open), `editorWritable` (the open note is editable), `settingsClean` (Settings has no unsaved edits). An unknown name counts as unmet, so the command stays unavailable |
| `handler` | a QML file in the package — **or** — |
| `workspaceAction` | one of `newNote`, `newNotebook`, `openSettings`, `toggleList`, `deleteNote` |

Exactly one of `handler` and `workspaceAction`. A command that is unavailable
still shows in the palette; choosing it says why in the palette's foot.

A `workspaceAction` command needs no QML: the app runs the action itself and
the command shares the action's availability and shortcut. It is how a
package puts an existing action in the palette under its own title.

## The handler

```qml
import NoteNote.Extensions 1.0

Command {
  function execute(context, parameters, done) {
    context.ui.notify("Hello!")
    done({ ok: true })
  }
}
```

- Import `NoteNote.Extensions 1.0` and make the root a `Command`. The app
  creates one instance per run and destroys it after `done`.
- `parameters` is a plain object — `{}` from the palette and from shortcuts.
- Call `done` exactly once: `{ ok: true }`, `{ cancelled: true }` or
  `{ error: "message the user will read" }`. Later or repeated calls are
  ignored; a command that never calls it stays the active command.
- Only one command runs at a time. A thrown error ends the command with that
  error; an infinite loop cannot be stopped — the handler is trusted code
  running in the app's own process.

### The context

Every member is a function.

| Call | Does |
|---|---|
| `context.ui.notify(message)` | a short status message in the workspace |
| `context.ui.pick(options, callbacks)` | a searchable list in the palette; returns its controller (below) |
| `context.workspace.invoke(action)` | closes the palette and hands over to a workspace action (the `workspaceAction` names); returns `{ ok: true }` or `{ error }`. At most one per run |
| `context.resources.readText(path, callback)` | reads a file of this package: `callback({ text })` or `callback({ error })`, 256 KiB at most |
| `context.resources.readJson(path, callback)` | the same, parsed strictly: `callback({ value })` or `callback({ error })` |
| `context.cancellation.isActive()` | whether this run still accepts work |
| `context.cancellation.onCancel(callback)` | cleanup to run if the run is cancelled |
| `context.themes.list(callback)` | rereads the themes: `callback({ items, diagnostics })`; each item has `enabled` and `reason` |
| `context.themes.current()` | the saved theme ID |
| `context.themes.beginPreview()` | a session with `preview(id)`, `commit(id)`, `cancel()`, ended with the command |
| `context.themes.diagnostics()` | contrast warnings for the colors in force |
| `context.settings.check(callback)` | reports stale configuration before an interaction: `callback({ error })` when there is some |
| `context.settings.setTheme(id, callback)` | saves the theme choice; `callback({ error })` on failure |

That is the whole API. There is no access to the open note, the editor,
providers, the clipboard or the network through it. QML itself can reach
further (`XMLHttpRequest`, `Qt.openUrlExternally`), but that is code the user
has to review and trust: keep a command to the context unless the user asks
for more, and bound anything it reads. When the user wants something the API
cannot do — such as inserting text into the note — say so rather than
reaching into the application's internals.

### The picker

```js
var picker = context.ui.pick({
  title: "Greeting",
  items: [{ id: "hello", label: "Hello!", detail: "English", keywords: ["hi"] }],
  selectedId: "hello",
  message: ""
}, {
  preview: function(id) {},   // the highlighted row changed; "" when nothing matches
  accept: function(id) {},    // Enter or click; the command decides when it is done
  cancel: function() {}       // Escape, a click outside, or cancellation
})
```

- An item is `{ id, label, detail?, keywords?, enabled?, reason?, shortcut? }`.
  `id` is stable; `detail` is shown after the label and searched; `shortcut` is
  display text only — it registers nothing.
- The controller has `setBusy(bool, message)`, `showError(message)` and
  `setMessage(message)`.
- The first `preview` arrives after `pick` has returned the controller.
- Call `done` from `accept` (or `cancel`) — the picker does not end the command.

### Pattern: pick from a list shipped in the package

`greetings.json`:

```json
[
  { "id": "hello", "label": "Hello!", "detail": "English" },
  { "id": "salut", "label": "Salut!", "detail": "Romanian" }
]
```

`Greeting.qml`:

```qml
import NoteNote.Extensions 1.0

Command {
  function execute(context, parameters, done) {
    context.resources.readJson("greetings.json", function(result) {
      if (result.error) {
        done(result)
        return
      }
      context.ui.pick({ title: "Greeting", items: result.value }, {
        accept: function(id) {
          var item = result.value.find(function(candidate) {
            return candidate.id === id
          })
          context.ui.notify(item.label)
          done({ ok: true })
        },
        cancel: function() {
          done({ cancelled: true })
        }
      })
    })
  }
}
```

### Pattern: hand over to a workspace action

```qml
import NoteNote.Extensions 1.0

Command {
  function execute(context, parameters, done) {
    var result = context.workspace.invoke("newNote")
    done(result.error ? result : { ok: true })
  }
}
```

Success means the workspace accepted the action, not that a later save
finished. Actions are unavailable while a page (Settings, help) is open, and
each has its own conditions: `newNote` needs a destination, `newNotebook` a
provider that creates notebooks, `deleteNote` a deletable note.

## Keybindings

A package gives its own commands default keys:

```json
"keybindings": [
  { "command": "greet", "key": "Ctrl+Alt+G", "context": "notes" }
]
```

- `command` is the local ID of a command **in the same package**; anything
  else rejects the manifest.
- `key`: at least one of `Ctrl`, `Alt`, `Meta` (Super), or a function key,
  plus optional `Shift`, joined with `+`: `Ctrl+Alt+G`, `Ctrl+Shift+E`,
  `Alt+F5`, `F7`. Keys are letters, digits, `F1`–`F35` and names such as
  `Tab`, `Enter`, `Up`, `Down`, `Left`, `Right`, `Space`, `Plus`, `Minus`.
  No multi-key chords. Bare text or navigation keys and the native clipboard,
  undo and select-all shortcuts can never be claimed.
- `context` (default `notes`) is where the key works: `application` (every
  view), `notes` (sidebar, editor, search), or the narrower `workspace` (the
  notes view outside the editor text and the search field), `editor`,
  `search`, `page` (Settings, keyboard help).
- A key or context the app cannot use costs only that binding; it is listed
  on the Key bindings page and the package still loads.
- Two actions of the same priority wanting the same key in overlapping
  contexts **both lose it**; nothing wins by load order. The app's own
  defaults outrank plugins, so avoid them: `Ctrl+Shift+P`, `Ctrl+K`,
  `Ctrl+L`, `Ctrl+N`, `Ctrl+Shift+N`, `Ctrl+D`, `Ctrl+E`, `Ctrl+J`, `Ctrl+S`,
  `Ctrl+Tab`, `Ctrl+Shift+Tab`, `Ctrl+Up/Down/Left/Right`, `Alt+1`–`Alt+9`,
  and the editing tools' keys (bold, italic, headings, lists…).
  `Ctrl+Alt+<letter>` is usually free.

The user can always override or unbind a key without changing the package,
in `config.json`:

```json
"keybindings": [
  { "command": "io.github.someone.nord/snippet", "keys": ["Ctrl+Alt+N"] },
  { "command": "io.github.someone.nord/other", "keys": [] }
]
```

Each entry replaces all the command's default keys (at most eight); `[]`
unbinds it. That takes effect on save, without a restart. A command with no
default key can still be bound this way (in the `notes` context).
