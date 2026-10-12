# Map: provider contract and capability plumbing (HEAD e2cdc4e)

Area: the provider contract (docs/providers.md and the skill mirror), the capability
flags providers declare, and every place the host (Workspace.qml, NoteSession.qml,
sidebar.js, NoteEditor bindings) reads them or calls the create/load/save surface.
All line numbers are at HEAD e2cdc4e. Nothing in the repository was modified.

## Summary

The format of a note is decided per provider, never per note. Each provider declares
`readonly property bool markdown` (plus `hasTitle`, `canImages` and optionally `tools`)
on its QML instance. The host reads these live off the provider that owns the open
note's path: Workspace.qml:2831-2848 binds the editor's `canImages`, `plain` (=`!p.markdown`),
`hasTitle` and `enabledTools` to `root.providerOf(root.currentPath)`. `plain` is the one
switch the `markdown` flag drives. It decides whether the editor converts Markdown to and
from HTML (setNote, requestMarkdown, snapshotDocument). It also decides the TextEdit
textFormat, paste behaviour, every block-editing helper and decorations, and through
EditorApi.writable whether any toolbar or tool runs at all. Nothing else reads `markdown`:
sidebar.js, previews, search and NoteSession never look at it. `hasTitle` reaches the
editor's title field, the focus choice after create, and (through sidebar.js row()) the
bold first line in the list and search results. `tools` and `canImages` gate the toolbar,
the tool shortcuts and the rich and image paste.

Creation has exactly one call site, `p.create(target, cb)` in Workspace.newNote
(Workspace.qml:1912). Every entry point funnels into newNote(providerId, target):
- footer actions (`action()` -> `host.newNote(id, target)`)
- Ctrl+N and the palette's New Note (WorkspaceActions -> newNote() -> the footer row
  marked `shortcut: "newNote"`, else createTargetFor)
- rows of kind `new`
- createSection's `target`

`target` is an opaque provider string such as "section:<key>", "parent:<id>" or "new".
There is no options channel: create takes two arguments, host.newNote two, and
NoteList.newRequested one string. The host handles `cb({path})` this way: status on
error; switch to the note's tab; choosePath (remember, then session.selectPath -> load);
scroll; focus the title only if `p.hasTitle`. Provisional notes (OneNote) answer at once
and later emit `notePathChanged(previous, next, view)`, which NoteSession.replacePath
honours without reloading.

The load answer is consumed in exactly one place, NoteSession.load (NoteSession.qml:246-300).
It reads error, version, base, title, body, view, editable, reason, recovered, conflict
and retry, and calls `editor.setNote(title, body, shown)`. A draft (NoteSession.drafts)
bypasses load entirely through `editor.restoreDocument(draft.document)`. OneNote's script
already returns `markdown: true` per page (onenote.py:1380,1387), and nothing reads it.

Rows pass through a whitelist (sidebar.js:24-31). It copies provider, notebook, kind,
path, title, hasTitle (provider-level), preview, icon, reorder, level, expanded, count,
menu and modified. Any other field a provider emits is silently dropped, so a provider
could start emitting `type` today without breaking anything. The host would only use it
once row() carries it and NoteList/NoteSummary show it. decisions.md:444-448 allows a row
to carry only what the list shows. Note rows render NoteSummary, which has no icon slot.

Optional members are detected with `typeof x === "function"` or a truthy signal check.
Capability defaults are inconsistent:
- absent `markdown` -> plain text
- absent `hasTitle` -> true in sidebar.js but falsy in newNote, and the editor binding
  keeps its previous value with a QML warning (verified on Qt 6.11.2)
- absent `canImages` -> false
- absent `tools` -> all

The compatibility precedent is canReorder/setOrder -> per-row `reorder` + async
`reorder()`: the legacy shorthand stays, the explicit per-item declaration wins (`null`
included), and the host dispatches modern versus legacy by feature detection. Other
precedents: optional trailing `options` (save), extra ignorable args (action), optional
hooks with host defaults (noteEdited), and the 1.x legacy directory adapter. The contract
must change "additively, never silently". The plugin manifest's apiVersion must equal 1,
and it declares no capabilities.

## Facts

### Provider declarations (what each built-in and the example declare today)

| Provider | markdown | hasTitle | canImages | tools | canCreate/canDelete | canCreateSection | canReorder | where |
|---|---|---|---|---|---|---|---|---|
| local | true | true | true | omitted (= all) | true/true | true | false | plugins/org.note-note.local/Provider.qml:20-29 |
| sticky | false | false | omitted (false) | omitted | true/true | false | false | plugins/org.note-note.sticky/Provider.qml:14-19 |
| notion | true | true | omitted (false) | 19 ids, no table/textColor | true/true | false | false | plugins/org.note-note.notion/Provider.qml:17-28 |
| onenote | true | true | true | 20 ids incl. table, textColor, calendar; no quote/codeblock/code/rule | true/true | false | false | plugins/org.note-note.onenote/Provider.qml:19-37 |
| hello (example) | true | true | omitted | omitted | true/true | false | false | examples/hello/Provider.qml:14-19 |

- **Footer actions.**
  - Local: provider-level `footerActions` is New notebook (`shortcut: "newNotebook"`).
    Each notebook section adds New Note (`shortcut: "newNote"`) and New section
    (`prompt`) — plugins/org.note-note.local/Provider.qml:98-112.
  - Sticky: New Note and Sign out — plugins/org.note-note.sticky/Provider.qml:80-81.
  - Notion: New Note (only when pages exist), Refresh and Settings —
    plugins/org.note-note.notion/Provider.qml:85-89.
  - OneNote: New section (prompt) on a notebook tab, and Sign out. There is no New Note
    footer: `new` rows sit inside sections — plugins/org.note-note.onenote/Provider.qml:261-263, 270-277.
  - Hello: New Note and Settings — examples/hello/Provider.qml:66-67.
- `markdown`'s meaning in the contract: "bodies are Markdown (rendered); false = plain
  text" — docs/providers.md:47. The skill mirror says the same —
  skills/note-note-plugin/references/providers.md:236.

### Q1 — consumers of markdown / hasTitle / tools / canImages

- **`markdown`.** The only host read of the provider-level flag is Workspace.qml:2837-2840,
  `plain: { var p = root.providerOf(root.currentPath); return p ? !p.markdown : false }`.
  A grep of Workspace.qml, services/, ui/ and hosts/ finds no other read of `p.markdown`.
- **`plain` (NoteEditor.qml:26-28) switches:**
  - conversion out: requestMarkdown returns `plainText()` with no converter (122-126)
  - conversion in: setNote skips `markdown.toHtml` (300-306)
  - snapshotDocument: body = plainText() vs documentHtml() (318-321)
  - showBody: raw text vs `Dialect.documentHtml` (339)
  - TextEdit `textFormat` PlainText vs RichText (2075)
  - paste and pastePlain fall back to Qt's `area.paste()` (392-395, 518-521)
  - insertImage refused (655)
  - block helpers refused: 739, 752, 764, 861 (withMarkdown), 1124 (normalizeNow),
    1322, 1473, 1702, 1727
  - updateDecorations clears quote bars, code slabs, images, checkboxes and audio (1142-1149)
  - configureLinks gets `root.plain` (1090)
  - custom Backspace/Delete/Right handling skipped (2127-2129)
- **Toolbar.** EditorApi.writable is `host.hasNote && !host.readOnly && !host.plain && !host.showingNotice`
  (ui/editing/EditorApi.qml:13). In plain mode that hides the tools strip
  (NoteEditor.qml:155 `toolsVisible`) and blocks every tool execution
  (ui/editing/ToolRegistry.qml:264-269).
- **Paste keys.** Workspace keyActions paste and pastePlain return false when `editor.plain`
  (Workspace.qml:2245-2250).
- **Not consumers.** Previews, search and sidebar never read `markdown`.
  - Previews are computed by providers: local notefile.preview
    (plugins/org.note-note.local/notefile.py:79-86, list.py:147-153); sticky previewOf
    (Provider.qml:52-61); Notion and OneNote send `preview: ""` (notion Provider.qml:82;
    onenote Provider.qml:252, 267).
  - The host matches title and preview (services/notes/sidebar.js:19-22).
  - displayTitle derives a label from the preview and turns `[x]`/`[ ]` into ☑/☐
    (Workspace.qml:1305-1324).
- **`hasTitle`.**
  - Editor binding `hasTitle: { var p = …; return p ? p.hasTitle : true }`
    (Workspace.qml:2841-2844). It sets the title field's visibility
    (NoteEditor.qml:1894 `visible: !root.showingNotice && root.hasTitle`).
  - After create: `if (p.hasTitle) editor.focusTitle() else editor.focusEditor()`
    (Workspace.qml:1932-1936).
  - sidebar.js:26 stamps `hasTitle: provider.hasTitle !== false` on every row. That sets
    NoteSummary `font.bold` (ui/NoteSummary.qml:24) in the list (ui/NoteList.qml:455) and
    in search results (ui/SearchResults.qml:111).
  - displayTitle shows unsaved typed titles only when `row.hasTitle !== false`
    (Workspace.qml:1306).
- **`tools`.**
  - Bound with `(p && p.tools !== undefined) ? p.tools : null` (Workspace.qml:2845-2848),
    so null means all tools.
  - The value flows NoteEditor.enabledTools (NoteEditor.qml:34) -> EditorApi.enabledTools
    (EditorApi.qml:14) -> `supports(capability)` (EditorApi.qml:63-65).
  - It gates ToolRegistry.isVisible / toolbarTools / canExecute
    (ui/editing/ToolRegistry.qml:46-48, 252-269) and tool panels (ui/editing/Tool.qml:41, 55).
  - A change to it closes panels (ToolRegistry.qml:316-319).
  - Rich paste is filtered through fitPaste/PasteFit (NoteEditor.qml:484-494;
    ui/PasteFit.js:98-125).
- **`canImages`.**
  - Bound with `p ? p.canImages === true : false` (Workspace.qml:2831-2834).
  - In paste(): when false it says "This notebook cannot store images" for an image, else
    pastes rich text (NoteEditor.qml:396-411). When true it calls takeImage -> insertImage
    (412-424).
  - fitPaste takes a fast path when `enabledTools === null && canImages`
    (NoteEditor.qml:485), and the flag also feeds PasteFit.lacking (PasteFit.js:98-125).

### Q2 — how create(target, cb) is reached

- The single call is `p.create(target, function(r) {...})` in newNote (Workspace.qml:1912).
- **newNote(providerId, target)** (Workspace.qml:1887-1938), in order:
  1. returns if `session.locked`;
  2. with no providerId, tries `activateFooterShortcut("newNote")` first;
  3. flushSave();
  4. clears an active search;
  5. resolves newNoteDestination (1873-1885): `p.createTargetFor(currentPath)`, falling
     back to the first provider with `canCreate && createTargetFor("")`;
  6. with no provider or target, startNewNotebook();
  7. returns if `!p.canCreate`.
- **Entry 1, footer action.** NoteList footer button -> `footerActionRequested(modelData, value)`
  (ui/NoteList.qml:728-729) -> runFooterAction (Workspace.qml:1668-1688) ->
  `p.action(path, value, sectionKey)`. The provider then calls `host.newNote(root.id, target)`:
  - local: Provider.qml:276-278
  - sticky: Provider.qml:96-97
  - notion: Provider.qml:126-127
  - hello: Provider.qml:115-116
- **Entry 2, Ctrl+N.** services/shortcuts/defaults.js:21 maps `newNote` to Ctrl+N, a
  workspace action. WorkspaceActions.handlers.newNote -> `host.newNote()`
  (services/commands/WorkspaceActions.qml:19-21). activateFooterShortcut picks the
  **first** footer action whose `shortcut === "newNote"` (Workspace.qml:1690-1703) and
  activates it through NoteList.activateFooterAction (ui/NoteList.qml:254-267). Otherwise
  newNote uses the createTargetFor fallback. Availability comes from
  WorkspaceActions.canCreateNote (WorkspaceActions.qml:42-48).
- **Entry 3, command palette.** "New Note" is `workspaceAction: "newNote"` in
  plugins/org.note-note.workspace/plugin.json:9-18 and runs the same handler.
- **Entry 4, `new` row.** A click on a row of kind `new` emits
  `newRequested(slot.modelData.path || slot.modelData.notebook)` (ui/NoteList.qml:576-579;
  signal at NoteList.qml:90 `signal newRequested(string target)`). onNewRequested finds
  the row with that path and calls `root.newNote(row.provider, target)`, else `root.newNote()`
  (Workspace.qml:2726-2734).
- **Entry 5, new notebook.** newNotebook -> `p.createSection(name, cb)`; when the answer
  has `r.target`, the host calls `root.newNote(p.id, r.target)` (Workspace.qml:1958-1979).
  Local returns `target: "section:"+key` (Provider.qml:615-616).
- **What `target` is: an opaque, provider-owned string.**
  - local "section:<folderKey>" (Provider.qml:219, 265, 277; parsed at 556)
  - onenote "section:<sectionId>" (Provider.qml:262, 330; parsed at 1135-1141)
  - notion "parent:<pageId>" or "new" (Provider.qml:105-111, 248)
  - sticky "new" (Provider.qml:90, 97), ignored by create (244-273)
  - hello "new" (86, 116), ignored (100-105)
- **No options today.**
  - Contract: `create(target, cb)` -> `cb({ path, error })` (docs/providers.md:350;
    skill references/providers.md:321).
  - `host.newNote(id, target)` (docs/providers.md:202-203).
  - NoteList's `newRequested` carries one string, and WorkspaceActions' newNote() none.
- **What the host does with cb({path})** (Workspace.qml:1912-1937):
  1. On error: `showStatus(p.name + ": " + r.error)` and stop.
  2. `sectionKeyOf(r.path)` (1941-1951) finds the tab whose rows hold the note, and
     `showSection(home)` runs if that tab differs.
  3. `choosePath(r.path)` (1759-1765): sets `defaultOwed = false` and `rememberOpened`
     (984-1010), which calls `owner.noteOpened` or updates lastNotes. Then
     `session.selectPath` (NoteSession.qml:185-193) runs flushSave, sets currentPath and
     calls `load(false)`, which calls `provider.load`.
  4. Scrolls to the row.
  5. `focusTitle` if `p.hasTitle`, else `focusEditor`.
- **Provisional notes.**
  - OneNote creates `draft-…` ids, lists the row and answers `cb({path})` before the
    remote create (Provider.qml:1134-1167).
  - finishCreation emits `notePathChanged(pathOf(id), path, note.view)` (Provider.qml:1186-1241).
  - The host connects it (Workspace.qml:767-776): `session.replacePath`,
    `replaceRememberedNote`, deletePath, invalidateContentSearch.
  - NoteSession.replacePath moves saveEpoch, stored, drafts, savesPending,
    pendingDeletions, loadingPath and currentPath without reloading
    (NoteSession.qml:75-114).
  - Local emits notePathChanged with view null when a folder is renamed
    (Provider.qml:698-700).
- **Local create.** operations.py writes `notefile.serialize("", "")`, a front matter with
  an empty title (plugins/org.note-note.local/operations.py:105-110). Provider.create
  inserts the entry after the folder's last note, opens the way to it and persists the
  order (Provider.qml:555-575).
- **Locking.** runRowAction locks the session before `p.rowAction` and unlocks in its
  callback (Workspace.qml:2115-2127). newNote returns early while locked
  (Workspace.qml:1888-1890).

### Q3 — how load()'s answer is consumed

- NoteSession.load(reload) (services/notes/NoteSession.qml:210-305) is the only consumer.
  1. It calls `provider.load(path, cb)` (252) and keeps the returned handle for
     cancelLoad (301-304, 177-183).
  2. `result.error` -> `noteUnavailable(provider.name + ": " + result.error)` (257-259).
  3. `loadedVersion = result.version || versionFor(path)` (261).
  4. `editor.documentBase = result.base || ""` (262).
  5. `editor.setNote(result.title || "", result.body || "", shown)` (263). `shown(false)`
     -> noteUnavailable(notDisplayable) (267-269).
  6. `editingView = result.view || …` (274).
  7. `noteReady(result.editable === false, result.reason || "")` (275). noteReady
     (313-323) sets documentEditable and reports the reason once when the note is read-only.
  8. `result.recovered` -> dirty, `setDraft(..., conflict: result.conflict)`, report
     "Recovered unsaved changes", then showConflict or (`result.retry`) a deferred
     flushSave (276-292).
  9. Otherwise `stored[path] = editor.snapshotDocument()` (294). On a reload it reports
     "reloaded, changed elsewhere" (295-297).
- **The draft path skips load.** If `session.drafts[path]` exists, it runs
  `editor.restoreDocument(draft.document)` and `noteReady(false, "")` (235-245).
  `draft.document` comes from `editor.snapshotDocument()` = `{ title, body, base }`
  (ui/NoteEditor.qml:318-321).
- **The save path.**
  - flushSave (471-507): snapshotDocument; `isStored(path, document)` compares title and
    body strings (364-367); setDraft.
  - Then `editor.requestMarkdown(function(body, ok) …)` (493) ->
    `provider.save(path, draft.document.title, body, cb, { view: draft.view, resolution })`
    (503-505).
  - finishSave (509-542) reads `result.error`, `result.conflict`, `result.merged` (525),
    `result.version` (528) and `result.warning`.
- **The editor surface the session depends on:**
  - editor.title (59)
  - editor.readOnly (120)
  - showConflict (143), clearConflict (173)
  - viewState (221), clearNotice (222)
  - documentBase (224, 262)
  - setNote (226, 263)
  - restoreDocument (237)
  - restoreViewState (272)
  - snapshotDocument (278, 294, 420, 480)
  - requestMarkdown (493)
- **What each provider answers.**
  - local `{ title, body, editable, reason, version, base }` (Provider.qml:509-511, from
    operations.py:111-121)
  - sticky `{ title: "", body, editable, version, reason? }` (Provider.qml:190-202)
  - notion `{ title, body, editable, reason, version }` (Provider.qml:161-200)
  - onenote: the script answer via cacheBody (Provider.qml:983-1029); onenote.py:1373-1388
    adds `editable, markdown: true, reason`, and the notemerge store adds
    `view/recovered/conflict/retry` (lib/notemerge/store.py:89, 98)
  - hello `{ title, body, editable }` (examples/hello/Provider.qml:90)
- **An unread per-note format marker.** onenote.py:1380 and 1387 already output
  `markdown=True` in every page answer. No QML reads it; the only `.markdown` read of a
  provider is Workspace.qml:2839.
- **Documentation drift in callback fields.**
  - docs/providers.md:260 lists `{ title, body, editable, reason, error, base, view, recovered, conflict }`,
    without `version` (described separately at 222-225) and without `retry`.
  - The skill lists `{ title, body, editable, reason?, version?, base? }`
    (references/providers.md:319).
  - `retry` is documented only in lib/notemerge/README.md:135-137.
  - Save's `merged` and `version` are read by the host (NoteSession.qml:525, 528), but
    docs/providers.md:282 lists `{ error, warning, conflict }`.
- **Local read is lossy-check gated.** operations.py runs `unkept(body)`, the editor
  writer's own list of constructs it cannot write back. It answers `editable: not lost`
  with a reason (operations.py:19-31, 111-121).

### Q4 — rows and sections[].notes

- **The whitelist.** sidebar.js `row(provider, key, source)` returns
  `{ provider, notebook, kind, path, title, hasTitle: provider.hasTitle !== false, preview, icon, reorder: Ordering.descriptor(...), level, expanded, count, menu, modified }`
  (services/notes/sidebar.js:24-31). Every other field of a provider row, `version`
  included, is dropped.
- **Search rows.** `notes = section.notes || rows.filter(kind === "note")`. With a query,
  rows are the `found` notes mapped through the same row() (sidebar.js:59-70). Tab counts
  use `section.count` or `notes.length` (66-67).
- **Contract shapes.**
  - Row: `{ kind, path, title, preview, icon, level, expanded, count, menu, reorder, version, modified }`
    (docs/providers.md:89-91).
  - notes: `[{ path, title, preview }]` (docs/providers.md:58).
  - Supply `modified` in notes as well as rows (docs/providers.md:227-232).
- **"A row carries only what the list shows or drags on"** (docs/decisions.md:444-448).
  rebuildRows assigns rows only when `JSON.stringify(model.rows) !== JSON.stringify(root.rows)`
  (Workspace.qml:1349-1362); the comment there says a field the delegates never read
  would make equal lists unequal.
- **Version and existence checks.** `version` is read straight from the providers'
  sections by versionOf (Workspace.qml:1396-1406). noteExists checks rows, then
  `section.notes`, by path (Workspace.qml:1415-1435). sectionKeyOf checks rows only
  (1941-1951).
- **Note rows have no icon slot.** They render NoteSummary (title, hasTitle, preview,
  modified) (ui/NoteList.qml:447-461; ui/NoteSummary.qml:6-58). The icon Text lives only
  in the non-note Row (NoteList.qml:464-477). `new` rows always show "+" and
  "New note…" whatever their title (NoteList.qml:472-473, 485).
- **No built-in sets `icon` on a note row:** local Provider.qml:213-215; sticky 77;
  notion 82; onenote 252-256; hello 63.
- **Per-note metadata already in rows and notes:** `modified` for display dates
  (sidebar.js:30; Workspace.qml:2851-2860 for the editor caption), and `version` for change
  detection (provider sections only).
- **Local listing stream.** list.py emits
  `N\tkey\tpath\ttitle\tpreview\tsize\tmtime` from `head_of` (front matter split by
  notefile) (plugins/org.note-note.local/list.py:147-153, 253). Provider.loadList parses
  `N` lines into notes (Provider.qml:429-446).
- **Local front matter.** notefile.split keeps every front-matter line that is not
  `title:` verbatim as `extra`, and serialize writes it back
  (plugins/org.note-note.local/notefile.py:1-12, 48-76). operations.py's save preserves
  `split(current)[2]` (operations.py:139-142).

### Q5 — host defaults for absent members; compatibility policy

- **Optional members, feature-detected:**
  - `searchChanged` (Workspace.qml:720), `saveRequested` (750), `noteChanged` (758),
    `notePathChanged` (767), `noteDeletionFinished` (778): truthy signal checks
  - `watch` (321, 332; ProviderLifecycle.qml:93, 179)
  - `noteOpened` (986), `defaultNote` (990, 1036), `searchStatus` (1241), `search` (1258, 1269)
  - `revealPath` (1536), `searchDiagnostics` (1590)
  - `reorder` vs `canReorder` + `setOrder` (927-928)
  - `rowAction`: truthy (2111)
  - `poll` (2406), `recording` (2880), `storageLabel` (2913)
  - `noteEdited` (NoteSession.qml:339-344; otherwise the host's 1500 ms Timer at 347-356)
  - The rest are `typeof === "function"` checks.
- **Called unconditionally (effectively required):**
  - refresh (Workspace.qml:320), crumb (1550)
  - createTargetFor (1876, 1880, 1882)
  - action (1660, 1682, 1685), toggleTree (1745)
  - saveState (2290), restoreState (785, when state exists)
  - load (NoteSession.qml:252), save (503), remove (429)
  - the signals updated, statusRequested, noticeRequested, noticeCleared, viewRequested,
    viewCleared and persistRequested are connected unconditionally (Workspace.qml:717-743)
- **Capability defaults:**
  - `markdown` absent -> `!undefined` -> plain text (Workspace.qml:2839). Not stated in
    docs/providers.md:47.
  - `hasTitle` absent:
    - sidebar.js:26 treats it as true;
    - newNote treats it as falsy, so focusEditor (Workspace.qml:1932);
    - the editor binding at Workspace.qml:2843 yields undefined. Verified on Qt 6.11.2
      with the same binding shape: "Unable to assign [undefined] to bool", and the
      property keeps its previous value.
  - `canImages` absent -> false (2833).
  - `tools` absent -> null = all (2847; EditorApi.qml:63-65).
  - `canCreate`, `canDelete`, `canCreateSection` absent -> falsy (Workspace.qml:1880, 1908,
    2002, 1964; WorkspaceActions.qml:51-52).
  - `writeBusy` absent -> falls back to `busy` (Workspace.qml:269-274; docs/providers.md:698-702).
  - `settings` and `liveSettings` non-arrays -> [] (Workspace.qml:646, 665;
    ProviderLifecycle.qml:66-69).
- **The built-in base supplies the boring required hooks:** LaneProvider gives
  restoreState/saveState/toggleTree/setOrder no-ops (services/providers/LaneProvider.qml:76-80),
  a debounced noteEdited -> saveRequested (34-45), unsentSave (87-89) and
  busy/writeBusy (104-106). External providers do not extend it.
- **Precedent 1: canReorder / setOrder -> per-row `reorder` + async `reorder()`.**
  - docs/providers.md:51 calls it "legacy shorthand…; new providers declare each row's
    `reorder` group".
  - docs/providers.md:170-175: "For compatibility, `canReorder: true` and a note row with
    neither `reorder` nor `fixed: true` still imply … Legacy `setOrder` remains supported
    … An explicit `reorder`, `null` included, takes precedence over the legacy flag".
  - Code: services/notes/ordering.js:5-18
    (`if (source === undefined && provider.canReorder && !row.fixed …)`), and
    Workspace.qml:927-961 (`var modern = typeof provider.reorder === "function"`; the
    comment reads "Compatibility for external providers implementing the 1.x hook").
- **Precedent 2: optional trailing arguments.**
  - save's `options`: "Existing providers can ignore `options` and retain their
    four-argument function" (docs/providers.md:283-291).
  - action's extra arguments: "Existing `action(path)` handlers can ignore the additional
    arguments" (docs/providers.md:197-198, 372-373).
- **Precedent 3: optional hooks with host defaults.** noteEdited/saveRequested: "Implement
  neither … and your notes are written on the host's own default pause (1500 ms)"
  (docs/providers.md:327-329).
- **Precedent 4: tolerated legacy keys.** `collapsedByDefault` is ignored and "Passing it
  is harmless" (docs/providers.md:85-87); `color` "remains accepted"
  (docs/providers.md:63-64).
- **Precedent 5: the 1.x legacy external provider directories.**
  - docs/providers.md:8-9.
  - docs/plugins.md:122-127: "a compatibility adapter for the 1.x series. Removal … is
    scheduled for 2.0 and must be announced".
  - Implemented at services/extensions/manifest.py:251-265.
  - Exercised by tests/standalone_selftest.py:190, which copies examples/hello into the
    legacy providers dir, and tests/standalone_launch.qml:38-40, which asserts it loads.
- **Policy.** "It is the API other people write against: change it additively, never
  silently" (docs/technical-requirements.md:99-101).
- **No version negotiation.** The plugin manifest must say `schemaVersion` 1 and
  `apiVersion` 1 (manifest.py:134-137; SKILL.md:71). Any bump rejects every existing
  package.
- **The manifest declares no capabilities.** A provider entry validates only `id`
  (LOCAL_ID), `path` (label ≤512, resource path) and `order` (int 0-9999)
  (manifest.py:79-87, 113-122). Unknown keys in an entry are ignored. check.py only runs
  manifest.py (skills/note-note-plugin/scripts/check.py:61-73), so capabilities are
  invisible to it. Capabilities are read off the live QML instance.
- **Process rule.** "When one of those contracts changes, change the skill's reference for
  it in the same commit" (docs/plugins.md:50-53). The skill has already drifted: its row
  shape lacks `count` (references/providers.md:267 vs docs/providers.md:89), and its load
  and save fields differ (above).

### Q6 — contract text a per-note content type contradicts or must amend

- docs/providers.md:47 — `markdown` | bool | "bodies are Markdown (rendered); false = plain
  text". The format is per provider, and only two formats exist.
- docs/providers.md:48 — `hasTitle` is per provider.
- docs/providers.md:53 — `canImages` assumes a Markdown body (`![](file:///…)`,
  `{width=N}`).
- docs/providers.md:54, 66-71 — `tools`: "omitted = all (when `markdown`)". It is
  toolbar vocabulary for rich text.
- docs/providers.md:58, 89-91 — `notes` and the row shape carry no type.
- docs/providers.md:72-76 — nested tables "within the Markdown body".
- docs/providers.md:181-187 — "`footerActions` supplies **every** button … It does not add
  creation buttons based on provider identity or capabilities."
- docs/providers.md:100-101 — row menus: "the host adds no item of its own".
- docs/providers.md:200-204 — `shortcut` names only `newNote` or `newNotebook`;
  `host.newNote(id, target)` has no type.
- docs/providers.md:260-281 — the load answer has no type.
- docs/providers.md:282-315 — the save signature and options have no type. Lines 307-315
  say "A `body` from a provider with `canImages` may contain `![alt](file:///…)`".
- docs/providers.md:350-357 — `create(target, cb)` has no options.
- docs/providers.md:367-371 — createSection `target` is "the same string your `new` row
  carries".
- docs/providers.md:388-404 — `search` matches "*body* contains `query`".
- docs/providers.md:419 — `createTargetFor(path)` returns the target for Ctrl+N.
- docs/providers.md:493-507 — Limits: never an editable partial note.
- docs/providers.md:705-716 — the local read and split, and front-matter lines being kept.
- **The skill mirror:**
  - minimal provider `markdown: true`, `hasTitle: true` (55-56)
  - properties table (229-247)
  - rows (267-286)
  - footer / newNote (304-310)
  - functions table: load, save, create, createTargetFor (314-328)
  - callback rules (342-353)
- docs/business-requirements.md:74 — "Sticky Notes are plain text; OneNote and Notion are
  Markdown". docs/business-requirements.md:32-34 — local notes are plain Markdown readable
  by any tool. docs/business-requirements.md:70 — one Markdown file per note.
- docs/technical-requirements.md:14 — "notes and the provider contract are **Markdown**".
  docs/technical-requirements.md:107-109 — a stale row shape (no menu, reorder, count,
  modified).
- docs/decisions.md:131-154 — "Notes on disk and the provider contract are unchanged
  [Markdown]".
- README.md:226 — "The body is Markdown, rendered live and saved back as Markdown".

## Integration points

| Where | What changes | Why |
|---|---|---|
| docs/providers.md:41-59, 89-91, 181-204, 257-428 | Add a content-type concept: the provider-level declaration of supported types; a per-note type on rows, notes and the load answer; the requested type on create; the save/body format per type; a compatibility paragraph for `markdown`, modelled on 170-175; amend 47, 53-54, 185 and 307 | It is the contract external authors write against (technical-requirements.md:99-101) |
| skills/note-note-plugin/references/providers.md:55-56, 229-247, 267-286, 304-328, 342-353 | Mirror the same contract change in the same commit | docs/plugins.md:50-53 |
| examples/hello/Provider.qml:14, 63, 90, 100-105, 114-117 | Show the new declaration and the per-note type, while still loading unchanged through the legacy directory | tests/standalone_selftest.py:190 and tests/standalone_launch.qml:38-40 load it as a legacy provider |
| Workspace.qml:2831-2848 | The `canImages`, `plain`, `hasTitle` and `enabledTools` bindings must come from the open note's type, not only from `providerOf(currentPath)` | Today the editor mode is per provider; this is the central switch |
| services/notes/NoteSession.qml:235-300 | Read the per-note type from the load answer and apply it before `editor.setNote(...)` (setNote reads `plain` synchronously, NoteEditor.qml:300). Draft restore (235-245) must restore the type too | load is the only consumer of the load answer; drafts bypass load |
| services/notes/NoteSession.qml:471-507 | flushSave -> requestMarkdown -> provider.save: the body serialization must be the open type's (e.g. a timeline serializer), and isStored (364-367) must compare that serialization | The save path assumes Markdown/HTML or plain text only |
| Workspace.qml:1873-1938 (newNoteDestination/newNote) and 1958-1979 | Carry a requested type to `p.create`, check the provider supports it, and decide focus per type (1932) | create is the single creation call site, and today it has no options channel |
| Workspace.qml:2726-2734 and ui/NoteList.qml:90, 472-485, 576-579 | `new` rows can only pass `target`, and their label is hardcoded "New note…" | A typed "new" affordance (e.g. New timeline) needs a channel and a label |
| Workspace.qml:1668-1703 and services/commands/WorkspaceActions.qml:19-48 | Footer `shortcut: newNote` / Ctrl+N / palette pick the first matching footer action; any typed creation path must fit this or extend the shortcut names | Ctrl+N semantics and availability checks |
| services/notes/sidebar.js:24-31, 59-70 | Add the per-note type (or a type-derived icon) to row() and make it flow through `notes` for search results | The whitelist drops unknown fields; decisions.md:444-448 lets a row carry only what the list shows |
| ui/NoteList.qml:447-461, ui/NoteSummary.qml, ui/SearchResults.qml:108-114 | Show the type (icon) on note rows and search hits, if desired | Note rows have no icon slot today |
| plugins/org.note-note.local/Provider.qml:429-446, 499-513, 538-575; list.py:147-153, 253; notefile.py:48-76; operations.py:105-149 | Persist a per-note type (e.g. a front-matter line), list it, return it from read and create, and make the `unkept` read-only check type-aware | Local is the provider most likely to support a timeline first; the front matter already round-trips unknown lines |
| plugins/org.note-note.sticky/Provider.qml:14-15, 190-202, 244-273 | Declare supported types (plain text only); load and rows report the type | The provider-level `markdown: false` becomes a per-note "text" type |
| plugins/org.note-note.notion/Provider.qml:17-28, 161-200, 241-279 | Declare supported types (Markdown); report them | Same |
| plugins/org.note-note.onenote/Provider.qml:19-37, 983-1029, 1134-1167; onenote.py:1373-1388 | Declare supported types; the existing unread `markdown=True` in page answers could become, or be replaced by, the per-note type | OneNote already emits a per-note format hint |
| services/extensions/manifest.py:79-87 | Only if content types were declared in plugin.json (not the case today); otherwise no change | Capabilities are QML-instance properties, not manifest data |
| tests/transitions.qml:120-127, 400-412, 540-548 | Fake providers and sessions show the minimal provider/load shape; new cases for per-note type and legacy defaults | Transition suites drive NoteSession and the host with fake providers |
| docs/business-requirements.md:70, 74; docs/technical-requirements.md:14, 107-109; docs/decisions.md:131-154; README.md:226 | Amend the "notes and contract are Markdown" statements; add a decision entry for per-note content types | These docs state the format is per provider and Markdown-only |

## Constraints (documented invariants)

- The contract changes additively, never silently — docs/technical-requirements.md:99-101.
- The host has no `if (provider.id === …)` branches — docs/technical-requirements.md:85-91.
- A provider owns load/save/create/remove and its capability flags, and never touches the
  UI — docs/technical-requirements.md:93-97.
- Three rules: notes are the product (read-only rather than risk a bad write); every input
  is bounded and untrusted; the provider owns its backend while the host owns the window,
  list and editor — docs/README.md:38-45.
- Never lose a note; open read-only with a visible reason when a note cannot be written
  back safely — docs/business-requirements.md:29-31; docs/decisions.md:660-721.
- Local notes stay plain Markdown readable by any other tool, with no database —
  docs/business-requirements.md:32-34, 70.
- Be honest about limits: say so in the UI rather than drop silently —
  docs/business-requirements.md:42-44.
- A new provider can be written against PROVIDERS.md without reading the host's code —
  docs/business-requirements.md:85-86.
- Change the skill reference in the same commit as the contract — docs/plugins.md:50-53.
- The legacy external provider dirs stay supported for 1.x; removal is announced in 2.0 —
  docs/plugins.md:122-127; docs/providers.md:8-9.
- Manifest `schemaVersion` and `apiVersion` must be the integer 1 —
  services/extensions/manifest.py:134-137; skills/note-note-plugin/SKILL.md:71.
- A row carries only what the list shows or drags on — docs/decisions.md:444-448.
- The host owns the note text and the conversion; the provider owns save timing —
  docs/decisions.md:450-487.
- A note is unsaved until a provider says otherwise; the conversion is part of the save —
  docs/decisions.md:489-521.
- The converter's answer is framed: a failure never reads as an empty note, and a note is
  loading until its document is on screen — docs/decisions.md:523-555.
- A rich paste brings only what the notebook can keep (tools/canImages) —
  docs/decisions.md:779-810.
- A tool is offered only where it can act — docs/decisions.md:852-869.
- The host adds no creation buttons and no menu items of its own; providers supply every
  footer action and row menu item — docs/providers.md:100-101, 181-187.
- Answer every load/save/create/remove exactly once; a superseded save answers `{}`, an
  unsent one `{ error }` — docs/providers.md:282-300; references/providers.md:342-353.
- Change the provider model only after the backend confirms — docs/providers.md:301-306.
- Provisional notes: keep saves and deletes behind creation, keep the draft on failure,
  and use notePathChanged — docs/providers.md:350-357, 445-451.
- Providers bound everything they read; never an editable partial note —
  docs/providers.md:493-507; docs/security.md:16-39.
- Note content from any backend is assumed hostile — docs/security.md:327-333.
- The sidebar model is a plain JS array replaced wholesale —
  docs/technical-requirements.md:167-168.
- Code style: no hacks or workarounds, proper fixes, braces on every block, bodies on
  their own lines — CLAUDE.md:1-6.

## Reusable pieces

- The legacy-flag plus explicit per-item override pattern, where explicit wins with `null`
  included: services/notes/ordering.js:5-18 (`descriptor`).
- Modern/legacy dispatch by feature detection: Workspace.qml:927-961 (reorderItems).
- One place to normalise per-row data from the provider:
  `hasTitle: provider.hasTitle !== false` in services/notes/sidebar.js:24-31.
- The single load consumer, with two endings: NoteSession.load / noteReady / noteUnavailable
  (services/notes/NoteSession.qml:210-331).
- The single create flow: Workspace.newNote / newNoteDestination
  (Workspace.qml:1873-1938), and createSection -> newNote(p.id, r.target) (1958-1979).
- An optional trailing options object that old providers can ignore: save's options
  (docs/providers.md:283-291; NoteSession.qml:503-505).
- Provider-supplied footer actions with an optional prompt or inline input, plus the
  Ctrl+N shortcut binding: Workspace.qml:1668-1703; ui/NoteList.qml:254-267, 714-729.
- A provider-defined row menu, with rowAction(path, id, value, cb) and the
  prompt/confirm/rename helpers: Workspace.qml:2059-2132.
- A single-field name dialog: design/controls/PromptDialog.qml:10-21, used via
  Workspace.askName (2083-2097). It has one field only.
- Per-note metadata that already reaches both rows and notes:
  `modified` (docs/providers.md:227-232; sidebar.js:30, 33-36).
- Front matter that round-trips unknown lines (`extra`), so a local `type:` line would
  survive older app versions: plugins/org.note-note.local/notefile.py:48-76.
- OneNote's per-page `markdown: true` field, emitted today and read by nobody:
  plugins/org.note-note.onenote/onenote.py:1380, 1387.
- The built-in provider base, where shared defaults live:
  services/providers/LaneProvider.qml:9-129.
- The plugin checker, which runs the app's own validator and repeats nothing:
  skills/note-note-plugin/scripts/check.py:1-8, 61-73.
- Fake-provider test scaffolding: tests/transitions.qml:120-127, 400-412, 540-548.

## Risks

1. Rows can't be the only carrier of a per-note type. Created notes may not be listed
   yet, and drafts restore without load. The editor mode needs the type from the load
   answer and from the draft snapshot (NoteSession.qml:235-300; NoteEditor.qml:318-321).
2. The editor's mode bindings (Workspace.qml:2831-2848) switch on currentPath before load
   answers, and setNote reads `plain` synchronously (NoteEditor.qml:300). A per-note type
   must be in place before setNote runs, or a note renders in the wrong mode. The async
   conversions are guarded only by noteToken (NoteEditor.qml:257-316).
3. The `hasTitle` defaults are already inconsistent: true in sidebar.js:26, falsy in
   Workspace.qml:1932, and "keep previous value plus a warning" for the editor binding at
   Workspace.qml:2843 (verified on Qt 6.11.2). Adding more per-type capability reads
   without one normalising place would multiply this.
4. An absent `markdown` silently means plain text (Workspace.qml:2839), and
   docs/providers.md does not say so. Mapping it to a default content type has to keep
   that meaning for existing external providers.
5. Encoding the type in the opaque create `target` string would be a hack (CLAUDE.md). The
   target is parsed by each provider (local Provider.qml:556; onenote 1135-1141; notion 248).
6. A host-added "New timeline" button or menu item would contradict
   docs/providers.md:100-101 and 185 unless those rules are amended. Ctrl+N
   (activateFooterShortcut) triggers only the first footer action marked `newNote`
   (Workspace.qml:1690-1703).
7. A provider calling host.newNote from inside rowAction before answering is ignored. The
   session is locked from Workspace.qml:2115-2116 until cb, and newNote returns while
   locked (1888-1890).
8. `new` rows always read "+ New note…" (ui/NoteList.qml:472-473, 485). A typed creation
   row needs UI support, not just contract text.
9. Local read-only gating: operations.py marks a note read-only when `unkept(body)` reports
   constructs the rich-text writer cannot keep (operations.py:19-31, 111-121). A timeline
   body format must pass that check, or the check must be skipped for non-Markdown types.
10. Raw-format leakage. Previews are provider-computed from the body
    (notefile.py:79-86; sticky previewOf 52-61), and provider content search scans the
    body (local search.py via Provider.qml:359-366; sticky 163-171). A serialized
    timeline shows its raw syntax in previews and search unless the format reads well as
    text.
11. Backend writers refuse what they cannot keep: OneNote refuse_unkept_formatting
    (onenote.py:1684-1692) and Notion `notion_md.Unkept` (docs/decisions.md:687-694, 785-787). A
    timeline representation must round-trip on each backend that offers the type, or the
    provider must not declare it.
12. Bumping apiVersion rejects every existing external package (manifest.py:136-137), so
    the change must be additive under apiVersion 1.
13. Contract drift already exists. The skill lacks `count` and the full load fields, and
    providers.md lacks `retry`, save `merged` and save `version`. An amendment that
    touches only one of the two documents breaks docs/plugins.md:50-53.
14. Search results come from `section.notes` when provided (sidebar.js:62-70). A type
    carried only on `rows` would be missing in search results, or in a folded tree's
    inventory.
15. isStored compares the snapshot title/body strings (NoteSession.qml:364-367). A
    timeline editor's snapshot must be a deterministic serialization, or no-op saves will
    be sent (or real ones skipped).
16. Timeline content is backend data, which the threat model treats as hostile
    (docs/security.md:327-333). Event counts and lengths need bounds, and rendering should
    use Text.PlainText.

## Open questions

1. Where is the per-note type authoritative: the load answer, rows/notes, or both? What
   should the host do on a mismatch?
2. What is the provider-level declaration? A list of supported types, with `markdown` as
   a legacy shorthand: true -> markdown, false/absent -> text.
3. How does the requested type reach `create()`? Options are an optional third argument
   (`create(target, cb, options)`, following the save `options` precedent), new row
   fields, or footer action data. host.newNote and NoteList.newRequested must change with
   it.
4. Who offers "New timeline"? Either a provider-supplied footer action, row or menu (the
   current rule), or a host affordance generated from the declared types, which needs an
   amendment to docs/providers.md:185.
5. What is the storage representation of a timeline per provider? Options for local: a
   front-matter `type:` line plus a Markdown task list, or another format. Does it satisfy
   business-requirements.md:32-34? Can OneNote, Notion and Sticky store one faithfully,
   or do they simply not declare the type?
6. Should save carry the type (e.g. in `options`), or does the provider infer it from the
   note it already has?
7. Can a note's type change after creation (Markdown <-> timeline conversion)? Is that out
   of scope?
8. Should `hasTitle` become per type? For example: a timeline always has a title, but
   Sticky has no title field.
9. Should the list show a type icon on note rows (sidebar.js row() + NoteSummary), and
   should it be host-derived from `type` or the provider-supplied `icon`? `icon` is in the
   row shape (docs/providers.md:89) but unused for note rows.
10. Version naming: the docs mention "since 2.8" (docs/providers.md:85) and "2.8.1"
    (docs/technical-requirements.md:108), while the app manifest is 1.0.40
    (manifest.json:5) and the plugin docs talk about a "1.x series". Which number should
    the content-type change be documented under?

## Recommendations (precedent only)

1. Follow the canReorder -> `reorder` precedent:
   - keep `markdown` as a documented legacy shorthand for the provider's default type;
   - add an explicit per-note type that wins when present;
   - feature-detect in one host helper;
   - document the mapping in a compatibility paragraph like docs/providers.md:170-175.
2. Pass the requested type to create through an optional trailing options object, so
   two-argument `create(target, cb)` providers keep working. This follows the save
   options precedent at docs/providers.md:283-291. Do not encode it in `target`.
3. Normalise every capability default (`markdown`, `hasTitle`, `canImages`, `tools` and
   the new type data) in one place. Fix the Workspace.qml:2841-2844 binding so an absent
   `hasTitle` no longer keeps the previous note's value.
4. Amend docs/providers.md, skills/note-note-plugin/references/providers.md and
   examples/hello in the same commit, reconciling the existing drift. Keep apiVersion 1,
   and keep tests/standalone_launch.qml's legacy hello passing unchanged.
