# Editing tools

Each editing tool lives in one QML file: the application's own in `ui/tools/`,
the others in plugin packages ([tools in a package](#tools-in-a-package)). The
editor discovers both when it starts. Adding a tool does not require changing
`Workspace.qml`, `NoteEditor.qml`, the toolbar model, or the shortcut table.
Restart the app after adding or editing a file.

`ui/editing/Tool.qml` defines the contract. `ToolRegistry.qml` creates a
separate set of tool instances for each editor, checks their
metadata, and dispatches actions. `ToolBar.qml` renders buttons, menus and
tool-owned panels. `EditorApi.qml` provides shared document operations; the
editor retains its document, keyboard behavior, conversion and undo machinery.

## Arrange the toolbar

Open **Settings** and edit `editor.toolbar` in the JSON. Each inner array is
a group; array order controls button order, with dividers between groups.
The tools stay on one row and scroll horizontally when space is tight;
use the mouse wheel, trackpad or drag the strip to reach more tools.
A top-level **Insert** dropdown stays fixed on the right. Save
to apply the layout immediately. Existing configurations gain these defaults
in the Settings page; the file is updated when you save it.
Saved layouts that match an earlier default adopt the latest arrangement;
custom layouts keep their chosen placement.

The default layout puts table and link insertion under **Insert** and shows row and
column actions in their own toolbar group while the caret is inside a table.
Text color, highlight and inline code stay on the toolbar. Insert also contains
the separator and a regional diacritics picker, with the calendar package's tools
under **Insert → Insert month**:

```json
"editor": {
  "toolbar": [
    ["heading"],
    ["bold", "italic", "underline", "strikeout"],
    ["textColor", "highlight", "code"],
    ["ul", "ol", "todo", "outdent", "indent"],
    ["quote", "codeblock"],
    ["addRow", "delRow", "addCol", "delCol"],
    [{ "dropdown": "insert", "items": [
      { "dropdown": "insertMonth", "items": ["currentMonth", "nextMonth", "customMonth"] },
      "rule", "link", "table", "diacritics"
    ] }]
  ]
}
```

To move tools into Insert, remove their direct entries and list them in its
`items` array, in the order you want. For example, this layout puts Italic and
Bold in one group, followed by an Insert dropdown containing Table and Link:

```json
"editor": {
  "toolbar": [
    ["italic", "bold"],
    [{ "dropdown": "insert", "items": ["table", "link"] }]
  ]
}
```

All installed tools omitted from the layout appear in a final group, sorted
by tool ID. A tool already listed in a dropdown is not appended. Unknown IDs
are preserved for tools installed later; they produce no empty buttons. If a
dropdown's QML file is removed, its installed members return to the final
group. An empty toolbar array appends all tools. Omitting `editor.toolbar`
restores the default arrangement.

Dropdown `items` can also contain dropdown objects, using the same structure
at each level. Each submenu displays its tool's label and a right arrow;
hovering, clicking or pressing Right opens its children. Left returns to the
parent, and selecting an action dismisses the menu tree. Use another tool
with `isMenu: true` to define an additional named group.

An empty top-level dropdown is visible but disabled. Provider capabilities and
caret context still determine which actions are available, including inside
submenus. Submenus with no available descendants are hidden. Rearranging an
action does not change its shortcut or behavior. Duplicate IDs (including
across menu levels) and malformed entries are rejected on Save.
If a hand-edited file contains an invalid toolbar, startup uses the default
toolbar while preserving provider settings and leaving the file untouched.
Dropdown objects name a configurable menu tool; strings name executable
tools or tools with their own fixed choices at any level. Incorrectly placed
installed tools fall back to the final group so they stay accessible.

No tool file contains a toolbar order, group or parent menu. A new insertion action
can be implemented as one tool file and then placed inside Insert through
settings. The Insert tool only provides the dropdown; each item generates
its own content.

## Where tools are offered

A tool is offered only where it can act on the text at the caret. Elsewhere
its button and menu row hide, and its shortcut and `editorTool <id>` do
nothing. The caret's context is read again as an action runs, so a shortcut
pressed straight after the caret moves is judged on where the caret is now.

| Caret in | Hidden | Still offered |
| --- | --- | --- |
| A code block | Heading, bold, italic, underline, strikethrough, text color, highlight, inline code, link, lists, indent, outdent, quote | Code block, which takes the block off; horizontal rule, table and calendar tools, which land after the block |
| A table cell | Heading, indent, outdent, quote, code block | Inline formatting, lists, link, row and column actions; table and calendar tools, which insert inside the cell; horizontal rule, which lands after the table |
| A list item | Heading | Everything else |
| Anywhere else | Row and column actions | Everything else |

A code block shows its text as it is: Markdown typed there stays literal, so
there is nothing for a style to apply. A selection reaching from the prose
around a code block into it keeps the tools, and inline formatting refuses it
with "Select text outside the code block" in the status bar.

## Lists

Default shortcuts match OneNote for Windows: **Ctrl+1** for checkboxes,
**Ctrl+.** for bullets, and **Ctrl+/** for numbered lists. They invoke the
same actions as the toolbar buttons. The Key bindings page lists them, as
`ctrl+1`, `ctrl+period` and `ctrl+slash`; to change one, name `tool/todo`,
`tool/ul` or `tool/ol` under `keybindings` in Settings
([commands](commands.md#registering-shortcuts)).

Checkbox, bullet and numbered list actions format the paragraph at the caret or
the selected paragraphs, including empty paragraphs and table cells. A selection
ending at the start of another paragraph leaves that paragraph untouched. Mixed
selections adopt the requested style; clicking again removes the markers. Existing
checked states survive when applying checkboxes to a mixed selection.

The native helper edits list membership directly, preserves the selection and
groups each action into one undo step. Enter continues a list; Enter on an empty
item leaves it in the same cell or paragraph. Backspace at the start of an item
removes its marker and list indentation together, preserving its text and table
cell. Lists inside tables are stored as
semantic HTML in Markdown so their markers and check states survive saving.
Shell installations without the optional helper retain the Markdown-based list
actions outside tables.

## Heading

`Heading.qml` provides one dropdown with **Heading 1**, **Heading 2**,
**Heading 3**, and **Normal**, with relative size and weight previews at
the menu's text scale. Use
`"heading"` in toolbar settings to move the dropdown as one tool, including
inside another menu. Older layouts naming `h1`, `h2`, `h3`, or `p` display
one Heading dropdown at the first of those positions.

The choices retain their `h1`, `h2`, `h3`, and `p` action IDs for IPC and
provider capabilities. Only supported choices appear; the dropdown hides
when none are supported or the caret is inside a list, a table or a code block.

## Text color

Text color opens a six-column palette of twelve compact circular swatches based on
OneNote's phone palette screenshot, omitting Dark brown. Reset color removes only the foreground
format. With a selection the action colors that text; with a caret it sets
the color for subsequent typing until the caret moves. Choosing or resetting
a selection is one undo step, and other inline formatting is preserved.

Colors are saved as `<span style="color:#0070c0;">Mushrooms</span>` in Markdown.
The shared parser accepts these spans, including nested Markdown formatting;
hex, basic CSS names such as `red`, and integer RGB values normalize to hex.
Local notes and OneNote preserve these colors through loading and saving,
including checklists, headings, links and tables. Theme ink for links, quotes
and highlights is drawn separately, so Reset color restores the appropriate
appearance without writing theme colors into the note.

The action requires the native text helper and the `textColor` provider
capability (or unrestricted tools). Code blocks and providers with restricted
formatting, such as Notion, do not offer it. Without the optional native helper,
stored colors still render and save; automatic link, quote and highlight ink
uses the document's ordinary foreground. Build with `sh cpp/build.sh`.

## Diacritics

**Insert → Diacritics** offers lowercase and uppercase letters for the country
identified by the system timezone. Romanian includes **ă â î ș ț** and **Ă Â Î Ș Ț**, using
the modern comma-below forms of ș and ț. Click a letter, or move with the arrow
keys and press Enter or Space, to insert it at the caret. A selection is replaced.
Insertion preserves text formatting, works in lists, table cells and code blocks,
and is one undo step with the native helper. Escape or clicking outside cancels;
a changed note, document or selection rejects the pending choice.

Detection reads the named system timezone locally (`TZ` when explicitly set,
otherwise `/etc/localtime`, with `/etc/timezone` for systems that copy the timezone
file). The installed IANA timezone database maps it to a country. For example,
`Europe/Bucharest` selects Romanian even with an English interface, and
`Europe/Zurich` offers Swiss German letters without ß. The catalog covers common
Latin alphabets, including Romanian, French, German, Spanish, Portuguese, Polish,
Hungarian, Turkish and the Nordic languages. Unsupported regions, unnamed timezones
and UTC hide the tool. Timezone changes take effect after restarting the app.

The tool inserts ordinary Unicode text, so it is available for every editable
provider. Its ID is `diacritics`. Existing default toolbar layouts upgrade
automatically; add `"diacritics"` to Insert's `items` in a customized layout.

## Calendar tools

The built-in `org.note-note.calendar` package, in `plugins/org.note-note.calendar/`,
supplies the calendar tools. `InsertMonth.qml` supplies the `insertMonth` submenu. `InsertCurrentMonth.qml`
supplies `currentMonth`, its first default item. It inserts a month-and-year
label and a seven-column calendar table,
with one row per week and empty cells outside the month. The month comes
from the local clock when the action runs; the inserted table remains ordinary
editable Markdown. The OS locale controls weekday order and localized month
and weekday names through [Qt's locale API](https://doc.qt.io/qt-6/qml-qtqml-locale.html#firstDayOfWeek-prop).

`InsertNextMonth.qml` supplies `nextMonth`, immediately after `currentMonth`.
It inserts the next calendar month using the local date when the action runs,
including January of the following year when run in December. It starts on
day one so dates at the end of a month cannot skip a shorter month.

`InsertCustomMonth.qml` supplies `customMonth`, the last default item in Insert month.
It opens a popup with a localized month dropdown and a year field (1–9999),
initially set to the current month and year. Insert or Enter in the year field
confirms; Cancel, Escape or clicking outside dismisses it without editing.
All three tools use the package's `Calendar.js`, including Gregorian leap-year rules
and years 1–99.

These tools use the existing `table` capability, so they are available automatically
for providers that support tables. All calendar actions and Insert a table can
insert inside the current table cell. Insertion uses the shared document
transaction and can be undone in one step.

Nested tables retain cell paragraphs and inner tables as semantic HTML in the
Markdown file; ordinary tables keep their pipe syntax. Local notes and OneNote
preserve this structure when saved and reloaded. The native text helper makes
row/column actions and double Enter operate on the innermost table at the caret.

Saved custom layouts keep their arrangement. To group the month tools in an
existing Insert dropdown, replace their entries with
`{ "dropdown": "insertMonth", "items": ["currentMonth", "nextMonth", "customMonth"] }`,
retaining the other entries and removing any direct entries for these tools.
As with all tools, omitting a tool from a custom layout puts it in the final
toolbar group. `"plugins": {"org.note-note.calendar": {"enabled": false}}` in
Settings removes the four tools on the next start; layouts keep naming them,
without empty buttons, for when the package is enabled again.

## Add a tool

An application tool goes in `ui/tools/`. For example, save this as
`ui/tools/InsertGreeting.qml`:

```qml
import QtQuick
import "../editing"

Tool {
  toolId: "greeting"
  label: "Insert greeting"
  icon: "+"
  available: !editor.inCode
  shortcutKey: Qt.Key_G
  shortcutModifiers: Qt.ControlModifier | Qt.ShiftModifier

  function execute() {
    editor.insertHtml("Hello")
  }
}
```

Its button, tooltip, shortcut and keyboard-help entry come from this file.
`available: !editor.inCode` hides it inside code blocks, whose text is
literal; `insertHtml` is refused there.
Its button initially appears in the final group. To put it in Insert, add
`"greeting"` to the dropdown's `items` array in settings.
The example uses HTML already supported by the document converters. A tool
that introduces new document syntax also needs converter support and, where
applicable, provider support so its content survives saving and reloading.

## Tools in a package

A [plugin package](plugins.md) contributes tools under `tools` in its
manifest. Each entry names the tool's action ID and its QML file:

```json
"contributes": {
  "tools": [{"id": "insertStamp", "path": "InsertStamp.qml"}]
}
```

The file's root is the same `Tool`, imported from the application's public
module instead of its source tree:

```qml
import NoteNote.Extensions 1.0

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

The contract, the `editor` it is given and everything below apply unchanged:
the registry places a package's tool in the toolbar, its menus, the shortcut
table and help exactly as it does the application's. `toolId` must be the
manifest's `id`; `options` keep their own IDs. IDs share one namespace, so pick
distinctive ones: a tool the application ships, in `ui/tools/` or a built-in
package, keeps its ID against a user package's, and any other shared ID
rejects every claimant, with the reason in the log. A tool is executable code,
so a user package holding one starts disabled until it is enabled in Settings.

`capability` defaults to the tool's ID. A provider that lists its `tools`
offers only what it lists, so a tool that writes an existing construct names
that construct: the calendar tools write tables and require `table`. The
[example package](../examples/plugins/greeting) contributes `insertHello`
beside its command.

Built-in packages in `plugins/` ship with the application and, like its
providers, may import its source tree by relative path: the calendar tools use
`ToolForm`, `ChromeTextField` and `ChromeDropdown` from `ui/`. `NoteNote.Extensions`
provides `Tool` itself; a package outside the application builds its panel from
Qt Quick's own controls.

## Tool properties

| Property | Meaning |
| --- | --- |
| `toolId` | Unique action ID. Existing IDs such as `bold`, `h1` and `addRow` remain stable for IPC. |
| `label`, `icon` | Button tooltip/menu text and icon glyph. |
| `toolbarLabelVisible` | Show the menu label on the toolbar button; defaults to true. Hiding it keeps the icon, dropdown arrow, menu labels and tooltip. |
| `capability` | Provider capability required; defaults to `toolId`. All four table alteration tools require `table`. Use an empty string for literal text requiring no formatting capability. |
| `checked` | Reactive pressed state for formatting buttons; false by default. |
| `available` | Reactive context condition, such as `editor.inTable`. Controls both presentation and execution; execution reads the caret's context again first. |
| `shortcutKey`, `shortcutModifiers` | Optional default key and modifiers. The central registry resolves conflicts and user overrides; `shortcutLabel` (read-only), tooltips, and help show its effective binding. |
| `isMenu` | This entry opens a menu; automatically true when `options` are provided. |
| `options` | Fixed executable `Tool` choices owned by this file, as in `Heading.qml`. They retain individual action IDs and capabilities but move together in the toolbar. Bind their `editor` and availability to the owning tool. |
| `previewScale`, `previewBold` | Optional menu-label styling relative to the chrome text size, used by headings. |
| `panelPopup` | Render the tool panel as a dropdown anchored to its toolbar button. |
| `panel`, `panelOpen` | Optional QML component and whether it is open. Shown in a popup when `panelPopup` is true, otherwise below the toolbar. |
| `panelContext` | Note, document revision and selection captured by `openPanel()`. Cleared when the panel closes. |

Implement `execute()` with the tool's specific behavior. Simple tools call a
shared operation; complex tools can keep additional functions, state and a
panel in the same file. `InsertLink.qml` and `InsertCustomMonth.qml` demonstrate popup forms, and `Insert.qml`
defines the dropdown container. Any executable tool can become a dropdown item.

Input tools call `openPanel()` from `execute()` after setting their initial
values. This captures the insertion context and opens their `panel` component.
Popup panels can provide `focusInput()` to focus and select their initial input
once the popup is open.
`ToolForm.qml` supplies the shared popover: the tool's icon and label as a
header, the spacing between fields, and a footer with the key hint and the one
Insert button. There is no Cancel button; Escape or a click outside cancels, as
for every popup. Set the form's `message` to say what blocks submitting, such
as an invalid value; it replaces the key hint until cleared. Form fields use
`ChromeTextField` and `ChromeDropdown`, which share the search field's theme
colors, borders, corner radius and height through `ChromeControlStyle`. Fields
carry no labels above them: a placeholder, and for a text field an `iconText`
glyph at its leading edge, say what each one is for.
On confirmation, validate the form and call `submitPanel(function() { ... })`
with the edit. It rechecks availability, provider support and the captured
context, closes the panel, then applies the edit and restores editor focus.
It returns false for a stale or closed panel. `cancelPanel()` closes without
editing and restores focus. Opening another action closes the previous panel.
All form fields, validation and content generation stay in the tool file;
adding another input tool requires no toolbar or main-app changes.

The tool registry rejects duplicate IDs and invalid tool
definitions, exposing diagnostics through `editor.tools.errors`
and the application log. Shortcut conflicts disable the binding while preserving
the tool; the Key bindings page reports these conflicts. Existing app shortcuts have priority over tool
definitions; undo, redo, cut, copy and select-all are also reserved. All
built-in formatting shortcuts use the registry, so a
provider restriction also prevents Qt's native formatting shortcut from
executing. Navigation and clipboard shortcuts remain editor/app behavior.
User overrides use `tool/<toolId>` in [Settings keybindings](commands.md#changing-bindings).

## Shared editor API

Tools receive `editor`; they must not reach through its implementation
references to the host or TextEdit. Shared primitives belong in `EditorApi.qml`;
an action's content, rules and UI belong in its tool file.

| Operation/state | Use |
| --- | --- |
| `writable`, `inTable`, `inList`, `inCode`, `supports(capability)` | Document and provider availability. `inCode` is the caret, or the whole selection, inside one code block. |
| `selection()` | Selected `from`, `to`, `text` and inline `html`. Positions use Qt document offsets. |
| `canColorText`, `setTextColor(color)` | Apply a hex foreground or clear it with an empty string; also supports pending typing. |
| `toggleFont(kind)` | Toggle a supported boolean font attribute, including pending formatting while typing. |
| `acceptsInline()` | Whether the selection takes inline formatting or HTML: false on a code line, and for a selection crossing a code block's edge, which also reports why. |
| `replaceInline(html, keepSelection)` | Replace selected formatting without breaking the containing list/paragraph; one undo step. Refused on a code line. |
| `insertHtml(html)`, `escapeHtml(text)` | Replace the selection with HTML in one undo step, and escape literal text/attributes. `insertHtml` is refused on a code line. |
| `insertText(text)` | Replace the selection with literal text, preserving the caret's formatting and pending font/color choices. Also works on code lines. |
| `insertSnippet(markdown)` | Insert after the current block, or on an empty paragraph, with a landing paragraph when needed. |
| `insertTable(markdown)` | Insert table content at the caret inside a cell, or as a normal snippet outside tables. |
| `transformBlocks(transform, options)` | Transform selected Markdown blocks. The callback receives `{ indent, prefix, content, isList }` and returns a line. `options.list` manages paragraph separators when toggling lists; `unchangedMessage` supplies optional feedback. |
| `toggleListStyle(style)` | Toggle `todo`, `ul` or `ol` on actual document blocks, including table cells, preserving selections and undo. |
| `tableContext()`, `changeTable(operation, index, count)` | Read the innermost table's row/column and dimensions, and insert/remove rows or columns as one undo transaction. Operations are `insertRows`, `removeRows`, `insertColumns`, `removeColumns`. |
| `transformTable(transform)` | Plain-table fallback when the native helper is absent. Callback arguments are `(rows, row, column)`; row 1 is the Markdown separator row. Return `false` to leave the document unchanged. |
| `withMarkdown(callback, asText)` | Read Markdown lines and the line/block map, rejecting stale or failed conversions. `asText` optionally reads a code block as prose. |
| `replaceDocument(markdown, caret, then)` | Render and replace the document in one undo step; optional `then` runs inside that transaction. |
| `cursorPosition()`, `blockAt(position)`, `blockInfoAt(position)`, `caretLine(map)`, `lineAt(map, position)`, `blockEndLine(lines, line)`, `lastBlockThrough(map, line)`, `selectBlock(block)` | Position and block mapping, used by code-block insertion. |
| `capture()`, `current(context)` | Capture and validate the note, document revision and selection around delayed UI work. |
| `selectionInCode()`, `typeInCode(from, to, text)` | Insert literal text using the code block's formatting. |
| `focus()`, `report(message)` | Return focus to the document or report feedback in the status bar. |

The API also exposes the editor's fonts, colors and inline-code chip color.
`withoutChip(html)` lets inline transforms distinguish the code background
from highlighting. `nbsp4` is the dialect's paragraph-indent unit.

Buttons, shortcuts and `editorTool <id>` all use the same capability and
document checks. Panels close when the note changes, becomes unavailable, or
provider capabilities or the layout change. `submitPanel()` validates delayed
submissions against their captured context. Markdown conversion and document
replacement retain the existing stale-note checks and atomic undo behavior.

## Verification

Run `python3 tests/transition_selftest.py --tools` for focused tool checks,
`python3 tests/transition_selftest.py` for all real editor cases, and
`python3 tests/transition_selftest.py --host` for host integration. The runner
copies the tool directory into a temporary workspace and adds an extra QML
tool to verify discovery, toolbar clicks, shortcuts and help without modifying
the application. It also checks formatting round trips, table actions,
provider restrictions, panel context and undo/redo. Layout checks cover group
and dropdown order, omitted tools, moving actions without losing shortcuts,
settings validation, backward-compatible defaults and failed settings saves.
Submenu checks cover nested settings, pointer and keyboard navigation, outside
clicks, empty groups, and dismissal when permissions or the layout change.
Availability checks cover code blocks and table cells: hidden buttons and
menu rows, refused commands and shortcuts straight after the caret moves,
and a selection crossing a code block's edge.
Calendar checks load the calendar package through the plugin catalog, as the
workspace does, and cover Sunday, Monday and Saturday week starts, localized
labels, four-to-six-week months, leap-year rules, year boundaries, table
capabilities, menu insertion, saving/reloading and undo/redo. Package checks
cover a manifest ID that differs from the `toolId`, and user packages claiming
IDs the application or a built-in package already uses. `tests/extensions_selftest.py`
loads the example package's tool through `NoteNote.Extensions` in both hosts,
then runs it from its shortcut and undoes it.
Nested-table checks cover empty and populated cells, three table levels,
inner and outer row/column changes, double Enter, caret placement and undo.

Lint changes with:

```bash
qmllint -I /usr/share/omarchy/shell ui/editing/*.qml ui/tools/*.qml plugins/org.note-note.calendar/*.qml ui/NoteEditor.qml Workspace.qml hosts/omarchy/Notes.qml
```

`Ctrl+Shift+P` is reserved for the global command palette and cannot be claimed
by a tool. Global commands have their own lazy execution contract; see
[commands](commands.md). Tool actions and their restricted editor API retain
their existing owners.
