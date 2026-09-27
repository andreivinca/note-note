# Commands and the picker

Commands are manifest descriptors plus lazily created QML handlers. Opening
the palette reads metadata; it does not instantiate all handlers. Qualified
command IDs are `<package-id>/<local-id>`. Labels and package directory names
can change without changing that identity.

Handlers import the application's public QML module:

```qml
import NoteNote.Extensions 1.0

Command {
  function execute(context, parameters, done) {
    context.ui.notify("Hello!")
    done({ ok: true })
  }
}
```

Call `done` once with `{ok: true}`, `{cancelled: true}`, or `{error: "message"}`.
The executor ignores late/duplicate completion, catches creation and synchronous
execution errors, and keeps one handler alive per interaction. One foreground
command is active at a time. Executable QML is trusted code; infinite loops and
process crashes cannot be isolated by this API.

Implemented context interfaces:

| Interface | Contract |
|---|---|
| `ui.notify(message)` | Short workspace status message |
| `ui.pick(options, callbacks)` | Generic searchable choices, described below |
| `workspace.invoke(action)` | Close the palette and hand control to an existing workspace action; returns `{ok: true}` or `{error}` |
| `resources.readText(path, callback)` | Bounded package-relative read returning `{text}` or `{error}` |
| `resources.readJson(path, callback)` | Strict JSON read returning `{value}` or `{error}` |
| `cancellation.isActive()` | Whether this invocation still accepts work |
| `cancellation.onCancel(callback)` | Register cancellation cleanup |
| `themes.list(callback)` | Reread and validate theme descriptors; returns `{items, diagnostics}` |
| `themes.current()`, `themes.supported` | Saved identity; availability of native display styling |
| `themes.beginPreview()` | Owned session with `preview(id)`, `commit(id)`, `cancel()` |
| `themes.diagnostics()` | Contrast diagnostics for the effective snapshot |
| `settings.check(callback)` | Detect stale configuration before an interaction |
| `settings.revision` | Captured configuration revision |
| `settings.setTheme(id, revision, callback)` | Persist one selection transaction; accepted writes finish before disposal |

Other proposed interfaces (editor commands and helper tasks) are added when a
real command needs them. The workspace, provider instances, and account objects
are not part of this command context.

The built-in [workspace plugin](../plugins/org.note-note.workspace/plugin.json)
provides New Note, New Notebook, Open Settings, Toggle Sidebar, and Delete Note.
Each handler uses the public API, for example:

```qml
import NoteNote.Extensions 1.0

Command {
  function execute(context, parameters, done) {
    done(context.workspace.invoke("newNote"))
  }
}
```

Supported action IDs are `newNote`, `newNotebook`, `openSettings`, `toggleList`,
and `deleteNote`. Success means the existing workspace flow accepted the action;
it is not a promise that a later provider write has completed. New Notebook opens
the existing name field, and Delete Note opens the existing confirmation. Their
later results and errors belong to those workspace flows. The palette closes
before control transfers, preserving the destination's focus. Each invocation
can hand off at most one action; canceled or finished commands cannot invoke one.

A command's optional manifest `workspaceAction` names its associated action.
The registry uses it to check availability and read the shortcut label from the
same keybinding definitions used by the keyboard and help page. The handler
still invokes the action explicitly. No shortcut is registered by this metadata.
Unknown actions remain unavailable. Availability is checked again when the API
is called, including for commands without a `workspaceAction` declaration.
Note actions and the sidebar toggle are unavailable while a page is open; note
creation needs a supported destination, notebook creation needs a provider's
creation entry, and deletion needs a deletable note. Existing transition and
modal guards apply to all workspace actions. Open Settings can focus the existing
Settings page without replacing its unsaved text.

Picker options are `{title, items, selectedId, message}`. An item has a stable
`id`, `label`, optional `detail`, `keywords`, `enabled`, `reason`, and `shortcut`.
Rows show only the label, with an optional shortcut hint aligned to the right.
The shortcut is display text; it does not register a keybinding. Details and
command categories remain searchable without appearing in the row. Callbacks
are `preview(id)`, `accept(id)`, and optional `cancel()`. Empty results preview
an empty ID. The returned controller provides `setBusy(bool, message)`,
`showError(message)`, and `setMessage(message)`; it belongs to that picker session.
An accept callback decides when its command completes.

Search uses case-insensitive exact labels, word prefixes, then substrings;
keyword/detail matches rank after label matches. Ties use label and stable ID.
Queries are limited to 256 characters, and at most 4,096 results are considered.
Up/Down and Page Up/Down navigate; Enter selects; Escape and outside clicks
cancel. Tab stays inside the picker. The prior live focus owner is restored
when it closes. The palette is unavailable over an active confirmation or
editing tool panel, and owns its keyboard events before page/editor shortcuts.

Commands can declare `requires` from `hasDocument`, `editorWritable`, and
`settingsClean`. Unavailable commands remain visible; selecting one shows its
reason in the footer.
The default palette shortcut is `Ctrl+Shift+P`. It participates in the same
registry and can be rebound with `app/commandPalette`.

## Registering shortcuts

A plugin declares defaults beside its commands in `plugin.json`. Registration
happens during discovery, before any handler executes:

```json
"contributes": {
  "commands": [{"id": "export-markdown", "title": "Export Markdown", "handler": "Export.qml"}],
  "keybindings": [{"command": "export-markdown", "key": "Ctrl+Shift+E", "context": "notes"}]
}
```

`command` must name a local command in the same package. Discovery qualifies it
as `<package-id>/export-markdown`. The palette obtains the effective label from
that identity; handlers never provide or format their command's shortcut label.
Keyboard execution uses the same executor and availability checks as the palette.
A picker opened by a shortcut restores the previous input focus when closed.
Commands without defaults still accept a user binding, in the `notes` context.

Contexts are `application` (all workspace views), `notes` (sidebar, editor,
search), or the narrower `workspace`, `editor`, `search`, and `page`. `workspace`
means the notes view outside the editor body and search input. `page` means
Settings or keyboard help. Confirmations, tool panels, and the command picker
own their local keys before the registry. Bare text/navigation keys and native
clipboard/undo/select-all shortcuts cannot be claimed by plugins or overrides.
Use Ctrl, Alt, Meta (Super), or a function key; Shift can be combined with them.
Keys include letters, digits, F1–F35, and names such as `Tab`, `Enter`, `Up`,
`Space`, `Plus`, and `Minus`. Multi-stroke chords are not supported.

## Changing bindings

Settings accepts a top-level `keybindings` array. Saving applies it immediately,
without restarting providers or redeploying plugins:

```json
"keybindings": [
  {"command": "app/newNote", "keys": ["Ctrl+Alt+N"]},
  {"command": "org.example.notes/export-markdown", "keys": ["Ctrl+Alt+E"]},
  {"command": "tool/bold", "keys": ["Ctrl+Alt+B"]},
  {"command": "app/search", "keys": []}
]
```

Each entry replaces **all** defaults for that action; an empty array unbinds it.
Removing an entry restores defaults. Up to eight keys per action are allowed.
Use `app/<action>` for built-ins (see [the catalogue](../ui/KeyBindings.js)),
`tool/<toolId>` for editing tools, and qualified command IDs for plugin commands.
A command with `workspaceAction: "newNote"` aliases `app/newNote`; overriding
either ID updates both keyboard execution and every associated command label.
Do not override both aliases at once: that ambiguity retains the defaults and
produces a diagnostic. Native clipboard actions remain fixed.

Overrides retain the action's context. For plugin commands, this is the union
of the contexts declared by their defaults, or `notes` when none were declared.
Bindings for absent/disabled plugins remain dormant, consuming no keys. Package
disable/removal takes effect at restart, together with all other contributions.

Precedence is user overrides, application defaults, then plugin/editing-tool
defaults. Two different actions at the same priority with overlapping contexts
lose that binding; load order never picks a winner. A conflicting binding is
disabled throughout its declared scope. Its command/tool stays available by
palette or button, and other nonconflicting bindings continue working. The
Key bindings page lists effective bindings and conflict diagnostics.

`services/shortcuts/KeybindingRegistry.qml` compiles registrations when metadata
or settings change. Keypress dispatch uses a lookup by normalized key, modifiers,
and context. The palette, tooltips, search hint, and help all read the same
result, so labels cannot drift from dispatch. No custom keyboard settings form
is required; a future form can edit the same override records.

See [the greeting package](../examples/plugins/greeting) for an independent
command that reads its own JSON resource and presents choices.
