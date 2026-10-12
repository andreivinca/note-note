# Note types and the timeline: extensibility-first design

Stance: **extensibility-first architect**. Repository `/home/andrei/Projects/note-note`, HEAD `e2cdc4e`, app 1.0.40.
Every `file:line` below was read at HEAD. The grammar claims were checked by running the repo's own Markdown stack
(scripts in `scratchpad/designs/architect-exp/`, run with `python3 -B`, nothing written to the repo).

## Thesis

A note's type becomes a fact about the note, not about its provider: a short id (`text`, `markdown`, `timeline`) that
the provider keeps beside the body string it already stores. The host owns what a type means — the body that edits it
and the codec that reads and writes it — through an internal note-type registry and two small versioned contracts,
`NoteType` and `NoteBody`, modelled on `Tool`/`ToolRegistry`. Adding the next type is then a folder under
`ui/notetypes/` plus one registry line, with no change to the session, the workspace or any provider. The note pane
keeps everything shared (title, notices, provider views, conflict review, toolbar row, read-only) and talks to whichever
body the note's type names through one protocol; the existing rich editor answers that protocol through an adapter and
stays permanently instantiated, so tools, theming and key bindings do not flap with the open note. The type travels
inside every document snapshot, so loads, drafts, recovery and the no-op-save check can never put a note in the wrong
editor. The timeline is the first non-text type: a Markdown task list with bold titles and hard-broken descriptions,
verified as a fixpoint of the app's own Markdown editor and of mistune, so a timeline file stays plain Markdown and
degrades to an ordinary checklist anywhere else. Providers change additively (`noteTypes`, `type`, create/action
options) and need no grammar knowledge; local keeps the type in a namespaced front-matter line, while OneNote and
Notion stay Markdown until they have a durable place for the marker. Opening note types to plugin packages is
deliberately deferred behind a recorded trigger, because a public body API frozen from one example and type ids
persisted in users' files are the two things this codebase cannot take back.

## Architecture overview

```
provider (QML + Python)            host: services/notes                 host: ui (note pane)
─────────────────────────          ────────────────────────             ─────────────────────────────────
noteTypes: ["markdown","timeline"] capabilities.js  (one reading of     NoteEditor.qml = the note pane
rows/notes: { …, type }            every declaration and default)         owns: toolbar row, date, title,
load → { title, body, type, … }    sidebar.js row() copies `type`         notices, views, conflict review,
create(target, cb, {type})         NoteSession                            skeleton, readOnly, noteToken
action(path, value, key, {type})     load: typeOf(provider, result.type)  protocol: setNote(document, shown)
host.newNote(id, target, type)       setNote({type,title,body,base})        clearNote() restoreDocument(s)
                                     snapshot {type,title,body,base}        snapshotDocument() requestBody(cb)
local: notefile.py                   isStored compares type                 viewState() focusEditor() …
  note-note-type: timeline           drafts / recovery carry the type     NoteTypeRegistry (owned by the pane)
  timeline_summary() → preview     Workspace                                text, markdown → documentBody
                                     newNote(id, target, type)              timeline → TimelineBody (Loader)
                                     chooseNewNoteType() → palette pick   documentBody: adapter over the
                                     ViewBar ← editor.countText             permanent rich/plain TextEdit
                                     shortcuts gated by editor.formOpen   bodyHost: the narrow API bodies get
```

Data flow for one note:

1. **Listing.** The provider lists notes with an optional `type` (local reads it from its front matter, 8th field of
   the `N` record). `sidebar.js row()` copies `type`; `NoteList`/`SearchResults` pass `typeIconFor(type)` to
   `NoteSummary`, which draws the type's glyph before the title. A timeline row's `preview` is the provider's summary
   (`3/7 · Pack the bags`).
2. **Load.** `NoteSession.load` blanks the pane with `editor.clearNote()`, asks `provider.load`, resolves the type with
   `Capabilities.typeOf(provider, result.type)` and calls
   `editor.setNote({ type, title, body, base }, shown)`. The pane activates the type's body first (registry lookup,
   `Loader.setSource` for a typed body, or the document editor in `plain`/`markdown` format), then sets the title, then
   hands the body string to the body. `shown(ok, refusal)` ends the load: a refusal (a body the type cannot hold, a
   type this version does not know) makes the session hold the note read-only and say why.
3. **Edit.** The body emits `host.edited()` → `NoteEditor.edited()` → `Workspace.onEdited()` → `NoteSession.onEdited()`,
   unchanged from today.
4. **Save.** `flushSave` takes `editor.snapshotDocument()` (`{type, title, body, base}`, body in the body's canonical
   form), skips the save when it equals `stored[path]` (type included), otherwise calls `editor.requestBody(cb)` — the
   document body converts HTML to Markdown as today; the timeline body serialises synchronously — and then
   `provider.save(path, title, body, cb, options)`.
5. **Create.** Ctrl+N is unchanged. "New Note of Type…" (Ctrl+Alt+N, palette, or the chooser at the end of the
   provider's New Note footer row) opens the palette picker over the types the provider declares and the registry
   knows; the choice runs the provider's New Note footer action with `{ type }`, which calls
   `host.newNote(id, target, type)` → `create(target, cb, { type })`.

---

## Decisions

### D1 — Vocabulary and identifiers

**Decision.**
- The concept is a **note type**. User-facing labels: "Note" (`markdown`), "Text note" (`text`), "Timeline"
  (`timeline`).
- Core type ids are unqualified and reserved for the app: `text`, `markdown`, `timeline`.
- One grammar, defined twice and pinned by the same test strings — JS `services/notes/capabilities.js` `TYPE_ID`,
  Python `plugins/org.note-note.local/notefile.py` `TYPE_ID`:
  - core: `[a-z][a-z0-9-]{0,31}`
  - package-qualified (reserved for a later plugin kind): `<package-id>/<local-id>` =
    `[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+/[a-z][a-z0-9-]{0,63}`
  - at most 128 characters.
- Field names:
  - provider property `noteTypes` (list of ids, the first is the default);
  - per note `type` on note rows, on `sections[].notes` entries and on the `load()` answer;
  - `options.type` in `create(target, cb, options)` and in `action(path, value, sectionKey, options)`;
  - host call `host.newNote(providerId, target, type)`;
  - `NoteType.typeId` on the QML contract object (as `Tool.toolId`).

**Rationale.** `kind` is taken by rows (`note | new | action | tree`); `type` reads naturally inside a note object and
on the load answer. Core ids stay readable in files (`note-note-type: timeline`). A package-contributed id always
contains `.` and `/`, so no package can take a core id and no later core type can capture a package type's notes —
the takeover risk the extensibility map raised for unqualified ids, since built-ins win at discovery.

**Rejected.** `contentType` (invites MIME strings like `text/markdown`); `noteType` per note (redundant inside a note
object); reusing `kind` (taken); qualifying core ids (`org.note-note/timeline` in every file is noise);
unqualified package ids (a later built-in of the same id would win and re-parse users' notes).

**Evidence.** docs/providers.md:89-91 (row `kind` values); services/extensions/manifest.py:24-27 (id grammars),
:52-59 (`owned()` gives `<package-id>/<local-id>`), :268-283 (built-ins keep their ids); ui/editing/Tool.qml:9
(`toolId`).

### D2 — Provider declaration and capability normalisation

**Decision.**
- A provider declares `readonly property var noteTypes: ["markdown", "timeline"]`: the types it can store, its
  default first. The default is what Ctrl+N creates and what a note reported without `type` is.
- Legacy shorthand, following the `canReorder` → `reorder` precedent: when `noteTypes` is absent or holds no valid
  id, the types derive from `markdown` — `true` → `["markdown"]`, anything else → `["text"]`. That keeps today's
  meaning of an absent `markdown` (plain text, Workspace.qml:2839). An explicit `noteTypes` wins.
- Entries that are not valid ids are dropped. Valid ids the app does not know stay declared (such notes open read-only,
  D3) but are never offered for creation.
- **One normaliser**, `services/notes/capabilities.js` (`.pragma library`), is the only reader of provider capability
  members. Every host read goes through it:
  - the Workspace editor bindings (Workspace.qml:2831-2848);
  - the focus choice after create (Workspace.qml:1932-1936);
  - `sidebar.js row()` (`hasTitle`, sidebar.js:26);
  - NoteSession's type resolution;
  - the creatable-type list used by the chooser and WorkspaceActions.

```js
.pragma library

// What a provider declares, read one way. Every default the contract gives an
// absent member lives here (docs/providers.md, "Properties the host reads").
var TYPE_ID = /^(?:[a-z][a-z0-9-]{0,31}|[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+\/[a-z][a-z0-9-]{0,63})$/

function validTypeId(value) {
  return typeof value === "string" && value.length <= 128 && TYPE_ID.test(value)
}

// The note types a provider keeps, its default first. `markdown` is the legacy
// shorthand: true is ["markdown"], anything else ["text"].
function noteTypes(provider) {
  var value = provider.noteTypes
  var declared = value && typeof value === "object" ? Array.from(value).filter(validTypeId) : []
  if (declared.length > 0) {
    return declared
  }
  return [provider.markdown === true ? "markdown" : "text"]
}

function defaultType(provider) {
  return noteTypes(provider)[0]
}

// A note's type from what its provider said of it, or the provider's default.
function typeOf(provider, value) {
  return typeof value === "string" && value !== "" ? value : defaultType(provider)
}

function hasTitle(provider) {
  return provider.hasTitle !== false
}

function canImages(provider) {
  return provider.canImages === true
}

function tools(provider) {
  return provider.tools !== undefined ? provider.tools : null
}
```

- **The absent-`hasTitle` bug is fixed** by the same move:
  `hasTitle: { var p = root.providerOf(root.currentPath); return p ? Capabilities.hasTitle(p) : true }` always yields a
  bool. Today the binding (Workspace.qml:2841-2844) yields `undefined`, Qt warns "Unable to assign [undefined] to bool"
  and keeps the previous note's value. `newNote` focuses the title by the same rule (today it treats absent as false,
  Workspace.qml:1932).
- Built-in declarations:

  | Provider | Phase 1 | Phase 4 |
  |---|---|---|
  | local | `["markdown"]` | `["markdown", "timeline"]` |
  | sticky | `["text"]` | — |
  | onenote | `["markdown"]` | — |
  | notion | `["markdown"]` | — |
  | examples/hello | `["markdown"]` | `["markdown", "timeline"]` |

  Built-ins drop the `markdown` bool, since the host they ship with reads `noteTypes`. The docs keep `markdown` as the
  legacy shorthand, kept by any provider that must also run on Note Note 1.0.40 or older.

**Rationale.** Additive and feature-detected, exactly like `reorder`. A single normaliser stops the defaults from
drifting further: today absent `hasTitle` means true in sidebar.js:26, false in newNote and "keep the previous value"
in the binding.

**Rejected.**
- Declaring types in `plugin.json`: capabilities are live QML properties today; the manifest validates only `id`,
  `path` and `order` (manifest.py:79-87), and a manifest change drags `check.py` and the skill along for no gain.
- Deriving types from `tools` (a `todo` capability is not a timeline).
- Per-section declarations (no provider needs them).
- Keeping `markdown` as the only switch (it cannot mix types within one provider).

**Evidence.** Workspace.qml:2831-2848, 1932-1936; services/notes/sidebar.js:24-31; services/notes/ordering.js:5-18
and docs/providers.md:170-175 (precedent); docs/providers.md:47-54; contract map Q5 (the "Unable to assign" warning,
verified on Qt 6.11.2).

### D3 — Per-note type reporting

**Decision.**
- **The load answer's `type` is authoritative** for which body edits the note. When it is absent, the type is
  `Capabilities.defaultType(provider)`.
- **Rows and notes carry `type` for display only.** Note rows and `sections[].notes` entries carry an optional `type`,
  omitted for the default type; the list draws it as a glyph. `sidebar.js row()` copies it — the list draws it, which
  is what docs/decisions.md:444-448 requires of a row field. It must ride on `notes` too, because search results and
  folded trees use `notes` (sidebar.js:62).
- The save answer carries no type in v1, since the type never changes after creation (D5). The create answer stays
  `{ path, error }`; the type arrives with the load that follows.
- **On a mismatch**, the editor follows the load and the row follows the next listing. Nothing is written to reconcile
  them.
- **An unknown or ill-formed id** opens the note read-only: its body shows as plain text in the document editor, with
  the reason "This note is a “<id>” note, which this version of Note Note cannot edit, so it opened read-only" (the id
  is shown as plain text, cut to 64 characters). Nothing can be written, so the provider's marker survives. A provider
  may report a type it does not declare; the note opens per the registry.
- The OneNote script's per-page `markdown: True`, which nothing reads (onenote.py:1380-1381, 1387), is removed, so
  `type` is the one per-note signal.

**Rationale.** Rows cannot drive the editor: a created note may not be listed yet, and drafts restore without a load
(contract map risk 1). The read-only fallback follows the precedents for absent contributions — layouts keep naming
missing tools, and a missing theme falls back without rewriting settings — and the rule "read-only rather than lossy
writes".

**Rejected.**
- Rows as the authority (late or missing).
- Requiring both and failing on a mismatch (punishes harmless listing lag).
- Host-side "repair" writes (a write without a user action).
- Opening unknown types as editable Markdown (that could write a type's structure through the wrong editor).

**Evidence.** services/notes/NoteSession.qml:233-300; services/notes/sidebar.js:24-31, 59-70; docs/decisions.md:444-448,
660-697; docs/plugins.md:129-134; docs/editing-tools.md:233-236; plugins/org.note-note.onenote/onenote.py:1380-1387.

### D4 — Creation

**Decision.**

Contract:
- **`create(target, cb, options)`.** The host always passes `options = { type }`, with a type from the provider's
  `noteTypes`. A two-argument provider ignores it and makes its default; it declares one type, so the host never asks
  it for another. The answer is unchanged.
- **`action(path, value, sectionKey, options)`.** The footer action marked `shortcut: "newNote"` receives
  `options.type` when the user chose a type, and passes it on as `host.newNote(id, target, options.type)`. No other
  action receives `options`. This is the extra-ignorable-arguments precedent, docs/providers.md:197-198.
- **`host.newNote(providerId, target, type)`.** `type` is optional; a falsy value means the provider's default. A type
  the provider does not declare, or the registry does not know, is refused with
  `"<provider name>: this notebook cannot hold <label> notes"`. Otherwise the host calls
  `p.create(target, cb, { type: chosen })`.

Host:
- `Workspace.creatableTypes(provider)` = `editor.noteTypes.creatable(Capabilities.noteTypes(provider))`: the
  declared ids the registry knows, in declared order.
- `Workspace.runFooterAction(action, value, options)` passes `options` to `p.action(path, value, section, options)`.
- `Workspace.chooseNewNoteType(footerAction)`:
  1. Takes the given footer action, or the active tab's action with `shortcut === "newNote"`.
  2. Lists its provider's creatable types in `commandPalette.pick(...)`. The title is `New note in “<tab name>”`. The
     items are `{ id: typeId, label, detail: description, keywords: [typeId] }`, with the default preselected.
  3. On accept: `commandPalette.close()`, then `runFooterAction(action, "", { type: id })`. With no New Note footer
     action, it calls `newNote(destination.provider.id, undefined, id)` instead.

Where creation is offered:
1. **Unchanged.** Ctrl+N, the palette's "New Note", the provider's New Note footer row and `+ New note…` tree rows
   create the default type. In v1, `+ New note…` rows create the default only.
2. **New workspace action `newNoteOfType`.**
   - Palette command `org.note-note.workspace/new-note-of-type`, "New Note of Type…"; default key **Ctrl+Alt+N**.
   - It calls `chooseNewNoteType()`.
   - Available only when the destination declares two or more creatable types; otherwise unavailable with "This
     notebook makes one kind of note."
3. **Footer chooser.** On the footer row a provider marks `shortcut: "newNote"`, when that provider declares two or
   more creatable types, the host draws a trailing chooser button (glyph 󰅀 U+F0140, tooltip "Choose the kind of
   note") that opens the same picker.
   - This amends docs/providers.md:185 ("It does not add creation buttons based on provider identity or
     capabilities"). New text: the host adds one control, the type chooser on the `newNote` row, driven by the
     provider's own `noteTypes`. Providers never add a footer row per type.

**Rationale.** Typed creation must reuse the provider's own target logic. In notebook-tab mode, local's New Note files
the note in the open tab's section (`"section:" + sectionKey`, local Provider.qml:275-278), which `createTargetFor`
cannot know when no note is open. One chooser, one key and one command serve every future type, with zero host changes
per type and no footer growth: each footer row costs `Style.space(32)` (NoteList.qml:716), and TitleBar.qml:112-116
records the codebase's case against rows of buttons that grow.

**Rejected.**
- Encoding the type in `target`: a hack, since providers parse their targets (local Provider.qml:556; OneNote
  1135-1141; Notion 248).
- A footer row per type: grows per type and per provider.
- A per-type workspace action such as `newTimeline`: four host edits for every new type.
- Row-menu entries: pointer-only (NoteList.qml:611-617).
- A modal type dialog: business-requirements.md:29-31.
- The host setting a "pending type" before activating the footer row: temporal coupling.

**Evidence.** Workspace.qml:1668-1703, 1873-1938, 2726-2734; services/commands/WorkspaceActions.qml:18-48, 63-98;
services/shortcuts/defaults.js:21-24; plugins/org.note-note.workspace/plugin.json:8-60;
ui/commands/CommandPalette.qml:116-138, 179-190; docs/providers.md:181-213, 283-291, 350-357; ui/NoteList.qml:689-732.

### D5 — Changing a note's type after creation

**Decision.** Not in the first release; nothing writes a type after creation. The design leaves room for it in three
ways:
- **The type is part of every snapshot.** Every document snapshot, draft and `stored` entry already carries the type,
  so a conversion would be "a document of another type" through the same session path.
- **The safe directions are known.** Timeline → Markdown is always lossless, because the timeline body is Markdown.
  Markdown → timeline is lossless exactly when `Timeline.parse` accepts the body. A later pane action, "Change type",
  offers only lossless directions.
- **The contract has an obvious extension.** The save contract would gain `options.type`, and providers a
  `canChangeType` flag. Local would rewrite its `note-note-type` line inside the `operations.py` save.

The docs say nothing about conversion until it exists.

**Rationale.** No requirement needs it now. Only local could store a changed type (OneNote and Notion cannot mark
types at all). Its absence costs one recorded limit: a timeline edited elsewhere into something that is not a timeline
stays read-only in Note Note (D8).

**Rejected.**
- Conversion now: more contract surface, and one provider able to do it.
- A host-kept "open as Markdown" override per path: a second source of truth for a note's type, path-keyed, so it would
  need re-keying in `replacePath` (the F1 class of bug).

**Evidence.** NoteSession.qml:37-43, 362-367, 471-507; plugins/org.note-note.local/operations.py:126-141; OneNote map
(no durable page marker); Notion/Sticky map (no invisible metadata).

### D6 — Note pane architecture

**Decision.** `ui/NoteEditor.qml` stays the one pane (`id: editor`, `objectName: "noteEditor"`) and becomes a host of
bodies.

**What the pane owns.** The toolbar row, the modified date, the title field, notices, provider views, the conflict
review, the skeleton, `readOnly`, `noteToken`, `documentBase`, and `typeId` (the open note's type id as stored).

**The pane protocol** (what NoteSession and Workspace call):

| Member | Meaning |
|---|---|
| `setNote(document, shown)` | `document = { type, title, body, base }`; `shown(ok, refusal)` once the body holds it |
| `clearNote()` | no note: token bumped, title "", typed body unloaded, document emptied |
| `restoreDocument(snapshot)` → `refusal` | a snapshot this pane took; activates `snapshot.type` first |
| `snapshotDocument()` | `{ type: typeId, title, body: body.snapshotBody(), base }` |
| `requestBody(callback)` | `body.requestBody(callback)`; `callback(body, ok)` |
| `viewState()` / `restoreViewState(s)` | the active body's |
| `focusEditor()` / `focusBody()` / `focusTitle()` | the active body's `focusBody()` / `focusStart()`; the title |
| `countText`, `formOpen`, `documentActive`, `noteTypes` | ViewBar text; key gate; document editor active; the registry (alias) |

**The NoteBody contract.** `ui/notetypes/NoteBody.qml` is a `FocusScope` with `apiVersion: 1`:

| Member | Meaning |
|---|---|
| `required property var host` | the narrow API below, given at creation |
| `countText` | what the view bar counts ("3 of 7 done"); "" shows nothing |
| `formOpen` | a form in the body has the keyboard; the workspace runs no shortcut under it |
| `focused` (readonly) | `activeFocus` |
| `setBody(text, shown)` | the provider's body; `shown(ok, refusal)`: `ok` false = could not show; a refusal = shown but this body cannot write it back |
| `restoreBody(snapshot)` → `refusal` | a snapshot this body took |
| `snapshotBody()` | canonical string, equal for equal content |
| `requestBody(callback)` | what the provider stores; `callback(body, ok)`, `ok` false sends nothing |
| `viewState()` / `restoreViewState(s)` | where the reader is |
| `focusBody()` / `focusStart()` | keyboard in, where it was / at its start |
| `clear()` | drop the content, forms and undo |

**`bodyHost`** is a QtObject inside the pane, the narrow API bodies get:
- properties: `readOnly` (`root.readOnly || !root.hasNote`), `foreground`, `accent`, `background`, `fontFamily`,
  `noteFontFamily`, `bodyFontSize`;
- functions: `shortcut(event)` (app shortcuts first, as the title and the document do), `edited()`, `status(text)`,
  `focusTitle()`.

**The document editor stays where it is.** The rich/plain TextEdit and all its code stay in NoteEditor.qml,
permanently instantiated. They answer the protocol through an internal `documentBody` adapter (a QtObject) that calls
the existing document functions:
- today's `setNote` conversion path is renamed `showDocument(text, shown)`;
- `requestMarkdown` is unchanged;
- today's `viewState`/`restoreViewState` are renamed `documentViewState`/`restoreDocumentViewState`, so the pane-level
  names can dispatch;
- `resetAudio()` and `editing.clearPending()` move into `showDocument`/`clear`.

**Typed bodies.** A typed body loads in `Loader { id: bodyLoader }`, a sibling of `flick` in the sheet:
- created by `bodyLoader.setSource(type.body, { host: bodyHost })`, synchronous for a local file;
- kept across notes of the same type, unloaded otherwise;
- `visible: item !== null && !root.showingNotice`;
- `readonly property var body: bodyLoader.item !== null ? bodyLoader.item : documentBody`.

**Type before body, by construction.** `setNote(document, shown)`:
1. `++noteToken`.
2. `activateType(document.type)`. This looks the type up in the registry, then either loads a typed body (and empties
   the document), or sets `plain` from `documentFormat`. An unknown type, or a body that fails validation, falls back
   to the document editor in plain format with a refusal reason.
3. Sets the title under `settingText`.
4. Sets `documentBase = document.base`.
5. Calls `body.setBody(document.body, …)`, whose callback checks the token. If the body answers `ok` with a refusal,
   the pane unloads it and shows the same text in the document editor as plain text (`showAsText`), then calls
   `shown(true, refusal)`.

One fallback serves both "unknown type" and "this body cannot hold this text".

```js
// The pane: a note goes in with its type, and the type picks the body first.
function setNote(document, shown) {
  var token = ++root.noteToken
  var refusal = root.activateType(document.type)
  root.settingText = true
  titleField.text = document.title
  titleField.cursorPosition = 0
  root.settingText = false
  root.documentBase = document.base || ""
  root.body.setBody(document.body, function(ok, bodyRefusal) {
    if (token !== root.noteToken) {
      return
    }
    if (ok && bodyRefusal) {
      root.showAsText(document.body)
    }
    if (shown) {
      shown(ok, refusal || bodyRefusal || "")
    }
  })
}
```

**Keeping the hidden document inert.** `documentActive` (= `root.body === documentBody`) is added to:
- `EditorApi.writable` (EditorApi.qml:13), so tools and the toolbar stand down;
- `applyReadOnly` (`area.readOnly = !hasNote || readOnly || !documentActive`);
- `flick.visible`;
- the guards of `paste()`, `pastePlain()`, `undo()` and `redo()`, which IPC can reach.

**Key routing.**
- `Workspace.handleShortcut` returns false while `editor.formOpen`, beside `editor.tools.panelOpen`
  (Workspace.qml:2150).
- `WorkspaceActions.blocked` includes `editor.formOpen` (Workspace.qml:2545-2547).
- `shortcutContext()` is unchanged: `bodyFocused` stays the TextEdit's focus, so a focused timeline is the
  `workspace` context, and tool and paste bindings never reach it.

**Host-level facts stay on the pane.** `canColorText`, `tools.actions`, `toolbarHeight` and `toolbarRowHeight` stay
valid because the document editor is a permanent part of the pane. `wordCount` and `hoveredLink` remain document
facts; `hoveredLink` is "" whenever the flick is hidden. The ViewBar shows `editor.countText`.

**Rationale.**
- It keeps about 50 Workspace `editor.*` references, notices, the conflict review and the toolbar alignment intact
  (session map recommendation).
- From day one the protocol has two very different implementations, the rich document and the timeline, which proves
  the seam before anyone else depends on it.
- The pane never names a type.
- Activating the type inside `setNote` makes "type before body" structural rather than a calling convention.

**Rejected.**
- A third flag threaded like `plain` (about 20 branches; CLAUDE.md forbids spaghetti).
- Swapping NoteEditor at Workspace level: it orphans about 50 references, and theming and key bindings would flap with
  the open note (editor map risks 1-2).
- Extracting the document editor into `DocumentBody.qml` now: about 1000 test references to `editor.*` internals
  (EditorKeys alone has 147 `plainText`, 102 `documentHtml`, 84 `setCursorPosition`) for no user value. This is
  recorded as a later, behaviour-free refactor, triggered when a second document-like body appears.
- Creating the rich editor per note: `canColorText` and `tools.actions` would change with the open note.
- A path-keyed type map in the session: `replacePath` would have to re-key it (F1 class).

**Evidence.** ui/NoteEditor.qml:24-34, 72, 112-134, 152-167, 237-247, 292-345, 357-383, 1778-1833, 1843-2035, 2075,
2401-2407; ui/editing/EditorApi.qml:13; Workspace.qml:122-123, 2135-2176, 2245-2250, 2520, 2543-2556, 2714-2715,
2916-2921; tests/transitions.qml:375-400 (the session needs only this protocol).

### D7 — Note-type registry and extensibility

**Decision.**

The contract object, `ui/notetypes/NoteType.qml` (a QtObject):

| Member | Meaning |
|---|---|
| `apiVersion: 1` (readonly) | contract version |
| `typeId` | the id providers file the type under |
| `label` | the user's name for it ("Timeline") |
| `description` | the picker's detail line ("Events you check off in order") |
| `icon` | Nerd Font glyph for the list; "" marks nothing |
| `body` (url) | the NoteBody file; "" for the document editor |
| `documentFormat` | `"plain"` or `"markdown"` for document types; "" otherwise |

The registry, `ui/notetypes/NoteTypeRegistry.qml`:
- Owned by the pane (`readonly property alias noteTypes: typeRegistry`), as the pane owns ToolRegistry.
- Declares the core types:
  - `text` — "Text note", plain;
  - `markdown` — "Note", markdown;
  - `timeline` — `TimelineType {}` from `ui/notetypes/timeline/`, with icon 󱔳 U+F1533. The code point is present in
    the bundled `assets/fonts/nerd-symbols/SymbolsNerdFont-Regular.ttf`; I rendered it as "timeline with check
    marks".
- Validates at completion, ToolRegistry-style: `apiVersion === 1`, a core-grammar id, unique ids, a non-empty label,
  and exactly one of `body` and `documentFormat`. A rejected type is logged as `Note type skipped: <reason>` and listed
  in `errors`.
- API:
  - `types`, `find(id)` → NoteType or null;
  - `label(id)`, `icon(id)` ("" when unknown);
  - `creatable(ids)`;
  - `unknownReason(id)`;
  - `bodyError(item)` — `apiVersion` and the NoteBody function members present, else a reason;
  - `definitionError(type)`.
- Static and synchronous. Nothing waits for the plugin catalog, so opening a note is never gated on registry
  readiness.

**No sixth catalog kind now.** The trigger for opening note types to packages is recorded in docs/decisions.md; all
three must hold:
1. a second non-document core type exists;
2. a concrete external type is wanted;
3. NoteBody has been unchanged for a release.

The template is commit 2c5920f's file list:
- `manifest.py` (`KINDS`, `BUILDERS`, `executable`);
- `PluginCatalog.noteTypes`;
- `extensions/NoteNote/Extensions/NoteType.qml` and `NoteBody.qml`, plus their qmldir lines;
- a registry `sources()` that appends catalog descriptors;
- docs/plugins.md, SKILL.md, a new `references/note-types.md`, `check.py`, an example package, and tests.

Package types would use qualified ids. A disabled or removed package's notes open read-only as text (D3).

**Rationale.**
- The user's stated future is more first-party types. An internal registry with a versioned contract delivers "a new
  type is one folder" now.
- The tools precedent is internal first: `ui/tools` with Tool and ToolRegistry existed long before 2c5920f made tools
  a package kind.
- A note type, unlike a tool, owns persistent user data. Its body API is a public surface that cannot change silently
  (technical-requirements.md:99-101), and it should not be frozen from a single example.

**Rejected.**
- The plugin kind now. On top of the reasons above: older app versions reject a whole package that declares an
  unknown kind (manifest.py:142-144), and type QML runs unsandboxed in the shell's engine, so a broken type takes the
  shell down.
- FolderListModel discovery like `ui/tools`: asynchronous readiness would gate note loading (extensibility map risk 6),
  for three types.
- The timeline as `plugins/org.note-note.timeline`: it needs the kind, and users could disable the editor of their own
  notes.

**Evidence.** ui/editing/ToolRegistry.qml:111-136, 138-224; ui/editing/Tool.qml:1-68; services/extensions/manifest.py:30,
98-101, 142-144, 151, 203-206; commit 2c5920f (`git show --stat`); docs/decisions.md:991-1005; docs/plugins.md:72-75,
129-134; skills/note-note-plugin/SKILL.md:32-33 (an app-owned component that is "not a plugin kind").

### D8 — Timeline data model and canonical format

**Model.** `events: [{ checked: bool, title: string, description: string }]`.
- `title`: one line, trimmed, non-empty, at most 300 characters (code points, `Array.from(text).length`).
- `description`: "" or at most 40 lines joined by `"\n"`, each line trimmed, no empty lines, at most 4000
  characters.
- At most 1000 events.

**Canonical body** — the serializer's only output (`␠` marks a trailing space):

```
- [x] **Book flights**␠␠
  Return on the 14th
- [x] **Reserve hotel**
- [ ] **Pack the bags**␠␠
  Passport, adapters␠␠
  Chargers
- [ ] **Go to the airport**
```

- One line per event: `- [x] ` or `- [ ] `, then `**`, the escaped title, `**`.
- Each description line is on its own line, indented two spaces.
- Every line of an event except its last ends with two spaces: a Markdown hard break.
- No blank lines, LF endings, a final LF. An empty timeline is the empty string.

**Escapes**, text → file:

| Character | Escaped |
|---|---|
| `` ` `` `*` `[` `]` `\|` | always |
| `\` | when followed by ASCII punctuation, or at the end of the text |
| `_` | when it could open or close emphasis, i.e. not between two word characters (mdtext's `_emphasises`) |
| `~`, `=` | when next to the same character |
| `<` | before a letter, `/`, `!` or `?` |
| `&` | when it starts `&name;`, `&#123;` or `&#x1F;` |
| `#` `>` `+` `-` `=` | at the start of a description line |
| `.` or `)` | after a number that starts a description line (`1\.`) |

Checked against the repo's mistune dialect (`services/markdown/parse.py`) on 12,000 seeded random models, whose
alphabet was all ASCII punctuation, tabs, NBSP and non-ASCII: zero round-trip failures, zero disagreements. In mistune
every body is one task list whose items carry exactly the titles, descriptions and states.

**Reader**, file → events, tolerant:
- CRLF and CR are normalised; blank lines are skipped, so loose lists are accepted.
- **Event line**: `^[-*+] \[([ xX])\](?:[ \t]+(.*))?$` at column 0.
  - Trailing whitespace and a trailing unescaped backslash are removed (both hard-break spellings).
  - The surrounding `**` is removed when present.
  - CommonMark backslash unescape: `\` + ASCII punctuation → the punctuation; any other backslash is literal.
- **Description line**: indented 2–5 spaces, or a tab, after an event; trimmed and unescaped the same way. Soft
  breaks are accepted: the lines decide.
- **Refusals** (read-only, with the reason naming the line):

  | Found | Reason |
  |---|---|
  | a non-blank line before the first event, or a column-0 line that is not an event | "text that is not an event" |
  | a description line starting a block (`#`, `>`, a list marker, a fence, `\|`, an HTML tag) | "a list, heading, quote, table or code in an event" |
  | indentation of 6 or more | code |
  | an event without a title | an event with no title |
  | any limit exceeded | the limit |
  | a body over 2,097,152 characters | not read at all |

  The reason reads, for example, "This timeline holds text that is not an event (line 4), so it opened read-only".
- Inline Markdown typed into a timeline elsewhere (`*socks*`, `` `x` ``) reads as its characters, shows as them, and
  is written back escaped on the next change — never dropped. This is a documented limit.

**Where the code lives.**
- `ui/notetypes/timeline/Timeline.js` (`.pragma library`; pure; no regex lookbehind, per engine-notes.md:17-19):
  `parse`, `serialize`, `setChecked`, `append`, `replace`, `remove`, `move`, `progress`, `countText`, `problem`, and
  the limit constants.
- Python reads timelines only for list previews: `notefile.timeline_summary(body)`, the event-line regex plus title
  decoding. `ui/notetypes/timeline/selftest.py` cross-checks it against the JS codec.

**Lossless guarantees.**
- `parse(serialize(e))` deep-equals `e` for every valid model (property test).
- `serialize(parse(b)) === b` for every canonical `b`.
- The canonical form is a fixpoint of the app's own Markdown round trip (`to_markdown(to_html(b)) == b`), and
  `qthtml.unkept(b) == []`. Both were verified at HEAD for the example above. So a timeline opened by 1.0.40, or one
  that has lost its type line, is an ordinary editable checklist.

**Rationale.** The body stays a plain Markdown checklist — goal 3 "your files stay yours", readable and checkable on
GitHub, Obsidian or a phone. Event text stays inside the body, so search finds it unchanged. Bold titles keep title and
description apart in every other renderer. Hard breaks survive the app's own editor; soft breaks do not.

**Rejected.**
- Events as front-matter YAML: there is no YAML parser and none may be added (pyproject.toml:13-17); front matter is
  not searched (search.py:52); and it is not a checklist anywhere else.
- A fenced JSON block: unreadable, and code to every other tool.
- An HTML comment marker in the body: `unkept` → read-only in the Markdown editor (local map 3.12).
- Loose items with paragraph descriptions: Notion's writer refuses multi-paragraph items (notion_md.py:440-467), and
  the app's editor rewrites the shape — verified: not a fixpoint, the blank line before the next item is dropped.
- Soft-broken descriptions: verified — the app's editor writes `- [x] **Book flights** Return on the 14th`, merging
  title and description.
- Unbolded titles: title and description become indistinguishable elsewhere.
- mdtext's lenient escaping as it stands: its context rules assume spaces at the edges; with `**` delimiters about 2%
  of 12,000 random models failed.
- Refusing inline Markdown from elsewhere: false positives would lock common text such as "[draft]" or "5 * 3".
- A Python twin of the codec deciding editability in the provider: two codecs to keep in step, and providers would
  need the grammar.

**Evidence.** services/markdown/parse.py:72-74, 120-135; services/markdown/mdtext.py:46-106;
services/markdown/qthtml/selftest.py:117 (case "list item hard break"); plugins/org.note-note.local/search.py:49-52;
experiments `architect-exp/grammar.py`, `escapes.py`, `proto.py`, `lenient.py`, `variants.py`.

### D9 — Check semantics

**Decision.**
- **Checking.** Space or a click on an unchecked event `k` checks events `0..k`.
- **Unchecking.** On a checked event `k`, it unchecks events `k..n-1`.
- Each is one undo step and emits `edited()` once.

```js
// Checking an event checks every event above it: the timeline is done up to
// there. Unchecking one unchecks every event below it, for the same reason.
// Answers a new list; the one given is not changed.
function setChecked(events, index, checked) {
  return events.map(function(event, at) {
    var reached = checked ? at <= index : at >= index
    if (!reached || event.checked === checked) {
      return event
    }
    return { checked: checked, title: event.title, description: event.description }
  })
}
```

**Order broken elsewhere.** A state that breaks the prefix rule (edited elsewhere, or a merge) is shown exactly as
stored:
- each circle shows its own state;
- the progress counts checked events, and "next" is the first unchecked one;
- the spine is accent only between two checked events.

Nothing is written until the user acts. The next check or uncheck applies the rule and restores a prefix.

**Undo and redo.**
- A body-owned stack of event arrays, 200 steps.
- Ctrl+Z, Ctrl+Shift+Z and Ctrl+Y while the list has focus. These keys are reserved from bindings (stroke.js:17-24),
  so they reach only the focused item.
- Cleared when another note is shown; never persisted.

**Rationale.** "Check one, check all above" is the user's rule. The mirror rule for unchecking keeps "the checked
events are how far along the timeline is" true after every action.

**Rejected.**
- Unchecking only `k`: it leaves exactly the holes the rule exists to prevent.
- Repairing on load: a write without a user action.
- Refusing out-of-order states read-only: common after an edit elsewhere, and harmless.
- Building it on Qt's TextEdit checkbox toggle: Qt's own single-item toggle, with no hook (NoteEditor.qml:2219-2223).

**Evidence.** ui/NoteEditor.qml:2219-2223; services/shortcuts/stroke.js:17-24; OneNote map ("never write anything to
'restore' it without the user's action"); notion-sticky map (Notion lets any to-do be checked alone).

### D10 — Timeline view UX

**Files.**

| File | Role |
|---|---|
| `ui/notetypes/timeline/TimelineBody.qml` | `NoteBody`; a `ListView` over `events` |
| `ui/notetypes/timeline/TimelineEvent.qml` | one row |
| `ui/notetypes/timeline/EventForm.qml` | the inline form |
| `ui/CheckMark.qml` | the drawn check face, extracted from NoteEditor.qml:2242-2284; the document overlay uses it unchanged |
| `ui/ChromeTextArea.qml` | a multi-line field on `ChromeControlStyle`; the first in the design system |

**Layout.**
- A left gutter holds the spine and circles; text sits to its right.
- Circle diameter `side = Math.round(host.bodyFontSize * 1.1)`; gutter = `side + 2 * Style.spacing.lg`.
- Spine: a 2 px line through the circle centres. The segment between event `i` and `i+1` is `host.accent` when both
  are checked, otherwise `Util.alpha(host.foreground, 0.25)`.
- Title: `host.noteFontFamily` at `host.bodyFontSize`, `Text.PlainText`, wrapped.
- Description: below the title, `Math.round(host.bodyFontSize * 0.9)`, `Style.secondaryText(host.foreground, 0.65)`,
  wrapped.
- Rows are spaced `Style.spacing.lg`.
- Only Style keys both hosts define are used (design/Style.qml:20-47).

**States.**

| State | Look |
|---|---|
| unchecked circle | border `Util.alpha(fg, 0.4)`, 0.75 on hover; width `max(1.2, side/9)` |
| checked circle | `host.accent` fill, tick cut out in `host.background` (CheckMark `round: true`) |
| done event | title in `Style.secondaryText(fg, 0.6)` |
| next event (first unchecked) | title bold, full ink |
| keyboard cursor | row fill as NoteList's hover, plus a 2 px accent ring around the circle (TextColor swatch precedent) |
| hover | a pointing-hand cursor on the circle; trailing edit 󰏫 (U+F03EB) and delete 󰆴 (U+F01B4) ChromeButtons, also shown for the cursor row |
| read-only | circles inert, no hover actions, no add row; the cursor still moves |

Colour changes animate with a 120 ms ColorAnimation.

**Add row and empty state.**
- "Add new event": a `+` in accentInk (`Qt.tint(fg, Util.alpha(accent, 0.6))`), the label at `Style.font.bodySmall`,
  dimmed to `Style.secondaryOpacity(0.65)` until hover or cursor, and a right-aligned hint "Ctrl+Enter".
- Empty timeline: "No events yet" in secondary ink above the add row. When an empty timeline is entered with
  `focusStart()` (the title's Enter or Down), the add form opens at once.

**The form** is inline and non-modal: in place of the add row when adding, in place of the event's text when editing.
- A ChromeTextField (placeholder "Event", leading glyph 󱔳) and a ChromeTextArea (placeholder "Description
  (optional)", two lines tall, growing to eight).
- The footer is the hint "Enter to add · Ctrl+Enter from the description · Esc to cancel", or `message` in
  `Color.urgent` when the input fails `Timeline.problem()`.
- One focusable Button, "Add" or "Save". There is no Cancel button (docs/editing-tools.md:345-364).
- After Add, the form stays open, cleared, for the next event. After Save, it closes, with the cursor on the edited
  event.
- Focus leaving the form cancels it (the SidebarAction and rename-field convention).

**Keyboard.**

The list has focus (the form is closed). Every key goes to `host.shortcut(event)` first, so app keys work — Escape
(back), Ctrl+N, Ctrl+K, Ctrl+Up/Down and the rest. Then:

| Keys | Action |
|---|---|
| Up / Down | previous / next event. Down from the last event reaches the add row; Up from the first goes to the title (`host.focusTitle()`) |
| Home / End | first event / add row |
| PageUp / PageDown | eight events |
| Space | check or uncheck the cursor event (D9) |
| Enter / Return | edit the cursor event; on the add row, open the add form |
| Ctrl+Enter | add form, from anywhere in the list |
| Delete | remove the cursor event; undoable, no confirmation |
| Alt+Up / Alt+Down | move the cursor event |
| Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y | undo / redo |

The form has focus. `formOpen` is true, so the workspace runs no shortcut.

| Keys | In the title field | In the description |
|---|---|---|
| Enter | submit, if the input is valid | new line |
| Ctrl+Enter | — | submit |
| Tab / Down | to the description | — |
| Shift+Tab, or Up on the first line | — | to the title |
| Esc | cancel | cancel |

Mouse:
- a click on a circle checks or unchecks;
- a click on the text moves the cursor there; a double-click edits;
- the add row opens the form.

Drag reordering is a later release; Alt+Up/Down cover v1.

**Shortcut context.** `workspace`: `bodyFocused` is the TextEdit's, so tool and paste bindings never reach a timeline.

**Accessibility.** This sets the app's first `Accessible.role` precedent, documented in docs/note-types.md.
- Each event: `Accessible.role: Accessible.CheckBox`, `Accessible.name` = title, `Accessible.description` =
  description, `Accessible.checkable: true`, `Accessible.checked`.
- Add row: `Accessible.Button`, "Add new event".
- List: `Accessible.List`, "Timeline".
- Form fields: "Event title", "Event description".

**objectNames.** `timelineBody`, `timelineList`, `timelineEvent-<i>`, `timelineCheck-<i>`, `timelineEventTitle-<i>`,
`timelineEventEdit-<i>`, `timelineEventDelete-<i>`, `timelineAddEvent`, `timelineEmpty`, `timelineForm`,
`timelineFormTitle`, `timelineFormDescription`, `timelineFormSubmit`, `timelineFormMessage`.

**Theme.** No new tokens. Inks derive from the pane's `foreground`, `accent` and `background` (fed from
`editor.foreground`, `editor.background` and the accent), the way the checkbox overlay does. Glyph Texts use
`Style.fontFamily`.

**Rejected.**
- A modal dialog for the form (goal 2; ui map risk).
- ToolForm (hard-typed to `Tool`, ToolForm.qml:13).
- Single-line descriptions (the user asked for a description; multi-line costs one control).
- Enter submitting from the description (it breaks every multi-line text convention).

**Evidence.** ui/NoteEditor.qml:2219-2291; ui/tools/TextColor.qml:49-96; ui/NoteList.qml:73-79, 440-492;
ui/SidebarAction.qml:5-41; ui/editing/ToolForm.qml:11-88; docs/editing-tools.md:345-364;
docs/business-requirements.md:29-31, 82; ui-design map Q4/Q5.

### D11 — List and search integration

**Decision.**

The glyph:
- `sidebar.js row()` copies `type: source.type || ""`.
- `NoteSummary` gains `property string icon`, drawn before the title: `Style.fontFamily`, `Style.font.iconSmall`,
  `Style.secondaryText(foreground, 0.55)`, a `Style.spacing.sm` gap.
- `NoteList` (ui/NoteList.qml:447-461) and `SearchResults` (ui/SearchResults.qml:104-117) pass
  `icon: root.typeIconFor(row.type)`.
- Workspace passes `typeIconFor: function(type) { return editor.noteTypes.icon(type) }`, beside `titleFor`.
- `text` and `markdown` have no glyph; unknown types have none.

The preview:
- **The provider computes a timeline's preview.** Local uses `notefile.preview(body, "timeline")` →
  `timeline_summary(body)`:
  - `"3/7 · Pack the bags"` — done/total, then the next event's title;
  - `"7/7 ✓"` — all done;
  - `""` — no events.
- The local listing reads a timeline note whole, up to 256 KiB; beyond that it gives the generic first-line preview.
- The save answer returns the preview, so the row updates when the save lands (local: a 500 ms debounce plus the
  write).

No host-side projection of unsaved previews in v1. The documented future seam is an optional synchronous
`NoteType.summary(snapshotBody)` projected like `NoteSession.unsavedTitles`, for slower providers.

Search:
- Provider body search finds event text unchanged.
- Title/preview matching (sidebar.js:19-22) also finds the next event's title.
- Escapes are minimal, so most text matches raw.
- `displayTitle`'s fallback (Workspace.qml:1302-1324) is unchanged.

**Rationale.** The glyph is the one fact rows need, and the list draws it. The summary turns the list into the "where
am I" view a timeline exists for. The provider already owns previews (decisions.md:444-448; notefile.py:79-86).

**Rejected.**
- Host-computed previews: the host has no bodies of unopened notes.
- Structured row fields (`done`, `total`): fields that change on every check, plus per-type formatting in NoteSummary.
- The provider's `icon` row field for note rows: every provider would own type glyphs.
- A per-row unsaved projection now: local lands in under a second.

**Evidence.** services/notes/sidebar.js:19-31; ui/NoteSummary.qml:6-58; ui/NoteList.qml:447-477;
ui/SearchResults.qml:28-29, 104-117; Workspace.qml:1302-1324, 1349-1362, 2721; plugins/org.note-note.local/notefile.py:79-86;
plugins/org.note-note.local/list.py:64, 147-153; services/notes/NoteSession.qml:48-62.

### D12 — Provider support matrix for the first release

| Provider | v1 types | Changes |
|---|---|---|
| local | markdown, timeline | D13 |
| examples/hello | markdown, timeline | `noteTypes: ["markdown", "timeline"]`; stores `type` per note in `notes` (`{ id, title, body, type }`); rows and `load()` report it; `create(target, cb, options)` stores `options.type`; `action(id, value, sectionKey, options)` forwards `options.type` to `host.newNote`. It demonstrates that a provider holding a string per note holds every type, with no grammar code |
| OneNote | markdown | `noteTypes: ["markdown"]`; drop the unread `markdown=True` (onenote.py:1380-1381, 1387). Timeline **deferred** |
| Notion | markdown | `noteTypes: ["markdown"]`. Timeline **deferred** |
| Sticky Notes | text | `noteTypes: ["text"]`. Timeline **unsupported** |

Why each is held back:
- **OneNote.** There is no documented durable page marker; a `data-id` wrapper div is the only candidate, and its
  survival in the OneNote apps is unverified. The converter's to-do and indent edge cases lose data (OneNote map
  section 4). Path later:
  1. a `data-id` marker verified live, recorded in `docs/onenote-timeline.md`;
  2. events written as to-do paragraphs with bold titles;
  3. the converter edge cases fixed first.
- **Notion.** There is no invisible metadata; the marker is a product choice (the page icon recommended). The
  canonical shape maps to one `to_do` with `"title\ndescription"` rich text, which round-trips (Notion probe B). Every
  check is a whole-page rewrite.
- **Sticky Notes.** Plain text with no title; any syntax would show raw in Microsoft's apps (decisions.md:557-561).

**Evidence.** Contract map provider table; OneNote map section 5; notion-sticky map Recommendations;
examples/hello/Provider.qml:14, 38, 63, 90-105, 114-117.

### D13 — Local provider details

**Front-matter key.** `note-note-type:` — column 0, case-sensitive, first occurrence, value trimmed.
- Absent or empty → `markdown`.
- Written only at creation, and only for a non-default type:
  ```
  ---
  title: 
  note-note-type: timeline
  ---
  ```
- It stays one of the "extra" lines, so every save preserves it with no new code: `operations.py` save re-reads the
  current file's extra lines (operations.py:131-136) and `serialize` writes them after the title (notefile.py:75).

**`notefile.py`** owns the key:
- `TYPE_KEY = "note-note-type:"`, `DEFAULT_TYPE = "markdown"`, `TYPE_ID`, `MAX_TYPE = 128`;
- `note_type(extra)`, `type_line(note_type)`, `timeline_summary(body)`, `preview(body, note_type=DEFAULT_TYPE)`;
- the module docstring becomes "The app owns `title` and reads `note-note-type`; it writes the type once, when the note
  is made".

```python
def note_type(extra):
    """The note's type: the first `note-note-type:` line among the front
    matter's other lines, or the default when there is none. A value that is
    not a type ID comes back as written, bounded, so the host can name it when
    it opens the note read-only."""
    for line in extra:
        if line.startswith(TYPE_KEY):
            value = line[len(TYPE_KEY):].strip()
            return value[:MAX_TYPE] if value else DEFAULT_TYPE
    return DEFAULT_TYPE


def type_line(note_type):
    """The front-matter lines a new note of `note_type` starts with."""
    if note_type == DEFAULT_TYPE:
        return []
    if len(note_type) > MAX_TYPE or not TYPE_ID.match(note_type):
        raise ValueError("invalid note type")
    return [TYPE_KEY + " " + note_type]
```

**`list.py`**
- `head_of` returns `(title, preview, type)`.
- For `timeline`, it re-reads the note up to `TIMELINE_BYTES = 256 * 1024` for `timeline_summary`.
- The `N` record gains an 8th field, `type`, and the docstring (list.py:5-11) changes with it.
- An old 7-field record parses as `markdown`.

**`operations.py`**
- read: splits into `(title, body, extra)`; `note_type = notefile.note_type(extra)`;
  `lost = unkept(body) if note_type == "markdown" else []` — the Markdown editor's check judges Markdown notes only,
  and a typed body is judged by its own type at the host. The answer adds `"type"`.
- create: takes payload `type` (default `markdown`); `type_line` raises "invalid note type" for a bad id; writes
  `notefile.serialize("", "", notefile.type_line(type))`. The answer adds `"type"`.
- save: the preview comes from `notefile.preview(body, notefile.note_type(notefile.split(current["text"])[2]))`.

**`search.py`** is unchanged: the body holds the event text.

**`Provider.qml`**
- `readonly property var noteTypes: ["markdown", "timeline"]`.
- `loadList`: `type: p[7] || "markdown"`.
- `folderRows` note rows and `searchable()` carry `type: n.type`.
- `load` forwards `type: result.type` — **trap 1**, the explicit answer object at Provider.qml:509-511.
- The save commit becomes
  `Object.assign({}, note, { title: title.trim(), preview: result.preview, size: result.bytes, version: result.version })`
  — **trap 2**, the explicit entry at :548-549, which would drop `type` and any later field.
- `create(target, cb, options)`:
  - the type is `options && options.type ? options.type : root.noteTypes[0]`;
  - a type not in `noteTypes` → `cb({ error: "this notebook cannot hold that kind of note" })`;
  - the payload is `{ action: "create", key, type }`;
  - the entry carries `type: result.type`.
- `action(id, value, sectionKey, options)`: `newNote` calls `host.newNote(root.id, target, options && options.type ? options.type : "")`.

**Edge.** A front matter longer than 4 KiB, with the type line beyond the listing head, lists as Markdown (no glyph, a
generic preview) and loads as a timeline. The load wins (D3). Titles already behave this way (local map 2.4).

**Rejected.**
- A bare `type:` key: Hugo and Obsidian vaults use `type:`, and the safe unknown→read-only rule would then lock those
  users' notes.
- A scalar `notenote:` key: no room for a second key.
- Owning the key inside `split()`: it changes the 3-tuple for every caller, while the line must round-trip verbatim
  like any extra line.
- A body marker (an HTML comment makes the note read-only through `unkept`).
- A file extension or a sidecar (identity, folder delete: local map 3.10-3.11).
- Inferring the type from the body's shape: any Markdown checklist would become a timeline by accident.

**Evidence.** plugins/org.note-note.local/notefile.py:10-15, 48-86; list.py:5-11, 64, 147-153, 253;
operations.py:19-31, 104-141; search.py:49-52; Provider.qml:20, 205-216, 226-230, 275-279, 429-446, 499-513, 538-575,
677-684.

### D14 — Save, merge, conflict and recovery

**Decision.**
- **Saving.** NoteSession calls `editor.requestBody(cb)` instead of `editor.requestMarkdown(cb)`. The document body
  still uses `requestMarkdown`. The timeline body answers `cb(Timeline.serialize(events), true)` synchronously.
  The framed `(body, ok)` contract is kept — `ok` false sends nothing (decisions.md:523-545).
- **No-op saves.** A snapshot is `{ type, title, body, base }`. `isStored` compares `type`, `title` and `body`. The
  timeline's `snapshotBody` is the canonical serialization, so a check followed by an uncheck sends no save. A
  tolerated but non-canonical file (CRLF, `*` bullets) is rewritten only after a real change.
- **Drafts and recovery.** Drafts, recovered answers (`result.recovered`) and deletion recovery all hold
  `snapshotDocument()`, so they carry the type. `restoreDocument` activates the type before restoring the body;
  `restoreBody` returns a refusal for a snapshot it cannot hold.
- **Conflicts.** MergeConflict shows the Markdown lines of each passage. Choosing sides yields Markdown the timeline
  then reads; a merge result that is not a timeline reopens read-only with its reason. In v1 no merge-capable provider
  holds timelines; local has no merge.
- **Save timing.** A timeline's save starts synchronously inside `flushSave`. The F2 race, a row action overtaking an
  asynchronous conversion, cannot happen for timelines.
- **F14, alongside and optional.** `stored` becomes a single `{ path, document }`, set on `shown` and on a save
  landing for `currentPath`, and dropped on a path change and in `cancelPendingSave`. This commit edits those exact
  lines anyway.

**Rationale.** One snapshot shape carries the type everywhere a document goes, so no new per-path state is needed
(F1/F14 hazards).

**Rejected.**
- A separate path-keyed type map: `replacePath` would have to migrate it.
- Sending the type with every save in v1: nothing would read it; it is reserved for D5.

**Evidence.** services/notes/NoteSession.qml:37-43, 233-300, 362-367, 402-469, 471-542; ui/MergeConflict.qml:62-130;
lib/notemerge/README.md:8-27; CODE-REVIEW-2026-10-11.md F2, F14.

### D15 — Commands, shortcuts and the palette

**Decision.** One new workspace action, `newNoteOfType`.

| Piece | Change |
|---|---|
| `WorkspaceActions.handlers.newNoteOfType` | `host.chooseNewNoteType()` |
| availability | `canChooseNoteType()` → `host.creatableTypes(host.newNoteProvider()).length > 1`; reason "This notebook makes one kind of note." Its inputs (`footerActions`, `currentPath`) are already in `state`, WorkspaceActions.qml:12-14 |
| `services/shortcuts/defaults.js` | `{ id: "newNoteOfType", workspace: true, keys: ["Ctrl+Alt+N"], context: "notes", group: "Notes", description: "A new note of a kind you choose" }` |
| `plugins/org.note-note.workspace/plugin.json` | `{ "id": "new-note-of-type", "title": "New Note of Type…", "category": "Notes", "keywords": ["create", "kind", "timeline"], "workspaceAction": "newNoteOfType" }` |
| `services/extensions/selftest.py:44-47` | the pinned workspace actions gain `"new-note-of-type": "newNoteOfType"` |
| `docs/commands.md:61-62` and `skills/note-note-plugin/references/commands.md` | the action-id lists gain it |

The timeline's keys are its own, like the TextEdit's, not registry bindings. They are documented in README "Keys" and
docs/note-types.md.

There is no `addEvent` command in v1. A per-type palette command would need a body-actions API (a NoteType declaring
actions the host routes), deferred until a second type needs one.

**Rationale.** It is the one executor the palette, keys and commands already share (WorkspaceActions.qml:3-5). It is
type-agnostic, so the next type adds no command.

**Rejected.**
- `newTimeline` and its kin (one action per type).
- Registry bindings for timeline keys: they need a new key context in resolve.js, and bare keys cannot be claimed by
  bindings anyway (resolve.js:141-146).
- A parameterised workspace action: `workspaceAction` names carry no parameters (manifest.py:62-72;
  Workspace.qml:2192-2202).

**Evidence.** services/commands/WorkspaceActions.qml:3-98; services/shortcuts/defaults.js:7-33;
plugins/org.note-note.workspace/plugin.json:1-62; services/extensions/selftest.py:44-47; docs/commands.md:49-77;
services/shortcuts/resolve.js:10-12, 137-148.

### D16 — Prerequisite fixes

| Item | When | Why |
|---|---|---|
| **F1** (high): `replacePath` aliases are permanent and one-way | before (Phase 0) | The new session cases go through `replacePath`; a timeline in a renamed local section hits it. Fix: `delete pathAliases[next]` and re-point aliases whose value is `previous`; plus a transition case for A→B→A, then open and save |
| **F17**: suite names in three lists | before (Phase 0) | The feature adds an EditorKeys suite and a Python selftest. Fix: `tests/transition_selftest.py` `SUITES` is the one list (argv tuples in `tests/selftest.py`; CMake reads `transition_selftest.py --list-suites` at configure time) |
| Capability defaults (absent `hasTitle`; Workspace.qml:2841-2844, 1932) | alongside (Phase 1) | The same normaliser that reads `noteTypes` |
| **F13**: the skill's row shape lacks `count` | alongside (Phase 1) | Same table, same commit |
| **F14**: `stored` never pruned | alongside (Phase 2), optional | Same lines as the type-aware `isStored` |
| **F10**: the rename field loses typed text on a row rebuild | alongside (Phase 4), recommended | Every timeline check is a save that rebuilds rows, so it fires more often |
| **F2/F21**: row actions do not wait; a `cb()` without a result locks | not required | Typed creation uses footer actions, and timeline saves start synchronously; fix independently |
| **F15**: read-only pushed by hand | not required | Bodies bind to the pane's flag; no new push site |
| **F16**: duplicated note-slot Loader | not required | The body Loader uses `setSource` initial properties, not a copy loop |
| **F20**: the local `unkept` double render | partly addressed | `unkept` is now limited to Markdown notes. The full fix — `unkept` from the converter's frame, reported through the new `shown(ok, refusal)` channel — becomes a small follow-up |

**Evidence.** CODE-REVIEW-2026-10-11.md F1, F2, F10, F13-F17, F20, F21; services/notes/NoteSession.qml:63-114;
CMakeLists.txt:99; tests/transition_selftest.py:18; tests/selftest.py:15-55.

### D17 — Test plan

**Pure JS, core suite.**
- `tests/TimelineChecks.js` (`.pragma library`, `run(verify)`, the `tests/ShortcutChecks.js` pattern), called from
  `pureCases()` (tests/transitions.qml:785-965):
  - parse/serialize golden cases, including the canonical example;
  - every tolerated variant (CRLF, `*`/`+` bullets, `[X]`, no bold, soft breaks, backslash breaks, loose lists);
  - every refusal, with its line number;
  - the escape table, row by row;
  - `setChecked` on prefix and out-of-order states;
  - `append`, `replace`, `remove` and `move`, including their bounds;
  - `problem()` messages at each limit;
  - `countText`;
  - titles named `constructor`, `__proto__` and `toString`.
- `capabilityCases()`:
  - an absent `hasTitle` is true, and the host emits no "Unable to assign" warning (the noise gate,
    transition_selftest.py:217-222, would catch it);
  - `markdown` absent → `["text"]`; `markdown: true` → `["markdown"]`;
  - `noteTypes` wins; invalid entries are dropped; a string `noteTypes` is ignored;
  - `typeOf` returns the default or the given value;
  - `validTypeId` accepts `timeline` and `com.example.kanban/board`, and rejects `Timeline`, `a/b` and a
    129-character id.
- Registry cases: `find`, `label`, `icon`, `creatable` (order kept, unknown dropped); `definitionError` on a duplicate
  id, a missing label, both `body` and `documentFormat`, and a bad id.

**Session, fake editor.** The fake editor (tests/transitions.qml:375-400) gains `type`, `setNote(document, shown)`,
`clearNote()`, a `restoreDocument` that returns "", `snapshotDocument` with `type`, and `requestBody`. Then
`noteTypeSessionCases()`:
1. the load answer's type reaches `setNote`;
2. an absent type → the provider default, for a legacy markdown, a legacy text and a declared provider;
3. a refusal → read-only, with the reason reported once;
4. a draft restore carries its type (slow save, switch away and back);
5. a recovered answer's draft holds the type;
6. `isStored` is false when only the type differs;
7. deletion recovery restores a typed draft;
8. `replacePath` keeps a typed draft;
9. an A→B→A load race across types (`ownsLoad`).

**Real keys, EditorKeys.**
- Every existing `setNote(t, b, shown)` call becomes `setNote({ type: "markdown", title: t, body: b }, shown)`
  (EditorKeys 3, audio 9). `resetEditor()` (tests/EditorKeys.qml:3336-3346) restores the `markdown` type through
  `restoreDocument`. The `viewBar` instance binds `countText`.
- The `keys` suite gains three cases:
  - "a note of an unknown type opens as plain text, read-only, with the reason";
  - "text and Markdown notes switch the document format per note";
  - "no tool, paste or undo acts on the hidden document while a timeline is open" (`editor.tool("bold") === false`;
    `paste` refused).
- A new `timeline` suite:
  1. events show as stored; the snapshot equals the canonical body;
  2. Space on event 3 checks 1-3, with one `edited`;
  3. Space on checked event 2 unchecks 2..n;
  4. undo restores, then redo;
  5. Ctrl+Enter opens the add form; title + Enter appends; the form stays open; Esc closes it, and Esc never reaches
     `back` (a host `shortcutHandler` stand-in counts calls);
  6. in the description, Enter adds a line and Ctrl+Enter submits;
  7. an empty title disables submit and shows the message;
  8. Enter on an event edits it in place;
  9. Delete removes, and Ctrl+Z brings the event back;
  10. Alt+Up/Down moves;
  11. read-only: Space does nothing, there is no add row, no `edited`;
  12. a refused body opens as plain text, read-only;
  13. the title's Down lands on the next unchecked event; Up from the first event reaches the title;
  14. an empty timeline opens its form from the title's Enter;
  15. clicking a circle checks everything above it (`mouseClick` on `timelineCheck-2`);
  16. an unchanged timeline sends no save (`quietSession`);
  17. limits refuse the 1001st event.

**Codec cross-check.** `ui/notetypes/timeline/selftest.py` + `selftest.qml`, the offscreen qml6 pattern of
services/requests/selftest.py, named `*selftest*` so packaging leaves it out:
- 2,000 seeded random models, the golden cases and the foreign bodies go through the JS codec;
- Python asserts JS `parse(serialize(e)) == e`;
- mistune sees one task list with the same states and texts;
- `qthtml.unkept == []`, and the app's round trip is a fixpoint, for the golden bodies;
- foreign bodies are refused at the expected lines;
- from Phase 4, `notefile.timeline_summary(body)` agrees with the JS `progress()` for every case.

**Local provider.** `plugins/org.note-note.local/selftest.py`:
- `test_note_type_round_trip`: create with type → the exact bytes, then list (8 fields), read, save with CRLF/BOM
  input, read again;
- `test_timeline_preview`: the summary strings; the whole read beyond 4 KiB; the 256 KiB cut;
- `test_timeline_search`: event text is found;
- `test_type_line_beyond_head`;
- `test_unknown_type_kept`: the value is reported verbatim, and the line survives a save;
- `test_markdown_check_only_for_markdown`;
- `test_invalid_type_refused_on_create`;
- `FIELDS["N"] = 8` (selftest.py:347).

**Other Python.**
- `tests/test_regressions.py`: `note_type`, `type_line`, and `preview(body, "timeline")`, plus the
  `split(serialize(…))` property with type lines (:97-110).
- `services/extensions/selftest.py`: the new workspace command pin.

**Transitions, host and standalone.**
- local `create` with `options.type` writes the line and loads as a timeline;
- `loadList` parses 8- and 7-field `N` records;
- the footer chooser appears only on multi-type providers;
- picking Timeline creates one;
- Ctrl+Alt+N is unavailable for a single-type provider, with its reason;
- the legacy `examples/hello` still loads (tests/standalone_launch.qml:38-40).

**Registration.** After F17, the `timeline` suite is one entry in `SUITES` plus the EditorKeys `suites` map. The codec
selftest goes into `tests/selftest.py` `SUITES` and gets `add_test(NAME timeline-format …)` in CMakeLists.txt.

**Evidence.** tests/transitions.qml:250-252, 375-414, 785-965, 2004-2048; tests/EditorKeys.qml:300-366, 3048-3059,
3336-3346; tests/transition_selftest.py:18, 217-222; tests/selftest.py:15-43; CMakeLists.txt:71-131;
services/requests/selftest.py:28-75; plugins/org.note-note.local/selftest.py:78-112, 347, 439-493, 557-582;
tests/test_regressions.py:86-110.

### D18 — Docs and decisions

Each document changes in the same commit as the behaviour it describes (docs/release-process.md:36-37).

**Phase 1**
- `docs/providers.md`:
  - a `noteTypes` row in "Properties the host reads";
  - the `markdown` row becomes the legacy shorthand;
  - a compatibility paragraph modelled on :170-175;
  - absent-member defaults stated (`hasTitle` true; `markdown` → plain text);
  - drift fixed: `retry` in the load answer; `merged` and `version` in the save answer.
- `skills/note-note-plugin/references/providers.md`: mirrors all of it, plus F13 `count`.

**Phase 2**
- New `docs/note-types.md`: what a type is; NoteType, NoteBody and `bodyHost`; the pane protocol; adding a type; why
  not a plugin kind yet, and the trigger; unknown and refused types; the accessibility precedent.
- `docs/technical-requirements.md:14`, the editor-format row: "every note has a type; Markdown notes are rich text
  converted by qthtml; text notes plain; other types have their own body; every body crosses the contract as a string".
- `docs/decisions.md`: "A note has a type; the host owns what it means" and "Note types are the app's own, not a plugin
  kind yet".
- `docs/testing.md`: `debugState` gains `noteType` and `count`; the `editor*` IPC calls act only on the document
  editor.
- `docs/README.md`: the index gains note-types.md.

**Phase 3**
- `docs/note-types.md`, "The timeline":
  - the grammar, with the escape table and examples;
  - the tolerated variants and the refusals;
  - the limits;
  - the check rules;
  - the keys;
  - the list summary.
- `docs/technical-requirements.md` limits table (:170-188): "Timeline | 1000 events; title 300 characters; description
  4000 characters and 40 lines; a body over 2 MiB of text is not read — more opens read-only".
- `docs/decisions.md`: "A timeline is a Markdown task list", and "Checking an event checks everything above it;
  unchecking unchecks everything below; order broken elsewhere is shown, not repaired".
- `docs/testing.md`: the timeline suite and the codec selftest.

**Phase 4**
- `docs/providers.md` + skill mirror:
  - `type` on rows, `notes` and the load answer;
  - `create(target, cb, options)`;
  - `action(…, options)` for the `newNote` footer row;
  - `host.newNote(id, target, type)`;
  - the type chooser, amending :185;
  - the local format's `note-note-type` (:705-716).
- `docs/commands.md` + skill: `newNoteOfType`.
- `docs/business-requirements.md`:
  - non-goals (:57-58) gain "A note type — plain text, Markdown, a timeline — is a way to edit one note whose body its
    provider keeps as text; it is not a template, a database or a plugin of its own".
  - The product-decisions row "Sticky Notes are plain text; OneNote and Notion are Markdown" (:74) becomes "Every note
    has a type: Sticky Notes hold plain text, OneNote and Notion Markdown, local notebooks Markdown and timelines".
    Why: "a provider offers only the types its backend can keep; a timeline needs a place for its type that other
    apps leave alone, which only local files have so far".
  - New rows: the check rule; "a note whose type this version cannot edit opens read-only as text".
- `README.md`:
  - the Notebooks format section (:185-204): the `note-note-type` line and what a timeline file looks like;
  - Keys: Ctrl+Alt+N and the timeline keys;
  - Providers: `noteTypes`.
- `docs/decisions.md`:
  - "A local note's type is a `note-note-type` line";
  - "A new note's type is chosen on the provider's New Note action", recording the :185 amendment.
- `docs/technical-requirements.md` data model (:105-117): the row shape, fixing its drift too
  (`menu`/`count`/`reorder`/`modified`/`type`).
- `docs/testing.md`: the local selftest cases.
- The metainfo release notes.

docs/plugins.md and SKILL.md are unchanged: there is no new kind.

### D19 — Phasing

Every commit is green on both runners and ships its docs.

**Phase 0 — prerequisites**
1. C1 "Keep a note's path aliases one-way" (F1, plus a test).
2. C2 "Name the transition suites once" (F17).

**Phase 1 — contract and capabilities** (no visible change except the `hasTitle` fix)
3. C3 "Let providers say which note types they keep": `capabilities.js`; the Workspace bindings, `newNote` focus and
   `sidebar.js hasTitle` go through it; built-ins declare `noteTypes`; OneNote's dead field is removed; hello gets
   `["markdown"]`; docs and skill (with F13); capability tests.

**Phase 2 — the seam** (behaviour-neutral for text and Markdown notes)
4. C4 "Show each note through its type's body":
   - NoteType, NoteBody and NoteTypeRegistry (text, markdown);
   - the pane protocol, `documentBody`, `bodyHost`, `bodyLoader` and `documentActive` gating;
   - the session's type flow;
   - the ViewBar's `countText`; the `formOpen` gates;
   - the unknown-type fallback; `debugState`;
   - the fake editor and test call sites; F14 optional;
   - docs/note-types.md (architecture), technical-requirements, decisions, testing.

**Phase 3 — the timeline type** (creatable nowhere yet)
5. C5 "Draw check boxes in one place": the CheckMark extraction, behaviour-free.
6. C6 "Add the timeline note type": `Timeline.js`, the body, event row, form, ChromeTextArea, the registry entry;
   TimelineChecks, the codec selftest, the EditorKeys timeline suite; docs.

**Phase 4 — timelines in local notebooks, creation and the list**
7. C7 "Keep timelines in local notebooks": notefile, list, operations and Provider.qml; local selftests;
   test_regressions; transitions `localCases`; sidebar `row().type`; the NoteSummary glyph; `host.newNote(…, type)`
   and the create options; hello timeline support; providers.md type sections and the local format; README format.
8. C8 "Choose the kind of a new note": `newNoteOfType`, the footer chooser and picker; defaults.js; plugin.json; the
   selftest pin; commands docs; business-requirements amendments; README keys; decisions; F10 recommended.
9. C9 "Release 1.1.0": manifest.json 1.0.40 → **1.1.0** and a leading metainfo `<release>`. Then
   `omarchy plugin validate .`, ctest, `python3 tests/selftest.py`, `packaging/package.py`, and the security
   pre-release checklist (docs/security.md:286-325).

**First release** = Phases 0–4: timelines in local notebooks and the hello example; OneNote, Notion and Sticky as
today.

**Version.** 1.1.0 follows the documented semver rule (feature → minor, docs/release-process.md:26-27) for an additive
contract change and a new user feature. Practice has been patch bumps; this is a user decision below.

### D20 — Risks and user decisions

See the two sections that follow.

---

## Risks

1. **The pane refactor regresses the document editor.** Mitigation:
   - the document code is kept and only renamed; the adapter only calls it;
   - Phase 2 changes no behaviour for text and Markdown notes;
   - every existing EditorKeys suite (keys 54/54 at HEAD), core (289/289) and the qthtml selftest (141/141) must stay
     green;
   - `CheckMark` is extracted in its own behaviour-free commit.
2. **The hidden document acts on input while a timeline is open** (tools, paste, IPC undo). Mitigation:
   `documentActive` gates `EditorApi.writable`, `applyReadOnly`, `paste`, `pastePlain`, `undo` and `redo`; the
   shortcut context stays `workspace`; a keys-suite case pins it.
3. **A note shows in the wrong body** (the type arrives late; a draft without a type). Mitigation:
   - the type is a field of the document passed to `setNote` and `restoreDocument`, activated before the body is
     touched;
   - every snapshot carries it;
   - session cases cover draft, recovery, `replacePath` and cross-type races.
4. **A codec bug corrupts a timeline.** Mitigation:
   - fail-closed parsing with line-numbered refusals;
   - one canonical serializer;
   - property tests;
   - the qml6 + mistune cross-check over seeded random corpora;
   - unknown and foreign bodies open read-only;
   - no write ever happens without a user edit.
5. **The front-matter key collides with other tools' metadata.** Mitigation: the namespaced `note-note-type`, written
   only at creation; absent means Markdown.
6. **Order is broken elsewhere** (an outside editor, a phone, a future merge). Mitigation: shown as stored; the next
   user check restores a prefix; nothing is repaired silently.
7. **Inline Markdown typed elsewhere** becomes literal, escaped characters after the next change. Mitigation:
   documented in docs/note-types.md and README; no characters are ever dropped; refusal was rejected because of its
   false positives.
8. **Listing cost** of whole-file reads for timelines. Mitigation: only for notes whose head says `timeline`; capped at
   256 KiB each; under the listing's existing deadline and byte budget.
9. **The Python summary drifts from the JS codec.** Mitigation: the codec selftest asserts that both agree on every
   corpus case.
10. **Keyboard collisions** (Escape, Enter or app keys under the form). Mitigation: the `formOpen` gate in
    `handleShortcut` and `WorkspaceActions.blocked`; the form handles its own Enter and Esc; EditorKeys counts
    `shortcutHandler` calls.
11. **Older app versions open timeline files as Markdown.** Mitigation: the canonical form is a fixpoint of their
    editor; the type line survives as an extra line; edits made there come back tolerated or refused, never lost.
12. **Noise gates fail the suites** on any QML warning, such as a required property left unset. Mitigation:
    `setSource` initial properties for `host`; the capability normaliser removes the `hasTitle` warning; suites run in
    both harnesses.
13. **The docs and the skill drift.** Mitigation: the same commit, the F13 fix, and a reviewer checklist line in
    docs/plugins.md:50-53.
14. **The type chooser is a host-added control**, against providers.md:185. Mitigation: an explicit, recorded
    amendment, driven only by the provider's own `noteTypes` and its `newNote` row.
15. **Glyph tofu.** Mitigation: glyph Texts use `Style.fontFamily`; U+F1533 is verified in the bundled Symbols Nerd
    Font; standalone registers it as a fallback.
16. **Building a public API too early.** Mitigation: no plugin kind; NoteType and NoteBody stay internal with
    `apiVersion: 1`, and the trigger is recorded.
17. **F1, F2 and F10 interact with timelines** (renamed sections, row rebuilds on every check). Mitigation: F1 first;
    F10 alongside; F2 is not reachable by timeline saves.
18. **Performance at 1000 events** (model reassignment on every check). Mitigation: ListView virtualisation; immutable
    arrays that reuse unchanged event objects; a codec selftest case timing `parse` and `serialize` at the limit.

## User decisions

| # | Question | Options | Recommendation | Why |
|---|---|---|---|---|
| 1 | What does unchecking an event do? | (a) uncheck it and every event below; (b) only that event; (c) unchecking is only undo | **(a)** | Keeps "the checked events are how far along the timeline is" true after every action; it mirrors your rule for checking |
| 2 | Local front-matter key | (a) `note-note-type: timeline`; (b) `type: timeline`; (c) `note-type: timeline` | **(a)** | Unique to the app, so an unknown value can safely open read-only; `type:` is used by Hugo and Obsidian vaults |
| 3 | How is "New timeline" offered? | (a) a chooser at the end of the New Note footer row, plus Ctrl+Alt+N, plus a palette "New Note of Type…"; (b) a "New timeline" footer row per provider; (c) the palette only | **(a)** | Scales to every future type with no footer growth and no host change per type; mouse-free |
| 4 | Event text in the file | (a) `- [x] **Title**` with description lines after hard breaks; (b) unbolded titles; (c) the description as a separate paragraph | **(a)** | The only shape that is a fixpoint of the app's own Markdown editor and keeps title and description apart in other tools; (c) is refused by Notion's writer |
| 5 | Event descriptions | (a) multi-line plain text (up to 40 lines); (b) a single line; (c) Markdown formatting | **(a)** | You asked for a description; plain text is what every backend and the escape rules can keep; formatting from other editors is kept as characters |
| 6 | Editing in v1 | (a) add, edit, delete, move with Alt+Up/Down, undo; (b) add and check only; (c) (a) plus drag reordering | **(a)** | Typos and mid-list insertions are everyday needs; drag is costly and can follow |
| 7 | Providers in v1 | (a) local and the hello example; (b) also Notion, marked by a page icon; (c) also OneNote, with a data-id marker after live verification | **(a)** | Notion and OneNote have no invisible place for the type; (b) and (c) are product choices and need verification |
| 8 | Note types as a plugin kind | (a) not now: an internal registry with a recorded trigger; (b) now | **(a)** | A public body API frozen from one example, and type ids persisted in files, cannot be taken back |
| 9 | Timeline preview in the list | (a) `3/7 · Pack the bags`; (b) the first event; (c) the generic first line | **(a)** | Turns the list into the "where am I" view the feature exists for |
| 10 | A new, empty timeline | (a) the add form opens when you leave the title with Enter or Down; (b) show the empty state with the add row focused | **(a)** | Title → Enter → first event → Enter → next is the fastest way to build a timeline |
| 11 | Version | (a) 1.1.0; (b) 1.0.41 | **(a)** | docs/release-process.md:26-27 says a feature is a minor bump, and the provider contract grows |
| 12 | Converting an existing note to or from a timeline | (a) later (D5); (b) in v1 | **(a)** | The safe directions are known, and the seam is in place; only local could store it today |

---

## File changes

| Phase | File | Change |
|---|---|---|
| 0 | services/notes/NoteSession.qml | F1: `replacePath` deletes `pathAliases[next]` and re-points aliases to `previous`; never leaves a live path aliased |
| 0 | tests/transitions.qml | case: rename A→B→A, then open and save a note in it |
| 0 | tests/transition_selftest.py | `SUITES` the one list; `--list-suites` |
| 0 | tests/selftest.py | argv tuples; `entry[-1] == "core"` |
| 0 | CMakeLists.txt | read the suite names from `--list-suites` at configure time (replaces the :99 list) |
| 1 | services/notes/capabilities.js (new) | `TYPE_ID`, `validTypeId`, `noteTypes`, `defaultType`, `typeOf`, `hasTitle`, `canImages`, `tools` |
| 1 | Workspace.qml | `canImages`/`hasTitle`/`enabledTools` bindings (2831-2848) and newNote focus (1932) through Capabilities |
| 1 | services/notes/sidebar.js | `row()` uses `Capabilities.hasTitle` |
| 1 | plugins/org.note-note.{local,sticky,onenote,notion}/Provider.qml | declare `noteTypes`; drop `markdown` |
| 1 | plugins/org.note-note.onenote/onenote.py | drop the unread `markdown=True` (1380-1381, 1387) |
| 1 | examples/hello/Provider.qml | `noteTypes: ["markdown"]` |
| 1 | docs/providers.md, skills/note-note-plugin/references/providers.md | `noteTypes`, legacy shorthand, defaults, drift (`retry`, `merged`, `version`, F13 `count`) |
| 1 | tests/transitions.qml | `capabilityCases()` |
| 2 | ui/notetypes/NoteType.qml (new) | the type contract |
| 2 | ui/notetypes/NoteBody.qml (new) | the body contract (`FocusScope`, `apiVersion` 1) |
| 2 | ui/notetypes/NoteTypeRegistry.qml (new) | text and markdown; validation; `find`/`label`/`icon`/`creatable`/`unknownReason`/`bodyError` |
| 2 | ui/NoteEditor.qml | pane protocol (`setNote(document)`, `clearNote`, `restoreDocument` → refusal, typed snapshot, `requestBody`, dispatching `viewState`/`focus`); `documentBody` adapter; `bodyHost`; `bodyLoader`; `activateType`/`showAsText`; `documentActive` gating; `countText`/`formOpen`/`typeId`; owns `typeRegistry`; document functions renamed (`showDocument`, `documentViewState`, `restoreDocumentViewState`) |
| 2 | ui/editing/EditorApi.qml | `writable` also requires `host.documentActive` |
| 2 | services/notes/NoteSession.qml | `clearNote`; `Capabilities.typeOf`; `setNote({type,…})`; refusals into `noteReady`; `restoreDocument` refusal; `isStored` with type; `requestBody`; F14 optional |
| 2 | Workspace.qml | remove the `plain:` binding; ViewBar `countText`; `editor.formOpen` in `handleShortcut` and `blocked`; `debugState` `noteType`/`count` |
| 2 | ui/ViewBar.qml | `countText` replaces the `wordCount` label text |
| 2 | tests/transitions.qml, tests/EditorKeys.qml, tests/audio.qml | fake editor; session type cases; `setNote` call sites; `resetEditor`; viewBar `countText`; keys-suite type cases |
| 2 | docs/note-types.md (new), docs/technical-requirements.md, docs/decisions.md, docs/testing.md, docs/README.md | architecture, editor format, decisions, IPC notes, index |
| 3 | ui/CheckMark.qml (new); ui/NoteEditor.qml | the extracted check face; the overlay uses it |
| 3 | ui/ChromeTextArea.qml (new) | multi-line ChromeControlStyle field |
| 3 | ui/notetypes/timeline/Timeline.js (new) | codec and model operations, limits |
| 3 | ui/notetypes/timeline/TimelineType.qml (new) | `NoteType { typeId: "timeline"; label: "Timeline"; icon: "󱔳"; body: TimelineBody.qml }` |
| 3 | ui/notetypes/timeline/TimelineBody.qml, TimelineEvent.qml, EventForm.qml (new) | the view, row and inline form (D10) |
| 3 | ui/notetypes/NoteTypeRegistry.qml | registers TimelineType |
| 3 | ui/notetypes/timeline/selftest.py, selftest.qml (new) | qml6 + mistune cross-check |
| 3 | tests/TimelineChecks.js (new); tests/transitions.qml | pure cases in `pureCases` |
| 3 | tests/EditorKeys.qml; tests/transition_selftest.py | the `timeline` suite |
| 3 | tests/selftest.py; CMakeLists.txt | register the codec selftest (`timeline-format`) |
| 3 | docs/note-types.md, docs/decisions.md, docs/technical-requirements.md, docs/testing.md | timeline format, rules, limits, tests |
| 4 | plugins/org.note-note.local/notefile.py | `TYPE_KEY`, `TYPE_ID`, `note_type`, `type_line`, `timeline_summary`, `preview(body, type)` |
| 4 | plugins/org.note-note.local/list.py | `type` field (8th), whole read for timelines, docstring |
| 4 | plugins/org.note-note.local/operations.py | read `type` and Markdown-only `unkept`; create `type`; typed save preview |
| 4 | plugins/org.note-note.local/Provider.qml | `noteTypes` + timeline; `loadList`; rows/notes `type`; load `type`; `Object.assign` commit; `create` options; `action` options |
| 4 | plugins/org.note-note.local/selftest.py; tests/test_regressions.py; tests/transitions.qml | type and summary cases; `FIELDS`; `localCases` |
| 4 | services/notes/sidebar.js | `row()` copies `type` |
| 4 | ui/NoteSummary.qml; ui/NoteList.qml; ui/SearchResults.qml | `icon` glyph; `typeIconFor` |
| 4 | ui/SidebarAction.qml; ui/NoteList.qml | `chooser` button and `chooserRequested` / `footerChooserRequested` |
| 4 | Workspace.qml | `newNote(providerId, target, type)`; `runFooterAction(…, options)`; `chooseNewNoteType`; `creatableTypes`; `newNoteProvider`; `typeIconFor` |
| 4 | services/commands/WorkspaceActions.qml | `newNoteOfType` handler and availability |
| 4 | services/shortcuts/defaults.js | `newNoteOfType` Ctrl+Alt+N |
| 4 | plugins/org.note-note.workspace/plugin.json | the `new-note-of-type` command |
| 4 | services/extensions/selftest.py | pin six workspace actions |
| 4 | examples/hello/Provider.qml | timeline support (per-note `type`, `create`/`action` options) |
| 4 | docs/providers.md + skill; docs/commands.md + skill; docs/business-requirements.md; README.md; docs/decisions.md; docs/technical-requirements.md; docs/testing.md | D18 Phase 4 |
| 4 | manifest.json; packaging/desktop/io.github.andreivinca.note-note.metainfo.xml | 1.1.0 and the release notes |
