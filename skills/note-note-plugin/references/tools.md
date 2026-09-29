# Editing tools

A tool is an action on the open note: a button in the editing toolbar (or an
entry in one of its menus), an optional default shortcut, and optionally a
panel that collects input first — the way **Insert → Insert month** works. The
app creates one instance per editor and hands it the editor's API. A package
with a tool is executable code: it starts disabled until the user enables it.

## Manifest entry

```json
"tools": [
  {"id": "insertStamp", "path": "InsertStamp.qml"}
]
```

| Field | Rule |
|---|---|
| `id` | the tool's **action ID**: a lowercase letter, then up to 63 letters and digits (`insertStamp`, not `insert-stamp`). It is not qualified with the package ID |
| `path` | the tool's QML file in the package |

The QML file's `toolId` must equal the manifest `id`, or the tool is skipped.
The ID is how everything else names the tool: the user's toolbar layout
(`editor.toolbar`), shortcut overrides (`tool/<id>`) and `editorTool <id>`.

IDs share one namespace with the app's own tools (`bold`, `h1`, `table`,
`link`, `currentMonth`, …) and every other package's. A tool the app ships
keeps its ID; a user package that reuses one loses its tool, and two user
packages that share an ID both lose it. Pick a distinctive ID. `scripts/check.py`
lists the package's tools but cannot see these clashes — they are decided when
the editor loads its tools and reported in the log as `Editing tool skipped:`.

## The QML

```qml
import NoteNote.Extensions 1.0

// Inserts today's date at the caret.
Tool {
  toolId: "insertStamp"
  label: "Insert date stamp"
  icon: "+"
  available: !editor.inCode
  shortcutKey: Qt.Key_D
  shortcutModifiers: Qt.ControlModifier | Qt.AltModifier

  function execute() {
    editor.insertHtml(editor.escapeHtml(new Date().toLocaleDateString()))
  }
}
```

- Import `NoteNote.Extensions 1.0` and make the root a `Tool`.
- `execute()` runs on a click, the shortcut or `editorTool <id>` — only when
  the note is writable and the tool is available and supported.
- `editor` is the only way into the note. Never reach past it to the text area
  or the workspace.
- A code block's text is literal: `insertHtml` and `replaceInline` are refused
  there, so a tool that writes text sets `available: !editor.inCode` and hides
  inside one, as the app's own formatting tools do.

| Property | Meaning |
|---|---|
| `toolId`, `label` | required; `label` is the tooltip and menu text |
| `icon` | a short glyph for the button |
| `toolbarLabelVisible` | show `label` beside the icon on the toolbar; default true |
| `capability` | what the note's provider must support; defaults to `toolId` (below) |
| `available` | a binding saying when the tool applies, such as `!editor.inTable`; hides and disables it otherwise |
| `checked` | a binding for a pressed look, for formatting toggles |
| `shortcutKey`, `shortcutModifiers` | the default shortcut, as Qt key and modifiers. The app's own keys, undo, redo, cut, copy, select-all and Ctrl+Shift+P always win; a conflict costs the tool its binding, not the tool. The user can override it with `{"command": "tool/insertStamp", "keys": [...]}` in Settings `keybindings` |
| `options` | a fixed list of `Tool` choices this tool owns, shown as its dropdown, each with its own unique `toolId`. Bind each option's `editor` and `available` to the owner's |
| `isMenu` | true for a named, empty menu whose members the user's toolbar layout supplies |

### Capability

A provider that lists its `tools` (OneNote and Notion do) offers only the
capabilities it lists; Local notes offer everything. A tool whose capability
is its own ID appears only where nothing is listed. When the tool writes an
existing construct, name that construct instead — `capability: "table"` for a
tool that inserts a table, `"bold"` for bold text — so it appears wherever that
construct can be saved.

### The editor

The most useful calls; everything is on `editor`.

| Call | Does |
|---|---|
| `writable`, `inTable`, `inList`, `inCode` | state for `available` bindings; `inCode` is the caret, or the whole selection, inside one code block |
| `supports(capability)` | whether the note's provider can store it |
| `selection()` | `{ from, to, text, html }` of the current selection |
| `insertHtml(html)` | replaces the selection with HTML, one undo step; refused on a code line |
| `escapeHtml(text)` | makes text safe inside `insertHtml` |
| `insertSnippet(markdown)` | inserts Markdown after the current block |
| `insertTable(markdown)` | inserts a Markdown table, inside the current cell when there is one |
| `replaceInline(html, keepSelection)` | reformats the selection in place, one undo step; refused on a code line |
| `capture()`, `current(context)` | remember the note and selection, and check later that they still hold |
| `focus()` | return focus to the note |
| `report(message)` | a short message in the status bar |

Insert only what the app's Markdown already has: text, emphasis, colors,
links, headings, lists, quotes, code, tables, rules. Anything else would not
survive saving.

### A panel

A tool that needs input sets `panel` to a component, `panelPopup: true` to show
it under its button, and calls `openPanel()` from `execute()`:

```qml
import QtQuick
import QtQuick.Controls
import NoteNote.Extensions 1.0

Tool {
  id: tool
  toolId: "insertSigned"
  label: "Insert signature"
  icon: "+"
  available: !editor.inCode
  panelPopup: true
  property string name: ""

  function execute() {
    name = ""
    openPanel()
  }

  panel: Component {
    Column {
      padding: 12
      spacing: 8

      function focusInput() {
        field.forceActiveFocus()
      }

      TextField {
        id: field
        placeholderText: "Name"
        onTextEdited: tool.name = text
        onAccepted: tool.submitPanel(function() {
          tool.editor.insertHtml(tool.editor.escapeHtml("— " + tool.name))
        })
        Keys.onEscapePressed: tool.cancelPanel()
      }
    }
  }
}
```

- `openPanel()` captures the note and selection; `submitPanel(apply)` closes
  the panel and runs `apply` only if they still hold, returning false
  otherwise; `cancelPanel()` closes it without editing. Both return focus to
  the note.
- `focusInput()` on the panel's root, if present, is called once it is shown.
- The panel closes by itself when the note changes or the tool stops applying.

## Placing it

A tool no layout names appears in a final toolbar group. The user moves it
with `editor.toolbar` in Settings — for example into the Insert menu:

```json
"editor": {
  "toolbar": [
    ["bold", "italic"],
    [{"dropdown": "insert", "items": ["insertStamp", "table", "link"]}]
  ]
}
```

A package cannot place its own tool; tell the user how. A layout keeps an ID
whose package is removed, and the tool returns to its place when the package
does.

## Trying it

Enable the package in `config.json` and restart. The tool shows in the
toolbar's last group, its shortcut in the tooltip and on the Key bindings
page. If it does not appear, look in the log for `Editing tool skipped:` —
a QML error, a `toolId` that differs from the manifest, or a clashing ID.
