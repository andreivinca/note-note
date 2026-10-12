# UI design map — note list, dialogs, forms, design system

Repository `/home/andrei/Projects/note-note`, HEAD `e2cdc4e` (master). Every citation is `file:line` at HEAD.
Paths are relative to the repository root unless stated otherwise. One citation points outside the repo
(the Omarchy shell's own `Style.qml`); it is marked as such.

## Summary

The sidebar (`ui/NoteList.qml`) renders a plain JS array of rows built by `services/notes/sidebar.js`. `row()`
copies only a whitelist of provider fields (kind, path, title, hasTitle, preview, icon, reorder, level,
expanded, count, menu, modified). There is no per-note content-type field anywhere in that path. Note rows
are drawn by the shared `ui/NoteSummary.qml`, which `ui/SearchResults.qml` also uses: a bold title, then
the date and a one-line, whitespace-collapsed preview. Note rows have no icon (the row's `icon` is drawn
only for action rows) and no unsaved marker. Unsaved state appears only in the view bar for the open note,
and as a typed title projected through `session.unsavedTitles`.

The workspace compares rows by `JSON.stringify` before assigning them. A recorded decision says a row
carries only what the list shows, so a type field must be something the list actually draws.

Form building blocks:
- `design/controls/PromptDialog.qml`: one modal text field (Enter submits a non-empty value, Escape cancels).
- `design/controls/ConfirmDialog.qml`: two buttons, keyboard driven through the workspace.
- `ui/editing/ToolForm.qml`: a popover card with header, fields, a key hint and one "Insert" button. It is
  hard-wired to an editing `Tool` and its editor.
- `design/controls/TextField.qml` and `ui/ChromeTextField.qml`: single-line fields.
- `design/controls/Button.qml` and `ui/ChromeButton.qml`: buttons. Keyboard focus is opt-in.
- `ui/SidebarAction.qml`: a footer row that turns into a single-line field in place.

No multi-line input exists in the design system. The only multi-line text controls are a read-only
`QQC.TextArea` in `MergeConflict` and the plain `TextEdit` pages.

Creating notes is provider-driven. Footer actions, row menus and "New note…" rows all come from the
provider. The host adds no creation buttons, and the shared `shortcut` vocabulary is only
`newNote`/`newNotebook`. Workspace actions and `host.newNote(providerId, target)` take no type parameter.
Row menus open only on right-click, so they have no keyboard path. The command palette offers New Note
through a parameterless `workspaceAction` and a generic `ui.pick` picker.

Colours come only from `design/tokens.js` (63 tokens), read through the `Color` singleton. Hover, pressed
and selected fills come from `Style.*FillFor`. "Accent as ink" is `Qt.tint(foreground, alpha(accent, 0.6))`,
and `Qt.lighter`/`Qt.darker` are explicitly forbidden. The editor already draws a checkbox (accent fill
with the tick cut out in the background colour, a 0.4-alpha border when unchecked). Circles exist in the
text-colour swatches and the audio player.

Spacing and font keys differ between hosts: the Omarchy shell exposes more keys than the standalone
fallback, so shared code may only use the keys both define. Glyphs are Nerd Font (Material Design range)
literals drawn with `Style.fontFamily`. The interface and note font is a bundled Nimbus Sans without
glyphs, and standalone registers a Symbols Nerd Font as a fallback.

Accessibility is thin: only `Accessible.name` is used, with no roles, no `activeFocusOnTab` and no
`KeyNavigation`. Keyboard work is explicit `Keys` handlers plus `forceActiveFocus`. Shortcuts are routed
by `Workspace.handleShortcut`, where modal states claim keys first and Escape means "back" in the notes
context. The business requirements demand mouse-free note work and no modal dialogs between the user and
their text.

---

## Q1 — How a note row renders, and what a per-type icon and timeline preview would take

| # | Fact | Where |
|---|---|---|
| 1 | NoteList documents its row kinds: `note`, `new` ("+ New note…"), `action` (path = action id, `icon` glyph), `tree` (expandable, `count`, indented by `level`); rows may have `reorder` and a right-click `menu` (`rename` items edit in place). | ui/NoteList.qml:7-21 |
| 2 | `row()` copies a fixed whitelist from a provider row: `provider, notebook, kind (default "note"), path, title, hasTitle (from provider.hasTitle), preview, icon, reorder, level, expanded, count, menu, modified`. There is no content-type field. | services/notes/sidebar.js:24-31 |
| 3 | Rows are rebuilt by `Sidebar.build` and assigned only when `JSON.stringify` differs; every assignment rebuilds every delegate. | Workspace.qml:1332, 1349-1362 |
| 4 | Recorded decision: *"a row carries only what the list shows or drags on"*. A `version` field once made equal lists compare unequal and rebuilt the list on every autosave. | docs/decisions.md:444-448 (also 438-442; docs/technical-requirements.md:167-168) |
| 5 | A note row is a `NoteSummary` fed `title: root.titleFor(row)`, `hasTitle`, `preview`, `modified`, `foreground`, `fontFamily`, `fontSize`. No icon or unsaved flag is passed. | ui/NoteList.qml:447-461 |
| 6 | Non-note rows draw a glyph plus a label: `"+"` for `new`, `modelData.icon \|\| "󰊻"` for `action`, `󰅀`/`󰅂` for `tree`, coloured `root.accentInk`, `font.family: Style.fontFamily`, size `Style.font.iconSmall`. Note rows never draw `icon`, although `row()` carries it. | ui/NoteList.qml:463-477 |
| 7 | NoteSummary is a Column holding (a) the title Text (PlainText, elided, `font.bold: root.hasTitle`, size `fontSize`) and (b) a Row of date + preview at `fontSize - 1`. The preview is whitespace-collapsed (`replace(/\s+/g, " ")`) and elided. The date shows `HH:mm` for today and `d MMM` otherwise; date colour is `Color.token("text.secondary")`, preview colour is `Style.secondaryText(foreground, 0.48)`. | ui/NoteSummary.qml:6-57 |
| 8 | The search panel reuses NoteSummary with the same geometry ("they must measure exactly as its rows do"). | ui/SearchResults.qml:33-38, 104-117 |
| 9 | The shown title is `Workspace.displayTitle(row)`: the unsaved typed title if any, else the provider title, else the first five words of `preview` with `[x]`/`[ ]` rewritten to ☑/☐, else "Untitled". It is passed as `titleFor`. | Workspace.qml:1302-1324, 2721 |
| 10 | `session.unsavedTitles` holds the drafts' titles plus the current editor title while dirty. It is the only unsaved projection into the list. | services/notes/NoteSession.qml:48-62 |
| 11 | The list has no per-row unsaved marker. Unsaved state shows only in the view bar for the open note: `●` "Unsaved", `󰄬` "Saved", "Read-only" or "Loading…". | ui/ViewBar.qml:135-146 |
| 12 | Geometry: `rowGap = Style.spacing.xs`. Note row height is `max(space(52), noteFontSize*2 + space(20)) + rowGap`; other rows are `controlHeight + rowGap`. Pill `rowRadius = min(cornerRadius, space(6))`, `textInset = spacing.lg`, `pagePadding = spacing.sm`, indent per level `= Style.font.icon + space(2) + md - sm`. | ui/NoteList.qml:116-126, 394-402 |
| 13 | Colours: the current row uses `selectionFill = Qt.tint(page, alpha(accent, 0.22))`, a hovered row uses `alpha(foreground, 0.05)`. `new` and `action` rows are dimmed to `Style.secondaryOpacity(0.65)` until hovered. | ui/NoteList.qml:128-129, 436-443 |
| 14 | `accentInk = Qt.tint(foreground, Util.alpha(accent, 0.6))`. The comment says never to use `Qt.lighter`/`Qt.darker`. | ui/NoteList.qml:73-79 |
| 15 | Wiring: NoteList gets `foreground: Color.token("sidebar.foreground")`, `accent`, `fontFamily: root.interfaceFont` (Nimbus Sans), `noteFontSize: root.chromeFontSize` (= `Style.font.subtitle`). | Workspace.qml:2693-2721, 94-103 |
| 16 | `matchesQuery` searches `title` and `preview`, so any text placed in `preview` becomes searchable. | services/notes/sidebar.js:19-22 |
| 17 | `modified` drives the preview date and the editor caption; `version` is change detection only. | docs/providers.md:222-232 |
| 18 | Header label: "N note(s)", from the section count. | ui/NoteList.qml:299-322 |
| 19 | NoteSkeleton, the generic loading placeholder (date bar, title bar, two body lines, pulsing opacity 0.55↔1 over 900 ms), is used only by the editor over the sheet. | ui/NoteSkeleton.qml:4-75; ui/NoteEditor.qml:2401-2407 |
| 20 | `NoteList.background` is set by the workspace but never read inside NoteList. The page colour is `Color.token("sidebar.background")`. | ui/NoteList.qml:52, 128, 292; Workspace.qml:2716 |

**What a per-type icon would take:**
1. A type field in the `row()` whitelist.
2. A glyph slot in NoteSummary, which serves both the list and search.
3. A type → glyph mapping, owned by the host or supplied by the provider.

The indent math assumes that only non-note rows have an icon column.

**What a timeline preview such as "3 of 7 done · next: Pack" would take:** it fits on NoteSummary's
second line as `preview` text with no UI change. However, that text is then searchable, it feeds the
untitled-title fallback, and it lags until the provider re-lists after a save. Structured row data (for
example done, total, next) would instead need NoteSummary to format it.

## Q2 — Building blocks for an "Add new event" form

| # | Fact | Where |
|---|---|---|
| 21 | PromptDialog API: `opened, message, placeholderText, confirmText ("Create"), background, foreground, accent, scrim, fontFamily, cornerRadius`; signals `canceled()`, `submitted(string name)`. It has one TextField (`objectName "promptField"`). | design/controls/PromptDialog.qml:8-23, 70-77 |
| 22 | PromptDialog keys and focus: when it becomes visible it clears and focuses the field ("an item still hidden cannot take the keyboard"). Escape emits `canceled`. Enter calls `submit()`, which emits only a non-empty trimmed value. Clicking the scrim cancels. The Create button is disabled while the field is empty. The Cancel and Create buttons are not focusable (the Button default). | design/controls/PromptDialog.qml:24-37, 39-45, 78-99 |
| 23 | PromptDialog and ConfirmDialog size with raw pixels: width `min(parent.width - 32, 400)`, height `+ 40`, spacing `20` and `12`. These do not scale through `Style.space()`. | design/controls/PromptDialog.qml:46-60, 88-90; design/controls/ConfirmDialog.qml:54-68, 78-80 |
| 24 | The workspace hosts a single PromptDialog driven by `promptPending {message, placeholder, confirmText, run}`. `askName` builds `"<title> in “<place>”"`. Cancelling refocuses the editor; submitting runs `run(name)`. | Workspace.qml:254-256, 2082-2097, 3037-3055 |
| 25 | While `promptPending` is set, `handleShortcut` returns false so no shortcut runs underneath, and WorkspaceActions is `blocked`. | Workspace.qml:2142-2145, 2543-2548 |
| 26 | ConfirmDialog API: `opened, message, confirmText, colours, selectedIndex`; signals `canceled()`, `confirmed()`. `handleKey`: Escape cancels; Left/Right/Tab/Backtab toggle the selection; Enter activates the selected button (Cancel is preselected). The confirm button is `Color.urgent`. Keys arrive from `Workspace.handleShortcut`. | design/controls/ConfirmDialog.qml:4-46, 81-91; Workspace.qml:2136-2141 |
| 27 | ToolForm API: `required property Tool action`, `default property alias fields`, `property alias submitButton`, `message`, read-only `foreground` (`popup.foreground`) and `fontFamily` (from `action.editor.fontFamily`), `signal submitted()`, width `space(320)`, padding `md`. | ui/editing/ToolForm.qml:11-25 |
| 28 | ToolForm layout: a header with the action's icon (alpha 0.55) and label; a fields Column (spacing `md`); a footer with the hint `"Enter to insert · Esc to cancel"`, or `message` in `Color.urgent`. The confirm Button is `"Insert"`, `selected: true`, `focusable: true`, and uses `action.editor.accent`. | ui/editing/ToolForm.qml:27-88 |
| 29 | ToolForm is hosted in the toolbar's `QQC.Popup` with `focus: true` and `closePolicy: CloseOnEscape \| CloseOnPressOutside`. `onOpened` calls `panel.focusInput()`; `onClosed` calls `tool.cancelPanel()`. | ui/editing/ToolBar.qml:253-298 |
| 30 | Tool panel lifecycle: `openPanel()` captures the editor context; `cancelPanel()` and `submitPanel(apply)` close the panel and refocus the editor. | ui/editing/Tool.qml:30-64 |
| 31 | Documented form conventions: no Cancel button; Escape or a click outside cancels; no labels above fields (a placeholder plus a leading `iconText` glyph instead); `message` replaces the hint; fields use ChromeTextField and ChromeDropdown. | docs/editing-tools.md:345-364 |
| 32 | InsertLink example: two ChromeTextFields with `iconText`, `placeholderText` and `Accessible.name`. Enter or Return in either field submits; the form's `Keys.onEscapePressed` cancels; `focusInput()` picks the field. | ui/tools/InsertLink.qml:42-86 |
| 33 | InsertCustomMonth example: validation through `submitButton.enabled` and `message: "Enter a year from 1 to 9999."`. | plugins/org.note-note.calendar/InsertCustomMonth.qml:45-106 |
| 34 | `design/controls/TextField` (QQC TextField): `foreground, accent, password, horizontalPadding, verticalPadding`; fill `alpha(fg, 0.04)`; 1 px border that turns `accent` on activeFocus (else `alpha(fg, 0.3)`); radius `Style.cornerRadius`. It has no Enter/Escape handling of its own. | design/controls/TextField.qml:7-31 |
| 35 | ChromeTextField: `focusBorderVisible` (defaults to activeFocus) and `iconText` (a leading glyph in `Style.fontFamily`, `iconSmall`, `secondaryText 0.55`). Colours come from ChromeControlStyle: `input.foreground`, `input.placeholder`, `input.background`, `input.border`, `border.focus`; radius `Style.controlRadius`; height `space(30)`. | ui/ChromeTextField.qml:6-44; ui/ChromeControlStyle.qml:7-16 |
| 36 | Button API: `iconText, tooltipText, selected, active, focusable` (default false, giving `Qt.NoFocus`), `bordered, foreground, backgroundColor, accent, hoverColor, pressedColor, selectedColor, selectedForeground, contentColor, fontFamily, fontSize, iconSize, radius, borderSpec`; signal `rightClicked()`. `Accessible.name: text \|\| tooltipText`; opacity 0.5 when disabled; tooltip delay 400; pointing-hand cursor; 120 ms ColorAnimation. | design/controls/Button.qml:6-117 |
| 37 | ChromeButton is a Button with `Style.controlRadius` and tint-on-surface fills. | ui/ChromeButton.qml:6-15 |
| 38 | There is no multi-line input in `design/controls/` (BorderSurface, Button, ConfirmDialog, Dropdown, PanelToolTip, PromptDialog, TextField). `QQC.TextArea` appears only read-only in MergeConflict, with a hard-coded `Qt.rgba(0,0,0,0.12)` background. | design/controls/; ui/MergeConflict.qml:90-104 |
| 39 | The settings and keys pages use a plain-text editor: a Flickable with `ListWheel` and `ensureVisible(cursorRectangle)`, around a `TextEdit` (PlainText, Wrap, `Keys.priority: BeforeItem` → `shortcutHandler`). | ui/TextPage.qml:175-225 |
| 40 | SidebarAction (in-place single-line input): `editable` comes from `inputPlaceholder`. `startEditing()` clears and focuses the field. Enter submits a non-empty trimmed value; Escape cancels; losing focus or hiding ends editing. Signals: `clicked()`, `submitted(name)`. | ui/SidebarAction.qml:5-41, 89-132 |
| 41 | The NoteList rename field has the same semantics and focuses on visible. | ui/NoteList.qml:493-529 |
| 42 | Dropdown (QQC ComboBox): `options [{value,label}], value, label, showLabel, foreground, accent, fontFamily, popupOpen`; `signal selected(value)`; `open()`/`close()`. ChromeDropdown styles it; its popup uses `CloseOnEscape \| CloseOnPressOutsideParent`. | design/controls/Dropdown.qml:8-36; ui/ChromeDropdown.qml:7-100 |
| 43 | Design note: a page, not a dialog, and "deliberately no form of switches" for settings. | ui/TextPage.qml:10-19 |

## Q3 — Offering a note-type choice at creation: existing conventions

| # | Fact | Where |
|---|---|---|
| 44 | Footer: one `SidebarAction` per provider footer action, stacked under a hairline, each `height: Style.space(32)`. A click emits `footerActionRequested(action, "")` and a submit emits it with the value. | ui/NoteList.qml:689-732 |
| 45 | Footer contract: `{ path, title, icon?, inputPlaceholder?, prompt?, shortcut? }`. *"It does not add creation buttons based on provider identity or capabilities."* Footer actions stay out of `rows` and remain available during search. | docs/providers.md:181-198 |
| 46 | `shortcut` names a shared action, *"currently `newNote` or `newNotebook`"*, binding Ctrl+N or Ctrl+Shift+N to that footer row. `newNote()` tries the footer row first. | docs/providers.md:200-204; Workspace.qml:1690-1703, 1887-1894 |
| 47 | A footer `prompt` asks for a name through PromptDialog (`runFooterAction`). | Workspace.qml:1666-1688 |
| 48 | Local provider footer: New Note (`󰐕`, shortcut newNote), New section (`󰉗`, prompt), New notebook (`󰉗`, inputPlaceholder). `action("newNote")` calls `host.newNote(id, target)`. | plugins/org.note-note.local/Provider.qml:98-112, 275-279 |
| 49 | `host.newNote(providerId, target)` calls `p.create(target, cb)`, then selects the note and focuses the title or body. Nothing in this path carries a type. | Workspace.qml:1873-1938 |
| 50 | Row menus are provider `menu` items `{ id, title, icon?, command?, rename?, prompt?, confirm? }`; the host adds no item. RowMenu is a `QQC.Menu`, and its choice is reported after it closes. | docs/providers.md:96-127; ui/RowMenu.qml:7-131 |
| 51 | Row menus are pointer-only: a right-click `TapHandler` is the only call site of `rowMenu.openFor`. | ui/NoteList.qml:611-617; ui/RowMenu.qml:25-28 |
| 52 | "+ New note…" rows (`kind "new"`) show only when the list has tree rows. A click calls `newRequested(path \|\| notebook)` → `Workspace.newNote(row.provider, target)`. The label and glyph (`"New note…"`, `"+"`) are hard-coded. | ui/NoteList.qml:414, 471-485, 576-578; Workspace.qml:2726-2734 |
| 53 | The palette's built-in commands are manifest entries with `workspaceAction` (newNote, newNotebook, openSettings, toggleList, deleteNote), and those are the only supported action ids. | plugins/org.note-note.workspace/plugin.json:8-60; docs/commands.md:49-62 |
| 54 | WorkspaceActions handlers take no parameters; `invoke(action)` takes an id only. The command context's `workspace.invoke(action)` likewise; provider instances are not in the command context. | services/commands/WorkspaceActions.qml:18-48, 91-98; services/commands/CommandApi.qml:43-59; docs/commands.md:45-47 |
| 55 | Generic picker `ui.pick(options, callbacks)`: items `{id, label, detail, keywords, enabled, reason, shortcut}`; keys Up/Down/PageUp/PageDown, Enter, Escape; Tab stays in the query. | docs/commands.md:79-97; ui/commands/CommandPalette.qml:116-138, 206-230 |
| 56 | Shortcut catalogue: `newNote` Ctrl+N and `newNotebook` Ctrl+Shift+N (`workspace: true`). An action may ship `keys: []` (openSettings). | services/shortcuts/defaults.js:21-24 |
| 57 | A codebase precedent against growing rows of buttons: *"A row of pills along the bar would have to grow with each new one, and each would spend the bar's width saying its own name; the menu spends none until it is asked."* The app menu is a Popup of `{id, icon, label}` rows. | ui/TitleBar.qml:112-116, 173-270 |
| 58 | The editor's `plain` is decided per provider: `!p.markdown`. | Workspace.qml:2837-2840 |

## Q4 — Tokens, palette, spacing, radii, fonts, glyphs, dark/light

| # | Fact | Where |
|---|---|---|
| 59 | `tokens.js` is *"Every colour the application has a name for, and the only list of them"*: 63 tokens, each with `recipe, inputs, systemRole, overlay, pair`. | design/tokens.js:3-79 |
| 60 | Recipe strengths: raised 0.07; muted (`text.secondary`) 0.65; disabled 0.4; border (`border.default`) 0.25; focus tint 0.35; selection accent 0.2; textSelection 0.35; input 0.08; inputBorder 0.18; placeholder 0.45; sidebar 0.05; link tint 0.65; quoteBorder accent 0.6; error `#d34747`. | design/resolve.js:21-55 |
| 61 | `Color` singleton: `token(name)`, `background`, `foreground`, `accent`, `urgent`, `menu.{background,text,border,scrim,selectedBackground,selectedText}`, `popups.text`; `tokens = theme ? theme.colors : baseline`. `token()` returns `tokens[name]` with no check. | design/Color.qml:9-53 |
| 62 | `Style` singleton: `cornerRadius` (shell value or 6), `controlRadius = space(8)`, `popupRadius = space(10)`, `fontFamily`, `font`, `spacing`, `hoverFill`, `selectionFill`, `space()`, `secondaryOpacity()`, `secondaryText()`, `hoverFillFor/pressedFillFor/selectedFillFor/hoverStateColor/selectedStateColor` (delegating to the shell), `chromeSurface()`. | design/Style.qml:5-83 |
| 63 | Standalone font keys: `family, menuFamily, baseSize 12, caption 10, bodySmall 11, body 12, subtitle 13, title 14, displayLarge 28, iconSmall 11, icon 14, iconLarge 18`. Spacing keys: `xxs 2, xs 3, sm 4, md 6, lg 8, xxxl 14, hairline 1, controlGap 8, controlHeight 28, controlPaddingX 10, panelPadding 18, popupRowHeight 28`. | design/Style.qml:20-47 |
| 64 | The Omarchy shell Style has extra keys the standalone objects lack: spacing `xl, xxl, huge, controlPaddingY, inputPaddingY, rowGap, rowPaddingX, labelGap, panelGap, popupPadding…` and font `heading, display, resolvedFamily`. Its `fontFamily` defaults to `"monospace"` (for example JetBrainsMono Nerd Font). | /usr/share/omarchy/shell/Commons/Style.qml:231-260, 269-275, 321-339 (outside repo) |
| 65 | The hosts install the design sources: Omarchy sets `Design.Style.source = Shell.Style` and `Design.Color.source = Shell.Color`; standalone sets `Design.Color.systemTheme`. | hosts/omarchy/Backend.qml:51-55; hosts/standalone/Backend.qml:30-33 |
| 66 | The workspace sets `Color.theme = themeService`. ThemeService publishes whole palettes and exposes `followsSystem`. `ControlPalette` maps Qt roles to tokens and is set on `content`. | Workspace.qml:2517-2527, 2625; services/themes/ThemeService.qml:22-56; design/ControlPalette.qml:4-28 |
| 67 | Helpers: `Util.alpha(color, opacity)` (clamped); `Border.flat/none/width`; `BorderSurface` (a Rectangle with a borderSpec). | design/Util.qml:4-8; design/Border.qml:4-15; design/controls/BorderSurface.qml:4-17 |
| 68 | Light/dark: secondary ink is boosted to at least 0.85 on light backgrounds only while following System; custom themes keep their opacities. No dark/light flag is exposed (only `resolve.js` `luminance`). | design/Style.qml:51-59; design/resolve.js:13-17, 76-79, 101-107; docs/themes.md:21-24 |
| 69 | Theme rules: *"the application never paints a colour of its own in place of a token"*; fonts, dimensions, icons, provider hues and authored content are outside the schema; hover, pressed and selected fills are made from the control's ink and are not tokens; the System file lists every token. | docs/themes.md:74-92 |
| 70 | Dividers: hairlines in `alpha(foreground, 0.1)` (list header and footer) and `0.09` (view bar). | ui/NoteList.qml:316-321, 701-706; ui/ViewBar.qml:71-76 |
| 71 | Editor checkbox precedent: `side = round(font * 0.9)`, `radius = max(3, side * 0.3)`. Checked: accent fill, border 0, two round-capped tick arms in the background colour. Unchecked: transparent, border `alpha(fg, 0.4)` (0.75 hovered), width `max(1.2, side/9)`; antialiased. | ui/NoteEditor.qml:2219-2291 |
| 72 | Circle precedents: text-colour swatches (`radius: width/2`, a 2 px accent ring on hover or focus); the audio play Button (circle, focusable, accent fill, glyphs in the background colour, but `Qt.lighter`/`Qt.darker` hover and pressed); the seek handle (12 px accent circle, 2 px foreground border on focus); the title-bar menu dots. | ui/tools/TextColor.qml:49-75; ui/AudioPlayer.qml:120-139, 265-274; ui/TitleBar.qml:142-158 |
| 73 | Note-pane palette and type: `foreground: editor.foreground`, `background: editor.background`, `accent`, `fontFamily: interfaceFont`, `noteFontFamily: noteFont`, `bodyFontSize: noteFontSize` (`round(baseSize*1.25)`); `titleSize = 2 * bodyFontSize`. | Workspace.qml:94-103, 2861-2866; ui/NoteEditor.qml:157-162 |
| 74 | Sheet layout: an optional right-aligned date caption, the title, then the body. Margins: top `space(12)`, bottom `panelPadding`, sides `max(panelPadding, min(space(72), width*0.064))`; spacing `xxxl`. | ui/NoteEditor.qml:1841-1866 |
| 75 | Fonts: Nimbus Sans is bundled in four faces and used for both the interface and note text. Glyph Texts set `Style.fontFamily` or `Style.font.family`. Standalone registers `SymbolsNerdFont-Regular.ttf` as an application fallback for `Script_Common`. | Workspace.qml:94-96, 2380-2395; ui/NoteList.qml:475; ui/SidebarAction.qml:67; ui/RowMenu.qml:103; ui/ChromeTextField.qml:42; ui/statusbar/StatusIcon.qml:30; hosts/standalone/application.cpp:48-51; docs/standalone.md:63 |
| 76 | Glyph centring: Button and StatusIcon centre the tight bounding rect of the glyph and use `Text.NativeRendering`. | design/controls/Button.qml:68-95; ui/statusbar/StatusIcon.qml:1-34 |
| 77 | Animation convention: 120 ms colour animations on control fills and 120 ms list displacement. | design/controls/Button.qml:51-55; ui/statusbar/StatusButton.qml:38-47; ui/NoteList.qml:647 |

### Glyph inventory (literal characters in source; there is no central icon map)

| Glyph | Code point | Used for | Where |
|---|---|---|---|
| 󰐕 | U+F0415 | New Note (footer) | docs/providers.md:209; plugins/org.note-note.local/Provider.qml:107; sticky :80; notion :86 |
| 󰉗 | U+F0257 | New notebook / New section | docs/providers.md:124, 210; local Provider.qml:99, 109, 125 |
| 󰑕 | U+F0455 | Rename (menu) | docs/providers.md:125; local Provider.qml:126 |
| 󰆴 | U+F01B4 | Delete (menu) | docs/providers.md:126; local Provider.qml:120 |
| 󰒓 | U+F0493 | Settings / Set up… | ui/TitleBar.qml:190; docs/providers.md:477 |
| 󰌌 | U+F030C | Key bindings | ui/TitleBar.qml:193 |
| 󰏌 / 󰨟 | U+F03CC / U+F0A1F | Detach / Back to overlay | ui/TitleBar.qml:187 |
| 󰅀 / 󰅂 | U+F0140 / U+F0142 | tree open/closed, dropdown indicator | ui/NoteList.qml:473; ui/ChromeDropdown.qml:37 |
| 󰊻 | U+F02BB | default action-row glyph, sign-in rows | ui/NoteList.qml:472; sticky Provider.qml:72 |
| 󰍉 | U+F0349 | search field | ui/NoteSearch.qml:31 |
| 󰅖 | U+F0156 | clear / close / cancel | ui/NoteSearch.qml:69; ui/TextPage.qml:127 |
| 󰄬 / ● | U+F012C / U+25CF | Saved / Unsaved | ui/ViewBar.qml:140 |
|  | U+EC02 | sidebar toggle | ui/ViewBar.qml:89 |
| 󰌹 󰦨 󰖟 | U+F0339 U+F09A8 U+F059F | link tool, link text, URL fields | ui/tools/InsertLink.qml:10, 63, 77 |
| 󰏘 / 󰃭 | U+F03D8 / U+F00ED | text colour / calendar tools | ui/tools/TextColor.qml:10; plugins/org.note-note.calendar/InsertCustomMonth.qml:12 |
| 󰑐 / 󰍃 | U+F0450 / U+F0343 | Refresh / Sign out | plugins/org.note-note.notion/Provider.qml:88; sticky Provider.qml:81 |
| + › … ☑ ☐ ✓ | plain Unicode | New-note row, submenu/breadcrumb arrow, "opens input" ellipsis, checkbox previews, MergeConflict choice | ui/NoteList.qml:472, 485; ui/editing/ToolMenuItem.qml:57; ui/ViewBar.qml:116; Workspace.qml:1317; ui/MergeConflict.qml:119 |

Glyph sizes: `Style.font.iconSmall` for rows, field leading icons and dropdown indicators
(ui/NoteList.qml:476; ui/SidebarAction.qml:68; ui/ChromeTextField.qml:43). `Style.font.icon` for menus,
tool-form headers and buttons (ui/RowMenu.qml:104; ui/editing/ToolForm.qml:40; design/controls/Button.qml:24).

## Q5 — Keyboard-first and accessibility conventions

| # | Fact | Where |
|---|---|---|
| 78 | `Accessible.*` usage is only `Accessible.name`. It appears in Button (`text \|\| tooltipText`), StatusButton, the ViewBar sidebar toggle, ChromeDropdown (`label`), the AudioPlayer seek bar, TextColor swatches, Diacritics letters, InsertLink fields, the CommandPalette query and rows, and the calendar's year field. No `Accessible.role`, `checked` or `description` is used anywhere. | design/controls/Button.qml:41; ui/statusbar/StatusButton.qml:29; ui/ViewBar.qml:93; ui/ChromeDropdown.qml:17; ui/AudioPlayer.qml:248; ui/tools/TextColor.qml:57; ui/tools/Diacritics.qml:93; ui/tools/InsertLink.qml:65, 79; ui/commands/CommandPalette.qml:281, 338-339; plugins/org.note-note.calendar/InsertCustomMonth.qml:87 |
| 79 | No `activeFocusOnTab` or `KeyNavigation` exists in `ui/`, `design/`, `plugins/`, `hosts/`, `examples/` or Workspace.qml (verified by grep). | (repo-wide grep) |
| 80 | Focus indicators: Button draws a 1 px `alpha(fg, 0.4)` border plus the hover fill on activeFocus. TextField turns its border `accent`. ChromeTextField and ChromeDropdown use the `border.focus` token. TextColor swatches get a 2 px accent ring; the slider handle a 2 px foreground border. StatusButton draws a ring but is `NoFocus`. | design/controls/Button.qml:29, 47-50; design/controls/TextField.qml:30; ui/ChromeTextField.qml:28; ui/ChromeDropdown.qml:46; ui/tools/TextColor.qml:65-66; ui/AudioPlayer.qml:272-273; ui/statusbar/StatusButton.qml:20, 28 |
| 81 | Keyboard focus is opt-in: Button defaults to `NoFocus`. ToolForm's confirm, MergeConflict's buttons, Diacritics, the audio play button and TextColor swatches (`StrongFocus`) opt in. PromptDialog's buttons do not. | design/controls/Button.qml:12, 40; ui/editing/ToolForm.qml:81; ui/MergeConflict.qml:123, 146; ui/tools/Diacritics.qml:94; ui/AudioPlayer.qml:127; ui/tools/TextColor.qml:56 |
| 82 | Grid navigation pattern: `Keys.onPressed` maps arrows to the neighbour's index and calls `forceActiveFocus()`. Edges hand off to another control (swatches → Reset; letters → language). Diacritics adds explicit Enter/Return handlers that choose. | ui/tools/TextColor.qml:76-96, 127; ui/tools/Diacritics.qml:100-121 |
| 83 | Shortcut routing: `handleShortcut` gives modal states the first claim (delete confirm, row-action confirm, prompt → false, palette, tool panel), then the open page, then the registry by context. The context is `editor` iff `editor.bodyFocused` (the TextEdit's activeFocus), else `workspace` (or `page`/`search`). | Workspace.qml:2135-2176; ui/NoteEditor.qml:72 |
| 84 | Text inputs let app shortcuts win: `Keys.priority: Keys.BeforeItem` plus `shortcutHandler(event)` (the editor title and body, search, TextPage). The content root also routes unaccepted keys to `handleShortcut`. | ui/NoteEditor.qml:237-247, 1909-1910, 2111-2113; ui/NoteSearch.qml:80-85; ui/TextPage.qml:199-205; Workspace.qml:2629-2634 |
| 85 | Escape is bound to `back` in the `notes` context ("Clear the search or put the window away"). Plugin bindings must use modifiers; bare navigation keys cannot be claimed. | services/shortcuts/defaults.js:20; docs/commands.md:128-136 |
| 86 | List rows take no focus; navigation uses workspace shortcuts: Ctrl+Up/Down for notes, Ctrl+Right/Left to open or fold trees, Ctrl+Tab for tabs, Alt+1..9. `treeCursor` highlights a section row. | services/shortcuts/defaults.js:13-18, 30-33; ui/NoteList.qml:36-38, 436-438, 552-617 |
| 87 | Focus restoration: `editor.focusEditor()` is `area.forceActiveFocus()` (the TextEdit). It runs after activating a row, cancelling a prompt or row action, and as the palette fallback. The palette restores `priorFocus`. A provider view is focused with `Qt.callLater` after it loads. | ui/NoteEditor.qml:377-383, 172-188; Workspace.qml:2079, 2090, 2639-2646, 2722-2725; ui/commands/CommandPalette.qml:153-169 |
| 88 | Business success criterion: *"Opening, editing and closing a note never needs the mouse."* Goal: *"no modal dialogs between the user and their text"*. | docs/business-requirements.md:82, 29-31 |
| 89 | Every Text showing note or provider strings sets `textFormat: Text.PlainText`. Note content from any backend is assumed hostile. | ui/NoteSummary.qml:20, 43, 51; ui/RowMenu.qml:100, 111; ui/SidebarAction.qml:62, 81; docs/security.md:329-331 |
| 90 | Test hooks are objectNames: `noteRow-<path>`, `footerAction-<provider>-<path>`, `renameField-<path>`, `treeNoteCount-<path>`, `rowMenu-<id>`, `promptField`, `toolFormNotice`, `commandChoice-<id>`. Tests locate them with `findChild`. | ui/NoteList.qml:430, 497, 532, 714; ui/RowMenu.qml:80; design/controls/PromptDialog.qml:72; ui/editing/ToolForm.qml:64; ui/commands/CommandPalette.qml:329; tests/ordering.qml:71; tests/extensions.qml:322 |
| 91 | The editor can host a non-TextEdit view in the sheet (provider views via `showView` and `customLoader`; conflict review) and track whether it has focus (`viewHasFocus`). | ui/NoteEditor.qml:148-151, 168-217, 1918-1948 |

---

## Integration points

1. **services/notes/sidebar.js:24-31 (`row()`).** Add the per-note content type to the whitelist so that
   NoteList and SearchResults can draw it. Rows carry only whitelisted fields and are compared by
   JSON (decisions.md:444-448).
2. **ui/NoteSummary.qml:6-57.** Add a type-glyph slot, and optionally a structured progress line. It is
   the single summary component used by both the list and search.
3. **ui/NoteList.qml:447-461 and 394-402.** Pass the new properties into NoteSummary. Revisit the indent
   math if note rows gain an icon column, because it assumes only non-note rows have one.
4. **ui/SearchResults.qml:104-117.** Pass the same properties, since search rows "must measure exactly"
   like list rows.
5. **Workspace.qml:1305-1324 (`displayTitle`).** For an untitled typed note, the preview-derived fallback
   title would read the summary text ("3 of 7 done…").
6. **Workspace.qml:1873-1938 (`newNoteDestination`/`newNote`) and 1690-1703 (`activateFooterShortcut`).**
   Typed creation must carry a type through `host.newNote` to `provider.create`; today nothing does.
7. **services/commands/WorkspaceActions.qml:18-48, services/shortcuts/defaults.js:21-24,
   plugins/org.note-note.workspace/plugin.json:8-60 and docs/commands.md:61.** Typed creation needs a
   keyboard and palette path. Actions are parameterless id strings, so this means a new action id or
   parameterised actions.
8. **docs/providers.md:181-213 (footer contract, `shortcut` vocabulary) and
   skills/note-note-plugin/references/providers.md.** These change if typed creation is a provider footer
   entry, or if the shortcut vocabulary grows (for example a typed new-note shortcut).
9. **design/controls/ (a new multi-line field).** The event description needs a multi-line input; none
   exists. ChromeControlStyle provides the shared input colours, radius and height.
10. **ui/editing/ToolForm.qml:11-89.** If its card layout is reused for the add-event form, it is bound to
    `Tool` (`required action: Tool`; `action.icon/label/editor.fontFamily/editor.accent`) and hard-codes
    "Insert" and "Enter to insert · Esc to cancel".
11. **design/controls/PromptDialog.qml.** It is a single-field modal with raw pixel sizes. A two-field
    modal would be new.
12. **ui/NoteEditor.qml:1841-2000 (sheet), 72 (`bodyFocused`), 377-383 (`focusEditor`/`focusBody`), 152-155
    (`toolsVisible`).** A timeline view stands in the sheet in place of the body Flickable. The keyboard
    context and every `focusEditor()` call currently target the TextEdit.
13. **Workspace.qml:2135-2176 (`handleShortcut`/`shortcutContext`).** An add-event form inside the note
    pane must own Enter and Escape before the registry, where Escape = back. Its pending state may also
    need to block workspace actions, as `promptPending` does.
14. **design/tokens.js, plugins/org.note-note.appearance/themes/system.json, docs/themes.md:74-83,
    skills/note-note-plugin/references/themes.md:84-161.** These change only if new colour tokens are
    introduced (for example a timeline line or checked colour). system.json lists every token
    (themes.md:81-82).
15. **ui/NoteSkeleton.qml.** An optional timeline-shaped loading placeholder; today it is document-shaped.
16. **tests (objectName hooks; tests/ordering.qml, tests/extensions.qml).** New controls should expose
    objectNames in the established `kind-<id>` style for `findChild`.

## Constraints

- Code style: braces on every if/else/for/while with the body on its own lines; no hacks; do the proper
  fix. (CLAUDE.md)
- The host must not branch on provider identity; `if (provider.id === "…")` is a design failure.
  (docs/technical-requirements.md:85-91)
- Providers never touch the UI directly; they signal. (docs/technical-requirements.md:93-97)
- A row carries only what the list shows or drags on; compare, then assign; the sidebar model is a plain
  JS array replaced wholesale. (docs/decisions.md:438-448; docs/technical-requirements.md:167-168)
- The provider contract changes additively, never silently. (docs/technical-requirements.md:99-101)
- The host adds no creation buttons based on provider identity or capabilities; footer actions stay out
  of rows. (docs/providers.md:185-187)
- Row menus: the host adds no item of its own. (docs/providers.md:100-101)
- Colours only from tokens; tokens.js is the only list; the application never paints its own colour.
  (design/tokens.js:3; docs/themes.md:74-87)
- Accent as ink is `Qt.tint(foreground, alpha(accent, …))`; never `Qt.lighter`/`Qt.darker`.
  (ui/NoteList.qml:73-79)
- Sidebar surfaces must not need to know whether the theme is dark or light. (docs/decisions.md:58-65)
- Hover, pressed and selected fills come from the control's ink via `Style.*FillFor`, not from tokens.
  (docs/themes.md:89-92; design/Style.qml:60-77)
- Shared code may only use Style spacing and font keys that both hosts define (the standalone
  `desktopFont`/`desktopSpacing` key set). (design/Style.qml:20-47 vs the shell Style)
- Render note content as `Text.PlainText`; note content is assumed hostile. (docs/security.md:329-331;
  UI convention)
- Opening, editing and closing a note never needs the mouse. (docs/business-requirements.md:82)
- No modal dialogs between the user and their text. (docs/business-requirements.md:29-31)
- Form conventions: no Cancel button in popovers; Escape or a click outside cancels; no labels above
  fields; a placeholder plus a leading glyph; `message` replaces the hint. (docs/editing-tools.md:349-357)
- Non-goal: "Not an Obsidian/Notion replacement. No … databases, templates". A typed-notes feature should
  state how it squares with this or amend it. (docs/business-requirements.md:57-58)
- UI change checklist: qmllint clean; screenshot and look; exercise it via `shell call` and check the
  saved file. (docs/testing.md:763-775)
- Plugin and override keybindings need a modifier; bare navigation keys cannot be claimed.
  (docs/commands.md:132-136)

## Reusable pieces

- NoteSummary, the two-line note summary shared by the list and search. (ui/NoteSummary.qml:1-58)
- The "+ New note…" add-row look: dimmed to `secondaryOpacity(0.65)` until hovered, a "+" glyph in
  accentInk, label at `bodySmall`. (ui/NoteList.qml:440-492)
- SidebarAction, a row-shaped action that becomes an in-place single-line input (Enter submits, Escape
  or blur cancels). (ui/SidebarAction.qml:1-134)
- ChromeTextField with ChromeControlStyle and ChromePopupStyle: input and popup colours, radius, height,
  leading glyph. (ui/ChromeTextField.qml; ui/ChromeControlStyle.qml; ui/ChromePopupStyle.qml)
- Button and ChromeButton: focusable opt-in, bordered, iconText, tooltip, `Accessible.name`.
  (design/controls/Button.qml; ui/ChromeButton.qml)
- Dropdown and ChromeDropdown for a choice among options. (design/controls/Dropdown.qml;
  ui/ChromeDropdown.qml)
- The ToolForm card layout (header, fields, hint or message, one confirm) as a pattern.
  (ui/editing/ToolForm.qml:27-88)
- PromptDialog and ConfirmDialog with the workspace's pending-state wiring.
  (design/controls/PromptDialog.qml; design/controls/ConfirmDialog.qml; Workspace.qml:2082-2103, 3001-3055)
- RowMenu, ChromePopupStyle and BorderSurface for context menus. (ui/RowMenu.qml)
- The CommandPalette generic picker `pick()` / `ui.pick` for searchable choices.
  (ui/commands/CommandPalette.qml:116-138; docs/commands.md:79-97)
- The editor's checkbox drawing recipe (accent fill, tick cut out in the background colour, 0.4/0.75
  border). (ui/NoteEditor.qml:2242-2289)
- Arrow-key focus navigation between sibling controls. (ui/tools/TextColor.qml:76-96;
  ui/tools/Diacritics.qml:100-121)
- Colour helpers: `Style.secondaryText`, `Util.alpha`, the accentInk recipe,
  `Style.hoverFillFor`/`selectedStateColor`. (design/Style.qml; design/Util.qml; ui/NoteList.qml:79)
- The shared scroll feel, scroll fades and a thin scroll track. (ui/ListWheel.qml:11-20;
  ui/NoteList.qml:652-676, 740-762)
- A plain-text TextEdit inside a Flickable with `ensureVisible`. (ui/TextPage.qml:175-225)
- NoteSkeleton, the loading placeholder. (ui/NoteSkeleton.qml)
- The `NoteEditor.showView`/`customLoader` pattern for hosting a non-TextEdit view in the sheet and
  focusing it. (ui/NoteEditor.qml:168-188, 1918-1931)
- PanelToolTip and the Button `tooltipText`. (design/controls/PanelToolTip.qml;
  design/controls/Button.qml:107-109)
- objectName test conventions with `findChild`. (tests/ordering.qml:71; tests/extensions.qml:322)

## Risks

- Using shell-only Style keys (for example `Style.spacing.xl`, `Style.font.heading`) evaluates to
  `undefined` in the standalone host, whose fallback objects lack them (design/Style.qml:20-47).
- A row field the list does not draw, or one that changes on every check, makes equal lists unequal and
  rebuilds the whole sidebar on each change (docs/decisions.md:444-448).
- A provider-computed timeline `preview` lags until save and re-list. Titles had the same problem and now
  use `session.unsavedTitles` (Workspace.qml:1302-1307; NoteSession.qml:48-62).
- A computed summary in `preview` becomes searchable (sidebar.js:19-22) and becomes the untitled-note
  title fallback (Workspace.qml:1312-1323).
- Row menus are pointer-only (NoteList.qml:611-617). A type choice offered only there breaks the
  mouse-free criterion.
- One footer row per type grows the footer by `space(32)` each (NoteList.qml:716), shrinking the list;
  the codebase argues against growing button rows (TitleBar.qml:112-116).
- ToolForm cannot be reused outside the editing-tool framework as is: it requires a `Tool` and reads
  `action.editor.*`.
- Copying existing inconsistencies would spread them: raw-pixel dialog sizes (PromptDialog/ConfirmDialog),
  `Qt.rgba(0,0,0,0.12)` in MergeConflict:101, `Qt.lighter`/`Qt.darker` in AudioPlayer:133-134, differing
  hover fills (NoteList 0.05 vs `Style.hoverFill`), and the unused `NoteList.background` and
  `TextField.hasCursor`.
- A multi-line description conflicts with the "Enter submits" convention used by every existing input.
- Escape left unhandled inside the note pane falls through to `back`, which clears the search or puts the
  window away (defaults.js:20).
- With a timeline view focused, `editor.bodyFocused` is false, so the context is `workspace`; every
  `editor.focusEditor()` call targets a hidden TextEdit (NoteEditor.qml:72, 377).
- `Color.token()` returns `undefined` for an unknown name, with no warning (Color.qml:36-38).
- Glyphs drawn in the Nimbus interface font render as tofu; glyph Texts must use `Style.fontFamily`.
- The accessibility baseline offers no precedent for a check or radio role; a custom circle control would
  be unnamed and roleless to assistive technology unless that is added.
- A modal "Add new event" dialog conflicts with "no modal dialogs between the user and their text"
  (business-requirements.md:29-31).

## Open questions

1. Is the per-type glyph host-owned (a single type registry: id → label, glyph, view) or provider-supplied
   through the row `icon`? `row()` carries `icon` for notes, but NoteList ignores it.
2. Where is the timeline summary computed: provider `preview` text, a shared helper, or structured row
   data formatted by NoteSummary? Must it update live before the save lands?
3. What shape should the add-event form take: an inline expansion below the list (SidebarAction-like), an
   anchored popover (ToolForm-like), or a centred modal (PromptDialog-like)? The business requirement
   points away from modals.
4. Description Enter semantics: Enter inserts a newline and Ctrl+Enter submits? Or a single-line
   description? No precedent exists.
5. How is the type chosen at creation: one provider footer action per type, a single "New…" entry that
   opens a type menu or picker, or a palette picker? Does each type need a shortcut?
6. Should a timeline note offer creation through the tree rows' "+ New note…" entries (`kind "new"`)?
7. Introduce new colour tokens (line, checked circle) or derive from `accent.primary`, `border.default`
   and `text.secondary`? Icons and dimensions are outside the theme schema.
8. Should the check circles carry `Accessible.role` (CheckBox or RadioButton) and a checked state, setting
   a new accessibility precedent?
9. When event k is unchecked, are the events below it unchecked too? This determines which visual states
   the circles need.
10. How do the formatting toolbar and the word count behave for a timeline note (`toolsVisible` gating,
    `countVisible`)? This belongs to the editor area but is visible chrome.

## Recommendations (grounded in the conventions above)

- Extend NoteSummary once, with a type-glyph slot and an optional progress text, so the list and search
  stay identical. Keep the type → glyph/label mapping in one host-owned module, like
  `services/notes/sidebar.js`, so rows, footer, menus and palette agree without provider-id branches.
- Draw the timeline's check circle on the editor checkbox recipe made round (`radius: side/2`):
  - unchecked: border `alpha(fg, 0.4)`, 0.75 on hover;
  - checked: accent fill with the tick in the background colour;
  - focus: a 2 px accent ring, as on the TextColor swatches;
  - spine: hairline `border.default`, with completed segments in accent or accentInk.
- Use only Style keys that both hosts define. Render event text as PlainText. Use 120 ms colour
  animations.
- For the description, add a multi-line Chrome field on ChromeControlStyle; keep title and description
  fields label-free (placeholder plus leading glyph), and show validation through a `message` line.
- Make "Add new event" a keyboard-reachable row styled like the "+ New note…" add row (dimmed "+",
  accentInk). Prefer a non-modal inline form, as SidebarAction does.
- Give typed creation a keyboard and palette path (a palette command plus an optional binding), not only
  a right-click menu.
- Add objectNames in the existing style (for example `timelineEvent-<i>`, `timelineCheck-<i>`,
  `timelineAddEvent`, `timelineEventTitle`, `timelineEventDescription`) for `findChild`-based tests.
