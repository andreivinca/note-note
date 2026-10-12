# Map: session (workspace and note-session lifecycle)

HEAD `e2cdc4e` (master). Repository: `/home/andrei/Projects/note-note`. Every
citation is `file:line` at HEAD. Nothing in the repository was edited.

## Summary

`services/notes/NoteSession.qml` is the note-session controller. It owns the
open note's identity (`currentPath`), load generations (`noteLoadSeq`, the
cancellable `loadHandle`), the dirty flag, retained save drafts (`drafts`),
per-note save epochs, in-flight save counts, pending deletions, path aliases
for provisional notes, the merge-conflict review and the "what the provider
holds" snapshots (`stored`). The editor, provider lookup, version lookup and
status reporting are injected (`NoteSession.qml:3-11`, wired at
`Workspace.qml:2614-2620`). The session is duck-typed against its `editor`. A
test fake of 16 members is enough to drive it (`tests/transitions.qml:375-400`).
In the app that editor is always the single `NoteEditor { id: editor }`
declared at `Workspace.qml:2824-2886`. `NoteEditor` is the whole note pane:
tool strip, title, notices, provider views, conflict review and the rich/plain
`TextEdit` body. A note loads in one of two ways. Either it shows a retained
draft synchronously, or it asks the provider. The provider answer is guarded
twice by `ownsLoad(path, generation)`: once when it arrives and once when
`editor.setNote` says the document is on screen. Only `noteReady` and
`noteUnavailable` end a load. An edit goes `edited()` → `session.onEdited()`
→ `dirty`, then the provider's own schedule (`noteEdited`/`saveRequested`) or
the host's 1500 ms timer, then `flushSave()`. `flushSave()` snapshots the
editor (`snapshotDocument`). If the snapshot equals `stored[path]` it skips the
save. Otherwise it registers a draft, bumps the epoch, and converts with
`editor.requestMarkdown`, then calls `provider.save(path, title, body, cb,
{view, resolution})`. `finishSave` settles the draft, `stored`, the dirty
flag, the version and the conflict. The list shows a typed title at once
through `session.unsavedTitles`, a binding over `drafts` (replaced wholesale)
plus `editor.title` while dirty. `Workspace.displayTitle(row)` reads it and
`NoteList`/`SearchResults` call it through `titleFor(row)`. The content type
is per provider today. The provider's `markdown` flag is read in exactly one
place, the `plain:` binding on the editor (`Workspace.qml:2837-2840`).
`NoteEditor` then branches on `plain` for its conversion, snapshot, text
format and tools. Commands and shortcuts share one executor. `defaults.js`
entries marked `workspace: true` and manifest commands that name a
`workspaceAction` both end in `WorkspaceActions.invoke(action)`. That
dispatches to argument-less handlers with a single availability function. Key
dispatch is `Workspace.handleShortcut`, which handles modal states first, then
registry lookup by context (`page` / `search` / `editor` if `editor.bodyFocused`
/ `workspace`), then `runBinding`. The host state file (version 4) holds no
per-note document data. Drafts and `stored` live in memory only. Neither host
(`hosts/omarchy/Notes.qml`, `hosts/standalone/Main.qml`) touches the editor or
the session.

## Facts

### NoteSession: state, read-only derivation, injection

- F1 NoteSession owns document identity, load generations, drafts and save completion. UI, provider lookup and status are injected through `editor`, `providerFor`, `versionFor`, `report` — `services/notes/NoteSession.qml:3-11`
- F2 Workspace instantiates it: `editor: editor`, `providerFor: root.providerOf`, `versionFor: root.versionOf`, `report: root.reportSave` — `Workspace.qml:2614-2620`
- F3 Workspace aliases `currentPath`, `loadingNote`, `loadFailed`, `dirty` and `loadingPath` to the session — `Workspace.qml:69-77`
- F4 `writable` is `currentPath !== "" && !loadingNote && !loadFailed && !locked && conflict === null && documentEditable` — `NoteSession.qml:26-29`
- F5 `updateReadOnly()` is the only writer of `editor.readOnly` (`editor.readOnly = !session.writable`) — `NoteSession.qml:116-121`. The design rule says the flag "is derived, never put back" — `docs/decisions.md:963-969`
- F6 `lock()`/`unlock()` are held by `remove` (`NoteSession.qml:428,437`), `runRowAction` (`Workspace.qml:2116,2127`) and the ProviderLifecycle drain (`services/providers/ProviderLifecycle.qml:85-88,172-174`)
- F7 Session state maps: `stored` (L43), `savesPending` (L44), `drafts` (L47, replaced wholesale), `pathAliases` (L63), `pendingDeletions` (L64), `saveEpoch` (L36). `busy` = any save or deletion pending (L65) — `NoteSession.qml:30-65`
- F8 `resolvedPath(path)` maps a provisional path through `pathAliases`. Aliases are only ever added (L76), never deleted — `NoteSession.qml:63,68-70,76`

### (a) Ctrl+N → note created → selected → editor focused

- F9 The default binding is `{ id: "newNote", workspace: true, keys: ["Ctrl+N"], context: "notes", ... }` — `services/shortcuts/defaults.js:21`
- F10 Key entry: the body `TextEdit` and the title field forward every key to `root.shortcut(event)` → `shortcutHandler` (`ui/NoteEditor.qml:242-247,1909-1910,2111-2113`). Workspace sets `shortcutHandler: root.handleShortcut` (`Workspace.qml:2867`). The `content` item catches other keys (`Workspace.qml:2629-2634`)
- F11 `handleShortcut` order: delete confirm → row-action confirm → prompt (returns false) → palette → tool panel (false) → page `handleKey` → `shortcutRegistry.match(event, shortcutContext())` → auto-repeat guard → `runBinding` — `Workspace.qml:2135-2165`
- F12 `shortcutContext()` returns `page`, else `search`, else `editor.bodyFocused ? "editor" : "workspace"` — `Workspace.qml:2168-2176`. `bodyFocused` is `area.activeFocus` — `ui/NoteEditor.qml:72`
- F13 `runBinding`: tool → `editor.tools.execute`; command → `commandRegistry.execute`; `binding.workspace` → `workspaceActions.invoke(binding.action)` (status on error); else `keyActions[binding.action](binding)` — `Workspace.qml:2182-2203`
- F14 `WorkspaceActions.invoke(action)` runs `unavailable(action)` and then `handlers[action]()`. The handlers take no arguments: `newNote` → `host.newNote()` — `services/commands/WorkspaceActions.qml:18-34,91-98`
- F15 `unavailable()` refuses an unknown action, `blocked`/`!opened`/`closing`, an open page or providers not loaded, then checks per action (`canCreateNote`, `hasFooter("newNotebook")`, `canDeleteNote`) — `WorkspaceActions.qml:42-87`
- F16 `blocked` is `session.locked || lifecycle.busy || root.deleteConfirmOpen || root.rowActionPending !== null || root.promptPending !== null || editor.tools.panelOpen` — `Workspace.qml:2543-2548`
- F17 `WorkspaceActions.state` holds `blocked, opened, closing, pageOpen, providersLoaded, footerActions, currentPath`. A change emits `availabilityChanged`, which refreshes the palette listing — `WorkspaceActions.qml:10-16`; `services/commands/CommandRegistry.qml:35-40`
- F18 `Workspace.newNote(providerId, target)`: locked guard. With no providerId it first tries `activateFooterShortcut("newNote")`. Then `flushSave`, clear search, `newNoteDestination`, `startNewNotebook` when there is no provider/target, return if `!p.canCreate`, and `p.create(target, cb)` — `Workspace.qml:1887-1912`
- F19 `activateFooterShortcut` finds the footer action whose `shortcut` matches and activates it through `list.activateFooterAction` → `footerActionRequested` → `runFooterAction` → `provider.action(path, value, section)` — `Workspace.qml:1690-1703,1668-1688,2735-2737`; `ui/NoteList.qml:254-267`
- F20 Providers send their New Note action back into `host.newNote(id, target)`: local (`plugins/org.note-note.local/Provider.qml:275-279`), notion (`plugins/org.note-note.notion/Provider.qml:125-127`), sticky (`plugins/org.note-note.sticky/Provider.qml:92-97`), hello (`examples/hello/Provider.qml:114-116`). This is documented at `docs/providers.md:200-204`
- F21 `newNoteDestination(providerId, target)`: the explicit or active provider, target `createTargetFor(currentPath)`. Without a providerId it falls back to the first provider with `canCreate && createTargetFor("")` — `Workspace.qml:1873-1885`
- F22 Create callback: on error, status `p.name + ": " + r.error`. Otherwise `showSection(home)` if the note is filed in another tab, `choosePath(r.path)`, scroll the row into view later, then `p.hasTitle ? editor.focusTitle() : editor.focusEditor()` — `Workspace.qml:1912-1937`
- F23 The contract is `create(target, cb) → cb({ path, error })`, with no options argument. A provisional note is allowed, followed by `notePathChanged` — `docs/providers.md:350-357`; mirror `skills/note-note-plugin/references/providers.md:321`
- F24 The local provider inserts the row and rebuilds before it answers, so `rowIndexOf(r.path)` finds the row — `plugins/org.note-note.local/Provider.qml:555-575`
- F25 A sidebar "new" row emits `newRequested(target)` → `root.newNote(row.provider, target)` or `root.newNote()` — `ui/NoteList.qml:576-578`; `Workspace.qml:2726-2734`
- F26 From the palette, the built-in command `org.note-note.workspace/new-note` names `workspaceAction: "newNote"`. `CommandRegistry.execute` → `runWorkspaceAction` closes the picker, then invokes the same executor — `plugins/org.note-note.workspace/plugin.json:9-18`; `CommandRegistry.qml:149-183`

### (b) Click a note row → load → editor shows it

- F27 Row click → `root.activated(path)` (`ui/NoteList.qml:583-585`) → `onActivated` → `root.choosePath(path); editor.focusEditor()` (`Workspace.qml:2722-2725`)
- F28 `choosePath` (a user choice) sets `defaultOwed = false`, calls `rememberOpened(path)` (provider `noteOpened`, `lastNotes`, `saveState`), then `selectPath` — `Workspace.qml:1759-1765,984-1010`
- F29 `Workspace.selectPath` clears `treeCursor`, then calls `session.selectPath` — `Workspace.qml:1767-1770`
- F30 `session.selectPath` resolves aliases and refuses while locked, for the same path, or when no provider owns the path. It then calls `flushSave()`, sets `currentPath`, and runs `load(false)` — `NoteSession.qml:185-193`
- F31 `load(reload)` start: `generation = ++noteLoadSeq`, `cancelLoad()`, `loadingNote = true`, `loadFailed = false`, `loadingPath = path`, `dirty = false`, `editingView = null`. It captures `viewState()` only on a reload, then `clearNotice()`, `closeConflict()`, `documentBase = ""`, and `editor.setNote("", "")` when not reloading — `NoteSession.qml:210-227`
- F32 Draft branch: with `drafts[path]` it calls `editor.restoreDocument(draft.document)`, takes `editingView` from the draft, then `noteReady(false, "")`, `dirty = !!draft.error`, and reopens `draft.conflict`. No provider read — `NoteSession.qml:233-245`
- F33 Provider branch: `delete stored[path]`, `handle = provider.load(path, cb)`. The handle is kept only if the load is still owned and still loading, because a synchronous provider may have answered already — `NoteSession.qml:246-252,300-304`
- F34 The stale-answer guard is `ownsLoad(path, generation)`: `currentPath === resolvedPath(path) && noteLoadSeq === generation`. It is checked when the answer arrives (L253) and again in setNote's `shown` callback (L264) — `NoteSession.qml:253-255,263-266,307-309`
- F35 Answer handling: an error goes to `noteUnavailable(name + ": " + error)`. Then `loadedVersion = result.version || versionFor(...)`, `editor.documentBase = result.base`, and `editor.setNote(result.title, result.body, shown)`. A failed `shown` goes to `noteUnavailable(notDisplayable)`. A reload restores the view. Then `editingView = result.view ...` and `noteReady(result.editable === false, result.reason)` — `NoteSession.qml:256-275`
- F36 A recovered answer sets `dirty = true` and `setDraft(path, {document: editor.snapshotDocument(), view, epoch: saveEpoch[path] || 0, error: "Recovered unsaved changes", conflict})`, then reports. A conflict goes to `showConflict`. `result.retry` schedules `Qt.callLater(flushSave)` if the load is still owned and no save is in flight — `NoteSession.qml:276-292`
- F37 A normal answer sets `stored[resolved] = editor.snapshotDocument()`. A reload reports `"<name>: reloaded, changed elsewhere"` — `NoteSession.qml:293-298`
- F38 `noteReady`/`noteUnavailable` are the only load endings — `NoteSession.qml:311-331`; rule at `docs/decisions.md:547-555`
- F39 `cancelLoad()` cancels and drops `loadHandle`. `requestClose` also cancels it — `NoteSession.qml:177-183`; `Workspace.qml:355`
- F40 `NoteEditor.setNote` bumps `noteToken`. Plain, no markdown service, or an empty body takes the synchronous path. Otherwise it runs async `markdown.toHtml` with a token check, and an overtaken setNote never calls `shown` — `ui/NoteEditor.qml:282-316`
- F41 Contract: load may return `{ cancel() }`. Cancelling withdraws only a read that has not started, and every load is answered exactly once — `docs/providers.md:271-277`
- F42 The load answer is `{ title, body, editable, reason, error, base, view, recovered, conflict }` (`docs/providers.md:260`). `retry`, consumed at `NoteSession.qml:284`, is produced by `lib/notemerge/store.py:98` and is not documented in `docs/providers.md`
- F43 `reloadCurrent` runs only when not locked, not dirty and with no save in flight — `NoteSession.qml:204-208`. Triggers: open after a failed load (`Workspace.qml:303-305`), provider `noteChanged` (`Workspace.qml:758-765`), and `reconcile` on a newer listing version (`NoteSession.qml:544-555`, reached from `Workspace.reconcileNote` `1384-1394` after `rebuildRows` `1380-1381`)
- F44 `putAway()` sets `currentPath = ""` and runs `load(false)` for a lock holder. It is used by `runRowAction` (`Workspace.qml:2124-2126`) and the provider retirement in ProviderLifecycle (`ProviderLifecycle.qml:143-145`) — `NoteSession.qml:195-202`

### (c) Typing → save → saved state

- F45 Edit signals: the title `onTextEdited: root.edited()` (`ui/NoteEditor.qml:1908`). The body `onTextChanged` emits `root.edited()` unless `settingText || readOnly` (`ui/NoteEditor.qml:2171-2190`). Many editor operations also emit `edited()` (for example `ui/NoteEditor.qml:476,552,650`; `ui/editing/EditorApi.qml:58,173`)
- F46 Workspace `onEdited: root.onEdited()` → `session.onEdited()` — `Workspace.qml:2869,2253-2255`
- F47 `onEdited`: returns unless `writable`, sets `dirty = true`, then calls `provider.noteEdited(path)` if present, else restarts the host `schedule` Timer (1500 ms; it flushes only if its path is still current) — `NoteSession.qml:333-356`
- F48 Provider schedules: local is 500 ms → `saveRequested` (`plugins/org.note-note.local/Provider.qml:34-42`); LaneProvider's `savePause` is 1500 (`services/providers/LaneProvider.qml:30-45`)
- F49 `saveRequested(path)` → `root.flushSave()` only when `resolvedPath(path) === currentPath` — `Workspace.qml:744-756`
- F50 `flushSave(resolution)`: guard `dirty && writable` → provider → `document = editor.snapshotDocument()` → `isStored` short-circuit → `delete stored[path]` → `epoch++` → `setDraft(path, {document, view, epoch, error: ""})` → `dirty = false` → `loadedVersion = ""` → `countSave(+1)` → `editor.requestMarkdown(cb)` — `NoteSession.qml:471-493`
- F51 Conversion callback: re-resolve the path; on an epoch mismatch, `countSave(-1)` and drop. `!ok` → `finishSave(error "the note could not be read for saving")`. Otherwise `provider.save(path, draft.document.title, body, cb, { view: draft.view, resolution })` — `NoteSession.qml:493-506`
- F52 `NoteEditor.requestMarkdown(cb)` answers `plainText()` when plain or with no markdown service. Otherwise it calls `markdown.toMarkdown(documentHtml())` and answers `map.note`, or `("", false)` on failure — `ui/NoteEditor.qml:112-134`
- F53 `snapshotDocument()` is `{ title, body: plain ? plainText() : documentHtml(), base: documentBase }`. `restoreDocument(snapshot)` sets the title, `documentBase` and the body — `ui/NoteEditor.qml:318-332`
- F54 `finishSave`: only the draft still registered for the path decides. On error, the conflict is kept only if there are no newer edits, `draft.error` is set, and `dirty = true` if the note is current. On success, `setDraft(null)`, `stored[path] = draft.document` unless `result.merged`, and the version is adopted if current and clean. It reports error or warning, calls `countSave(-1)` last, then `showConflict` — `NoteSession.qml:509-542`
- F55 Save contract: call `cb` exactly once. A superseded save answers `{}`, an unsent one answers `{error}`, and the host counts saves per note — `docs/providers.md:282-300`
- F56 `busy` → `writesSettled` (`Workspace.qml:271-277`). `finishClose` refuses while `failureFor(ids)` or `dirty` (`Workspace.qml:366-381`). `failureFor` returns the first errored draft of those providers (`NoteSession.qml:557-564`). ProviderLifecycle uses the same check before a commit (`ProviderLifecycle.qml:115`)
- F57 `close`, `requestClose` and `dismiss` all flush — `Workspace.qml:338-343,347-364,383-389`. Missed save errors are reported on the next open — `Workspace.qml:2266-2272,295-299`
- F58 The ViewBar unsaved dot is `root.dirty || root.saveInFlight(root.currentPath)` — `Workspace.qml:2917`

### (d) No save when the body equals what the provider holds (commit 5887a8f)

- F59 `stored` is path → `{title, body}` in snapshotDocument form. It is known from a note shown as loaded and from a landed save, and forgotten as a save starts or fails — `NoteSession.qml:37-43`
- F60 `isStored` compares the strings exactly: `!!known && known.title === document.title && known.body === document.body` (`base` is ignored) — `NoteSession.qml:362-367`
- F61 Written at L294 (load shown, not recovered) and L526 (landed, non-merged save). Deleted at L251 (provider load start) and L485 (flush start). Moved in `replacePath` (L77-83). Never pruned otherwise — `NoteSession.qml`
- F62 The check runs before any conversion: an equal snapshot sets `dirty = false` and returns — `NoteSession.qml:480-484`. Test `unchangedNoteUnsent` — `tests/EditorKeys.qml:333-360` (registered at L3331)

### (e) Delete

- F63 Ctrl+D (`defaults.js:23`) → workspace action `deleteNote` → `host.requestDelete(host.currentPath)` (`WorkspaceActions.qml:31-33`). A row-menu item with `command: "deleteNote"` also leads to `requestDelete(row.path)` (`Workspace.qml:2064-2065`)
- F64 `requestDelete`: locked guard, `canDelete`, sets `deletePath`, opens the ConfirmDialog — `Workspace.qml:1996-2009,3001-3017`
- F65 `confirmDelete`: picks the next note (upward from the row, else the first), then `session.remove(path, cb)`. On success: `selectPath(next)` and `editor.focusEditor()` — `Workspace.qml:2016-2052`
- F66 `session.remove`: refuses a deletion already pending, a locked session or a missing provider. Recovery is the editor snapshot (current note) or the draft document; it computes `unsaved`, runs `cancelPendingSave`, records `pendingDeletions[path]`, locks, then calls `provider.remove`. The callback runs `finishDeletion` unless pending, sets `dirty = !!error && unsaved`, unlocks, and calls back — `NoteSession.qml:402-440`
- F67 `cancelPendingSave` bumps the epoch and drops the draft, so a conversion in flight is discarded — `NoteSession.qml:392-400,495-498`
- F68 `finishDeletion`: on error, restores the unsaved draft and reports; always clears `pendingDeletions[path]`. It is wired to the provider `noteDeletionFinished` signal — `NoteSession.qml:447-469`; `Workspace.qml:778-782`

### (f) Conflict view

- F69 `showConflict(path, conflict)`: only for the current note with no save in flight. Sets `session.conflict`, marks read-only, and calls `editor.showConflict({conflict, remoteName, retry, continueEditing, resolve})` — `NoteSession.qml:135-167`
- F70 `retry` → `closeConflict(); flushSave()`. `continueEditing` → `closeConflict()`. `resolve(choices)` → `closeConflict(); flushSave({ id: conflict.id, choices })` — `NoteSession.qml:146-165`
- F71 `closeConflict` clears `session.conflict`, calls `editor.clearConflict()` and `updateReadOnly()`. Every load closes it — `NoteSession.qml:169-175,223`
- F72 `NoteEditor.showConflict` installs a fresh `conflictReview` and focuses it. `conflictLoader` sits in the sheet, hidden while a notice covers it, and survives `clearNotice` — `ui/NoteEditor.qml:189-211,1933-1948`
- F73 MergeConflict is presentation only. Each part is labelled `"Title"` or `"Passage"` and shows base/local/remote in `TextEdit.PlainText`. `complete` holds once every part is local/remote/both. Buttons: Save resolved note / Retry merge / Continue editing — `ui/MergeConflict.qml:6-20,62-130,133-169`
- F74 Conflict parts are `{id, field, base, local, remote}`, with choices `local`/`remote`/`both`/`{text}`. Bodies may be plain text or Markdown and merge by lines — `lib/notemerge/README.md:8-27`
- F75 `Workspace.open()` clears notices (`Workspace.qml:310-314`) but not the review — `docs/decisions.md:969-972`

### Titles (commit 7162589)

- F76 `unsavedTitles` binding: every draft's `document.title`, plus `editor.title` for the current note while `dirty` — `NoteSession.qml:48-62`
- F77 `drafts` is replaced wholesale through `setDraft` so that bindings follow it. `finishSave` mutates `draft.conflict` and `draft.error` in place — `NoteSession.qml:45-47,369-378,516-518`
- F78 `displayTitle(row)`: the unsaved title when `row.hasTitle !== false && row.path in session.unsavedTitles`, else `row.title`, else a preview-derived five-word title (with the Markdown checkbox mapping `[x]`→"☑ ", `[ ]`→"☐ "), else "Untitled" — `Workspace.qml:1302-1324`
- F79 `titleFor: root.displayTitle` is passed to NoteList (`Workspace.qml:2721`). NoteList and SearchResults bind `title: root.titleFor(modelData)` — `ui/NoteList.qml:82-85,350,454`; `ui/SearchResults.qml:28-29,110`
- F80 `sidebar.js row()` carries `hasTitle: provider.hasTitle !== false` (per provider) and no type field — `services/notes/sidebar.js:24-31`
- F81 Search title matching uses the provider's row title and preview only, never unsaved titles — `services/notes/sidebar.js:19-22,63-65`

### Text-format and editor assumptions in Workspace/NoteSession (Q2)

- F82 The only reader of `provider.markdown` is `plain: { var p = root.providerOf(root.currentPath); return p ? !p.markdown : false }` — `Workspace.qml:2837-2840` (repo grep)
- F83 Other per-provider editor flags: `canImages` (L2831-2834), `hasTitle` (L2841-2844) and `enabledTools` (L2845-2848) — `Workspace.qml`
- F84 The Markdown service and colour tokens feed the editor: "Markdown on disk, rich text in the editor: everything the note pane shows or saves passes through here" — `Workspace.qml:110-123,2424-2433,2829`
- F85 Key actions `paste` and `pastePlain` return `editor.plain || editor.readOnly ? false : editor.paste()` — `Workspace.qml:2245-2250`
- F86 ViewBar reads `editor.readOnly`, `hoveredLink`, `wordCount` and `!editor.showingNotice` — `Workspace.qml:2916-2921`
- F87 The sidebar header aligns to `editor.toolbarHeight` and `toolbarRowHeight` — `Workspace.qml:2714-2715`
- F88 `shortcutRegistry.tools: editor.tools.actions` (L2554); `themeService.supportsCustom: editor.canColorText` (L2520); `codeChipColour` depends on `editor.canColorText` (L122-123) — `Workspace.qml`
- F89 Notices and provider views go through `editor.showNotice`, `showView` and `clearNotice` (Microsoft sign-in device code, provider setup) — `Workspace.qml:313,506-552,729-740`
- F90 IPC helpers `editorTool`, `editorPaste`, `editorUndo` and `editorCursor` (L1720-1740), and `debugState` (L1576-1619), read NoteEditor internals — `Workspace.qml`
- F91 `contextState.editorWritable: !!root.currentPath && !editor.readOnly` — `Workspace.qml:2578-2583`
- F92 `editor.focusEditor()` is called after open, page close, delete, cancel, the palette fallback, a row click and acceptSearch — `Workspace.qml:326,441,2013,2049,2079,2090,2220,2644,2724`. `focusTitle()` is called after create — `Workspace.qml:1932-1936`
- F93 NoteSession calls these editor members: `title` (L59), `readOnly` (L120), `showConflict`/`clearConflict` (L143,173), `viewState`/`restoreViewState` (L221,272), `clearNotice` (L222), `documentBase` (L224,262), `setNote` (L226,263), `restoreDocument` (L237), `snapshotDocument` (L278,294,420,480), `requestMarkdown` (L493) — `NoteSession.qml`
- F94 The Markdown-specific vocabulary in the session: the name `requestMarkdown` (L493), the error "the note could not be read for saving" (L500), and `documentBase` (an image-base concept) — `NoteSession.qml`

### NoteEditor pane structure (where a switch could sit)

- F95 NoteEditor holds the tool strip (`1826-1833`), then one `sheet` Column (`1843-2399`) with the modified caption (`1857-1866`), the title field (`1890-1914`), `customLoader` (provider views, `1918-1931`), `conflictLoader` (`1934-1948`), the notice column (`1950-1998`) and the body `flick`/`TextEdit` (`2000-2398`). The skeleton overlays the sheet while loading (`2401-2407`) — `ui/NoteEditor.qml`
- F96 `showingNotice = noticeShown || conflictReview !== null`, and `noticeShown` includes provider `customView` — `ui/NoteEditor.qml:163-167`
- F97 The title is visible when `!showingNotice && hasTitle` and enabled when `hasNote && !readOnly`. The body flick is visible when `!showingNotice` — `ui/NoteEditor.qml:1894-1895,2002`
- F98 The tool strip is gated by `editing.writable`, which is `host.hasNote && !host.readOnly && !host.plain && !host.showingNotice` — `ui/NoteEditor.qml:152-155`; `ui/editing/EditorApi.qml:13`
- F99 `textFormat: root.plain ? TextEdit.PlainText : TextEdit.RichText` — `ui/NoteEditor.qml:2075`
- F100 `viewState()` is `{cursor, scroll}` of the TextEdit. `focusEditor()` is `area.forceActiveFocus()`. `wordCount` is counted from `area` — `ui/NoteEditor.qml:1779-1797,377`
- F101 `objectName: "noteEditor"` (`Workspace.qml:2826`) is used by tests (`tests/transitions.qml:133`, `tests/extensions.qml:405`, `tests/standalone.qml:113`). `"noteBody"` is used by many tests (for example `tests/EditorKeys.qml:405`, `tests/audio.qml:225`)

### Session test seam

- F102 Fake editor for the session: `title, body, documentBase, readOnly, conversions, conflictReview, cursorPosition(), setCursorPosition(), viewState(), restoreViewState(), clearNotice(), showConflict(), clearConflict(), setNote(t,b,shown), snapshotDocument(), restoreDocument(), requestMarkdown(cb)` — `tests/transitions.qml:375-400`
- F103 Session suites `mergeCases`, `sessionCases` and `unsavedTitleCases` (`tests/transitions.qml:424-578`) are run at `2004-2035` (and with `--notes`: `tests/transition_selftest.py:33`; `docs/testing.md:184`)
- F104 The real-editor session harness is `quietProvider`/`quietSession`/`quietSave` — `tests/EditorKeys.qml:300-331`

### Provisional identity

- F105 `replacePath(previous, next, view)` migrates the alias, `saveEpoch`, `stored`, `drafts`, `savesPending`, `pendingDeletions`, `loadingPath`, `currentPath` and `editingView`. It is wired from `notePathChanged`, together with `replaceRememberedNote` and `deletePath` — `NoteSession.qml:72-114`; `Workspace.qml:767-776`

### Commands and shortcuts (Q4)

- F106 Built-in commands are manifest entries in `plugins/org.note-note.workspace/plugin.json:8-60` (new-note, new-notebook, open-settings, toggle-sidebar, delete-note, each a `workspaceAction`)
- F107 A manifest command names a handler or a workspaceAction, not both. `workspaceAction` is checked only against `ACTION_ID = [a-z][a-zA-Z0-9]{0,63}` — `services/extensions/manifest.py:26,62-72`
- F108 `CommandRegistry.unavailable`: extensions availability, then `requires`, then `workspaceActions.unavailable(...)` — `CommandRegistry.qml:55-64`. Requirements are `hasDocument`, `editorWritable` and `settingsClean`; unknown names fail closed — `CommandRegistry.qml:18-24,42-53`
- F109 `CommandApi.workspace.invoke(action)` allows at most one hand-off per invocation. There is no editor interface for commands — `services/commands/CommandApi.qml:43-60`; `docs/commands.md:45-47,61-67`
- F110 `resolve.js addTargets`: every default becomes `app/<id>` (carrying `workspace`, `parameters`, `protected`); tools become `tool/<id>` in the `editor` context. A command aliases `app/<workspaceAction>` when that app action has `workspace: true`, else it gets its own `notes` target — `services/shortcuts/resolve.js:66-93`
- F111 Scopes: `application`→workspace,editor,search,page; `notes`→workspace,editor,search; `editor`, `search`, `page` and `workspace` are single scopes — `resolve.js:10-12`
- F112 Plugin and user bindings need Ctrl/Alt/Meta or an F-key. Reserved: `ctrl+a/c/x/v`, `ctrl+shift+v`, `ctrl+z`, `ctrl+shift+z`, `ctrl+y`, `ctrl+insert`, `shift+insert`, `shift+delete`. App defaults may use bare keys (the search context's Down/Up/Enter) — `resolve.js:137-148`; `stroke.js:19-20,105-112`; `defaults.js:10-12`
- F113 Same-priority conflicts in overlapping contexts lose the binding, with a diagnostic — `resolve.js:225-259`; `docs/commands.md:166-171`
- F114 `KeybindingRegistry` compiles once (`compiled`), and `match` is one lookup `context + "/" + signature`. `helpText` feeds the Key bindings page — `services/shortcuts/KeybindingRegistry.qml:12-18`
- F115 A `workspace` binding passes only `binding.action` to `invoke` (no parameters), whereas non-workspace app actions receive `binding` (for example `selectTab` uses `binding.parameters.tab`) — `Workspace.qml:2192-2202,2235-2240`; `defaults.js:30-33`
- F116 The selftest pins exactly the five built-in workspace commands — `services/extensions/selftest.py:44-47`. Docs list the supported action IDs at `docs/commands.md:61-62` and `skills/note-note-plugin/references/commands.md:31`
- F117 Notes-context bindings active while any notes view has focus: Ctrl+Up/Down/J (move note), Ctrl+Left/Right (tree), Ctrl+Tab, Ctrl+E, Escape (back → dismiss or focus search), Ctrl+N, Ctrl+Shift+N, Ctrl+D, Alt+1..9 — `defaults.js:9-23,30-33`

### State file, search, hosts, misc

- F118 `writeState` (version 4) writes `detached`, `active`, `lastNotes`, `providers` (plus optional `listWidth`, `listCollapsed`). It holds no per-note document data — `Workspace.qml:2295-2317`. `loadState` trusts `lastNotes` only as a map of strings — `Workspace.qml:2340-2350`
- F119 Accepted saves finish after close and are in memory only — `docs/decisions.md:360-369`; `docs/business-requirements.md:53-56`
- F120 `searchLanding` selects the first matching note with `selectPath` (shown, not chosen), which flushes the current note — `Workspace.qml:1502-1523`. Content search calls `provider.search` after a 350 ms debounce with generation guards — `Workspace.qml:1244-1300,2602-2606`
- F121 The Omarchy host subclasses Workspace (`supportsOverlay`, `contentHost`) and inherits every shell-call method. The standalone host embeds `App.Workspace` (objectName `workspace`) and handles close. Neither references the editor or the session — `hosts/omarchy/Notes.qml:4-35`; `hosts/standalone/Main.qml:24-60`
- F122 Every root function is IPC-callable with exactly one argument — `docs/testing.md:111-127`
- F123 `PromptDialog` has a single field. `askName`/`submitPrompt`/`cancelPrompt` drive it, and `handleShortcut` yields while it is open — `design/controls/PromptDialog.qml:8-104`; `Workspace.qml:2082-2097,2143-2145,3037-3055`
- F124 `ConfirmDialog.handleKey` owns Escape, Left/Right/Tab and Enter while open — `design/controls/ConfirmDialog.qml:20-41`
- F125 The checkbox face (rounded box with a drawn tick, accent fill when checked) is inline in NoteEditor's `checkBoxes` Repeater — `ui/NoteEditor.qml:2219-2291`
- F126 notemerge aligns entry labels independently of checkbox states and treats checking a deleted item as a conflict — `lib/notemerge/README.md:8-21`
- F127 NoteSummary shows title, date and preview only, with no icon for note rows — `ui/NoteSummary.qml:6-58`; `ui/NoteList.qml:447-461`
- F128 Provider flags: sticky `markdown: false`, `hasTitle: false`; local, notion and onenote are `markdown: true`, `hasTitle: true`; onenote declares `tools` — `plugins/org.note-note.sticky/Provider.qml:14-19`; `plugins/org.note-note.local/Provider.qml:20-26`; `plugins/org.note-note.notion/Provider.qml:17-22`; `plugins/org.note-note.onenote/Provider.qml:19-35`

## Integration points

| Where | What changes | Why |
|---|---|---|
| `services/notes/NoteSession.qml:13-36` | Hold the open note's content type (one property), reset at load start (`210-227`), set before `editor.setNote` / `restoreDocument` | The type decides the body component and its parse/serialize. Today `plain` is per provider and bound to `currentPath` |
| `NoteSession.qml:233-245` | Restoring a draft must set the type from `draft.document` before `restoreDocument` | Drafts are restored with no provider read. A wrong component would render, and autosave would write the wrong format |
| `NoteSession.qml:252-300` | Read the type from the load answer (new additive field) before `setNote` at L263. The recovered snapshot (L278) must carry it | The type is known only when the answer arrives, unless rows carry it |
| `NoteSession.qml:471-506` | `snapshotDocument` carries the type and a canonical body. `requestMarkdown` becomes a per-type body serializer with the framed `(body, ok)`. Optionally pass the type in `provider.save` options | isStored equality, draft retention and save payload |
| `NoteSession.qml:362-367` | Decide whether the type takes part in `isStored` | Exact-equality no-op save |
| `NoteSession.qml:402-469` | Deletion recovery carries the type through the snapshot | A failed delete restores the draft |
| `NoteSession.qml:72-114` | Any new path-keyed map must be migrated in `replacePath` | Provisional to permanent identity |
| `NoteSession.qml:53-62` | Keep `title` on whatever object the session holds as `editor` | unsavedTitles reads `session.editor.title` |
| `Workspace.qml:2824-2886` | Replace the provider-level `plain:` (2837-2840) with the session's per-note type. Revisit `hasTitle`, `enabledTools` and `canImages` per type | The single place the content type enters the editor |
| `ui/NoteEditor.qml:1843-2399` | A type-switched body Loader beside customLoader/conflictLoader/flick. `setNote`, `snapshotDocument`, `restoreDocument`, `requestMarkdown`, `viewState`, `restoreViewState`, `focusEditor`, `bodyFocused` and `wordCount` dispatch by type | Least disturbance to Workspace (about 50 `editor.*` references) and keeps notices, conflict review, title and tool-strip alignment |
| `Workspace.qml:1873-1938` | `newNote` / `newNoteDestination` take a type, filter providers that support it, and pass the type to `p.create` (options). Per-type focus after create (1932-1936) | Typed creation; the fallback provider must support the type |
| `services/commands/WorkspaceActions.qml:12-14,18-34,42-48,63-87` | Handlers and availability for `newTimeline` and `addEvent` (or similar). Add the current note type / writable to `state` | One executor for palette, keys and commands; listings follow `state` |
| `services/shortcuts/defaults.js:7-28` | New `workspace: true` entries with non-conflicting keys | Keyboard access and help page |
| `plugins/org.note-note.workspace/plugin.json:8-60` | New command entries naming the new `workspaceAction`s | Palette entries alias the app actions |
| `services/extensions/selftest.py:44-47` | Update the pinned built-in commands | Test asserts the exact set |
| `docs/commands.md:49-77`; `skills/note-note-plugin/references/commands.md:31,170` | List the new action IDs and their availability | Documented contract |
| `Workspace.qml:2135-2176` | Add a modal pending state for a timeline event form (if modal); optionally a context or `handleKey` hook for a focused timeline | Escape and Enter must reach the form; notes-context keys fire while the timeline has focus |
| `Workspace.qml:2543-2548` | Include an open event form in `blocked` | Workspace actions must not run over an open form |
| `Workspace.qml:2578-2583`; `CommandRegistry.qml:20-24` | Optional new requirement name (for example a timeline note writable) | Command `requires` fails closed for unknown names |
| `Workspace.qml:1302-1324` | Preview fallback is Markdown-checkbox specific | A titleless timeline note's preview |
| `services/notes/sidebar.js:24-31` | Optional per-note type on rows (icon, early knowledge) | Rows are JSON-compared before reassigning (`Workspace.qml:1359`) |
| `ui/NoteSummary.qml`; `ui/NoteList.qml:447-461` | Optional type icon on note rows | Distinguish note kinds in the list |
| `Workspace.qml:2888-2927` | wordCount and countVisible per type | `editor.wordCount` counts the TextEdit |
| `Workspace.qml:2245-2250` | `paste`/`pastePlain` guard per type | They call into the TextEdit body |
| `Workspace.qml:1576-1619` | Add the type to `debugState` | IPC verification |
| `docs/providers.md:41-59,257-357` and the skills mirror | Additive: supported content types, `type` in the load answer, options in `create`, document `retry` | The contract is the API others write against |
| `ui/MergeConflict.qml:62-130` | Type-aware presentation, or accept raw serialized passages | A timeline conflict would show its storage text |
| `tests/transitions.qml:375-400,424-578`; `tests/EditorKeys.qml:300-360` | Fake editor gains a type; cases for type switches, drafts, recovery, no-op save | Session guards are tested with delayed callbacks |
| `Workspace.qml:2614-2620` | Only if a facade replaces `editor` for the session | Injection point |

## Constraints

- No `if (provider.id === "…")` in the host: the host must not know any backend or path format — `docs/technical-requirements.md:85-91,105-106`
- The provider contract changes additively, never silently — `docs/technical-requirements.md:99-101`
- Never lose a note. A note that cannot be written back safely opens read-only with a visible reason — `docs/business-requirements.md:29-31`; `docs/decisions.md:660-667`; `docs/README.md:38-45`
- `editor.readOnly` is derived only by the session (`updateReadOnly`) — `docs/decisions.md:963-969`
- A note is unsaved from keystroke until the provider says otherwise. One mark spans the conversion, and `dirty` means uncaptured text — `docs/decisions.md:489-521`
- A converter failure is never an empty note. A failed out-conversion sends nothing, and a failed in-conversion holds the note read-only — `docs/decisions.md:523-555`
- The host says a note changed and the provider says when it is written (`noteEdited`/`saveRequested`). The host default is 1500 ms. The host keeps flush-on-switch/close and drop-on-delete — `docs/decisions.md:450-487`; `docs/providers.md:316-329`
- A note is loading until its document is on screen. `noteReady`/`noteUnavailable` are the only endings — `docs/decisions.md:547-555`
- The conflict review is the session's own. Notices come and go over it — `docs/decisions.md:963-972`
- Accepted saves finish even after close (in memory only), and failures are reported once — `docs/decisions.md:360-369`
- Every load is answered exactly once. Cancel withdraws only a read that has not started — `docs/providers.md:271-277`
- Save callbacks: exactly once; a superseded save answers `{}`, an unsent one `{error}` — `docs/providers.md:282-300`
- The sidebar model is replaced wholesale and only when different — `docs/technical-requirements.md:167-168`; `Workspace.qml:1349-1362`
- Plugins never receive the workspace. Commands reach it only through `workspace.invoke` — `services/commands/WorkspaceActions.qml:3-5`; `docs/commands.md:45-47`
- Unknown command requirements fail closed — `docs/commands.md:99-103`
- Plugin and user shortcuts need modifiers or F-keys, native editing keys are reserved, and same-priority conflicts disable a binding — `docs/commands.md:128-136,166-171`
- Bound every input at read time. The state file is capped at 1 MiB — `docs/security.md:16-39`; `Workspace.qml:264`
- The two contract docs are mirrored for plugin authors — `docs/providers.md`, `skills/note-note-plugin/references/providers.md`, `docs/commands.md`, `skills/note-note-plugin/references/commands.md`
- Code style: braces on every if/else/for/while with the body on its own line; no hacks or workarounds; do the proper fix even if it touches more code — `CLAUDE.md`
- Testing checklist for a UI change (lint, round trip when touching the editor) — `docs/testing.md:763-775`

## Reusable

- NoteSession's load and save state machine (generation guards, drafts, epochs, `stored`, conflict, deletion recovery) is type-agnostic as long as the editor contract is honoured — `services/notes/NoteSession.qml:185-542`
- The duck-typed editor contract proven by the test fake — `tests/transitions.qml:375-400`
- `noteReady`/`noteUnavailable` as the only load endings — `NoteSession.qml:311-331`
- Provider-owned save scheduling (`noteEdited`/`saveRequested`, LaneProvider Timer) — `services/providers/LaneProvider.qml:30-45`
- One executor for palette, keys and commands: `WorkspaceActions` + `defaults.js workspace:true` + manifest `workspaceAction` aliasing — `WorkspaceActions.qml`; `resolve.js:84-88`
- The `askName`/`PromptDialog` modal pattern with `promptPending` gating (single field; title+description needs a two-field variant) — `Workspace.qml:2082-2097`; `design/controls/PromptDialog.qml`
- `ConfirmDialog.handleKey` / `TextPage.handleKey` patterns for components that claim keys before the registry — `design/controls/ConfirmDialog.qml:20-41`; `Workspace.qml:2153-2156`
- Loader-in-sheet with props assigned on load (customLoader, conflictLoader) as a template for a type body loader — `ui/NoteEditor.qml:1918-1948`
- Checkbox face drawing (rounded box with tick, accent) — `ui/NoteEditor.qml:2219-2291`
- Markdown task-list format plus notemerge's checkbox-aware alignment, if a timeline serializes to a checklist — `lib/notemerge/README.md:8-21`; preview mapping `Workspace.qml:1316-1317`
- `setDraft`-style wholesale map replacement for bindable state — `NoteSession.qml:369-378`
- `unsavedTitles` + `displayTitle` + `titleFor(row)` for typed titles — `NoteSession.qml:48-62`; `Workspace.qml:1302-1324`
- IPC: any new root function is shell-callable (one argument) — `docs/testing.md:111-127`
- Session test harnesses: `transitions.qml` (fake editor, delayed callbacks) and `EditorKeys.qml` (real editor, `quietSession`) — `tests/transitions.qml:375-578`; `tests/EditorKeys.qml:300-360`

## Risks

- **Type known late.** `load()` blanks the editor with `setNote("", "")` before any answer (`NoteSession.qml:225-227`), and the provider answer is the first time a per-note type could be known (`NoteSession.qml:252-263`). The component switch must happen before `setNote` or `restoreDocument`, and must respect the noteToken "newest wins" race (`ui/NoteEditor.qml:260,295,308-310`).
- **Replacing NoteEditor at Workspace level.** About 50 `editor.*` references would be orphaned: notices (including the Microsoft device-code sign-in), provider views, the conflict review, `tools.actions` for the keybinding registry, `tools.panelOpen` in `blocked`, header heights, `canColorText` for themes, ViewBar, IPC and `debugState` (`Workspace.qml:122,313,506-552,729-740,1576-1619,1720-1740,2150,2175,2184,2520,2547,2554,2714-2715,2916-2921`).
- **Canonical body.** `isStored` uses exact string equality (`NoteSession.qml:362-367`). A timeline snapshot body must be canonical, or the no-op check will either always save or wrongly skip a save.
- **Drafts must carry the type.** Drafts, recovered drafts and deletion-recovery documents are editor snapshots (`NoteSession.qml:278,420,488`). If one lacks the type it restores into the wrong body, and autosave then writes the wrong format.
- **requestMarkdown semantics.** The session converts via `requestMarkdown` (`NoteSession.qml:493`). A timeline serializer must keep the framed `(body, ok)` answer so that a failure cannot write an empty note (`docs/decisions.md:523-545`).
- **Provider support.** Sticky is plain/titleless, Notion refuses what it cannot round-trip, and OneNote's writer refuses some constructs (`docs/decisions.md:557-561,660-697`). A "New timeline" must not be offered where it cannot be stored.
- **Notes-context keys while the timeline has focus.** Escape → `back` (dismiss/focus search), Ctrl+Up/Down → change note, Ctrl+E, and so on (`defaults.js:13-23`). Bare keys cannot be claimed by plugin or user bindings (`resolve.js:141-146`).
- **Shortcut context.** `shortcutContext()` reports `editor` only for `area.activeFocus` (`Workspace.qml:2175`; `ui/NoteEditor.qml:72`). A focused timeline counts as `workspace`, so editor-context bindings (paste, tool shortcuts) do not apply there.
- **Conflict view.** MergeConflict shows raw stored passages as plain text (`ui/MergeConflict.qml:90-104`). A timeline conflict would show its serialization.
- **Preview fallback.** `displayTitle`'s preview fallback maps Markdown checkboxes (`Workspace.qml:1316-1317`). A titleless timeline stored as a checklist would show its first event.
- **Unsaved titles and search.** Unsaved titles are not searchable until the save lands (`services/notes/sidebar.js:19-22`).
- **Edits while not writable.** `session.onEdited` ignores edits when not writable (`NoteSession.qml:333-336`). A timeline that mutates its model while read-only or loading would diverge from what is saved. It needs the `settingText`/`readOnly` guard NoteEditor has (`ui/NoteEditor.qml:2185-2189`).
- **Test dependencies.** Tests depend on `objectName` `noteEditor` and `noteBody`, and on `editor.tools.editor.textArea` (`tests/extensions.qml:405-409`). Moving the TextEdit inside a Loader could break `findChild` lookups.
- **Existing session hazards (verified at HEAD).** An untracked `CODE-REVIEW-2026-10-11.md` also flags them, but that file is not part of HEAD:
  - Path aliases are only added, never removed (`NoteSession.qml:76`).
  - `runRowAction` calls `rowAction` right after `flushSave`, whose save starts only after an async conversion (`Workspace.qml:2115-2117`; `NoteSession.qml:493`).
  - `stored` keeps a snapshot for every note opened (`NoteSession.qml:294,526`).
  - The read-only derivation relies on every transition calling `updateReadOnly` (`NoteSession.qml:119-121`).

  New per-note state must not deepen these.
- **Workspace-action availability.** `WorkspaceActions.state` lacks note-type and writability inputs (`WorkspaceActions.qml:12-14`). An `addEvent` action's palette availability would go stale unless they are added.

## Open questions

- Is a note's content type fixed at creation, or can a note be converted (for example Markdown to timeline)? If it can, how do `stored`/`isStored` and the save options carry the change?
- Is the type learned from the listing rows (provider `sections` rows), from the load answer, or both? Rows would let the list show an icon and let the editor switch before the answer arrives.
- What is the storage form of a timeline per provider: a Markdown task list, front matter (for example `type: timeline`), or a provider-specific body? Does `body` stay a string in `load`/`save`?
- Should "New timeline" be offered through provider footer actions (a new footer `shortcut` name such as `newTimeline`, `docs/providers.md:200-204`), as a host-only workspace action, or both? `host.newNote(id, target)` has no type parameter today.
- Is the "Add new event" form modal at workspace level (like PromptDialog, extended to title + description) or inline in the timeline body? This decides the `handleShortcut`/`blocked` gating.
- Does the timeline need registry-visible key bindings (shown on the Key bindings page) or local key handling only?
- Unchecking semantics: the user specified "check one → check all above". Behaviour on uncheck (uncheck all below? only that one?) is not specified.
- How should merge conflicts on timeline notes be presented, given that MergeConflict shows raw passages?
- Should timeline notes share the title field (and `hasTitle` per provider), and is word count meaningful for them?
- `result.retry` (`NoteSession.qml:284`; `lib/notemerge/store.py:98`) is undocumented in `docs/providers.md`. Should it be documented along with any new load fields?
- `newNote` calls `editor.focusTitle()` synchronously after `choosePath` while the load may still be pending. The editor is then read-only and the title field is disabled (`ui/NoteEditor.qml:1895`). Whether focus lands for asynchronous providers was not verified here.

## Recommendations

- Keep `session.editor` as the NoteEditor pane and put the type switch inside its sheet where `flick` sits (`ui/NoteEditor.qml:2000`), as a sibling of `customLoader`/`conflictLoader` (`1918-1948`). NoteEditor's session-facing API (`setNote`, `snapshotDocument`, `restoreDocument`, `requestMarkdown` or its renamed successor, `viewState`, `restoreViewState`, `focusEditor`, `bodyFocused`, `wordCount`) then dispatches by type. Every Workspace `editor.*` use, the notices, the conflict review, the title and the toolbar alignment stay valid. If NoteEditor's size is a concern, split it properly into a pane plus per-type bodies instead of growing conditionals.
- Hold the open note's content type in NoteSession as a single property. Thread it through `snapshotDocument()` (so `draft.document`, recovered drafts and deletion recovery carry it) and set it before `editor.setNote`/`restoreDocument` in all three load branches (`NoteSession.qml:233-245,252-275`). Do not add a separate path-keyed type map: drafts already carry their document, and `replacePath` would otherwise need another migration.
- Replace the provider-level `plain:` binding (`Workspace.qml:2837-2840`) with the per-note type. Keep the provider `markdown: bool` as the default type for providers that declare no types, so the contract change stays additive (`docs/technical-requirements.md:99-101`).
- Make typed creation explicit and additive: `create(target, cb, options)` mirroring `save`'s options, and `host.newNote(providerId, target, type)` so that the provider footer route keeps the type. Make `newNoteDestination` and `WorkspaceActions.canCreateNote` filter by type support.
- Add `newTimeline` and `addEvent` (names illustrative) as workspace actions. Each needs a `defaults.js` entry with `workspace: true`, a handler and availability in `WorkspaceActions` with the inputs added to `state`, a `plugin.json` command, the docs/commands.md and skills mirror, and the `services/extensions/selftest.py` pin.
- Rename or generalize `requestMarkdown` into a per-type body serializer that keeps the framed `(body, ok)` answer, and keep `isStored` on a canonical body form.
- Extend `tests/transitions.qml`'s fake editor with a type and add session cases. Cover A(markdown) → B(timeline) → A load races, restoring a timeline draft, a recovered timeline, the no-op save on a timeline, and deletion recovery of a timeline.
