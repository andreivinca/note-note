# Editor map — area: editor (HEAD e2cdc4e, branch master)

All citations are `file:line` at HEAD. Repo root: `/home/andrei/Projects/note-note`.
`cpp/textlists.h` (named in the brief) does not exist at HEAD: list operations are
declared in `cpp/textblocks.h:75-83` and implemented in `cpp/textlists.cpp`.

## Summary

- `ui/NoteEditor.qml` (2409 lines) is the whole note pane. From top to bottom it holds:
  - the formatting `ToolBar` pinned across the top;
  - a "sheet" `Column` with the modified-date line, then the notice title or the editable title field;
  - the provider-view `Loader`, the conflict-review `Loader` and the notice column;
  - a `Flickable` with one rich-text `TextEdit` (`area`), plus overlays (quote bars, code slabs, checkbox faces, audio players, image handles);
  - a `NoteSkeleton` shown while the note loads.
- It is instantiated once, in `Workspace.qml:2824-2886` (`id: editor`, `objectName: "noteEditor"`). Two clients drive it:
  - `Workspace.qml` feeds provider capabilities, theme, fonts and keybindings, and reads or calls about 30 members.
  - `services/notes/NoteSession.qml` uses the document protocol: `setNote` / `restoreDocument` / `snapshotDocument` / `requestMarkdown` / `viewState` / `restoreViewState` / `title` / `documentBase` / `readOnly` / `showConflict` / `clearConflict` / `clearNotice`.
- Today the content type is a per-PROVIDER boolean:
  - `Workspace.qml:2837-2840` binds `plain: !provider.markdown`, the only reader of `markdown` in QML/JS.
  - `plain` is then threaded through about 20 branches of NoteEditor and through `EditorApi.writable`, switching the same `TextEdit` between PlainText and RichText.
- **How a body enters.** `setNote(title, body, shown)`:
  1. bumps `noteToken`, which guards against an older note's conversion winning the race;
  2. sets the title under `settingText`;
  3. for Markdown, runs `Markdown.toHtml` in a Python subprocess (`services/markdown/qthtml`);
  4. calls `showBody`, which assigns `area.text`, refreshes link display and decorations, and puts the caret and scroll at the top.

  `shown(ok)` reports whether the document now holds the note. Only then does the session end the load (`noteReady` / `noteUnavailable`).
- `restoreDocument(snapshot)` puts back the editor's own form (HTML for rich notes, text for plain ones) without converting. It is used for drafts and in tests.
- **Saving.** `NoteSession.flushSave` takes `snapshotDocument()` (`{title, body, base}`) and compares it with `stored[path]`: what the provider is known to hold, in the editor's own form (commit 5887a8f). If they are equal, it skips the save. Otherwise `requestMarkdown` converts `documentHtml()` through `Markdown.toMarkdown` and hands `map.note` (trailing blank lines trimmed by `reader.as_note`) and `ok` to `provider.save`.
- **Edits.** Every edit ends in `edited()`, which Workspace forwards to `NoteSession.onEdited`. This covers typed text (`onTextChanged`, gated by the native content revision, `settingText` and `readOnly`), the title, tools, pastes and undo/redo. `NoteSession.onEdited` sets `dirty`, then calls `provider.noteEdited` or starts the host's 1500 ms timer.
- **Read-only** is pushed by the session (`editor.readOnly = !session.writable`).
  - `applyReadOnly` applies it to the `TextEdit` and preserves caret and scroll.
  - The title field disables, and the tool strip hides through `EditorApi.writable`.
- **Notices, provider views and the conflict review** stand in place of the title and body. The loading skeleton shows while `hasNote && loading` and no notice is up.
- **Task-list items** round-trip as `- [ ]`/`- [x]` ↔ `<li class="unchecked|checked">`.
  - Qt paints a ☐/☒ glyph. The editor covers it with its own rounded box: decoration only, with no handlers.
  - A mouse click on the glyph is Qt's own toggle of that one item.
  - Ctrl+1 (tool `todo`) toggles the checkbox list *style*, not the checked state.
  - Nothing checks items in order.
- **Keyboard.** The body `TextEdit` and the title field call `shortcut(event)` with `Keys.priority: BeforeItem`, which runs `Workspace.handleShortcut` first. That function checks, in order:
  1. modal states;
  2. `editor.tools.panelOpen`;
  3. keys for an open page;
  4. `KeybindingRegistry.match` in context page/search/editor/workspace, where "editor" means `editor.bodyFocused`.

  Tool bindings run `editor.tools.execute`, and paste bindings run `editor.paste()` / `pastePlain()`. Keys left unhandled reach NoteEditor's own rich-text logic.
- **Host-level facts that hang off the rich editor:**
  - `canColorText` says whether the native inspector is built, and feeds theme support.
  - `tools.actions` feeds the KeybindingRegistry.
  - `toolbarHeight` aligns the sidebar header.
  - `hoveredLink` and `wordCount` feed the view bar.
- **Timing of a per-note type.** It would only be known inside `provider.load`'s callback. But `setNote("", "")` and `restoreDocument(draft.document)` run before that point, and drafts and recovery documents are stored in one editor's form.
- **Tests.**
  - `tests/EditorKeys.qml` drives a real NoteEditor with real keys and the real converter, in suites run by `tests/transition_selftest.py`. The suite names are duplicated in `CMakeLists.txt:99`.
  - `tests/transitions.qml:375-400` gives the session a stand-in editor with only 12 functions plus a few properties. That is the session's real contract.

---

## 1. Public surface as used by Workspace.qml and NoteSession.qml

### 1.1 What Workspace sets on the instance (`Workspace.qml:2824-2886`)

| member | value | NoteEditor decl | meaning |
|---|---|---|---|
| `objectName` | `"noteEditor"` | — | tests find the editor by it (`tests/extensions.qml:405`, `tests/standalone.qml:113`, `tests/transitions.qml:133`) |
| `markdown` | `markdownService` (`Workspace.qml:2426-2433`) | `:49` | the conversion service; `null` = no conversion |
| `clipboard` | `clipboardService` | `:52` | the clipboard service, used for image and HTML paste |
| `canImages` | `provider.canImages === true` | `:56` | whether pasting a picture is allowed |
| `hasNote` | `root.currentPath !== ""` | `:24` | a note is open |
| `loading` | `root.loadingNote && root.loadingPath === root.currentPath` | `:25` | drives `showingSkeleton` (`:167`) |
| `plain` | `p ? !p.markdown : false` (`:2837-2840`) | `:28` | per-provider content type: plain text vs Markdown |
| `hasTitle` | `p ? p.hasTitle : true` | `:30` | show the title field |
| `enabledTools` | `p.tools` or `null` | `:34` | provider capabilities that gate the tools |
| `toolbarLayout` | `root.config.editor.toolbar` | alias `:1805` | toolbar arrangement (`ToolRegistry.layout`) |
| `toolContributions` | `pluginCatalog.tools` or `null` | alias `:1804` | tools contributed by packages |
| `modifiedText` | the row's `modified`, formatted | `:1808` | the date line at the sheet's top right (`:1857-1866`) |
| `foreground` / `accent` / `background` | theme tokens | `:35`, `:36`, `:39` | colours |
| `fontFamily` / `noteFontFamily` / `bodyFontSize` | interface font, note font, note size | `:40`, `:45`, `:46` | typography |
| `shortcutHandler` | `root.handleShortcut` | `:241` | the app's key hook |
| `keybindings` | `shortcutRegistry` | `:1800` (required) | the shortcut registry, read by the tools |
| `onEdited` | `root.onEdited()` → `session.onEdited()` (`:2253-2255`) | signal `:249` | an edit happened |
| `onLinkOpenRequested` | `Qt.openUrlExternally` | `:86` | link click |
| `onStatusRequested` | `root.showStatus(text)` | `:251` | status-line message |
| `onRecordingRequested` | `p.recording(source, title, answer)` | `:255` | fetch a remote recording |

### 1.2 Members Workspace reads or calls (component members; `Color.token("editor.*")` strings excluded)

| member | Workspace lines | what it is in NoteEditor |
|---|---|---|
| `bodyFocused` | 2175 (`shortcutContext`) | `readonly property bool bodyFocused: area.activeFocus` (`:72`) |
| `canColorText` | 122-123 (`codeChipColour`), 2520 (`ThemeService.supportsCustom`) | `!!nativeBlocks.item`, i.e. the native inspector is built (`:787`) |
| `clearNotice()` | 313 (`open`), 552 (account signed in), 733, 739 (provider `noticeCleared` / `viewCleared`) | `:226-235`, serial-guarded |
| `conflictReview` | 1604 (`debugState`) | `:193` |
| `cursorPosition()` | 1739 (IPC `editorCursor`) | `:1778` |
| `focusEditor()` | 326, 441, 1935, 2013, 2049, 2079, 2090, 2220 (`acceptSearch`), 2644, 2724 | `area.forceActiveFocus()` (`:377`) |
| `focusTitle()` | 1933 (`newNote` when `p.hasTitle`) | `:1791` |
| `hoveredLink` | 2919 (ViewBar) | `:84-85` |
| `inTable`, `updateInTable()` | 1738-1739 (IPC) | `:945`, `:959-987` |
| `noticeTitle` | 1603 (`debugState`) | `:138` |
| `paste()` / `pastePlain()` | 1725 (IPC), 2245-2250 (`keyActions`, guarded by `editor.plain` / `readOnly`) | `:388-425` / `:514-554` |
| `plain` | 2246, 2249 | `:28` |
| `readOnly` | 1601, 2246, 2249, 2580 (`contextState.editorWritable`), 2916 (ViewBar) | `:32` |
| `setCursorPosition()` | 1737 | `:1790` |
| `showingNotice` | 2921 (ViewBar `countVisible`) | `:166` |
| `showNotice()` | 506, 530, 533, 542 (Microsoft sign-in), 730 (provider `noticeRequested`) | `:218-225`, returns a serial |
| `showView()` | 736 (provider `viewRequested`) | `:172-188` |
| `tool(id)` | 1721 (IPC `editorTool`) | `:1822-1824` → `toolRegistry.execute` |
| `tools.actions` | 2554 (`KeybindingRegistry.tools`) | alias `tools: toolRegistry` (`:1802`); `ToolRegistry.actions` (`ToolRegistry.qml:26-28`) |
| `tools.execute()` | 2184 (`runBinding`, kind "tool") | `ToolRegistry.qml:271-280` |
| `tools.panelOpen` | 2150 (`handleShortcut` gate), 2547 (`WorkspaceActions.blocked`) | `ToolRegistry.qml:23-25` |
| `toolbarHeight` / `toolbarRowHeight` | 2714-2715 (NoteList header alignment) | `:1806-1807` |
| `undo()` | 1731 (IPC `editorUndo`) | `:717` |
| `viewHasFocus` | 1605 (`debugState`) | `:216-217` |
| `wordCount` | 1602, 1733, 2920 (ViewBar) | `:1794-1797` |

### 1.3 Members NoteSession reads or calls (`services/notes/NoteSession.qml`)

| member | lines | role |
|---|---|---|
| `editor` (property) | 8 | injected (`Workspace.qml:2614-2620`) |
| `title` | 59 | `unsavedTitles` for the open, dirty note |
| `readOnly` (write) | 120 (`updateReadOnly`) | the derived flag, pushed in |
| `showConflict(props)` | 143-166 | `{conflict, remoteName, retry, continueEditing, resolve}` |
| `clearConflict()` | 173 | |
| `viewState()` | 221 | caret and scroll before a reload |
| `clearNotice()` | 222 | at every load |
| `documentBase` (write) | 224, 262 | `""` then `result.base` before `setNote` |
| `setNote(t, body, shown)` | 226 (`("", "")` on a non-reload load), 263 | shows the provider body; `shown(ok)` ends the load |
| `restoreDocument(snapshot)` | 237 | shows a draft's captured document |
| `restoreViewState(view)` | 272 | after a reload |
| `snapshotDocument()` | 278 (recovered draft), 294 (`stored` at load), 420 (delete recovery), 480 (`flushSave`) | `{title, body, base}` in the editor's form |
| `requestMarkdown(cb)` | 493 | the body for `provider.save` |

### 1.4 The session's real contract: the stand-in in `tests/transitions.qml:375-400`

A plain `QtObject` stands in for the editor:

- properties: `title`, `body`, `documentBase`, `readOnly`, `conversions`, `conflictReview`;
- functions: `cursorPosition()`, `setCursorPosition()`, `viewState()`, `restoreViewState()`, `clearNotice()`, `showConflict(props)`, `clearConflict()`, `setNote(t, b, shown)`, `snapshotDocument()`, `restoreDocument(snapshot)`, `requestMarkdown(callback)`.

NoteSessions under test use it as `editor: document` (`tests/transitions.qml:426`, `491`, `551`, `1198`, `1227`). It shows that the session needs only this surface, not the rich editor.

### 1.5 Signals

- `edited()` (`:249`). The internal handler bumps `documentRevision` and schedules the caret-context update (`:267-270`).
- `statusRequested(string)` (`:251`)
- `recordingRequested(source, title, answer)` (`:255`)
- `linkOpenRequested(url)` (`:86`)

### 1.6 Tests reach rich internals directly through `editor.*`

- `tests/transitions.qml`: `plainText`, `replaceDoc`, `withMarkdown`, `noteToken`, `documentHtml`, `blockEndLine`, `insertFormattedText`, `pasteRich`, `paste`, `pastePlain`, `undo`/`redo`, `tools`, `restoreDocument`, `readOnly`, `edited`, `setCursorPosition`, `cursorPosition`.
- `tests/extensions.qml`: `focusEditor`, `tools` (including `editor.tools.editor.textArea` at `:409`), `plainText`, `setCursorPosition`, `bodyFocused`, `requestMarkdown`, `canColorText`, `undo`, `foreground`.
- `tests/standalone.qml`: `plainText`, `focusEditor`, `setCursorPosition`, `canColorText`.
- `tests/audio.qml`: `setNote`, `plainText`, `paste`, `focusBody`, `readOnly`, `updateDecorations`, `requestMarkdown`, `inspectorUrl`, `activeAudioPlayer`, `grabToImage`.
- `tests/EditorKeys.qml`: the most of all; it instantiates `Ui.NoteEditor` directly (`:51`, `:73`).

---

## 2. How a body enters; plain mode; states; title; focus

### Entering

- **`setNote(t, body, shown)`** (`NoteEditor.qml:292-316`):
  1. `resetAudio()`, then `editing.clearPending()`, then `token = ++noteToken`.
  2. Sets the title under `settingText` and moves the title caret to 0 (`:296-299`).
  3. If the note is plain, or there is no markdown service, or the body is empty: `showBody(body || "", token)` then `shown(true)` (`:300-306`).
  4. Otherwise: `markdown.toHtml(body, cb, documentBase)`, and in the callback drops a stale token, then calls `showBody(ok ? html : "", token)` and `shown(ok)` (`:307-315`).

  Its header comment (`:282-291`) explains the empty-on-failure rule: "the document is then left empty on purpose, since an editable blank is what autosave would write back over the note".
- **`showBody(document, token)`** (`:334-345`): a stale token returns. Otherwise it sets `settingText = true` and assigns `area.text = plain ? document : Dialect.documentHtml(document)`. It then runs `configureLinkDisplay()`, sets `settingText = false` and `audioDocumentToken = token`, and calls `updateDecorations()` and `showTop()`.
- **`showTop()`** (`:351-355`): caret 0, `flick.contentY = 0`, `updateContext()`.
- **`restoreDocument(snapshot)`** (`:323-332`): resets audio and pending style, bumps the token, sets the title, sets `documentBase = snapshot.base` and calls `showBody(snapshot.body, token)`. There is no conversion and no `shown` callback; the session calls `noteReady(false, "")` itself (`NoteSession.qml:237-239`).
- **`documentBase`** (`:57-62`) is set by the host from `load()`'s `base` "before the body goes in". It feeds `area.baseUrl` (`:2078-2080`) and the converter's `--base`.
- **The conversion service** (`services/markdown/Markdown.qml`):
  - `toHtml(markdown, cb(html, ok), base)` (`:60-76`): an empty input answers `cb("", true)`.
  - `toMarkdown(html, cb(md, map), base, asText)` (`:90-108`): `map = {blocks, kinds, count, note, ok}`.
  - Both run `python3 qthtml/__main__.py` through `ProcessRunner` (`:110-114`), with the payload on stdin (`qthtml/__main__.py:26-28`, `:68-72`, `MAX_BYTES` 8 MiB `:41`).
  - The answer is framed JSON (`:74-80`).

### Plain mode (`plain`)

Every branch:

| what changes | where |
|---|---|
| `textFormat: PlainText` | `:2075` |
| `requestMarkdown` → `plainText()` | `:123-126` |
| `setNote` bypasses conversion | `:300` |
| snapshot body = `plainText()` | `:319` |
| `showBody` assigns the raw text | `:339` |
| `paste()` / `pastePlain()` → `area.paste()` | `:392-394`, `:518-520` |
| `insertImage` refuses | `:655` |
| `deleteParagraphBoundary` / `deleteListMarker` / `deletePreviousTable` refuse | `:739`, `:752`, `:764` |
| `withMarkdown` refuses | `:861` |
| `normalizeNow` skips | `:1124` |
| `updateDecorations` clears everything | `:1142-1149` |
| `resizeImage` refuses | `:1322` |
| `returnLeavesBlock` / `escapeForward` / `typeLeavesRule` refuse | `:1473`, `:1702`, `:1727` |
| key handler returns to Qt's own handling after undo/redo | `:2127-2129` |
| native link display told `plainText` | `:1090` |
| `onPlainChanged` reconfigures it | `:73` |
| `EditorApi.writable` requires `!host.plain`, so tools and toolbar are off | `EditorApi.qml:13`; `toolsVisible` `:155` |
| Workspace paste bindings return false, so the focused item's own paste runs | `Workspace.qml:2245-2250` |

### States

- **Read-only.**
  - The session sets `editor.readOnly` (`NoteSession.qml:119-121`).
  - `onReadOnlyChanged` → `applyReadOnly()` and `scheduleDecorations()` (`:365-368`); `onHasNoteChanged` and `Component.onCompleted` also call `applyReadOnly` (`:369-370`).
  - `applyReadOnly` sets `area.readOnly = !hasNote || readOnly`, saving and restoring caret and scroll, because Qt moves the caret to the end on a `readOnly` change (`:357-375`).
  - The title field disables (`:1895`), image handles drop (`imageBoxes = []` when read-only, `:1158`) and the toolbar rail hides (`EditorApi.writable`).
  - The provider's reason is said once on the status line (`NoteSession.qml:313-323`), and the ViewBar shows read-only (`Workspace.qml:2916`).
- **Notice** (`:136-151`, `:218-235`): `showNotice(title, text, code, actions)` returns a serial, and `clearNotice(serial)` clears only that one.
  - What shows: the notice title text (`:1879-1888`), the notice column (`:1950-1998`), the `code` in large letter-spaced accent ink (`:1968-1978`), and buttons `{label, icon, action}` (`:1980-1997`).
  - `noticeShown = noticeText.length > 0 || customView !== null` (`:164`).
- **Provider view**: `showView(title, component, props)` loads into `customLoader` and focuses it via `Qt.callLater` (`:172-188`, `:1918-1931`). `clearView()` is at `:212-215`.
- **Conflict review**: `showConflict(props)` loads `MergeConflict` and focuses it later; `clearConflict()` closes it (`:193-211`, `:1934-1948`). It stays alive under notices (`visible: active && !noticeShown`, `:1937`).
  - `showingNotice = noticeShown || conflictReview !== null` (`:166`).
  - The `Flickable` hides while `showingNotice` (`:2002`).
- **Loading**: `showingSkeleton = hasNote && loading && !showingNotice` (`:167`). The sheet hides (`:1845`) and `NoteSkeleton` shows (`:2401-2407`, `ui/NoteSkeleton.qml`).

### Title field (inside NoteEditor)

- `TextField { id: titleField }` sits in the sheet header (`:1890-1914`).
- `visible: !showingNotice && hasTitle` (`:1894`); `enabled: hasNote && !readOnly` (`:1895`).
- Font: `noteFontFamily`, `titleSize = round(bodyFontSize * 2)` (`:162`), bold.
- `onTextEdited: root.edited()` (`:1908`): title and body share the one `edited` signal.
- Keys: `Keys.priority: BeforeItem`, `onPressed → root.shortcut(event)`; Return, Enter and Down → `focusBody()` (`:1909-1913`).
- `readonly property alias title: titleField.text` (`:71`).

### Focus

- `focusEditor()` (`:377`) and `focusBody()` (showTop + focus, `:380-383`).
- `focusTitle()` (`:1791`).
- `showView` and `showConflict` focus their loaded item via `Qt.callLater` (`:182-186`, `:203-207`).
- `bodyFocused` (`:72`) and `viewHasFocus` (`:216-217`).
- Workspace focus calls: `open` (`:325-327`), `closePage` (`:441`), `newNote` (`:1932-1936`), cancel or confirm of delete, row action and prompt (`:2013`, `:2049`, `:2079`, `:2090`), `acceptSearch` (`:2220`), palette fallback (`:2644`), list activation (`:2724`).

---

## 3. Save capture, unchanged detection, edit signalling

- **`requestMarkdown(callback)`** (`NoteEditor.qml:112-134`):
  - plain or no service → `callback(plainText(), true)`;
  - otherwise `markdown.toMarkdown(documentHtml(), cb, documentBase)` → `callback(map.ok ? map.note : "", map.ok)`.

  Its comment: "an empty answer from a converter that died is not an empty note — sending it would write nothing over everything".
- **`documentHtml()`** (`:108-110`) is `area.length > 0 ? area.getFormattedText(0, area.length) : area.text`. The `text` case exists so an empty checkbox block is still seen (`docs/engine-notes.md:202-207`).
- **The map** (`Markdown.qml:105-106`; `qthtml/reader.py:73-103`) is `{markdown, note, blocks, kinds, count}`.
  - `blocks[i]` is the document block that line `i` came from.
  - `kinds[i]` is one of text/heading/blank/rule/item/code/table/html/separator.
  - `note = as_note(markdown)`, which drops trailing blank lines (`reader.py:61-70`).
  - `_loses_text` triggers a strict re-render; if text would still be lost, `convert` raises `ValueError` (`reader.py:98-101`), which surfaces as `ok: false`.
- **Unchanged detection** (commit 5887a8f, which touched `NoteSession.qml`, `tests/EditorKeys.qml` and `tests/transitions.qml`):
  - `property var stored` (`NoteSession.qml:37-43`) maps path → `{title, body}` in the editor's form.
  - It is deleted before every load (`:251`) and set when a load is shown, unless the load returned a recovered draft (`:293-294`). It is deleted when a save starts (`:485`), and set when a save lands unmerged (`:524-527`). `replacePath` re-keys it (`:77-83`).
  - `isStored(path, document)` compares title and body exactly (`:362-367`).
  - `flushSave` calls `snapshotDocument()`; if it matches what is stored, it sets `dirty = false` and sends nothing (`:480-484`).
  - Tested by `unchangedNoteUnsent` (`tests/EditorKeys.qml:336-360`), using `quietProvider` (`:301`) and `quietSession` (`:312`).
- **`snapshotDocument()`** (`:318-321`) is `{title, body: plain ? plainText() : documentHtml(), base}`.
- **The save pipeline** (`NoteSession.qml:471-507`):
  1. dirty and writable checks; `isStored` check;
  2. bump the epoch; `setDraft(path, {document, view, epoch, error})`; `dirty = false`; `countSave +1`;
  3. `requestMarkdown`;
  4. `provider.save(path, draft.document.title, body, cb, {view, resolution})`;
  5. `finishSave` (`:509-542`).
- **Edit signalling.**
  - `TextEdit.onTextChanged` (`:2171-2190`) returns early while normalizing or when the native content revision is unchanged. Otherwise it normalizes and schedules decorations. It returns if `settingText || readOnly`; else it runs `applyPendingToInsertion` and emits `edited()`.
  - Other emitters of `edited()`:
    - title edits: `:1908`;
    - NoteEditor functions: `pasteRich` `:476`, `pastePlain` `:552`, `typeInCode` `:650`, `insertImage` `:673`, `replayHistory` `:735`, `deleteParagraphBoundary` `:747`, `deleteListMarker` `:759`, `deletePreviousTable` `:772`, `toggleListStyle` `:839`, `replaceDoc` `:934`, `changeTable` `:1005`, `resizeImage` `:1329`, `insertSnippet` in a cell `:1382`, `returnLeavesBlock` `:1478`, `tableReturn` `:1510`, `escapeInlineCode` `:1774`;
    - EditorApi: `setTextColor` `:58`, `replaceInline` `:173`, `insertHtml` `:187`, `insertText` `:204`, `toggleFont` `:458`.
  - The path from there: `Workspace.qml:2869` → `root.onEdited` (`:2253-2255`) → `NoteSession.onEdited` (`:333-345`).
  - `NoteSession.onEdited` sets `dirty = true` if writable, then calls `provider.noteEdited(path)` or restarts the 1500 ms `schedule` timer (`:347-356`), which calls `flushSave`.

---

## 4. Task-list checkboxes in the rich editor today

- **Grammar.**
  - `parse.py` enables mistune `task_lists` (`services/markdown/parse.py:72-74`).
  - The writer: `item()` emits `<li class="checked|unchecked" style=…>` for `task_list_item` tokens (`qthtml/writer.py:295-314`), with `dialect.CHECK_CLASS` (`qthtml/dialect.py:37-39`).
  - An empty item carries `EMPTY_ITEM` U+00A0 (`dialect.py:41-43`; `writer.py:305-306`).
  - The reader: `marker()` maps `class="checked"` → `"- [x] "` and `"unchecked"` → `"- [ ] "` (`qthtml/reader.py:362-366`).
  - `docs/engine-notes.md:124` has the dialect table row.
- **Rendering.**
  - Qt Quick paints ☐/☒ glyphs (`docs/engine-notes.md:127-137`).
  - `updateDecorations` (`NoteEditor.qml:1141-1186`) computes `checkBoxes = [{position, checked, x, y}]`, from `QuoteBars.boxesFromBlocks(nativeBlocks.item.blocks())` (`:1155-1157`) or from `QuoteBars.boxes(html, text)` (`:1163`), plus `area.positionToRectangle` (`:1179-1182`).
  - The native `blocks()` reports `marker` 0/1/2 only for blocks that are list members (`cpp/textblocks.cpp:443-452`; `textblocks.h:125-139`).
  - The scan fallback reads the `li` class (`ui/QuoteBars.js:116-127`, `:195-217`).
  - The overlay (`NoteEditor.qml:2219-2291`) covers the glyph's cell with the background, then draws a rounded face: accent fill when checked, otherwise a border at alpha 0.4, or 0.75 on hover. The tick is two rotated rounded bars in the surface colour. `FontMetrics` sizes the glyph cell (`:1103`).
- **Toggling.**
  - The overlay is "deliberately without handlers: the click falls through to Qt's marker underneath, which toggles the real state and comes back through textChanged" (`:2219-2223`). It only adds a pointing-hand `HoverHandler` (`:2286-2289`). The engine side: `qquicktextcontrol.cpp` flips the block format on release (`docs/engine-notes.md:132-134`).
  - The toggle comes back as an ordinary edit: `onTextChanged` → `edited()`.
  - No code in `ui/`, `cpp/` or `services/` sets the checked state. `textlists.cpp:160-168` only preserves it.
- **Keyboard.**
  - Tool `todo` (`ui/tools/Checkbox.qml:4-16`; label "Checkbox"; `available: !editor.inCode`; Ctrl+1) runs `editor.toggleListStyle("todo")`. That goes to `EditorApi.toggleListStyle` (`EditorApi.qml:350-374`) and `NoteEditor.toggleListStyle` (`:825-842`).
  - The native path is `TextBlocks::toggleList` (`cpp/textlists.cpp:216-246`): it applies or removes the checkbox list *style* on the selected paragraphs, keeping each item's existing checked state.
  - Without the helper, the fallback rewrites the Markdown with the `"- [ ] "` prefix.
  - Documented in `docs/editing-tools.md:120-140`.
  - No key toggles checked/unchecked, and nothing toggles items in order.
- **Other checkbox code.**
  - Backspace at an item's start: `deleteListMarker` → `removeListAtStart` (`NoteEditor.qml:751-761`; `textlists.cpp:248-263`).
  - A second Enter on an empty item leaves the list (`textlists.cpp:265-285`).
  - Pasting checklists into a notebook without `todo`: `PasteFit.js:68`.
  - Provider capability `todo`: `docs/providers.md:54`.
- **Reusable for a timeline's check circles.**
  - The drawn face (`:2242-2284`) and its hover-cursor pattern (`:2286-2289`). This needs extracting: today it is inline in a `Repeater` delegate tied to Qt's glyph cell.
  - The Markdown task-list grammar and its reader/writer, if a timeline is stored as task items. That is a design question.

---

## 5. The seam: generic note pane vs rich-text-specific editor

**Generic (note pane):**

- properties: `hasNote` `:24`, `loading` `:25`, `hasTitle` `:30`, `readOnly` `:32`, colours and fonts `:35-46`, `documentBase` `:62` (a slot the session writes and snapshots; its meaning is image resolution), `title` `:71`, notice properties `:138-151`, `titleSize` `:162`, `noticeShown` / `showingNotice` / `showingSkeleton` `:164-167`, `conflictReview` `:193`, `viewHasFocus` `:216-217`, `shortcutHandler` `:241`, `modifiedText` `:1808`;
- functions: `showView` `:172-188`, `showConflict` / `clearConflict` `:200-211`, `clearView` `:212-215`, `showNotice` / `clearNotice` `:218-235`, `shortcut` `:242-247`, `focusTitle` `:1791`;
- the document protocol, generic in contract and type-specific in implementation: `setNote` `:292-316`, `restoreDocument` `:323-332`, `snapshotDocument` `:318-321`, `requestMarkdown` `:122-134`, `viewState` / `restoreViewState` `:1784-1789`, `cursorPosition` / `setCursorPosition` `:1778`, `:1790`, `focusEditor` `:377`, `bodyFocused` `:72`, `wordCount` `:1794-1797`;
- signals: `edited` `:249`, `statusRequested` `:251`;
- UI: background `:1835-1839`, sheet layout `:1843-1855`, modified date `:1857-1866`, header and title `:1868-1916`, `customLoader` `:1918-1931`, `conflictLoader` `:1934-1948`, notice column `:1950-1998`, `NoteSkeleton` `:2401-2407`.

**Rich-text specific:**

- properties: `plain` `:28`, `enabledTools` `:34`, `markdown` `:49`, `clipboard` `:52`, `inspectorUrl` `:55`, `canImages` `:56`, colours `:63-83`, `hoveredLink` `:84-85`, `toolsVisible` `:155`, tokens and revisions `:257-266`, `objectChar` / `imageLead` `:682-685`, `replayingHistory` `:715`, `canColorText` `:787`, `sep` `:844`, table state `:945-947`, `inList` / `inCode` `:1019-1020`, decoration models `:1039-1048`, `normalizing` `:1119`, image and audio state `:1213-1300`, tool aliases and heights `:1802-1807`;
- functions: `linkAt`, `plainText`, `documentHtml`, `editContext` / `contextCurrent`, `showBody`, `showTop`, `applyReadOnly`, `focusBody`, the paste family `:388-554`, code-block helpers `:577-652`, images `:654-714`, `:1302-1352`, undo/redo `:717-736`, delete helpers `:738-775`, `atomic` `:805-821`, `toggleListStyle` `:825-842`, the Markdown trip `:860-937`, tables `:945-1008`, `:1499-1571`, `:1649-1690`, decorations and normalization `:1054-1203`, audio `:1225-1296`, snippets and landing `:1354-1647`, escapes `:1701-1776`, `tool(id)` `:1822-1824`;
- signals: `linkOpenRequested` `:86`, `recordingRequested` `:255`;
- components: `pasteReader` `:497-503`, timers `:948`, `:1049`, `nativeBlocks` `Loader` `:1065-1081`, `FontMetrics` `:1103`, `audioModel` `:1223`, `EditorApi` `:1810-1814`, `ToolRegistry` `:1816-1820`, `ToolBar` `:1826-1833`, `Flickable` / `TextEdit` / overlays `:2000-2398`.

**Mixed: rich-specific, but read by the host.**

| member | host reader | why it matters |
|---|---|---|
| `canColorText` | theme support (`Workspace.qml:122-123`, `:2520`) | |
| `tools.actions` | key bindings (`:2554`) | |
| `tools.panelOpen` | key gates (`:2150`, `:2547`) | |
| `tools.execute` | (`:2184`) | |
| `toolbarHeight` / `toolbarRowHeight` | sidebar header alignment (`:2714-2715`) | the strip keeps its row height even with no tools (`NoteEditor.qml:1831-1832`; `ToolBar.qml:46`, `:77`) |
| `hoveredLink` / `wordCount` | ViewBar | |
| `paste` / `pastePlain` / `plain` | `keyActions` | |
| `undo` / `tool` / `inTable` / `updateInTable` | IPC | |

---

## 6. Keyboard routes

1. **The focused item calls the pane's `shortcut(event)` first.**
   - Body: `NoteEditor.qml:2111-2116`. Title: `:1909-1910`.
   - `shortcut` (`:237-247`) runs `shortcutHandler(event)` (`Workspace.handleShortcut`), or, with no host handler, `area.activeFocus && toolRegistry.handleShortcut(event)`.
2. **`Workspace.handleShortcut`** (`Workspace.qml:2135-2165`) checks in order:
   1. `deleteConfirmOpen`, `rowActionPending`, `promptPending` ("no shortcut runs under it", `:2145-2148`), `commandPalette`;
   2. `editor.tools.panelOpen` → false (`:2150-2152`);
   3. an open page's `handleKey`;
   4. `shortcutRegistry.match(event, shortcutContext())`;
   5. an autorepeat check;
   6. `runBinding`.

   The workspace content item also routes unaccepted keys to `handleShortcut` (`Workspace.qml:2629-2634`).
3. **`shortcutContext()`** (`:2168-2176`) answers `"page"` if a page is open, `"search"` if search is focused, else `editor.bodyFocused ? "editor" : "workspace"`.
4. **`runBinding`** (`:2182-2203`):
   - kind "tool" → `editor.tools.execute(binding.action)`, always returning true;
   - kind "command" → `commandRegistry.execute`;
   - workspace actions → `workspaceActions.invoke`;
   - otherwise `keyActions[...]` (`:2207-2251`).
5. **Registry.**
   - `KeybindingRegistry.match` → `compiled.index[context + "/" + signature]` (`services/shortcuts/KeybindingRegistry.qml:16-18`).
   - Scopes: `application` → workspace/editor/search/page; `notes` → workspace/editor/search; `editor` → editor (`resolve.js:10-12`).
   - Tools are offered in context "editor" at plugin priority from `Tool.shortcutKey` / `shortcutModifiers` (`resolve.js:179-191`; `Tool.qml:16-21`).
   - App defaults: `defaults.js:7-33`. Paste and plain paste use context "editor" and are protected (`:26-27`). Escape is "back" in notes (`:20`). Ctrl+Up/Down step notes (`:13-14`). Ctrl+Right/Left open and close the tree (`:17-18`); they return false on a note so the key stays the editor's (`Workspace.qml:1825-1857`).
   - Reserved native keys: `stroke.js:17-24` (Ctrl+A/C/X/V/Shift+V/Z/Shift+Z/Y, Ctrl+Insert, Shift+Insert, Shift+Delete). Refusals: `resolve.js:137-148`.
6. **`ToolRegistry.handleShortcut`** (`ToolRegistry.qml:282-292`) consumes disabled tool actions too ("so native formatting cannot bypass capabilities"). `execute` (`:271-280`) calls `updateContext`, then `canExecute` (`upToDate`, not a menu, `editor.writable`, visible).
7. **NoteEditor's own key logic after the hook** (`:2117-2166`):
   - Undo (`StandardKey.Undo`) → `undo()`; Redo (`StandardKey.Redo` or `Stroke.redoes`) → `redo()`.
   - In plain mode, return to Qt's handling.
   - Backspace → `deleteListMarker` / `deletePreviousTable`. Delete → `deleteParagraphBoundary`. Right → `escapeForward`.
   - Printable text → `typeLeavesRule`, then `editing.typePending`.
   - Return/Enter → `returnLeavesBlock`, else `beforeReturn`.
8. **Escape** runs `goBack` (`Workspace.qml:460-474`): in the overlay it dismisses the window, detached it focuses search.
   - Tool panels avoid this through the `panelOpen` gate and their own `Keys.onEscapePressed` (`ui/tools/InsertLink.qml:48`).
   - Popups use `CloseOnEscape` (`ui/editing/ToolBar.qml:274`).
9. **Pages** (`ui/TextPage.qml:198-205`) route keys through `shortcutHandler` the same way, and expose `handleKey` / `focusBody` (`:33-35`, `:78-87`).
10. **Tests.**
    - `EditorKeys` (`tests/EditorKeys.qml:17-98`) has its own `KeybindingRegistry` (`:44-47`) and no host `shortcutHandler`, so `ToolRegistry.handleShortcut` is exercised. It sends keys with `keys.keyClick` (TestCase `when: false`, `:98`), e.g. `listToolShortcut` (`:2442-2450`).
    - A helperless editor uses `StaleInspector.qml` (`:73-82`).
    - Suites: `tests/EditorKeys.qml:3051-3059`; runner `tests/transition_selftest.py:18`; CMake `CMakeLists.txt:99`.

**Routes a second editor would have to receive:**

- 1 (the `shortcut` hook on its focusable items);
- 3 (`bodyFocused` for the "editor" context, or a new context);
- 2 (a pane-level gate like `tools.panelOpen` for an in-pane form);
- 4 and 6 (tool bindings must not act on a hidden rich document);
- 5's paste bindings (`keyActions.paste`/`pastePlain` gated on `editor.plain`);
- 7's undo and redo;
- the title's Return/Down → `focusBody`;
- every `focusEditor` call site;
- 8 (Escape).

---

## Integration points

| where | what changes | why |
|---|---|---|
| `Workspace.qml:2837-2840` | the `plain: !p.markdown` binding gives way to a per-note content type that selects the editor | the only place a content type reaches the editor today |
| `Workspace.qml:2818-2886` (`notePane` / NoteEditor instance) | becomes a note pane hosting type-specific editors | there is one editor instance for every note |
| `NoteSession.qml:210-305` (`load`) | the type must be known and applied before `editor.setNote` (`:263`) and `editor.restoreDocument` (`:237`); `setNote("", "")` (`:226`) runs before any type is known | today `plain` flips with `currentPath`, before load; a per-note type would arrive with the load result |
| `NoteSession.qml:235-245`, `:404-469` (drafts, recovery) | drafts and delete-recovery documents must carry the content type | `snapshotDocument` bodies are in a specific editor's form (HTML or text), restored without conversion |
| `NoteSession.qml:37-43`, `:362-367`, `:480-485`, `:524-527` (`stored` / `isStored`) | the snapshot form must be canonical per type, and comparison type-aware | no-op-save detection compares editor-form strings |
| `NoteSession.qml:471-507` (`flushSave` → `requestMarkdown`) | a timeline editor answers with the body form its provider stores; consider renaming to a type-neutral name | `provider.save(path, title, body)` is type-agnostic; `requestMarkdown` already returns plain text for plain notes |
| `NoteSession.qml:59` (`unsavedTitles` reads `editor.title`) | the pane must expose `title` whatever the type | the sidebar shows typed titles at once |
| `NoteSession.qml:119-121` (`updateReadOnly`) | the pane must forward `readOnly` to the active editor | the session pushes the flag |
| `Workspace.qml:2150-2152`, `:2545-2547` | add a pane-level "form/panel open" gate for the timeline's add-event form, next to `editor.tools.panelOpen` | otherwise app shortcuts (Escape → `goBack` dismissing the overlay, Ctrl+N…) fire under the form |
| `Workspace.qml:2168-2176` (`shortcutContext`) | decide what `bodyFocused` means for a timeline, or add a context | tool bindings and paste bindings live in the "editor" context |
| `Workspace.qml:2182-2185` (`runBinding` tool) | tools must be no-ops or hidden when a non-rich editor is active | `runBinding` returns true and `ToolRegistry` consumes disabled actions |
| `Workspace.qml:2245-2250` (`keyActions` paste) | replace the `editor.plain` guard with a capability of the active editor | the plain guard is the content-type flag in another place |
| `Workspace.qml:2550-2556` (`KeybindingRegistry.tools: editor.tools.actions`) | keep the tool registry stable across type switches | otherwise shortcuts and the key-bindings page recompile or lose tools per note |
| `Workspace.qml:122-123`, `:2520` (`canColorText`) | a host-level capability, independent of the open note's type | theme support (`ThemeService.supportsCustom`) and the inline-code chip read it |
| `Workspace.qml:2714-2715` (NoteList `headerHeight`) | the pane must still expose `toolbarHeight` / `toolbarRowHeight` | sidebar header alignment |
| `Workspace.qml:2916-2921` (ViewBar) | `readOnly` / `hoveredLink` / `wordCount` / `showingNotice` come from the pane or the active editor | ViewBar status and word count |
| `Workspace.qml:1576-1606`, `:1720-1740` (`debugState`, IPC) | `debugState` keeps working; `editorTool` / `editorPaste` / `editorUndo` / `editorCursor` address the rich editor or become type-aware | documented IPC (`docs/testing.md:110-125`) |
| `Workspace.qml:1932-1936` and all `focusEditor` sites | the pane's `focusEditor` / `focusTitle` focus the active editor | keyboard-only success criterion |
| `Workspace.qml:2253-2255` (`onEdited`) | timeline check and add actions emit `edited()` | autosave starts from `edited` |
| `NoteEditor.qml:1826-1833` (ToolBar), `:155` | for a timeline, the rich tools hide (`EditorApi.writable` false); decide whether the row hosts type-specific controls | the strip always keeps its height |
| `NoteEditor.qml:1843-2407` (sheet) | extraction seam: generic chrome vs `Flickable` / `TextEdit` / overlays | the pane-vs-editor split |
| `ui/editing/EditorApi.qml:13` (`writable` includes `!host.plain`) | gate on "the rich editor is the active one" rather than a plain flag | tools follow the content type |
| `docs/providers.md:47`; `skills/note-note-plugin/references/providers.md:236`; `examples/hello/Provider.qml:14` | document the content type additively; keep `markdown: bool` working | contract is the API others write against |
| tests: `tests/transitions.qml:375-400` stand-in; `tests/EditorKeys.qml` suites; `tests/transition_selftest.py:18`; `CMakeLists.txt:99` | extend the stand-in with the type; add a timeline suite in both suite lists | session tests and real-key editor tests |
| `NoteEditor.qml:2219-2291` | extract the drawn checkbox face into a shared component, if the timeline reuses it | avoids a second copy of the box visuals |

## Constraints (documented invariants)

- No spaghetti, no hacks or workarounds. Do the proper fix even when it touches more code. Braces on every if/else/for/while, with the body on its own line. (`CLAUDE.md` at the repo root.)
- The provider contract "is the API other people write against: change it additively, never silently." (`docs/technical-requirements.md:99-101`)
- The host must not know any backend. "Every branch of the form `if (provider.id === …)` is a design failure." (`docs/technical-requirements.md:85-91`)
- "The host owns the window, the list and the editor." (`docs/README.md:44-45`)
- Never lose a note: autosave, and a note that cannot be written back safely opens read-only with a visible reason. (`docs/business-requirements.md:29-31`; `docs/README.md:40-41`)
- Honest about limits: say in the UI what cannot be represented. (`docs/business-requirements.md:42-44`)
- "Opening, editing and closing a note never needs the mouse." (`docs/business-requirements.md:82`)
- Notes on disk and the provider contract stay Markdown; the editor document is rich text, converted at both ends by `qthtml`. (`docs/decisions.md:131-154`; `docs/technical-requirements.md:14`)
- Converter answers are framed so a failure never reads as an empty note. A note is loading until its document is on screen (`setNote`'s `shown(ok)`). (`docs/decisions.md:523-556`)
- A note is unsaved until a provider says otherwise; `dirty` means text nobody has captured yet. (`docs/decisions.md:489-521`)
- The host says a note changed (`noteEdited`); the provider decides when it is written (`saveRequested`). (`docs/decisions.md:450-487`; `docs/providers.md:316-329`)
- The editor's read-only flag is derived by the session, never restored from before. (`docs/decisions.md:963-967`)
- Note bodies travel to scripts over stdin, never argv or temp paths. (`docs/security.md:53-60`; `services/markdown/qthtml/__main__.py:26-28`)
- Bound every input, including collections (counts of blocks, notes and so on). (`docs/security.md:16-40`)
- Tools are discovered; adding one does not change `Workspace.qml` or `NoteEditor.qml`. A tool is offered only where it can act. (`docs/editing-tools.md:1-13`; `docs/decisions.md:852-869`)
- A tool's edit is one transaction (one undo step). (`docs/decisions.md:748-765`)
- Native editing shortcuts are reserved and cannot be rebound. (`services/shortcuts/stroke.js:17-24`; `resolve.js:137-148`)
- Sticky Notes stay plain text with no title; plain text must remain a content type. (`docs/decisions.md:557-561`; `docs/business-requirements.md:73-74`)
- Not a rich-text word processor: no fonts, colours or sizes beyond what Markdown can carry. (`docs/business-requirements.md:59-60`)
- If a change touches the editor, run the round-trip test again; `qthtml/selftest.py` must stay green. (`docs/testing.md:765-772`)
- A Qt TextEdit moves the caret to the end on a `readOnly` change, so apply the flag while preserving caret and scroll. (`ui/NoteEditor.qml:357-375`)
- Read the document as a range, not as `text`, except for the empty case. (`docs/engine-notes.md:195-207`)

## Reusable pieces

| what | where |
|---|---|
| The session's minimal editor contract (stand-in) | `tests/transitions.qml:375-400` |
| Notice / provider-view / conflict machinery | `ui/NoteEditor.qml:136-235`, `:1868-1998` |
| Loading skeleton | `ui/NoteSkeleton.qml` (used at `NoteEditor.qml:2401-2407`) |
| Conflict review UI (title/body passages, local/remote/both) | `ui/MergeConflict.qml` |
| Drawn checkbox face and hover cursor | `ui/NoteEditor.qml:2242-2289` |
| Two-field popover form with Enter/Esc footer | `ui/editing/ToolForm.qml` (requires a Tool, `:13`); example `ui/tools/InsertLink.qml:42-87` |
| Form field style | `ui/ChromeTextField.qml` |
| One-field modal and its workspace gate | `design/controls/PromptDialog.qml`; `Workspace.qml:2083-2097`, `:2145-2148` |
| Buttons (bordered, `iconText`) | `design/controls/Button.qml` (used `NoteEditor.qml:1984-1995`) |
| Scrolling body pattern | `NoteEditor.qml:2000-2035`; `ui/ListWheel.qml` |
| Async-edit context tokens | `ui/EditContext.js` |
| Framed conversion service + process runner | `services/markdown/Markdown.qml:49-115`; `services/processes/ProcessRunner.qml` |
| Task-list grammar and round trip | `services/markdown/parse.py:72-74`; `qthtml/writer.py:295-314`; `qthtml/reader.py:362-366`; `qthtml/dialect.py:37-43` |
| Tool shortcut and context machinery | `services/shortcuts/resolve.js:10-12`, `:179-191`; `ui/editing/Tool.qml:16-21` |
| Pure `.pragma library` JS modules (for unit-testable timeline logic) | `ui/MarkdownBlocks.js`, `ui/EditContext.js`, `ui/PasteFit.js` |
| Read-only caret/scroll preservation | `ui/NoteEditor.qml:365-375`, `:1784-1789` |

## Risks

1. **`canColorText` lives on the rich editor** and feeds `ThemeService.supportsCustom` and `codeChipColour`. If the rich editor were not always instantiated, theming would change with the open note's type.
2. **`tools.actions` feeds the `KeybindingRegistry`.** A per-note rich editor would recompile shortcuts and empty the key-bindings page's tool section while a timeline is open.
3. **The type would arrive late.**
   - A per-note type is known only in the load callback, but `setNote("", "")` and `restoreDocument(draft.document)` run before it.
   - Drafts and recovery documents are editor-form snapshots, and restoring one into the wrong editor would corrupt or lose it.
4. **`stored` equality compares editor-form strings.** A non-canonical timeline snapshot either saves needlessly or, worse, skips a save. The comparison must also not match across types.
5. **Tool shortcuts get swallowed.** `runBinding` returns true for tool bindings, and `ToolRegistry.handleShortcut` consumes disabled ones. If timeline focus counts as the "editor" context, Ctrl+B, Ctrl+1 and so on are silently eaten. If the rich editor stays writable while hidden, they could edit an invisible document.
6. **Escape dismisses the overlay.** It is the app's "back" action (`goBack`). An in-pane add-event form must consume it, or be gated like `tools.panelOpen`, or Escape dismisses the overlay instead of closing the form.
7. **Tests are coupled to rich internals** through `editor.*` (`transitions.qml`, `extensions.qml`, `standalone.qml`, `audio.qml`, `EditorKeys.qml`). A split changes many test references.
8. **A third flag would be spaghetti.** `plain` is threaded through about 20 branches. Adding `timeline` the same way breaks the `CLAUDE.md` rule; the content type needs a proper seam.
9. **The toolbar row always takes its height** (sidebar alignment), so a timeline may show an empty strip.
10. **The rich editor cannot do "check all above".** A checkbox click there is Qt's own single-item toggle with no hook (the overlay has no handlers by design). Implementing the rule in the rich editor would mean intercepting Qt's click.
11. **Undo differs.** The rich editor uses Qt's undo stack plus native edit blocks. A timeline editor needs its own undo/redo for check and add, and Ctrl+Z/Ctrl+Y are reserved and routed only by the focused item.
12. **IPC assumes the rich editor.** `editorTool`, `editorCursor`, `editorPaste` and `editorUndo` are documented in `testing.md`.
13. **`wordCount` and `hoveredLink` have no defined meaning for a timeline.**
14. **Read-only is pushed by hand.** `updateReadOnly` pushes the flag from six call sites (the untracked `CODE-REVIEW-2026-10-11.md`, F15, notes this). A pane forwarding to child editors adds one more hop.
15. **Stale copies pollute greps.** `.claude/worktrees/agent-a4f19c270115b62cd/` holds an older `Workspace.qml` and docs, which show up in repo-wide greps.
16. **A stale cross-reference.** `qthtml/__main__.py:26-28` cites "docs/security.md rule 2" for stdin payloads; in the current `security.md` that rule is number 3 (`:53-60`).

## Open questions

1. How is a timeline stored in a provider body: Markdown task items (`- [x] **title** — description`), front matter, fenced JSON, or something else? Can plain-text providers (Sticky) hold one?
2. Where does a note's content type come from? Options: a provider default (today's `markdown` bool) plus a per-note `type` in `load()` results, rows or `create()`. Is it known from the row before the load, or only after?
3. Can the user change a note's type (Markdown ↔ timeline), and what happens to the content?
4. Does unchecking event k also uncheck every event below it (the mirror of "check one → check all above")?
5. What is the keyboard model, to meet the "never needs the mouse" criterion? For example: Up/Down between events, Space to check, a key for "Add new event", Enter/Escape in the form.
6. Is the event description plain text or Markdown (rich)? Can events be edited, deleted or reordered after creation?
7. What should the view bar's word count and link-hover line show for a timeline?
8. Should a focused timeline count as the "editor" key context (tool bindings eaten), or get a new context?
9. Should the rich editor stay instantiated (hidden) to keep `canColorText` and `tools.actions` stable, or should those move to the pane or Platform?
10. Is `MergeConflict`'s raw-passage view acceptable for timeline conflicts (it shows the stored body form)?
11. What does a "radiobox" check circle look like: the drawn checkbox face with a full radius, or a new design?

## Recommendations

1. Split NoteEditor into a generic note pane and type-specific editors.
   - The pane owns: title, notices, provider view, conflict review, skeleton, modified date, read-only, focus routing, toolbar row height, and the `edited` / `statusRequested` signals.
   - Each editor implements one small interface: `setNote`, `restoreDocument`, `snapshotDocument`, a body request, `viewState` / `restoreViewState`, `focusBody`, `bodyFocused`, `wordCount`, `edited`.
   - `tests/transitions.qml:375-400` already proves the session needs only that.
2. Replace the boolean `plain` with a content-type value (for example text | markdown | timeline) chosen per note. Keep the provider's `markdown: bool` as the default type, so the contract change stays additive.
3. Make the type part of the document: include it in `snapshotDocument`, drafts and `stored`, and select the editor before `setNote` / `restoreDocument`.
4. Move host-level capabilities off the rich editor: `canColorText`, the tool registry and its actions, the toolbar row height. Put them in the always-present pane, or in Platform.
5. Give the pane a "form open" flag that `Workspace.handleShortcut` and `WorkspaceActions.blocked` check, as they do `tools.panelOpen`. Have the add-event form consume Escape and Enter.
6. Extract the drawn checkbox face into a shared component used by both the rich overlay and the timeline. Put the "check everything above" rule in a pure `.pragma library` JS module, unit-tested.
7. Add a timeline real-key suite. Register it in both `tests/transition_selftest.py:18` and `CMakeLists.txt:99`.

## Note on sources not at HEAD

- `CODE-REVIEW-2026-10-11.md` is untracked (`git status`).
  - It flags `NoteSession.stored` never being pruned (F14).
  - It flags `updateReadOnly` pushing the flag from six places (F15).
  - It flags `NoteEditor`'s two near-identical `Loader`s, `:1918-1931` and `:1934-1947` (F16), and suggests a `PropsLoader`.
  - It verifies that 5887a8f's stored snapshot is taken after the editor shows the note.
- These are review opinions, not HEAD facts.
