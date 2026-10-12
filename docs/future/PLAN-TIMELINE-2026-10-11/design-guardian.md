# Timeline notes and per-note types: the guardian design

Stance: data safety and compatibility first. No note is lost, duplicated or corrupted. Every external
provider, older app version, outside editor, sync tool, and unknown or disabled type is handled
safely: parsing is bounded and fails closed, read-only with a reason beats a lossy write, the
contract change is the smallest additive one, the rollout is staged, and each guarantee is pinned by
a test. The timeline feature the user asked for is built on that base.

Repository: `/home/andrei/Projects/note-note`, HEAD `e2cdc4e`, app version 1.0.40. All citations are
`file:line` at HEAD. The experiments cited as `scratchpad/guardian/*.py` were run against the repo's
own Python modules with bytecode writing off; the tree stayed unchanged (`git status`: only the
untracked review file).

## Thesis

A timeline note is an ordinary Markdown task list in one strict shape, plus a per-note type marker
kept where its provider keeps metadata. For local notes the marker is one namespaced front-matter
line, `note-note-type: timeline`, written once at creation and never by a save.

The canonical body is exactly what the editor's own Markdown writer produces for that list. Every
reader that does not know timelines therefore sees a readable checklist and writes it back
unchanged: an older Note Note, Obsidian, GitHub, a phone app, a sync tool, or this app's own Markdown
fallback. If the marker is lost, the note becomes a checklist; no text is lost.

The host decides how each note is shown in one pure function. It uses the load answer's `noteType`
when the provider declares types, and the legacy `markdown` bool otherwise. An unknown or undeclared
type opens read-only as raw text with a reason. A timeline whose body is not in timeline form opens
as the Markdown it is, and the status line says why. Saves never change a note's type.

The codec reads with the shared mistune parser (`services/markdown/parse.py`) and writes through the
qthtml reader. Canonical timeline text is therefore, by construction, a fixpoint of the editor's
Markdown round trip. A 3000-model property test and a pass through Qt confirmed this once a
one-character escaping bug found during this design is fixed.

The contract grows additively, with `apiVersion` staying 1:
- `noteTypes` on the provider;
- `noteType` on rows, notes and the load answer;
- an optional `options` argument to `create`.

These are feature-detected the way `canReorder` led to `reorder`. The timeline view is a second body
inside the existing note pane, behind the session's document protocol. That protocol gains the type
as part of every snapshot, so drafts, recovery, no-op saves and load races keep their proven
guarantees.

The rollout is staged:
1. Fix the defects already on these paths first.
2. Add the plumbing with no visible change.
3. Add the codec.
4. Add the local marker.
5. Turn on the view.

## Decisions

### D1 — Vocabulary and identifiers

**Decision.** There are three core type ids, unqualified and reserved: `text` (plain text, today's
`markdown: false`), `markdown` (today's `markdown: true`) and `timeline`. Types contributed by
packages in a later release are qualified as `<package-id>/<local-id>`, for example
`com.example.kanban/board`, so they can never take over a core name.

Id grammar, checked by both the host and the local provider, at most 128 characters:
`^(?:[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+/)?[a-z][a-z0-9-]{0,63}$`

Field names:
- `noteTypes`: the provider property, a list of declared types.
- `noteType`: what a note is. It appears on rows, `sections[].notes` items, the load answer and the
  create options `{ noteType }`.
- `documentType`: the form the editor holds a note in. It appears on `NoteEditor` and on every
  snapshot `{ documentType, title, body, base }`. It equals the note type, except that a timeline
  whose body is not in timeline form is held as `markdown`.
- `note-note-type:`: the local front-matter key.

**Rationale.** `kind` already means note/new/action/tree on rows (docs/providers.md:89-91). `type` is
generic enough that an external provider may already emit it for its own reasons. `contentType` is
already used by Sticky Notes' Graph payloads (`body.contentType: "text"`). `noteType` is used nowhere
(repo grep), so reading it cannot change behaviour for any existing provider. Splitting `noteType`
(what the provider stores) from `documentType` (what the editor holds) is what makes the Markdown
fallback honest: a snapshot never claims a timeline form for an HTML body. Qualified package ids
follow the takeover risk recorded for built-ins (services/extensions/manifest.py:268-283).

**Rejected.**
- `type` and `contentType`: collisions, described above.
- `kind`: already taken on rows.
- Unqualified package ids: a later built-in could take over a user's notes.
- A MIME-like vocabulary such as `text/markdown`: no benefit, longer markers on disk.

**Evidence.**
- docs/providers.md:89-91 (row `kind`).
- plugins/org.note-note.sticky/sticky.py:90,108 (`contentType`).
- Repo grep: `noteType` and `note-note-type` are absent.
- services/extensions/manifest.py:24-27, 268-283.

### D2 — How a provider declares types; legacy derivation; one place for defaults

**Decision.** A provider may declare `readonly property var noteTypes: ["markdown", "timeline"]`.

Rules:
1. The first entry is the default type. It is the type of a note that reports none, and of a note
   made without asking for one (Ctrl+N, `new` rows, footer New Note).
2. When `noteTypes` is absent, the provider is legacy. Its types are
   `[provider.markdown === true ? "markdown" : "text"]`, which keeps today's meaning that an absent
   `markdown` is plain text (Workspace.qml:2837-2840). The host ignores any per-note `noteType`
   field from a legacy provider and never asks it for a non-default type.
3. A declaration is valid when it is a non-empty array of at most 16 distinct strings matching the
   id grammar, and it includes `markdown` whenever it includes `timeline`. The Markdown fallback must
   be a type the provider can store.
4. An invalid declaration is treated as absent. A diagnostic is shown once when the provider loads:
   `Workspace.addProvider` does `showStatus(p.name + ": noteTypes ignored: <why>")`, never from a
   binding.
5. Providers keep declaring `markdown` for hosts before 1.1.0.

Defaults are normalised in one new pure module, `services/notes/capabilities.js` (`.pragma
library`), through `Capabilities.of(provider)`. It returns
`{ noteTypes, defaultType, declaresTypes, hasTitle, canImages, tools }`, where:
- `hasTitle` is `provider.hasTitle !== false`, so an absent value is true;
- `canImages` is `=== true`;
- `tools` is `undefined → null`.

Every reader of these members goes through it:
- Workspace's editor bindings (Workspace.qml:2831-2848) become
  `root.openCapabilities = Capabilities.of(root.providerOf(root.currentPath))`, with the `plain`
  binding removed (the note's type now decides);
- `newNote`'s focus choice (Workspace.qml:1932);
- `sidebar.js row()`'s `hasTitle` (services/notes/sidebar.js:26).

This fixes the absent-`hasTitle` bug, where the binding `p ? p.hasTitle : true` yields `undefined`,
warns "Unable to assign [undefined] to bool" and keeps the previous note's value, while
`newNote` treats it as false.

**Rationale.**
- It follows the `canReorder` → `reorder` precedent: the legacy shorthand stays, the explicit
  declaration wins, and feature detection is done once (docs/providers.md:170-175;
  services/notes/ordering.js:5-18).
- One normalising function ends the three inconsistent defaults (contract map Q5).
- Requiring `markdown` with `timeline` closes the one path where a fallback could send Markdown to a
  provider that cannot keep it.

**Rejected.**
- A separate `defaultNoteType` property: one more member for authors to keep consistent.
- Declaring types in `plugin.json`: capabilities live on the QML instance, and the manifest
  validator reads only id/path/order (services/extensions/manifest.py:79-87). A manifest field would
  also need a validator change and older apps reject unknown kinds.
- Deriving the default from `markdown` even when `noteTypes` is present: two sources of truth.
- Warning inside the pure function: it would spam from bindings and trip the noise gates
  (tests/transition_selftest.py:217-222).

**Evidence.**
- Workspace.qml:2831-2848 (bindings; hasTitle at 2841-2844), 1932-1936 (focus).
- services/notes/sidebar.js:24-31.
- docs/providers.md:47 (markdown), 51, 170-175.
- Contract map Q5: the hasTitle warning, verified on Qt 6.11.2.

### D3 — Per-note type reporting, authority, mismatch and unknown rules

**Decision.**
- **Rows and notes.** Rows of `kind: "note"` and `sections[].notes` items may carry `noteType`.
  `sidebar.js row()` copies it through `Capabilities.rowType(provider, source)`. That returns `""`
  for a legacy provider, for an absent value, for the provider's default type, or for an invalid
  id, and the id otherwise. The row therefore carries a value only when the list draws something for
  it (a glyph, D11), and it rarely changes, so the JSON comparison of rows does not churn
  (docs/decisions.md:444-448; Workspace.qml:1349-1362).
- **Load answer.** It gains an optional `noteType`; absent means the provider's default.
- **Save answer.** It carries no type. The host never changes a type through a save.
- **Authority.** The load answer decides how the note is shown; rows are a display hint only.

The pure function `NoteTypes.opened(capabilities, answer)` in the new `services/notes/notetypes.js`
returns `{ documentType, readOnly, reason }`:
1. A legacy provider gets its default type.
2. An absent `noteType` gets the default.
3. A non-string, or an id the host's registry does not know, gives `{ documentType: "text",
   readOnly: true, reason: "This note is a “kanban” note, which this version of Note Note cannot
   show, so it opened read-only" }`. The id is quoted only if it matches the grammar; otherwise the
   reason says "a note of an unknown kind".
4. A known id the provider does not declare gives the same raw read-only view, with the reason
   "This notebook reported a kind of note it does not declare, so it opened read-only".
5. Otherwise the documentType of that type is shown.

A row/load mismatch is not an error. The load wins, and the row glyph corrects itself on the next
relist; for local, also on the save answer (D13). The registry lookup is prototype-free, so ids
like `constructor` or `__proto__` are simply unknown.

**Rationale.**
- Rows cannot drive the editor: created notes may not be listed yet, and drafts restore without a
  load (NoteSession.qml:233-245).
- The load answer is the single place the editor's input comes from (NoteSession.qml:246-300).
- Showing unknown types raw and read-only follows "absent contributions stay dormant, never
  rewritten" and "read-only rather than lossy" (docs/decisions.md:660-667; docs/plugins.md:129-134).
  Rendering a future type through any other type's editor could rewrite its structure on the first
  save.

**Rejected.**
- Rows as the authority: missing for new notes and drafts.
- Showing an unknown type as editable Markdown: a lossy write for a future non-Markdown format.
- Showing it as rendered Markdown read-only: it assumes a format the host does not know; raw text is
  the honest view.
- Refusing to display unknown types: it hides the user's content (the same argument as
  docs/decisions.md:705-708).

**Evidence.**
- services/notes/sidebar.js:24-31, 59-70.
- NoteSession.qml:233-245, 252-300.
- Workspace.qml:1349-1362.
- docs/decisions.md:444-448, 660-708.
- docs/plugins.md:129-134.

### D4 — Creation

**Decision.**
- **Contract.** `create(target, cb, options)`, where `options` is `{ noteType }` and `noteType` is
  always one the provider declares. The host passes `options` to every provider; legacy providers
  ignore the third argument, and the host only ever asks them for their default type. The provider
  must create a note of exactly that type or answer `{ error }`, and must never silently create
  another type. `target` stays opaque and never encodes the type.
- **Host.** `newNote(providerId, target, noteType)`:
  - `noteType` is optional; absent means the destination's default.
  - The footer-shortcut route (`activateFooterShortcut("newNote")`, Workspace.qml:1690-1703) is taken
    only for untyped creation.
  - `newNoteDestination(providerId, target, noteType)` keeps today's choice (an explicit provider,
    else the active one with `createTargetFor(currentPath)`), but when `noteType` is given and the
    active provider does not support it, it falls back to the first provider with `canCreate`, that
    type, and `createTargetFor("")`, then switches tabs as Ctrl+N's fallback already does.
  - If no destination exists, the status line says "No notebook here can hold a timeline".
  - Focus after creation uses `Capabilities.of(p).hasTitle`.
- **Surfaces in the first release.**
  - A host workspace action `newTimeline`, bound to Ctrl+Alt+N in the notes context.
  - A palette command "New Timeline" (`plugins/org.note-note.workspace/plugin.json`, workspaceAction
    `newTimeline`).
  - No sidebar button, footer row or menu item is added by the host. `new` rows ("+ New note…") stay
    default-type creation. A provider may add its own footer or menu entry that calls
    `host.newNote(root.id, target, "timeline")`; built-ins add none in this release.
- **Docs.** docs/providers.md:185 is amended to: "the host adds no sidebar buttons; typed creation is
  a host command aimed at the destination Ctrl+N would use, offered only where that provider
  declares the type".

**Rationale.**
- Follows the save-options precedent ("Existing providers can ignore `options`",
  docs/providers.md:283-291).
- Keyboard-first: Ctrl+N's family (Ctrl+N, Ctrl+Shift+N, Ctrl+Alt+N) needs no footer growth
  (ui/NoteList.qml:716; the anti-growth note at ui/TitleBar.qml:112-116).
- Avoids the pointer-only row menus (ui/NoteList.qml:611-617).
- Avoids the locked-session trap where `host.newNote` inside `rowAction` is ignored
  (Workspace.qml:2115-2116, 1888-1890).

**Rejected.**
- Encoding the type in `target`: providers parse targets themselves (local Provider.qml:556), and
  that would be a hack.
- One footer row per type: grows the footer.
- A "New…" type picker opened by Ctrl+N: changes Ctrl+N's meaning for every user.
- A local row-menu item: pointer-only, and it collides with the runRowAction lock (F2/F21).
- A host-generated footer button from `noteTypes`: contradicts the contract rule for no keyboard
  gain.

**Evidence.**
- Workspace.qml:1873-1938, 1690-1703, 2726-2734.
- services/commands/WorkspaceActions.qml:18-48.
- services/shortcuts/defaults.js:21-23.
- docs/providers.md:181-213, 283-291, 350.
- ui/NoteList.qml:472-485, 611-617, 716.

### D5 — Changing a note's type

**Decision.** Not in the first release. No command converts Markdown to timeline or back. The design
leaves room in five ways:
1. A save never carries or changes a type. The only writer of the marker is creation, and later an
   explicit operation.
2. `timeline.read(markdown)` already answers whether any Markdown body is a timeline in canonical
   form. A future "Convert to timeline" can be offered only when it changes no body bytes, and
   "Convert to Markdown" is always lossless because the body is Markdown.
3. A future optional provider member, `setNoteType(path, noteType, cb)`, is feature-detected like
   `reorder`. Locally it would be an `operations.py` action `retype` that rewrites only the marker
   line through `write_atomic` behind the mutation queue.
4. The session needs no new state: the editor reloads the note after a successful retype.
5. Snapshots already carry `documentType`, so drafts stay consistent across a retype.

**Rationale.** Conversion is the only path that writes the marker after creation. Keeping it out of
v1 means every timeline marker on disk was written by creation, which is the simplest invariant to
test. Conversion can be added without migrating anything.

**Rejected.**
- Conversion in v1: doubles the write paths that touch metadata.
- Converting by editing the type through save options: a save would then be able to change types,
  which breaks the "saves never change types" guarantee that makes older apps and sync safe.

**Evidence.**
- plugins/org.note-note.local/operations.py:126-141 (save re-reads `extra` from the current file).
- plugins/org.note-note.local/notefile.py:48-76.
- Workspace.qml:927-961 (feature detection).

### D6 — Note pane architecture

**Decision.** NoteEditor stays the one note pane, so all ~50 Workspace `editor.*` references, the
notices, the provider views, the conflict review, the title, the toolbar alignment and the IPC keep
working. The rich TextEdit stays permanently instantiated, so `canColorText`, `tools.actions` and
`toolbarHeight` (Workspace.qml:122-123, 2520, 2554, 2714-2715) do not change with the note. The
timeline is a sibling body in the sheet:
- `ui/timeline/TimelineView.qml` sits beside `flick` (ui/NoteEditor.qml:2000);
- it is `visible: !root.showingNotice && root.documentType === "timeline"`;
- `flick` becomes visible only when `documentType !== "timeline"`.

The type switch lives at the document-protocol boundary, in one place per protocol function, and
never inside the ~20 internal `plain` branches.

**NoteEditor members (new or changed).**

| Member | Behaviour |
|---|---|
| `property string documentType` | `"markdown"` initially; written only by `setNote`, `restoreDocument` and `clearDocument` |
| `readonly property bool plain` | `documentType === "text"`; replaces the settable `plain` |
| `readonly property bool richText` | `documentType === "markdown"` |
| `readonly property bool formOpen` | `timelineView.formOpen` |
| `function clearDocument()` | Replaces `setNote("", "")`: drops the title, both bodies and any conversion in flight, and sets `documentType` to `"markdown"` |
| `function setNote(documentType, title, body, shown)` | Type first. An unknown `documentType` throws an `Error`, a programming error the noise gates catch. For `"timeline"`: the hidden rich document is blanked, then `markdown.toTimeline` runs under the same `noteToken` race guard. On `notTimeline` the editor sets `documentType = "markdown"`, emits `statusRequested("This timeline holds <reason>, so it opened as Markdown")` and renders the body through the existing Markdown path. A converter failure is `shown(false)` |
| `function restoreDocument(snapshot)` | Selects the body by `snapshot.documentType` before showing |
| `function snapshotDocument()` | `{ documentType, title, body, base }`. For a timeline, `body` is `TimelineModel.form(events)`, a deterministic JSON string |
| `function requestBody(document, callback)` | Replaces `requestMarkdown(callback)`. It converts the given snapshot, not the live editor: timeline uses `markdown.fromTimeline`, Markdown uses `toMarkdown(document.body)`, text is identity. The framed `(body, ok)` answer is kept (docs/decisions.md:523-545) |
| `function openEventForm()` | Opens the timeline view's add form |
| `focusEditor`, `focusBody`, `viewState`, `restoreViewState`, `wordCount` | Dispatch on `documentType` |
| `paste`, `pastePlain`, `undo`, `redo`, `tool` | Refuse when the timeline is shown |
| `applyReadOnly` | Also sets the hidden area read-only while a timeline is shown |

`EditorApi.writable` uses `host.richText` in place of `!host.plain`, so the tools strip hides and no
tool can act on a hidden document (ui/editing/EditorApi.qml:13).

**TimelineView interface.** Pure presentation and interaction on an events array:
- properties: `events` (array, replaced wholesale), `readOnly`, `foreground`, `accent`,
  `background`, `fontFamily`, `noteFontFamily`, `bodyFontSize`, `shortcutHandler`;
- read-only properties: `formOpen`, `wordCount`;
- signals: `edited()`, `statusRequested(string)`, `titleRequested()`;
- functions: `show(events)`, `focusFirst()`, `openAddForm()`, `viewState()`,
  `restoreViewState(state)`.

`bodyFocused` keeps meaning "the rich text body has focus", so a focused timeline is the `workspace`
shortcut context (Workspace.qml:2168-2176). Editor-context bindings (tools, paste) then cannot fire
there. Workspace's paste keyActions guard becomes `!editor.richText || editor.readOnly ? false : …`.
That is false for plain text, as today, and for a timeline, so the focused field's own paste runs
(Workspace.qml:2245-2250).

**Rationale.**
- The session's real contract is the 12-member fake (tests/transitions.qml:375-400).
- Adding the type to that protocol keeps every session guarantee type-agnostic: `noteToken` races,
  drafts, `stored`/`isStored`, deletion recovery and `replacePath`.
- `requestBody(document)` removes the hidden coupling "must be called synchronously right after
  `snapshotDocument`".
- Keeping the rich editor instantiated avoids recompiling key bindings and theme support per note.
- Splitting NoteEditor (2409 lines) into a pane plus a RichBody now would be a large refactor of the
  component that holds every existing note, with no safety gain. It stays possible later behind the
  same protocol.

**Rejected.**
- Swapping NoteEditor at the Workspace level: orphans ~50 references.
- A `timeline` flag threaded through the `plain` branches: spaghetti, against CLAUDE.md.
- Drawing the timeline as RichText inside the TextEdit: Qt's own checkbox toggle cannot implement
  "check all above" (ui/NoteEditor.qml:2219-2223), and it would inherit the known table bug.
- A Loader that creates the rich editor only for rich notes: theming and key bindings would change
  with the note.
- A session-held type property beside the snapshot: two sources of truth.

**Evidence.**
- ui/NoteEditor.qml:26-28, 72, 112-134, 282-332, 365-377, 1784-1797, 1802-1807, 1843-2010,
  2219-2291.
- ui/editing/EditorApi.qml:13.
- Workspace.qml:2168-2203, 2245-2250, 2824-2886.
- tests/transitions.qml:375-400.

### D7 — Registry and extensibility

**Decision.** Core types are app-owned in v1, in `services/notes/notetypes.js` (`.pragma library`).
The registry is a prototype-free map from id to:
- `label`: "Plain text", "Note", "Timeline";
- `glyph`: "" for text and markdown, U+F1533 `md-timeline_check_outline` for timeline, verified
  present in assets/fonts/nerd-symbols/SymbolsNerdFont-Regular.ttf by scratchpad/guardian/glyphs.py;
- `document`: the `documentType` it opens as;
- `previewNames`: whether a preview may stand in for a missing title (false for timeline);
- `untitled`: "Untitled timeline".

Its functions are `known(id)`, `label(id)`, `glyph(id)`, `previewNames(id)`, `untitled(id)` and
`opened(capabilities, answer)`.

No plugin kind ships now. When one is added, the sixth catalog kind (`noteTypes`) follows commit
2c5920f:
- qualified ids;
- manifest metadata (title, glyph);
- a contract QML `NoteType` re-exported from `NoteNote.Extensions`;
- a registry modelled on ToolRegistry (null until the catalog is ready, PreferSynchronous, built-ins
  win, diagnostics);
- `executable` set to true;
- text, markdown and timeline stay app-core so they can never be disabled.

A note whose type is unknown, or later disabled, opens raw and read-only with a reason (D3), and its
marker is never touched.

**Rationale.**
- A plugin kind now would add discovery, trust, ordering and Omarchy native-helper gating
  (hosts/omarchy/Backend.qml:15-19) to the first release, for one type the app ships itself.
- Disabling a built-in type package would turn every timeline into a read-only note.
- The registry module gives the later kind its seam without committing to its shape.

**Rejected.**
- `plugins/org.note-note.timeline/` as a package now: disable-ability, catalog ordering (notes could
  open before the registry is ready, Workspace.qml:839-845) and exact-count test churn
  (services/extensions/selftest.py:37-55).
- A registry with QML components: v1 has one non-rich body.

**Evidence.**
- services/extensions/manifest.py:30, 151, 203-206.
- docs/decisions.md:991-1005.
- docs/editing-tools.md:233-236.
- docs/plugins.md:129-134.
- assets/fonts/nerd-symbols/SymbolsNerdFont-Regular.ttf (glyph list).

### D8 — Timeline data model and canonical body format

**Decision.**

**Model.** An ordered list of at most 500 events `{ checked, title, description }`.
- `title`: 1–256 UTF-16 code units.
- `description`: 0–4096 UTF-16 code units, one paragraph, no line breaks.
- Neither may contain C0/C1 controls (U+0000–U+001F, U+007F–U+009F), U+2028 or U+2029.
- Neither may have leading or trailing whitespace by Python's `str.isspace`.
- Text is plain and never Markdown: a `*` is a star.

**Canonical body** (the editor writer's form, verified): no blank line between events; a blank line
and a two-space indent before a description.

```
- [x] Kickoff

  Agree the scope with the team
- [ ] Design
- [ ] Pack the bags

  Passport, charger, the blue jacket
```

Escaping is the editor writer's (mdtext), for example `\*\*bold\*\*`, `\=\=mark\=\=`, `\<b>`,
`\-` at a line start. An empty timeline is the empty body.

**Read** (`services/markdown/timeline.py: read(markdown) -> events | NotTimeline(reason)`). The body
is accepted when `parse.parse()` yields exactly one unordered list of `task_list_item`s, ignoring
`blank_line` tokens. Each item must hold one or two `paragraph`/`block_text` children whose inline
tokens are only `text` and `softbreak`; a soft break reads as a space. Titles must be non-empty,
everything must be within the limits, and there must be no control characters. So hand edits that
render the same are accepted and normalised on the next save from the view: blank lines between
items, `*`/`+` bullets, `[X]`, CRLF, wrapped lines, four-space-indented descriptions.

Anything else raises `NotTimeline` with words for the status line:
- "text outside its list of events";
- "an item without a checkbox (item 4)";
- "an event with more than a title and one paragraph (event 2)";
- "bold text (event 3)", "a link (event 1)", "a line break (event 2)";
- "an event without a title (event 5)";
- "more than 500 events";
- "a control character (event 1)".

**Write** (`write(events) -> markdown`). Builds the editor dialect's HTML
(`<ul><li class="checked|unchecked"><p>title</p><p>description</p></li></ul>`, text HTML-escaped)
and returns `qthtml.convert(html)["note"]`. The editor's own reader writes the Markdown, so the output
is the editor's fixpoint by construction. Any invalid model raises.

**Summary** (`summary(events) -> str`): "3 of 7 done · next: Pack", "All 7 done", or "No events yet".
The next event's title is capped at 200 characters like `notefile.PREVIEW_CHARS`.

**CLI.** `python3 services/markdown/timeline.py read|write`:
- stdin is capped at 8 MiB, like qthtml/__main__.py:41;
- framed JSON answers: `{"events": [...]}`, `{"notTimeline": "<reason>"}`, `{"markdown": "..."}`;
- a run with no frame is a failure.

**JS side.** `ui/timeline/TimelineModel.js` (`.pragma library`) holds only model operations and the
editor form: `event`, `form`, `fromForm`, `check`, `uncheck`, `toggle`, `add`, `edit`, `remove`,
`summary`, `inOrder`, `clean`, `problem`, and the limits `MAX_EVENTS`, `MAX_TITLE`,
`MAX_DESCRIPTION`. It has no Markdown parser.

**Lossless guarantees, each pinned by a test.**
1. `read(write(m)) == m` for every valid model.
2. `to_markdown(to_html(write(m))) == write(m)`, pure and through Qt.
3. `unkept(write(m)) == []`.
4. Every title and description character survives a read; only whitespace that Markdown itself
   collapses is normalised.
5. A body that is not a timeline is never rewritten by the timeline view.
6. A save never writes the marker.

**Prerequisite found here.** `mdtext.LINE_START` misses a lone `+` (services/markdown/mdtext.py:27,
`[-+*](?=\s)`). A paragraph or description that is exactly `+` cannot be saved at all ("the document
cannot be saved without changing its text"), and that is true in the Markdown editor today
(scratchpad/guardian/marker.py). The fix, `[-+*](?=\s|$)`, breaks none of the existing converter
CASES, and with it 3000 random models pass (1)–(3) with zero failures, and sampled bodies stay
unchanged through Qt (scratchpad/guardian/proto_fixed.py).

**Rationale.**
- A Markdown task list keeps local notes "plain Markdown readable by any tool"
  (docs/business-requirements.md:32-34).
- The body opens editable in the existing Markdown editor (unkept is empty).
- It is searchable by search.py.
- It degrades to a checklist without the marker.
- Writing through the reader avoids a second, cross-language escaper that could drift.
- Single-paragraph descriptions avoid three backend hazards:
  - trailing-space hard breaks, which outside editors strip; the reader writes `"  \n"`,
    reader.py:524-525;
  - OneNote's loss of indent on multi-line descriptions;
  - Notion's refusal of multi-paragraph items.
  Multi-line descriptions can come later as an additive grammar change, and older versions would
  then fall back to Markdown safely.

**Rejected.**
- Bold titles (`- [ ] **Pack**`): a hand-added plain item would fall back.
- Tight items with continuation lines: the Markdown editor joins them, so it is not
  Markdown-editor-safe.
- Title and description in one paragraph with a hard break (Notion's natural shape): fragile
  trailing spaces, and OneNote flattens `<br>` on toggle.
- YAML or JSON events in front matter: needs a YAML subset, is invisible to search and preview, and
  is unreadable elsewhere.
- Fenced JSON or an HTML comment marker in the body: `unkept` makes it read-only.
- A pure-JS Markdown codec: duplicates the escaper across languages.
- Strict byte-exact acceptance: every outside edit that renders the same would fall back to Markdown.

**Evidence.**
- services/markdown/parse.py:72-74, 100-106, 120-134.
- services/markdown/qthtml/reader.py:73-101 (convert raises when text would be lost), 283-366,
  519-525.
- services/markdown/mdtext.py:27, 84-101.
- services/markdown/qthtml/__main__.py:41.
- scratchpad/guardian/fixpoint.py, shape.py, timeline_proto.py, proto_fixed.py, entities.py,
  marker.py.
- Notion map probes A/C; OneNote map section 4.

### D9 — Check semantics

**Decision.**
- **Check** event k: events 1..k become checked.
- **Uncheck** event k: events k..n become unchecked, so what is done stays the top of the list.
- The status line says "Checked 3 events" or "Unchecked 2 events" only when more than one changes.
- **Triggers.** Space on the focused event, or a click on its circle. A click on the text only
  focuses it.
- **States from outside edits** (an unchecked event above a checked one, from Obsidian, a phone, or
  merges) are shown exactly as stored, and the progress line adds "· not in order". They are never
  repaired silently: no write happens until the user acts, and that action's rule repairs the part
  it covers.
- **Undo.** Ctrl+Z, Ctrl+Shift+Z and Ctrl+Y inside the view. One step per user action (check,
  uncheck, add, edit, delete), at most 200 steps, cleared when the note changes. A new action clears
  redo. Each undo or redo is an edit and is saved.

**Rationale.**
- The user asked for "check one, check all above". The mirror rule keeps the invariant the user's
  own actions create, so the view never produces an out-of-order state itself.
- Silent repair on load would be an unrequested write to a file another tool owns.
- Undo is the safety net for a multi-event uncheck.

**Rejected.**
- Uncheck only k: creates out-of-order states from the user's own clicks.
- Normalise on load: a silent write.
- Refuse to show out-of-order notes: hides content for a cosmetic reason.
- Qt's native checkbox toggle: per item, with no hook (ui/NoteEditor.qml:2219-2223).

**Evidence.**
- The user request.
- ui/NoteEditor.qml:2219-2223.
- lib/notemerge/README.md:8-21 (per-entry checkbox merges).
- Notion and OneNote maps (their apps toggle each item independently).

### D10 — Timeline view UX

**Decision.**

**Layout.** Inside the sheet under the title, as a ListView over `events`:
- a progress line ("3 of 7 done · next: Pack", Color.token("text.secondary"), Style.font.bodySmall,
  objectName `timelineProgress`);
- then one row per event: a check circle on a vertical spine, the title (note font,
  `bodyFontSize`), and the description below it, wrapped, in `Style.secondaryText(foreground, 0.65)`;
- then the "Add new event" row: "+" in accent ink, the label dimmed to `Style.secondaryOpacity(0.65)`
  until hovered or focused, like ui/NoteList.qml:440-492.

**Drawing.**
- Circle side `Math.round(bodyFontSize * 1.1)`, radius side/2.
- Unchecked: border `Util.alpha(foreground, 0.4)`, 0.75 on hover.
- Checked: accent fill with the tick in `background`, drawn by a shared `ui/CheckFace.qml` extracted
  from NoteEditor's checkbox face (2242-2284) with a `radius` parameter.
- Focused: a 2 px accent ring.
- Spine: `Style.spacing.hairline` wide. A segment is accent ink
  (`Qt.tint(foreground, Util.alpha(accent, 0.6))`) when both of its ends are checked, otherwise
  `Color.token("border.default")`.
- Checked titles use `Style.secondaryText(foreground, 0.6)`, with no strikethrough.
- The focused row has `Style.hoverFillFor(foreground, accent)`.
- Colour animations are 120 ms.
- Only Style keys both hosts define (design/Style.qml:20-47) are used. There are no new theme tokens.
- All text is `Text.PlainText`.

**States.**
- unchecked, checked, hover, focus;
- read-only: circles inert, add row hidden, no edits, no `edited()`;
- loading: the skeleton, as today;
- empty: "No events yet" and the add row.

**Form.** Inline, never modal: the add row turns into `ui/timeline/EventForm.qml`, in the
SidebarAction and ToolForm conventions:
- a title `ChromeTextField` (single line);
- a description `ui/ChromeTextArea.qml`: new, wrapping, no newlines; pasted line breaks become
  spaces;
- a hint "Enter to add · Tab for a description · Esc to close", replaced by a validation `message`
  in `Color.urgent`;
- an "Add" button, or "Save" and "Delete event" when editing.

**Form keys.**
- Enter in either field submits. After an add, the form clears and stays open for the next event.
- Tab and Shift+Tab move between the fields.
- Escape closes the form. Its text is kept until the note changes, so reopening restores it.
- An empty title, or text over the limits, refuses with a message.
- At 500 events the add row reads "A timeline holds at most 500 events".

**Editing and deleting (first release).**
- Enter, or a double click, on an event opens the same form in its place, prefilled. Enter saves,
  Escape cancels.
- Delete on a focused event removes it, and the status line says "Deleted “Pack” — Ctrl+Z brings it
  back".
- Reordering is later.

**Keyboard model.**
- Down or Enter from the title focuses the first event, or the add row.
- Up/Down move between events and the add row; Home and End jump to the first event and the add row.
- Up from the first event goes to the title.
- Space toggles by the D9 rule.
- Enter edits the focused event, or opens the form on the add row; Ctrl+Enter opens the add form from
  anywhere in the view.
- Delete removes the focused event.
- Ctrl+Z, Ctrl+Shift+Z and Ctrl+Y undo and redo.
- Every key goes first to `Workspace.handleShortcut` (Keys.priority BeforeItem, as the title and body
  do), so Ctrl+N, Ctrl+Up/Down, Ctrl+K and Escape ("back") keep working.
- There is no new shortcut context. A focused timeline is `workspace`.
- `handleShortcut` and `WorkspaceActions.blocked` gain `editor.formOpen` beside `tools.panelOpen`.
  While the form is open, no app shortcut runs and Escape reaches the form (Workspace.qml:2150,
  2545-2547).

**Accessibility.** These set a new precedent and are documented.
- Event rows: `Accessible.role: Accessible.CheckBox`, `Accessible.checked`, `Accessible.name: title`,
  `Accessible.description: description`.
- Add row: `Accessible.Button` "Add new event".
- Form fields: named "Event title" and "Event description".

**objectNames.** `timelineView`, `timelineProgress`, `timelineEvent-<i>`, `timelineCheck-<i>`,
`timelineAddEvent`, `timelineForm`, `timelineFormTitle`, `timelineFormDescription`,
`timelineFormMessage`, `timelineFormSubmit`, `timelineFormDelete`.

**Rationale.**
- Mouse-free is a success criterion (docs/business-requirements.md:82).
- "No modal dialogs between the user and their text" (:29-31) rules out a PromptDialog-like form.
- Edit and delete are required so a typo is not a trap that sends the user to another app.
- The gates reuse the tool-panel precedent exactly.

**Rejected.**
- A modal two-field dialog.
- A ToolForm popover: hard-typed to `Tool` (ui/editing/ToolForm.qml:13).
- A new `timeline` shortcut context with registry bindings for bare keys: plumbing through resolve.js
  scopes for little gain.
- Strikethrough for checked items: harms readability.
- Reordering in v1: it creates out-of-order states and more undo cases.

**Evidence.**
- ui/NoteEditor.qml:1890-1914, 2219-2291.
- ui/NoteList.qml:440-492.
- ui/SidebarAction.qml:89-132.
- ui/editing/ToolForm.qml:11-88.
- docs/editing-tools.md:345-364.
- Workspace.qml:2135-2176, 2543-2548.
- design/Style.qml:20-47, 57-77.
- services/shortcuts/defaults.js:20.

### D11 — List and search integration

**Decision.**

**Glyph.** `ui/NoteSummary.qml` gains `property string glyph`. When it is non-empty, a Text in
`Style.fontFamily` at `Style.font.iconSmall`, `Style.secondaryText(foreground, 0.55)`, sits before
the title on the first line. NoteList and SearchResults pass `NoteTypes.glyph(row.noteType)`. Rows
carry `noteType` only when it differs from the provider's default (D3), so Markdown notes in local
and plain notes in Sticky show no glyph.

**Progress preview.** The provider's `preview` for a timeline row is `timeline.summary(...)`:
"3 of 7 done · next: Pack". For local it is computed in Python from the whole note when the note is at
most 64 KiB (`TIMELINE_PREVIEW_BYTES`), both at listing and in the save answer, so the two never
disagree. A larger timeline, or a body that is not in timeline form, keeps the generic first-line
preview.

**Live update.** The save answer's preview refreshes the row about 500 ms after a check (local
debounce, Provider.qml:37-42). There is no host-side projection in v1.

**Untitled timelines.** `Workspace.displayTitle` uses `NoteTypes.previewNames(row.noteType)`: for a
timeline with no title, the list says "Untitled timeline" instead of deriving a title from the
progress text.

**Search.** Body search already finds event text (search.py matches the body), and title/preview
matching is unchanged.

**Rationale.**
- Rows carry only what the list shows (docs/decisions.md:444-448).
- One summary helper used by the provider keeps list and save consistent.
- The 64 KiB bound keeps the listing's 10 s deadline safe (list.py:64-67).

**Rejected.**
- A structured `progress` row field: more contract surface for the same pixels.
- Computing the summary from the 4 KiB head: wrong for long timelines.
- Reading whole notes up to 2 MiB in the listing: risks partial listings.
- The provider's `icon` row field as the glyph: per-provider drawing of a host concept.
- A live host projection like unsavedTitles: unnecessary at a 500 ms save debounce.

**Evidence.**
- ui/NoteSummary.qml:6-57.
- ui/NoteList.qml:447-461.
- ui/SearchResults.qml:104-117.
- services/notes/sidebar.js:19-22.
- Workspace.qml:1302-1324.
- plugins/org.note-note.local/list.py:64-67, 147-153.
- plugins/org.note-note.local/search.py (body-only match).

### D12 — Provider support matrix (first release)

**Decision.**

| Provider | `noteTypes` | Changes |
|---|---|---|
| local | `["markdown", "timeline"]` | The changes in D13 |
| examples/hello | `["markdown", "timeline"]` | Keeps `markdown: true`. Its in-memory notes gain `noteType`; rows and the load answer carry it; `create(target, cb, options)` honours `options.noteType` or answers `{ error }`; new code uses braces with bodies on their own lines. It must still load as a legacy-directory provider (tests/standalone_launch.qml:38-40) |
| OneNote | `["markdown"]` only | Deferred until a `data-id` marker is verified live in every OneNote app. The body shape stays OneNote-compatible: single-line title paragraph plus at most one description paragraph. Its unread per-page `markdown: true` field (onenote.py:1380, 1387) stays untouched |
| Notion | `["markdown"]` only | Deferred until the user chooses a visible marker; no invisible metadata exists, and every check would rewrite the whole page |
| Sticky Notes | `["text"]` only | Unsupported: plain text, no title, and a timeline would be invented syntax shown raw in Microsoft's apps (docs/decisions.md:557-561) |

All built-ins declare `noteTypes` explicitly, which exercises the modern path. A provider may declare
`timeline` only when its save stores the body byte for byte (line endings aside) and is not
merge-aware. A merge-aware provider must first prove that its merge keeps timeline bodies in timeline
form.

**Rationale.**
- Each deferral is the provider map's own verified finding.
- Local is where the format guarantees can be pinned by tests today.

**Rejected.**
- OneNote via a title convention or `<meta>`: visible or unsupported.
- Notion via the icon now: a product decision the user has not made.
- Sticky plain-text syntax: invents behaviour.

**Evidence.**
- OneNote map section 3, recommendations.
- Notion/Sticky map recommendations.
- docs/decisions.md:557-561.
- tests/standalone_selftest.py:190.
- tests/standalone_launch.qml:38-40.

### D13 — Local provider details

**Decision.**

**`notefile.py`.**
- Adds `TYPE_KEY = "note-note-type:"`, `TYPE_ID` (the D1 grammar) and `UNREADABLE = "?"`.
- `note_type(extra)` returns `""` when no line names a type. Otherwise it returns the one value the
  key lines agree on, or `UNREADABLE` for disagreeing lines or a value that is not an id.
- `type_line(noteType)` returns the line to write.
- `preview(body, note_type="", size=0)`: the timeline summary when `note_type == "timeline"` and
  `0 < size <= TIMELINE_PREVIEW_BYTES`, falling back to the generic preview on `NotTimeline`. It
  imports `timeline` lazily, as operations.py imports qthtml (operations.py:19-24).
- The marker stays an unowned `extra` line, so a save writes it back verbatim (notefile.py:66-76;
  operations.py:136). The app writes it only for non-default types, and never writes
  `note-note-type: markdown`, so existing notes are never rewritten.

**`list.py`.**
- `head_of(path, size, deadline)` returns `(title, preview, note_type)`.
- It reads `TIMELINE_PREVIEW_BYTES` instead of `HEAD_BYTES` only when the head names a timeline and
  the file fits.
- The N record gains a trailing 8th field: `""`, an id, or `?`. Today's Provider.qml reads p[1]..p[6],
  so older code ignores it. The docstring changes too.

**`operations.py`.**
- `read` answers `noteType: note_type or "markdown"`. `UNREADABLE` answers `editable: false`, with
  the reason "This note's front matter names its kind in a way Note Note cannot read
  (note-note-type), so it opened read-only", and no `noteType`.
- `unkept` still runs for every Markdown-bodied type.
- `create` takes `noteType` in `("markdown", "timeline")`, else raises "this notebook cannot hold
  that kind of note". It writes `notefile.serialize("", "", [notefile.type_line("timeline")])` for a
  timeline and returns `noteType`.
- `save` returns `noteType` (from the current file's extra) and the type-aware preview.

**`Provider.qml`.**
- Entries carry `noteType: p[7] || "markdown"`.
- Note rows (211-216) and `searchable()` (226-230) carry `noteType`.
- The load answer (509-511) forwards `noteType: result.noteType`.
- The save commit (548-549) keeps `noteType: result.noteType || note.noteType`.
- `create(target, cb, options)` sends `noteType` and builds the entry with `noteType`.
- `readonly property var noteTypes: ["markdown", "timeline"]`, keeping `markdown: true`.

**Limits.** A front matter longer than 4 KiB hides the type from the listing (no glyph, generic
preview), but the load is authoritative and the view still opens. Creation writes the marker right
after the title line.

**Search.** Unchanged; body-only matching finds event text.

**Selftests.** Every one round-trips through the real `operations.py` and `list.py`:
- `test_note_type_round_trip`: create a timeline, check the marker bytes, the N field, `read`
  noteType, and that a save keeps the marker byte-exact.
- `test_type_marker_survives_foreign_front_matter`: tags before and after, CRLF, BOM.
- `test_conflicting_type_lines_open_read_only`.
- `test_unknown_type_is_reported_verbatim`: `kanban`.
- `test_create_refuses_an_undeclared_type`.
- `test_timeline_preview_and_its_bound`.
- `test_type_beyond_the_head`.
- `test_search_finds_event_text`.
- FIELDS N becomes 8 (selftest.py:347).

**Rationale.**
- The front matter is the format's own metadata place. It is read in the listing head, preserved
  by today's save path (verified), invisible to search, and shown as a property by Obsidian.
- A namespaced key cannot collide with Hugo's or Obsidian vaults' `type:`. A bare `type:` would make
  every such note open read-only as an unknown type, or force "unknown means Markdown", which would
  lose the forward-compatibility rule.
- Absent means Markdown, so the change is zero-touch for existing files.
- Fixing both rebuild traps explicitly keeps the propagation visible.

**Rejected.**
- A bare `type:` key.
- Owning the key in `split()`/`serialize()` like `title`: a save could then rewrite or drop it.
- A file extension: changes identity and .order names.
- A sidecar file: blocks folder delete (operations.py:55-68).
- A body marker: an HTML comment makes `unkept` answer read-only.
- `Object.assign` for the load answer: hides which fields the contract carries.

**Evidence.**
- plugins/org.note-note.local/notefile.py:1-86.
- operations.py:19-24, 104-141.
- list.py:5-11, 64, 147-153, 253.
- Provider.qml:20, 211-216, 226-230, 444-446, 499-575.
- selftest.py:347, 439-493, 524-554.
- Local map 3.5 (an unowned line survives a save, verified).

### D14 — Save, merge, conflict and recovery

**Decision.**

**Save.** `flushSave` keeps its order. `snapshotDocument()` returns
`{ documentType: "timeline", title, body: TimelineModel.form(events), base }`. Then `isStored` runs,
the draft is registered, and `editor.requestBody(draft.document, cb)` serialises that exact snapshot
through `markdown.fromTimeline` into the framed `(body, ok)`. `provider.save(path, title, body, cb,
{ view, resolution })` is unchanged. If the codec fails, the save fails with "the note could not be
read for saving" and the draft is kept (NoteSession.qml:499-501).

**No-op detection.** `isStored` compares `documentType`, `title` and `body`, so the same strings in a
different form never match (NoteSession.qml:362-367). The timeline form is the deterministic JSON
`[[1,"Kickoff","Agree…"],[0,"Design",""]]`: checking and then unchecking the same event sends
nothing.

**Drafts, recovery and deletion recovery.** Each is a snapshot, so each carries `documentType`, and
`restoreDocument` picks the right body (NoteSession.qml:233-245, 276-282, 402-469). `replacePath`
needs no new map.

**Conflicts.** None arise in v1: no timeline-declaring provider is merge-aware. If one does, the
existing MergeConflict shows the raw stored Markdown passages, which read as checklist lines
(ui/MergeConflict.qml:90-104). A resolution re-enters `flushSave`. A merged body that is no longer in
timeline form opens as Markdown on the next load.

**Fallback notes.** These are timelines held as Markdown. They save Markdown through the existing
path, and the provider keeps the marker.

**Rationale.** Every existing session guarantee becomes type-safe by making the type part of the
snapshot rather than state beside it. The framed answer keeps "a failure never reads as an empty
note".

**Rejected.**
- Sending the type in save options: a save could then change types.
- A canonical Markdown string as the timeline snapshot: needs a synchronous Python call.
- A JS Markdown serialiser for the snapshot: the cross-language escaper again.

**Evidence.**
- services/notes/NoteSession.qml:37-43, 233-300, 362-367, 402-507, 509-542.
- docs/decisions.md:489-555.
- ui/MergeConflict.qml:90-104.

### D15 — Commands, shortcuts and the palette

**Decision.**

**`services/shortcuts/defaults.js`.**
- `{ id: "newTimeline", workspace: true, keys: ["Ctrl+Alt+N"], context: "notes", group: "Notes",
  description: "A new timeline in the open notebook" }`
- `{ id: "addTimelineEvent", workspace: true, keys: [], context: "notes", group: "Notes",
  description: "Add an event to the open timeline" }`. No default key: in the view, Ctrl+Enter and the
  add row do this, so no global key is stolen from the title field.

**`WorkspaceActions`.**
- Handlers: `newTimeline: host.newNote("", undefined, "timeline")` and
  `addTimelineEvent: host.addTimelineEvent()`, which calls `editor.openEventForm()`.
- `state` gains `documentType` and `editorWritable`.
- `canCreateNote(noteType)` filters by type.
- `unavailable()` answers "Open a notebook that can hold timelines." and "Open a timeline you can
  edit.".
- `blocked` includes `editor.formOpen`.

**Other files.**
- `plugins/org.note-note.workspace/plugin.json`: `new-timeline` ("New Timeline"; keywords create,
  add, checklist, steps) and `add-timeline-event` ("Add Timeline Event"; keywords event, step,
  timeline).
- docs/commands.md:61 and skills/note-note-plugin/references/commands.md: the supported action ids.
- services/extensions/selftest.py:44-47: the pin.
- The Key bindings page shows both. The new combination does not collide with any existing default
  or tool key (defaults.js:7-28; ui/tools shortcuts).

**Rationale.**
- One executor serves keys, the palette and commands (Workspace.qml:2182-2203).
- Availability follows `state` (WorkspaceActions.qml:10-16).
- The Ctrl+N family is consistent.

**Rejected.**
- Ctrl+Shift+T: an unrelated letter in the creation family.
- A default Ctrl+Enter for `addTimelineEvent` in the notes context: it would steal the key in a
  Markdown note's title with an "unavailable" status.
- A registry-bound timeline context.

**Evidence.**
- services/shortcuts/defaults.js:7-33.
- services/commands/WorkspaceActions.qml:10-98.
- plugins/org.note-note.workspace/plugin.json:8-60.
- services/extensions/selftest.py:44-47.
- docs/commands.md:49-62.
- ui/tools/*.qml shortcut keys.

### D16 — Prerequisite fixes

**Decision.**

**Before the feature** (release 1.0.41):
1. The lone-`+` escaping bug (services/markdown/mdtext.py:27). Add CASES "a lone plus sign is
   text" in qthtml/selftest.py and a case in test_regressions.py:422.
2. F1: `replacePath` deletes `pathAliases[next]` and re-points aliases whose value is `previous`
   (NoteSession.qml:75-76). A timeline in a renamed local section would otherwise silently stop
   saving.
3. F17: CMake reads the suite names from `tests/transition_selftest.py --list-suites`, and
   tests/selftest.py SUITES become argv tuples. A new `timeline` suite then cannot run under one
   runner only.
4. Capability defaults through `Capabilities.of` (the hasTitle binding bug, newNote focus).
5. F13: add `count` to the skill's row shape, folded into the contract-doc edit.
6. F2 and F21: `runRowAction` waits until `session.saveInFlight(currentPath)` is false before
   `rowAction`, and unlocks unconditionally on `result || {}` (Workspace.qml:2109-2131).

**Alongside, recommended but not blocking.**
- F14: `stored` as a single `{ path, document }`.
- F15: a `Binding` for `editor.readOnly`; the timeline view binds to `editor.readOnly`, so one
  derived source matters more.

**Not needed.**
- F16: the timeline view is a plain child, not a third props Loader.
- F20: `unkept` stays the local provider's verdict for every Markdown-bodied type.

**Rationale.**
- Each "before" item sits on a path the feature extends: the converter it writes through, the
  session it saves through, the suite lists it registers in, and the capability defaults it reads.
- Shipping them first keeps the feature's diff about the feature.

**Rejected.**
- Shipping the feature over F1: a rename and rename-back would stop a timeline's saves silently.
- Leaving F17: a new suite missing from CTest.

**Evidence.**
- CODE-REVIEW-2026-10-11.md F1 (:52-57), F2 (:59-64), F13, F14, F15, F17, F20, F21.
- services/markdown/mdtext.py:27.
- scratchpad/guardian/marker.py.
- CMakeLists.txt:99.
- tests/transition_selftest.py:18.
- tests/selftest.py:41, 50, 55.

### D17 — Test plan

**Decision.** Every new suite is registered in both tests/selftest.py and CTest. Python suites are
named `*selftest*` so they are kept out of packages.

1. **Codec**, `services/markdown/timeline_selftest.py` (new):
   - a seeded property test (3000 models): `read(write(m)) == m`, the pure fixpoint, `unkept` empty;
   - the accepted-variant and refused-variant tables with exact reasons;
   - limits on read and on write: 501 events, 257-unit title, 4097-unit description, control
     characters;
   - lone markers `+ - * # > 1. 1)` in titles and descriptions;
   - CLI framing: `read`, `write`, a crash means no frame, an 8 MiB cap.
2. **Converter**, services/markdown/qthtml/selftest.py CASES: "timeline: events with and without
   descriptions", "timeline: escaped titles", "a lone plus sign is text". These run in the pure leg
   and through Qt.
3. **Pure JS** in tests/transitions.qml pureCases:
   - TimelineModel: check and uncheck ranges, out-of-order input preserved, add, edit, remove,
     summary, `clean` (the Python whitespace set, controls, UTF-16 limits), deterministic form, and
     titles `__proto__` and `constructor`;
   - Capabilities: legacy true, false and absent; explicit wins; invalid falls back to legacy;
     `timeline` without `markdown` is invalid; hasTitle absent is true;
   - NoteTypes.opened: unknown and undeclared give raw read-only; a legacy provider's `noteType` is
     ignored; the registry is prototype-free.
4. **Session**, tests/transitions.qml sessionCases. The fake editor gains `documentType` and
   `setNote(documentType, t, b, shown)`. Cases:
   - the load answer's type reaches `setNote`;
   - the snapshot carries the type, and `isStored` fails when only the type differs;
   - a timeline draft restores as a timeline;
   - deletion recovery keeps the type;
   - `replacePath` keeps the draft's type;
   - A(markdown) → B(timeline, slow) → A drops B's late answer;
   - an unknown type gives `noteReady(readOnly)` with the reason.
5. **Real keys**, the `timeline` suite in tests/EditorKeys.qml with the real converter and codec:
   - Space checks above and unchecks below;
   - an out-of-order body is shown as stored, with no save without an action (`quietSession`);
   - the add form: End, Enter, title, Tab, description, Enter appends, and `requestBody` equals the
     expected Markdown;
   - Escape keeps the form text; Escape with the form closed reaches the host;
   - empty and overlong titles are refused;
   - edit and delete, then undo and redo;
   - read-only is inert;
   - a body not in timeline form opens rich, with the status;
   - Ctrl+B and Ctrl+1 do nothing and do not touch the hidden document;
   - Down from the title focuses event 1.
   `resetEditor()` calls `clearDocument()`.
6. **Local** provider selftest cases (D13).
7. **tests/test_regressions.py**:
   - notefile property cases with type lines;
   - `note_type` cases;
   - `TimelineModel.js` limits equal `timeline.py` limits, after the `test_document_dialect_agrees_across_adapters`
     pattern at :551-570.
8. **services/extensions/selftest.py**: the new workspace commands pin.
9. **Host level**, the core suite with `--standalone`:
   - Ctrl+Alt+N on a Sticky tab creates a local timeline and switches tabs;
   - the file holds the marker;
   - the row shows the glyph;
   - the palette lists New Timeline as available or unavailable.
10. **Unchanged legacy tests stay green.** hello still loads from the legacy directory
    (tests/standalone_launch.qml:38-40).

**Rationale.** Each guarantee in D8, D9, D13 and D14 has a test at the lowest level that can see it.

**Rejected.**
- UI-only testing.
- Mocking the codec in the real-key suite: it would miss the Python/JS seam.

**Evidence.**
- tests/selftest.py:15-43.
- CMakeLists.txt:71-131.
- tests/transitions.qml:250-252, 375-414, 785-965.
- tests/EditorKeys.qml:300-366, 3048-3059, 3336-3346.
- plugins/org.note-note.local/selftest.py:78-112, 557-582.
- tests/test_regressions.py:86-110, 422, 551-570.

### D18 — Docs and decisions

**Decision.** Each document changes in the same commit as the behaviour it describes
(docs/release-process.md:36-37; docs/plugins.md:50-53).

- **docs/providers.md.**
  - Properties table: `noteTypes`; `markdown` as legacy shorthand, with "absent = plain text";
    `hasTitle`, with "absent = true".
  - A new section "Note types": vocabulary, declaration rules, per-note `noteType`, the host's rules
    (unknown or undeclared means raw read-only; a body not in form opens as Markdown; saves never
    change types), the timeline body format, the codec and summary helper, and a compatibility
    paragraph modelled on :170-175.
  - The footer rule at :185, amended (D4).
  - Load gains `noteType` and the existing `retry`.
  - Save documents the existing `merged` and `version`, and "never changes a type".
  - `create(target, cb, options)`.
  - The local format: the `note-note-type` key.
  - Limits.
- **skills/note-note-plugin/references/providers.md**: mirrors all of the above, plus F13 `count`.
- **skills/note-note-plugin/references/commands.md**: the action ids.
- **docs/commands.md**: the supported action ids and availability.
- **docs/decisions.md**: a dated section "2026-10: note types and timelines" with these entries:
  1. a note's type is per note, declared per provider;
  2. a timeline is a Markdown task list (the Markdown-safe-body rule for every type stored by a
     Markdown provider);
  3. the local marker is written at creation, never by a save;
  4. unknown types open raw and read-only;
  5. a body not in form opens as Markdown;
  6. the codec writes through the editor's reader;
  7. check above, uncheck below, out-of-order shown and never repaired;
  8. typed creation is a command, not a button;
  9. why OneNote, Notion and Sticky do not hold timelines yet;
  10. core types are app-owned.
- **docs/business-requirements.md**:
  - a product-decisions row for note types;
  - row 74 reworded per provider type list;
  - the non-goal at :57-58 clarified: "a note type changes how one note is shown and edited; there
    are no templates, schemas or queries across notes";
  - goal 3 restated: a timeline is plain Markdown plus one front-matter line.
- **docs/technical-requirements.md**:
  - :14, the editor format with the timeline codec;
  - :107-109, the stale row shape updated;
  - limits table: timeline 500 events, 256 and 4096 characters, 64 KiB preview bound.
- **README.md**:
  - Notebooks: timeline notes, the file format example;
  - Keys: Ctrl+Alt+N and the in-view keys;
  - Providers: which providers hold timelines.
- **plugins/org.note-note.local/getting-started.md**: a shortcut-table row for Ctrl+Alt+N. Only new
  roots get it.
- **docs/testing.md**: the codec selftest, the timeline suite, the local cases, `debugState`'s
  `documentType`, and a timeline manual checklist.
- **docs/security.md**: the codec as a decoder of hostile input, with its bounds and pre-release
  checklist line.
- **Release notes**: the metainfo `<release>`.

**Rationale.** The contract is "the API other people write against"; an additive change must still
be a documented one.

**Rejected.** Documenting the timeline only in the README: plugin authors read the skill.

**Evidence.**
- docs/providers.md:41-60, 170-213, 257-360.
- skills/note-note-plugin/references/providers.md:55-56, 229-247, 267, 314-328.
- docs/business-requirements.md:29-34, 57-58, 66-78.
- docs/technical-requirements.md:14, 99-101, 107-109, 170-188.

### D19 — Phasing and release

**Decision.** There are six phases. Each one keeps both runners green and is safe on its own.

- **P0, release 1.0.41: prerequisites.** The lone-`+` fix, F1, F2 and F21, F17, F13, and
  `Capabilities.of` with the hasTitle fix.
- **P1: type plumbing with no visible change.**
  - capabilities.js and notetypes.js (text and markdown only);
  - the NoteSession and NoteEditor protocol (`documentType`, `clearDocument`,
    `setNote(documentType, …)`, `requestBody(document, cb)`, `isStored` with the type);
  - sidebar row `noteType`, the NoteSummary glyph slot, and create `options`;
  - built-ins and hello declare their current single type;
  - contract docs.
- **P2: the codec.** timeline.py, its selftest, the `Markdown.qml` functions `toTimeline` and
  `fromTimeline`, and the converter CASES.
- **P3: local marker support.** The provider still declares only `markdown`, so a hand-written
  marker opens raw and read-only: safe.
- **P4, release 1.1.0.**
  - TimelineModel.js, TimelineView, EventForm, CheckFace and ChromeTextArea;
  - NoteEditor integration;
  - commands and shortcuts;
  - local and hello declare `timeline`;
  - all user docs;
  - version 1.1.0, a minor bump per docs/release-process.md:26-27 because the contract is added to,
    with a metainfo release.
- **Later.**
  - convert (D5);
  - reorder;
  - multi-line descriptions;
  - OneNote after live marker verification (docs/onenote-*.md);
  - Notion after a marker choice;
  - the `noteTypes` plugin kind;
  - a local version check.

**Rationale.** Staged rollout: every phase can stop and ship safely, and the riskiest change, the
protocol, lands before any new format exists.

**Rejected.**
- One big commit.
- Shipping the UI before the codec's property tests.
- A patch bump for a contract addition.

**Evidence.**
- docs/release-process.md:25-37.
- manifest.json:5.
- packaging/package.py:70-77.

### D20 — Risks and user decisions

See the two sections below.

## Architecture overview

**Declaring.** Each Provider.qml declares `noteTypes` (legacy: `markdown`). `Capabilities.of()`
normalises every capability once.

**Listing.**
1. The provider's rows and notes carry `noteType`.
2. `sidebar.js row()` copies the non-default ones.
3. NoteList, SearchResults and NoteSummary draw `NoteTypes.glyph()`.
4. The provider's `preview` carries the timeline summary, which local computes with
   `services/markdown/timeline.py summary()`.

**Opening.**
1. `Workspace.choosePath` → `NoteSession.selectPath` → `load`: `editor.clearDocument()`, then either
   the draft is restored with `restoreDocument(snapshot)` by `snapshot.documentType`, or
   `provider.load` runs.
2. `NoteTypes.opened(capabilities, answer)` gives `{ documentType, readOnly, reason }`.
3. `editor.setNote(documentType, title, body, shown)`.
4. For a timeline, `Markdown.toTimeline` runs `python3 timeline.py read`, which parses with
   `parse.py`. Events go to `TimelineView.show`, then `shown(true)`. `notTimeline` means the editor
   becomes Markdown, reports why, and runs `toHtml`. No frame means `shown(false)`, which ends in
   noteUnavailable.
5. `session.noteReady`.
6. `stored[path] = editor.snapshotDocument()`, that is `{ documentType, title, body, base }`.

**Editing.**
1. A TimelineView action runs a pure `TimelineModel` op. Events are replaced wholesale and pushed to
   undo, then `edited()`.
2. NoteEditor forwards `edited` → `session.onEdited` → `provider.noteEdited` (local 500 ms)
   → `saveRequested` → `flushSave`.
3. `flushSave`: snapshot (JSON form), then `isStored`, then the draft.
4. `editor.requestBody(draft.document)` → `Markdown.fromTimeline` → `python3 timeline.py write`, which
   builds editor-dialect HTML and runs it through the `qthtml.convert` reader into canonical Markdown.
5. `provider.save(path, title, body, cb, { view, resolution })`.
6. Local `operations.py save` re-reads the file's `extra` (the marker stays) and writes atomically. It
   answers `{ preview: summary, noteType, version }`; the Provider commit updates the entry, and the
   rows rebuild.

**Creating.**
1. Ctrl+Alt+N or the palette → `WorkspaceActions.newTimeline` → `host.newNote("", undefined,
   "timeline")`.
2. `newNoteDestination` is filtered by `Capabilities` support.
3. `p.create(target, cb, { noteType: "timeline" })`.
4. Local `operations.py create` writes `---\ntitle: \nnote-note-type: timeline\n---\n`.
5. `cb({ path })` → `choosePath` → open as above → `focusTitle`.
6. Enter or Down from the title → the add row → Enter → the inline EventForm.

**Keys.** The timeline's items forward keys to `Workspace.handleShortcut` first. A focused timeline
is the `workspace` context. While the form is open, `editor.formOpen` gates every shortcut and
`blocked`.

## File changes

| File | Phase | Change |
|---|---|---|
| services/markdown/mdtext.py | P0 | LINE_START `[-+*](?=\s|$)`: a lone `+` is escaped |
| services/markdown/qthtml/selftest.py | P0, P2 | CASES: lone plus; timeline shapes; escaped titles |
| tests/test_regressions.py | P0, P3, P4 | Lone markers stay text; notefile type cases; limits agree JS↔Python |
| services/notes/NoteSession.qml | P0, P1 | F1 `replacePath`; `NoteTypes.opened` in load; `clearDocument`; `setNote(documentType, …)`; `requestBody(document, cb)`; `isStored` with `documentType` |
| Workspace.qml | P0, P1, P4 | F2/F21 `runRowAction`; `openCapabilities` bindings (no `plain`); typed `newNote` and `newNoteDestination`; create options; paste guard on richText; `displayTitle` via NoteTypes; `debugState` `documentType` and `formOpen`; `handleShortcut` and `blocked` gate `editor.formOpen`; `addTimelineEvent()`; diagnostic for an invalid `noteTypes` in `addProvider` |
| tests/transition_selftest.py, CMakeLists.txt, tests/selftest.py | P0, P2, P4 | F17 single suite list (`--list-suites`), argv tuples; register `timeline_selftest` and the `timeline` suite |
| services/notes/capabilities.js (new) | P0, P1 | `of(provider)`, `rowType`, `supports`; legacy derivation; hasTitle and canImages defaults |
| services/notes/notetypes.js (new) | P1, P4 | Prototype-free registry (text, markdown; timeline in P4); `opened()`, `glyph`, `label`, `previewNames`, `untitled` |
| services/notes/sidebar.js | P0, P1 | `row()` `hasTitle` via Capabilities; `noteType` |
| ui/NoteEditor.qml | P1, P4 | `documentType`, `plain`/`richText` derived, `clearDocument`, typed `setNote`, `restoreDocument`/`snapshotDocument` with type, `requestBody`, dispatching focus/view/wordCount, guards on paste/undo/tool, TimelineView in the sheet, `formOpen`, `openEventForm`, CheckFace extraction |
| ui/editing/EditorApi.qml | P1 | `writable` uses `host.richText` |
| ui/NoteSummary.qml, ui/NoteList.qml, ui/SearchResults.qml | P1 | Glyph slot and pass-through |
| services/markdown/timeline.py (new) | P2 | `read`, `write`, `summary`, limits, `NotTimeline`, CLI |
| services/markdown/timeline_selftest.py (new) | P2 | Property, variant, limit and CLI tests |
| services/markdown/Markdown.qml | P2 | `toTimeline(markdown, cb)` and `fromTimeline(events, cb)`, framed |
| plugins/org.note-note.local/notefile.py | P3 | `TYPE_KEY`, `TYPE_ID`, `UNREADABLE`, `note_type`, `type_line`, type-aware preview |
| plugins/org.note-note.local/list.py | P3 | `head_of` type, 8th N field, docstring |
| plugins/org.note-note.local/operations.py | P3 | read/create/save carry `noteType`; unreadable marker opens read-only |
| plugins/org.note-note.local/Provider.qml | P1, P3, P4 | `noteTypes`; entries, rows, notes and load answer carry `noteType`; save commit keeps it; `create(target, cb, options)` |
| plugins/org.note-note.local/selftest.py | P3 | Type round trip, foreign front matter, conflicts, unknown, create refusal, preview, head, search; FIELDS N 8 |
| plugins/org.note-note.sticky/Provider.qml, notion/Provider.qml, onenote/Provider.qml | P1 | Declare `noteTypes` (`["text"]`, `["markdown"]`, `["markdown"]`) |
| examples/hello/Provider.qml | P1, P4 | `noteTypes`; per-note `noteType`; `create(target, cb, options)` |
| ui/timeline/TimelineModel.js (new) | P4 | Pure model ops, editor form, limits, `clean`, `problem` |
| ui/timeline/TimelineView.qml (new) | P4 | The view (ListView, progress, rows, add row, keys, undo, accessibility) |
| ui/timeline/EventForm.qml (new) | P4 | Inline add/edit form |
| ui/CheckFace.qml (new) | P4 | Shared check face (radius parameter) used by the editor overlay and the timeline circles |
| ui/ChromeTextArea.qml (new) | P4 | Wrapping, single-paragraph text area styled like ChromeTextField |
| services/commands/WorkspaceActions.qml | P4 | `newTimeline`, `addTimelineEvent`; `state` `documentType` and `editorWritable`; typed `canCreateNote` |
| services/shortcuts/defaults.js | P4 | `newTimeline` (Ctrl+Alt+N), `addTimelineEvent` (no key) |
| plugins/org.note-note.workspace/plugin.json | P4 | `new-timeline`, `add-timeline-event` commands |
| services/extensions/selftest.py | P4 | Workspace command pin |
| tests/transitions.qml | P1, P3, P4 | Fake editor protocol; session, pure and host cases; `record()` 8 fields |
| tests/EditorKeys.qml | P1, P4 | `setNote`/`requestBody` call sites; `resetEditor` `clearDocument`; `timeline` suite |
| tests/audio.qml, tests/extensions.qml | P1 | Call sites of `setNote` and `requestBody` |
| docs/providers.md, skills/note-note-plugin/references/providers.md | P0, P1, P4 | Contract (D18) and F13 |
| docs/commands.md, skills/note-note-plugin/references/commands.md | P4 | Action ids |
| docs/decisions.md, docs/business-requirements.md, docs/technical-requirements.md, docs/testing.md, docs/security.md, README.md | P4 | D18 |
| plugins/org.note-note.local/getting-started.md | P4 | Ctrl+Alt+N row |
| manifest.json, packaging/desktop/io.github.andreivinca.note-note.metainfo.xml | P0, P4 | 1.0.41, then 1.1.0 |

## Phases

### P0: prerequisites (release 1.0.41)

**Goal.** Remove the defects on the paths the feature extends, and normalise capability defaults.

**Steps.**
1. Fix mdtext LINE_START, with the CASES entry and regression test.
2. F1 in `replacePath`, with a transitions case for rename A→B→A, then open and save.
3. F2 and F21 in `runRowAction`, with a delayed-converter transitions case.
4. F17: `--list-suites`, CMake configure-time read, argv tuples, and a test that both lists agree.
5. Add `capabilities.js`; switch the Workspace bindings, `newNote` focus and `sidebar.js` to it, with
   pure tests for absent, true and false.
6. F13 and the defaults text in docs/providers.md and the skill.
7. Bump to 1.0.41 with a metainfo release.

**Exit criteria.**
- tests/selftest.py and ctest are green.
- A paragraph `+` saves.
- No "Unable to assign" warning for a provider without `hasTitle`.
- `omarchy plugin validate` passes.

### P1: type plumbing (no visible change)

**Goal.** Notes have a `documentType` end to end, with only text and markdown known.

**Steps.**
1. Add `notetypes.js` and `opened()`.
2. Change the NoteEditor protocol: `documentType`, `clearDocument`, typed `setNote`, snapshots,
   `requestBody`.
3. Change NoteSession: use `opened`, the type in `isStored`.
4. Workspace: remove `plain`; typed `newNote` and create options; paste guard.
5. sidebar.js `noteType` and the NoteSummary glyph slot.
6. Declare `noteTypes` on all providers and hello.
7. Update tests (fake editor, call sites, session cases, pure cases).
8. Update the contract docs and skill.

**Exit criteria.**
- Every existing suite is green, with no behaviour change visible in the app.
- The legacy hello loads.
- Session tests prove the type travels through drafts, recovery and `replacePath`, and that unknown
  types open read-only.

### P2: timeline codec

**Goal.** A bounded, fail-closed Markdown ⇄ events codec that is the editor writer's fixpoint.

**Steps.**
1. Add services/markdown/timeline.py (`read`, `write`, `summary`, CLI).
2. Add timeline_selftest.py (property, variants, limits, framing).
3. Add the `Markdown.qml` `toTimeline` and `fromTimeline` functions.
4. Add qthtml CASES through Qt.
5. Register the suite in both runners.

**Exit criteria.**
- 0 failures in the seeded property test.
- The CASES pass both legs.
- Over-limit and garbage input is refused with reasons, and there is no traceback output.

### P3: local marker

**Goal.** The local provider reads, writes and lists the type safely before any UI uses it.

**Steps.**
1. notefile: `note_type`, `type_line`, the type-aware preview.
2. list.py: the 8th field and the bounded whole read for timelines.
3. operations.py: read, create and save carry `noteType`.
4. Provider.qml: entries, rows, notes, load and save commit, create options.
5. Selftests and regressions; the transitions `record()` gets 8 fields.

**Exit criteria.**
- The marker survives every save byte-exact.
- An unreadable marker opens read-only.
- The local selftest is all green.
- A hand-written marker opens raw and read-only in the app, because local still declares only
  markdown.

### P4: timeline view and commands (release 1.1.0)

**Goal.** The feature the user asked for, on the verified foundation.

**Steps.**
1. Add TimelineModel.js and pure tests.
2. Add CheckFace (extracted), ChromeTextArea and EventForm.
3. Add TimelineView: layout, keys, undo, accessibility, objectNames.
4. NoteEditor integration and the `formOpen` gates.
5. Add `timeline` to the notetypes registry.
6. WorkspaceActions, defaults.js, workspace plugin.json, extensions selftest.
7. Local and hello declare `timeline`.
8. The EditorKeys `timeline` suite and host-level creation tests.
9. All docs, getting-started, release notes; bump to 1.1.0.

**Exit criteria.**
- All runners are green.
- The manual checklist passes: create with Ctrl+Alt+N, add three events, check the third (all three
  checked), uncheck the second (2 and 3 unchecked), undo, edit, delete.
- The file opens unchanged in another Markdown editor.
- Toggling a box in Obsidian keeps the note a timeline.
- Adding a heading outside opens it as Markdown, with the reason.
- `omarchy plugin validate` and `package.py` pass.

### Later

**Goal.** Extensions decided separately.

**Steps.**
1. Convert to and from timeline (D5).
2. Reorder events.
3. Multi-line descriptions (an additive grammar change).
4. OneNote: verify a `data-id` marker live and document it.
5. Notion: the user picks a marker.
6. The `noteTypes` plugin kind.
7. A local save version check.

**Exit criteria.** Each one gets its own design note and tests.

## Risks

| Risk | Mitigation |
|---|---|
| An older Note Note (≤1.0.40) opens a timeline as editable Markdown | Canonical body = the editor writer's fixpoint, so its saves keep timeline form; its saves keep the marker as an unowned `extra` line (verified). Residual: its lone-`+` bug fails a save of a "+" description; the draft is kept |
| Outside editors break the shape (heading, bold, nesting) | The codec refuses with a reason, and the note opens as the Markdown it is, editable per the provider's `unkept` verdict; nothing is rewritten by the timeline view |
| The first timeline save normalises a hand-edited file (blank lines, `*` bullets, `[X]`, wrapping) | Only whitespace and markers Markdown renders identically change; every text character is property-tested to survive; documented in README and decisions |
| A phone or sync check and a desktop check race (local is last-writer-wins) | Existing local policy (no version check); a clean note reloads on external change (NoteSession.qml:544-555); 500 ms debounce keeps the window small; documented; local version check listed for later |
| A front matter over 4 KiB hides the type from the listing | The load is authoritative and opens the view; creation writes the marker on line 3; selftest pins the behaviour |
| A maximal timeline exceeds the local 2 MiB note limit | The save fails with the provider's message and the draft is kept; limits documented |
| Hidden rich TextEdit receives input or tool actions while a timeline is shown | Area read-only; `EditorApi.writable` requires `richText`; paste, undo and tool guards; the focused timeline is the `workspace` context; EditorKeys tests Ctrl+B and Ctrl+1 |
| JS and Python disagree on limits or whitespace | Python validates every write and fails closed (draft kept); `test_regressions` pins equal constants; JS trims a superset of Python's whitespace after mapping controls |
| Form text lost when leaving the note | Escape keeps it; documented; it is never note content |
| Unchecking an early event unchecks many | Status line count plus a one-step undo |
| External providers already emitting a `noteType` field | Read only when the provider declares `noteTypes` |
| Contract and skill drift | Same-commit rule; existing drift (count, retry, merged, version) reconciled in the same edit |
| Test runner drift | F17 fixed before the new suite exists |
| Glyph shows as a missing-glyph box | U+F1533 verified in the bundled Symbols Nerd Font; drawn with `Style.fontFamily` |
| The protocol change breaks many tests at once | P1 lands alone with zero behaviour change; the fake editor mirrors the new protocol |
| Listing slows on many timelines | Whole-note reads only for timeline-marked notes ≤ 64 KiB, within the existing 10 s deadline |

## User decisions

1. **What does unchecking event k do?**
   - Options: (a) unchecks k and every event below it; (b) unchecks only k.
   - Recommendation: (a).
   - Why: it keeps "done" a prefix the user's own clicks cannot break. A count on the status line
     and one-step undo cover mistakes.
2. **What is the local front-matter key?**
   - Options: (a) `note-note-type: timeline`; (b) `type: timeline`; (c) `notenote: timeline`.
   - Recommendation: (a).
   - Why: a bare `type:` already means things in Hugo and many Obsidian vaults, and is permanent on
     disk once written.
3. **Where can a timeline be created in the first release?**
   - Options: (a) palette and Ctrl+Alt+N only; (b) also a "New timeline" footer row in local
     notebooks; (c) a type picker behind Ctrl+N.
   - Recommendation: (a).
   - Why: it is keyboard-first, does not grow the footer and keeps Ctrl+N's meaning. (b) can be added
     later by the local provider alone.
4. **What shape does an event description take?**
   - Options: (a) one paragraph with no line breaks; (b) multi-line with hard breaks; (c) several
     paragraphs.
   - Recommendation: (a).
   - Why: it is robust to outside editors stripping trailing spaces and representable in OneNote and
     Notion later. Lines can be added later without migration.
5. **What happens to a timeline note whose text an outside editor took out of timeline form?**
   - Options: (a) it opens as Markdown, editable per the usual rules, with the reason; (b) it opens
     as a read-only raw view.
   - Recommendation: (a).
   - Why: the Markdown path is the existing lossless-or-read-only path, and the user can fix the
     text in place.
6. **How strict is the reading of hand-edited timelines?**
   - Options: (a) accept anything that renders the same and normalise on the next save; (b) accept
     only byte-exact canonical text.
   - Recommendation: (a).
   - Why: (b) turns every harmless outside edit into a Markdown fallback.
7. **How do the fixes and the feature ship?**
   - Options: (a) 1.0.41 prerequisites, then 1.1.0 timeline; (b) one release; (c) patch-numbered
     like recent features.
   - Recommendation: (a), numbered 1.1.0.
   - Why: F1 is high severity and should not wait. The documented semver rule makes a contract
     addition a minor bump.
8. **Can events be edited, deleted and reordered in the first release?**
   - Options: (a) edit and delete now, reorder later; (b) all three now; (c) add only.
   - Recommendation: (a).
   - Why: without edit and delete a typo is a trap. Reorder creates out-of-order states and can wait.
9. **When do remote notebooks get timelines?**
   - Options: (a) local only now; OneNote after live `data-id` verification; Notion after you choose
     a visible marker (page icon or marker block); Sticky never. (b) Ship OneNote now with a title
     convention.
   - Recommendation: (a).
   - Why: there is no durable invisible marker on either remote today, and both apps toggle items
     independently.
10. **What does a timeline show in the note list?**
    - Options: (a) "3 of 7 done · next: Pack" as the preview, plus a timeline glyph; (b) the glyph
      only; (c) neither.
    - Recommendation: (a).
    - Why: progress at a glance is the point of a timeline, and the cost is one bounded helper.
