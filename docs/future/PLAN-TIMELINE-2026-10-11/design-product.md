# Timeline notes and note types - product and interaction design

Stance: **PRODUCT AND INTERACTION DESIGNER**. HEAD e2cdc4e, app 1.0.40. Nothing in the repository was changed; the codec prototype that backs D8 lives in scratchpad/product/.

## Thesis

A note's type is a property of the note that the provider stores and the host edits: a provider declares the types it can hold (noteTypes, with the legacy markdown flag kept as shorthand), reports each note's type (noteType) on rows and in the load answer, and the host picks the editor body before the document goes in, carrying the type in every snapshot, draft and save. The timeline is a GitHub task list on disk - one '- [ ]' / '- [x]' item per event, a bold one-line title and indented plain-text description paragraphs - so a local timeline stays readable, searchable and checkable in any Markdown tool, and an older Note Note (or a host that cannot show it) opens it as an ordinary checklist and saves it without losing an event (verified against the app's own converter). One Python codec on the vendored mistune (services/markdown/timeline) owns that grammar for the editor and for provider previews; the interaction rules (check everything above, uncheck everything below, add, move, delete) are a pure JS module. The note pane keeps its chrome and gains a body seam: the existing rich/plain TextEdit becomes one body behind a small interface and the new TimelineBody another, so no third flag is threaded through NoteEditor and the host capabilities that hang off the rich editor (themes, tool shortcuts, toolbar height) stay where they are. The experience is keyboard-first and modeless: arrows walk the events, Space checks (with everything above), Enter edits in place, 'Add new event' opens an inline title + description form that is part of the note as you type (nothing typed is ever lost; Esc discards, undoable), Ctrl+Shift+T creates a timeline and Ctrl+Enter adds an event from anywhere in it; no dialog ever stands between the user and the text. The first release ships the type for local notebooks and the example provider; OneNote and Notion stay Markdown until a durable marker is verified, Sticky Notes stays plain text. It fits this codebase because it reuses its own precedents - canReorder->reorder for additive contract change, framed converters so a failure never writes an empty note, read-only-with-a-reason for anything the editor cannot keep, provider-supplied footer actions for creation - and adds no dependency, no database and no hidden state.

## Decisions

### D1 - Content-type vocabulary and identifiers

**Decision.** Concept name everywhere (UI, docs, code): 'note type'. Ids: 'text' (plain text), 'markdown', 'timeline'. Core ids are short, unqualified and reserved; a future package-contributed type will be qualified '<package-id>/<local-id>'. Id grammar (validated wherever an id is read from untrusted data): ^[a-z][a-z0-9-]{0,31}(\.[a-z][a-z0-9-]{0,31})*(/[a-z][a-z0-9-]{0,31})?$, at most 128 characters; the local reader accepts qualified ids already so providers can store them, but this host knows only the three core ids (anything else opens read-only, D3/D7). Field names: provider property 'noteTypes' (list of ids); per note 'noteType' on note rows, on sections[].notes entries, in the load answer, in create options { noteType }, in save options { noteType } (informational in this release), in the editor snapshot { title, body, base, noteType } and as NoteEditor.noteType. Row 'kind' keeps meaning note/new/action/tree. Local front-matter key 'note-note-type:' (D13). Local listing record: field 8 is the type (empty = Markdown). User-facing labels: 'Plain text', 'Note' (markdown), 'Timeline'.

**Rationale.** 'kind' is already the row kind, and 'type' next to it reads as a synonym (kind vs type) and is ambiguous inside a load answer; 'noteType' names exactly what the user calls it ('other note types in the future'). Unqualified core ids keep files readable ('note-note-type: timeline'); qualifying package ids later prevents a future built-in of the same name from capturing a package type's notes (built-ins win at discovery).

**Rejected.** 'type' (kind/type confusion in rows; collides with the 'type:' property Hugo and many Obsidian vaults use if reused on disk); 'contentType' (MIME connotation, not the user's word); qualified core ids such as 'org.note-note/timeline' (noise on disk and in every row); numeric enums (opaque in files and logs).

**Evidence.** services/notes/sidebar.js:24-31 (row kind whitelist); docs/providers.md:89-91 (row kinds); plugins/org.note-note.local/notefile.py:10-15 (front matter owns only title); services/extensions/manifest.py:24-27 (id grammars), 268-283 (built-ins keep their ids); plugins/org.note-note.local/list.py:5-11, 253 (N record).

### D2 - Provider declaration and capability defaults

**Decision.** Declaration: 'readonly property var noteTypes: [...]' on the provider instance - the types it can store AND create, by id; the first is the type of a new note (the default). Legacy derivation when noteTypes is absent, not an array, or holds no id this host knows: [markdown === true ? 'markdown' : 'text'] - an absent markdown flag means plain text, as the host already behaves (Workspace.qml:2837-2840) and as the docs will now say. noteTypes wins over markdown when both are present (the canReorder -> reorder precedent: the explicit declaration wins). Built-ins migrate and drop their markdown line: local ['markdown','timeline'] (['markdown'] in phase 1), sticky ['text'], notion ['markdown'], onenote ['markdown'], examples/hello ['markdown','timeline']. Normalisation lives in ONE new module, services/notes/capabilities.js: of(provider) -> { hasTitle: provider.hasTitle !== false (default true; true also when no provider), canImages: provider.canImages === true, tools: undefined -> null (all), array -> its strings, anything else -> [] (fail closed), noteTypes, defaultNoteType: noteTypes[0] }; noteTypes(provider) filters to known ids, de-duplicates, caps at 16, else the legacy derivation, and with no provider at all answers ['markdown'] (today's binding gives plain = false then, so the resting pane stays rich); canCreate(provider, noteType); noteTypeOf(provider, reported) -> { noteType, refusal } (D3). Every capability read goes through it: the NoteEditor bindings at Workspace.qml:2831-2848 (the 'plain:' binding is deleted - plain becomes derived from the note's type, D6), newNote's focus choice at Workspace.qml:1932-1936, sidebar.js row() hasTitle (sidebar.js:26), WorkspaceActions availability. This fixes the absent-hasTitle defect: today the binding at Workspace.qml:2841-2844 yields undefined, Qt refuses it ('Unable to assign [undefined] to bool') and the field keeps the previous note's value, while sidebar.js treats absent as true and newNote as false.

**Rationale.** Additive and silent-free (docs/technical-requirements.md:99-101): every existing external provider keeps working unchanged; one place for every default removes three inconsistent hasTitle readings and stops the next capability from adding a fourth.

**Rejected.** Declaring types in plugin.json (capabilities are live QML properties; the manifest validates only id/path/order for providers - manifest.py:79-87 - and check.py would need a schema change); per-type booleans such as canTimeline (one flag per future type); keeping 'markdown' and adding 'timeline: bool' (the third flag CLAUDE.md calls spaghetti); bumping apiVersion (rejects every existing package - manifest.py:134-137).

**Evidence.** Workspace.qml:2831-2848 (bindings), 1932-1936 (focus after create); services/notes/sidebar.js:26; docs/providers.md:47-54 (properties), 170-175 (reorder compatibility paragraph); services/notes/ordering.js:5-18 (explicit-wins precedent); plugins/org.note-note.local/Provider.qml:20, plugins/org.note-note.sticky/Provider.qml:14, plugins/org.note-note.notion/Provider.qml:17, plugins/org.note-note.onenote/Provider.qml:19, examples/hello/Provider.qml:14; tests/standalone_selftest.py:190 and tests/standalone_launch.qml:38-40 (hello must keep loading through the legacy directory).

### D3 - Per-note type reporting

**Decision.** Providers report noteType on note rows, on sections[].notes entries (search results and folded trees use notes - sidebar.js:62-70) and in the load answer; absent means the provider's default. Authority: the LOAD ANSWER decides the editor body; rows only feed the list (glyph, progress, D11). sidebar.js row() copies noteType for note rows (a known id, else '') and progress (normalised { done, total, next } or null). Mismatch (row says timeline, load says markdown because the file changed in between): the load wins for the editor, the row follows on the next listing, nothing is reported. Unknown type (a valid id this host does not know, or garbage): Capabilities.noteTypeOf returns { noteType: 'text', refusal: 'This is a “<id>” note, which this version of Note Note cannot edit, so it opened read-only' } (id cut to 64 characters, shown as plain text); NoteSession opens it in the text body, read-only, and says the reason once. A body that cannot keep its note answers a refusal through shown(ok, refusal) (D6) and is treated the same way. Drafts, recovered drafts and deletion-recovery documents restore with the noteType captured in their snapshot - never re-resolved. The save answer is unchanged for the host (finishSave reads error/conflict/merged/version/warning); providers use their own save answers to refresh their rows (local returns progress, D13).

**Rationale.** Rows cannot drive the editor: a created note may not be listed yet, a draft restores without a load (NoteSession.qml:233-245), and folded trees hide rows. One authority per consumer avoids races; read-only rather than lossy for anything unknown (docs/decisions.md:660-697).

**Rejected.** Rows authoritative (late or missing rows, folded trees); a session path->type map (another map replacePath must migrate - the F1 class of bug); opening unknown types as editable Markdown (a future type's body may not survive the Markdown writer); repairing a mismatch by writing (never write on open).

**Evidence.** services/notes/NoteSession.qml:210-305 (the only load consumer), 233-245 (draft branch), 278/294/420 (snapshots); services/notes/sidebar.js:24-31, 59-70; Workspace.qml:1349-1362 (rows JSON-compared); docs/decisions.md:444-448 (a row carries only what the list shows); docs/providers.md:58, 89-91, 260.

### D4 - Creation

**Decision.** Contract: create(target, cb, options) with options.noteType; the host ALWAYS passes options = { noteType: <requested or the provider's default> }, so new-contract providers never see it missing, and two-argument create(target, cb) providers ignore it (the save-options precedent, docs/providers.md:283-291). The opaque target is untouched. Host: newNote(providerId, target, noteType) - optional third argument; newNoteDestination(providerId, target, noteType) keeps only providers whose Capabilities.noteTypes hold the type (an explicit provider that cannot hold it yields no destination; the no-provider fallback searches canCreate && holds type && createTargetFor('')); with no providerId, newNote first activates the footer row whose shortcut is the type's ('newTimeline' for timeline, 'newNote' for the default), exactly as Ctrl+N does today (Workspace.qml:1892-1894); with no destination for a typed request it reports '<provider>: this notebook cannot hold timelines' (or the WorkspaceActions reason) instead of starting a new notebook. After create: focus the title when Capabilities.of(p).hasTitle, else the body; in an empty timeline Enter in the title opens the add-event form. Surfaces that offer 'New Timeline': (1) a provider-supplied footer action { path: 'newTimeline', title: 'New Timeline', icon: U+F0F97 md-timeline_plus_outline, shortcut: 'newTimeline' } - local adds it after New Note in every notebook footer (and in the folded-tree footer), hello beside its New Note; the provider's action('newTimeline') calls host.newNote(id, target, 'timeline'); the documented rule 'the host adds no creation buttons' stays true; (2) workspace action newTimeline, Ctrl+Shift+T, and the palette command 'New Timeline' (D15); (3) no typed '+ New note...' rows (kind 'new' keeps creating the default type and its label) and no right-click items. Footer 'shortcut' vocabulary becomes newNote, newNotebook, newTimeline.

**Rationale.** Stays inside the documented creation model (providers supply every footer action and decide targets; a shortcut connects a key to a footer row) while giving keyboard, palette and mouse paths. A provider that cannot hold timelines never shows the option.

**Rejected.** Encoding the type in target (providers parse their own targets - local Provider.qml:556, OneNote 1135-1141, Notion 248 - a hack); a host-generated type chooser on New Note (amends providers.md:185, and the host cannot reproduce the target a provider computes inside action()); Ctrl+N opening a type picker (friction on the most common action); a section row-menu item (pointer-only, and runRowAction locks the session so host.newNote is refused - Workspace.qml:1888-1890, 2115-2116); one footer row per type for every future type (acceptable for one extra type; a chooser is the later answer when a third type arrives).

**Evidence.** Workspace.qml:1873-1938 (newNoteDestination/newNote, single create call at 1912), 1690-1703 (activateFooterShortcut), 2726-2734 (new rows); plugins/org.note-note.local/Provider.qml:106-112 (notebookActions), 275-279 (action newNote); docs/providers.md:181-204 (footer contract and shortcut vocabulary), 283-291 (save options), 350 (create); ui/NoteList.qml:472-485 (new rows hard-code 'New note...'); services/commands/WorkspaceActions.qml:18-48.

### D5 - Changing a note's type after creation

**Decision.** No conversion in the first release. The design keeps it a small later step: (1) the type is provider metadata separate from the body (local: one front-matter line), so converting is a metadata flip, never a body rewrite; (2) a timeline body is valid Markdown, so timeline -> Markdown is always lossless, and Markdown -> timeline is guarded by the codec's read(): a refusal names what blocks it ('This note holds a heading...'); (3) save options already carry noteType, so the later contract text is 'a provider that declares several types writes options.noteType with the body' (local rewrites its type line on save) and the host adds palette commands 'Convert to Timeline' / 'Convert to Note' that flush, save with the new type and reload in place (NoteSession.load(true)); (4) no path-keyed type state exists to migrate.

**Rationale.** Not requested; a mis-created timeline can be deleted and recreated; conversion needs a provider operation, session flow, UI and tests that the first release does not need, and nothing here blocks it.

**Rejected.** Shipping conversion now (scope); body markers that would make conversion a body rewrite; converting implicitly when a Markdown note happens to be a pure task list (surprising).

**Evidence.** plugins/org.note-note.local/operations.py:126-141 (save keeps the current file's extra front-matter lines), notefile.py:48-76; services/notes/NoteSession.qml:204-208, 219-221 (reload in place keeps the view); prototype probe: canonical timeline body has qthtml.unkept() == [] and the qthtml round trip reads back the same events (scratchpad/product/probe2.py).

### D6 - Note pane architecture

**Decision.** Keep NoteEditor (id editor, objectName noteEditor) as the note PANE - toolbar row, modified date, title, notices, provider views, conflict review, skeleton, read-only - and give it a body seam instead of a third flag. New 'property string noteType' (written only by setNote/restoreDocument and tests); 'plain' and 'rich' become read-only derivations (noteType === 'text' / 'markdown'); 'readonly property var body' is the active body. Two bodies implement one interface: textBody - a QtObject adapter inside NoteEditor over its existing TextEdit machinery (serves text and markdown; the ~20 'plain' branches stay, they are about plain vs rich inside the text body) - and TimelineBody (ui/timeline/TimelineBody.qml), an always-instantiated sibling of 'flick' in the sheet. Body interface: readonly hasFocus, wordCount, countText, progress (null for text); show(markdown, token, done(ok, refusal)); restore(form, token); capture() -> string (the body's own canonical form); request(callback(body, ok)) - framed; clear(); viewState(); restoreViewState(state) (clamps); focusEditor(); focusBody(); undo(); redo(); TimelineBody also emits edited(), statusRequested(text), leaveTop(). Pane protocol: setNote(title, body, shown, noteType) - title set under settingText, then useType(noteType) switches the body BEFORE the document goes in (clearing the other body so no hidden document keeps a note, a recording or an undo stack, and moving keyboard focus to the new body if the old one had it), then noteToken++ and body.show; if the body answers ok with a refusal, the pane switches to markdown and shows the same text in textBody, then calls shown(true, refusal); restoreDocument(snapshot) reads snapshot.noteType; snapshotDocument() -> { title, body: body.capture(), base: documentBase, noteType }; requestBody(callback) replaces requestMarkdown (same framed (body, ok)); viewState, restoreViewState, focusEditor, focusBody, undo, redo, wordCount, countText, progress delegate to the body. Host capabilities stay on the pane, unchanged, because the rich machinery stays instantiated: canColorText (Workspace.qml:122-123, 2520), tools.actions (2554), toolbarHeight/toolbarRowHeight (2714-2715; ToolBar keeps its row height with no tools), hoveredLink (now also requires body === textBody), wordCount (delegated). Rich-only entry points refuse unless the text body is active: paste()/pastePlain(); applyReadOnly forces area.readOnly when the text body is inactive (re-run on noteType change); EditorApi.writable becomes host.hasNote && !host.readOnly && host.rich && !host.showingNotice, so tools and the toolbar exist for Markdown notes only; 'flick' is visible only for textBody, TimelineBody only for timelines. bodyFocused stays area.activeFocus (the 'editor' shortcut context = the TextEdit). Pane functions for the timeline: addEvent() and toggleEvent(index) (false otherwise). The title field's Return/Enter/Down call the pane's focusBody(), i.e. the body's.

**Rationale.** Least disturbance: the ~50 Workspace editor.* references, notices (Microsoft device-code sign-in), the conflict review and IPC keep working; the type travels with the document so it is known before setNote/restoreDocument (the 'type known late' race disappears); one body selection replaces per-function type branches; theming and the key-binding registry never change with the open note; a later extraction of the rich body into ui/TextBody.qml fits behind the same interface.

**Rejected.** Threading a 'timeline' flag through NoteEditor's branches (spaghetti); swapping NoteEditor per type at Workspace level (orphans notices, conflict review, tools.actions, canColorText, header alignment, IPC); a Loader-created rich editor per type (themes and shortcuts would recompile per note - canColorText and tools.actions live on it); extracting the 2000-line rich body now (large diff, test churn through editor.*, no user value in this release).

**Evidence.** ui/NoteEditor.qml:28-34 (plain/hasTitle/readOnly/enabledTools), 72 (bodyFocused), 84 (hoveredLink), 122-134 (requestMarkdown), 155 (toolsVisible), 166, 292-332 (setNote/snapshot/restore), 371-383 (applyReadOnly/focus), 388-395, 717-736 (undo/redo replay emits edited even for a hidden area), 1784-1833 (view state, wordCount, tools, toolbar heights), 1843-2001 (sheet, title, loaders, flick), 2075; ui/editing/EditorApi.qml:13; ui/editing/ToolBar.qml:46; Workspace.qml:122-123, 1716-1740 (IPC), 2245-2250, 2520, 2554, 2714-2715, 2837-2840, 2916-2921; tests/transitions.qml:375-400 (the session needs only the document protocol).

### D7 - Note-type registry and extensibility

**Decision.** Core types now, no sixth catalog kind in this release. services/notes/notetypes.js (.pragma library) is the host's static table: id -> { label, body ('text' | 'timeline'), glyph (list glyph; '' for text and markdown, U+F1533 md-timeline_check_outline for timeline), footerShortcut ('' | 'newTimeline') }, with known(id) using Object.prototype.hasOwnProperty (provider ids are untrusted: '__proto__', 'constructor' and 'toString' are not types), bodyOf, glyphOf, labelOf, footerShortcutOf, progressText(progress) and normalizedProgress(value). Provider-facing defaults live in capabilities.js (D2). The D6 body interface is the member list a future contract QML will publish. When a second non-core type is designed: add 'noteTypes' to manifest.py KINDS/BUILDERS/executable, a PluginCatalog property, a NoteNote.Extensions 'NoteType' contract (apiVersion 1: id, label, icon, body Component, codec), a NoteTypeRegistry modelled on ToolRegistry (null until the catalog is ready, PreferSynchronous, built-ins win, diagnostics), qualified ids, core types unremovable. Unknown or (later) disabled types: the note opens as plain text, read-only, with the reason (D3); the provider keeps its marker untouched (local: the note is read-only, and its front-matter line is never rewritten).

**Rationale.** A plugin kind is a large surface - trust and enable switches, a codec channel for provider previews (Python cannot reach a package's QML), in-process crash risk in the shared shell engine - for one built-in user. The rules a disabled package type would need (read-only, marker kept) are already the unknown-type rules, so nothing is lost by waiting.

**Rejected.** plugins/org.note-note.timeline/ as a package now (a user could disable it and strand every timeline note; previews could not call its codec; extensibility risks 1-3); unqualified package ids (a later built-in could capture them); a QML registry with one entry (ceremony without a second contributor).

**Evidence.** services/extensions/manifest.py:30, 98-101, 151, 203-206, 268-283; ui/editing/ToolRegistry.qml:8-224 (registry template); commit 2c5920f (the tools kind); docs/plugins.md:129-134 and docs/editing-tools.md:233-236 (absent contributions stay dormant); cpp/extensionruntime.h:7-8 (shared engine); docs/engine-notes.md (prototype-free maps; docs/testing.md:54-60).

### D8 - Timeline data model and canonical body format

**Decision.** MODEL. An event is { title, description, checked }: title = one line of plain text (line breaks folded to spaces, trimmed, at most 500 characters, may be empty); description = plain text where '\n' is a line break and a blank line separates paragraphs (each line trimmed, blank runs collapsed, none leading or trailing, at most 10,000 characters); checked = boolean. A timeline is an ordered list of at most 1,000 events. No inline formatting, links, images or dates in this release.

CANONICAL MARKDOWN (what the codec writes; LF endings; the body ends with one LF, an empty timeline is the empty string):

```text
  timeline  = '' | event *( LF LF event ) LF
  event     = marker [ SP '**' title '**' ] *( LF LF paragraph )
  marker    = '- [ ]' | '- [x]'
  paragraph = line *( SP SP LF line )      ; two trailing spaces = the dialect's hard break
  line      = SP SP escaped-text           ; indented to the item's content column
```

Example (exact bytes; the first description line ends with two spaces):

```markdown
- [x] **Book the van**

  Saturday 8am, the big one.  
  Ask for the long wheelbase.

- [ ] **Pack the kitchen**

- [ ] **Hand over the keys**

  Meet the agent at noon.

  Bring both sets.
```

An empty title writes the bare marker '- [ ]'. ESCAPING: titles through mdtext.escape_inline(title, before='*', after='*'); description lines through escape_line_start(escape_inline(line)); plus a backslash before '&' when it starts an entity reference (mistune would decode '&amp;'); the writer re-reads its own output and must get exactly the normalised events, else retries once with strict escaping, else raises - the save is refused (framed failure), never written wrong.

READING (tolerant, on services/markdown/parse.py): the top level may hold only unordered task lists and blank lines; bullets -, * or +; [x] or [X]; a leading U+FEFF is dropped before parsing (parse.py already drops CR, so CRLF reads as LF). An item's first block is the title: plain text, or a single bold run spanning it; a soft or hard break inside it starts the description (the tight shape Notion writes and people type). Further paragraphs of the item, and top-level paragraphs that follow an event (the shape OneNote writes today), are its description; leading spaces and NBSPs on description lines are indentation and dropped. REFUSALS (exact names, used in 'This timeline holds %s, which a timeline cannot show, so it opened read-only'): a heading, a paragraph before the first event, a numbered list, a list item without a checkbox, a nested list, a code block, a quote, a table, a rule, HTML, a picture, a recording, formatting in an event title, formatting in an event description, more than 1000 events, an event title longer than 500 characters, a description longer than 10000 characters. Bounds are checked while reading; nothing is truncated.

WHERE: services/markdown/timeline/ - __init__.py (read(markdown) -> { events, refusal }; write(events) -> markdown or ValueError; summary(markdown) -> { done, total, next } or None; MAX_EVENTS, MAX_TITLE, MAX_DESCRIPTION), __main__.py (CLI 'read' | 'write', payload on stdin capped at 8 MiB like qthtml, one framed JSON answer: { events, refusal } / { markdown } / { error }; write input parsed with lib/jsondata.py), selftest.py. The host reaches it through services/markdown/Markdown.qml toTimeline(markdown, cb(answer, ok)) and fromTimeline(events, cb(markdown, ok)) over ProcessRunner, exactly like toHtml/toMarkdown; provider Python imports it for summaries. ui/timeline/TimelineModel.js mirrors the three limits (a regression test asserts they agree).

GUARANTEES: write(read(x).events) re-reads to the same events; read(write(e)) == normalised e; write is a fixpoint; the Markdown editor's own round trip (qthtml to-html -> to-markdown) of a canonical body reads back the same events, so an older Note Note or a host without the type saves it as a checklist without losing an event. FOREIGN CONTENT: tolerated shapes are read as events and NOT rewritten on open; they become canonical only when the user changes something (the save writes the whole body); anything outside the grammar opens read-only, shown as rendered Markdown, with the refusal.

**Rationale.** A GitHub task list is what every Markdown tool renders and lets you tick (business goal 3: readable and editable by any tool), it is found by the existing body search, and OneNote and Notion can represent it later (to-do paragraphs / to_do blocks). A bold title over indented paragraphs reads as a timeline everywhere and keeps each description attached to its event. One parser on the vendored mistune means no hand-written JS Markdown parser and no second grammar for previews. Prototyped against HEAD's parse.py/mdtext.py/qthtml (scratchpad/product/timeline_proto.py): 3,000 fuzzed round trips with Markdown metacharacters and entities, 0 failures; the strict-escape fallback was never needed in 2,000 cases; qthtml.unkept() of the canonical body is empty and its qthtml round trip reads back identical events; Notion's tight shape and OneNote's shapes A and C read as events.

**Rejected.** YAML or JSON in the front matter (no YAML parser may be added, invisible to search and other tools); a fenced JSON body (unreadable elsewhere); an HTML-comment marker or HTML body (local read turns any raw HTML read-only via unkept - operations.py:19-31); tight items with a hard-break description as the canonical form (an editor that strips trailing spaces joins title and description; OneNote flattens it); unindented sibling paragraphs as the canonical form (ambiguous with free text; accepted on read only); plain (non-bold) titles (title and description look alike elsewhere; bold is accepted, and added losslessly); a JS parser (duplicate grammar, Markdown edge cases in an engine without lookbehind).

**Evidence.** services/markdown/parse.py:1-11, 66-69 (task_lists), 100-105; services/markdown/mdtext.py:1-14, 46-106 (escape_inline, escape_line_start; leading 4+ spaces become NBSP); services/markdown/Markdown.qml:49-115 (framed service); services/markdown/qthtml/__main__.py:1-80 (framing, 8 MiB cap); services/markdown/qthtml/reader.py:61-70 (as_note: one trailing LF); plugins/org.note-note.local/operations.py:19-31; docs/decisions.md:523-555 (framed answers), 660-697 (read-only rather than lossy); docs/security.md:16-39 (bound collections); scratchpad/experiments/roundtrip.py (OneNote shapes); notion-sticky map probes A/B.

### D9 - Check semantics and undo

**Decision.** toggle(k): if event k is unchecked, events 0..k become checked (everything above it and itself) and those below are untouched; if it is checked, events k..n-1 become unchecked (itself and everything below) and those above are untouched. On a timeline kept in order the checked events are therefore always a prefix - 'you are here'. The 'next' event is the first unchecked one. States that break the order (ticked in another editor, merged per entry) are shown exactly as stored: no repair on open, no warning - the accent run of the spine simply breaks at the gap; the rule acts only on the user's next action. When an action changes more than one event the status line says so: 'Checked 3 events, up to “Pack the kitchen”' / 'Unchecked 4 events, from “Pack the kitchen” down'. Undo: TimelineBody keeps a bounded stack (50 steps) of capture() strings plus the cursor - one step per toggle, add, discard, edit session, delete and move; Ctrl+Z undoes, Ctrl+Shift+Z and Ctrl+Y redo (Stroke.redoes), on the event list; inside the form's fields Ctrl+Z is the field's own text undo. The stacks clear on show/restore. A mis-click is one click to repair (checking the last done event re-checks everything above) or one Ctrl+Z. Pure functions in ui/timeline/TimelineModel.js: toggled(states, index), changed(before, after), nextIndex(states), progress(events), moved(events, from, to).

**Rationale.** Symmetric and predictable: a timeline is a path you follow, so a done step after an undone one means nothing; the same click on any circle sets 'where you are'. Tolerating foreign states keeps the rule 'never write the user's file just because it was opened'.

**Rejected.** Unchecking only k (creates holes by default); allowing uncheck only on the last checked event (a click that silently does nothing); repairing out-of-order states on open (a write without an action); a confirmation before multi-uncheck (a modal dialog, business goal 2).

**Evidence.** The user's request ('when the user checks one, we will check everything above'); docs/business-requirements.md:29-31; lib/notemerge/README.md:8-14 (checkbox changes merge per entry, so holes will arrive from merge-aware providers); services/shortcuts/stroke.js:17-24, 114 (reserved undo keys, redoes); ui/NoteEditor.qml:717-736 (the rich editor's undo).

### D10 - Timeline view UX

**Decision.** LAYOUT (inside the note sheet, under the title, same margins): a rail on the left - circle diameter side = round(bodyFontSize x 1.1); rail width side + 2 x Style.spacing.lg; spine max(2, round(side x 0.12)) wide, centred, drawn per row as a segment above and below each circle so rows abut into one line; each circle centred on its title's first line. Text column: title (note font, bodyFontSize, PlainText, wraps); description under it (note font, round(bodyFontSize x 0.92), PlainText, wraps, line height 1.2); row padding Style.spacing.md. Below the last event the 'Add new event' row: a hollow circle (border alpha 0.3) holding U+F0415 md-plus in accent ink (Qt.tint(fg, alpha(accent, 0.6))), label 'Add new event' in accent ink, dimmed to Style.secondaryOpacity(0.65) until hovered or focused - the '+ New note...' look. Empty timeline: a faint hollow circle and 'No events yet' in secondary ink above the add row. A Flickable with the shared ListWheel feel; the cursor row is kept in view; a note opens scrolled to its next event. The events live in a ListModel (roles title, description, checked) edited in place - setProperty, move, remove, append - shown by a Column + Repeater, so a check or a keystroke never recreates the row under the caret or resets the scroll (the engine note's reason to prefer arrays - roles fixed at the first insert - does not apply to three uniform roles; recorded in decisions.md).

STATES: unchecked - hollow, border alpha(fg, 0.4), 0.75 on hover; checked - accent fill with the tick cut out in the background colour (the editor's checkbox face made round, extracted to ui/CheckFace.qml { round: true }), title Style.secondaryText(fg, 0.55), description 0.45; next - hollow with an accent ring (border max(1.5, side/7)) and a bold title; spine segment between two checked circles in accent, all others alpha(fg, 0.18); hover - row fill Style.hoverFillFor(fg, accent), pointing hand over the circle; keyboard cursor (while the timeline has focus) - row fill Style.selectedFillFor(fg, accent) and a 2 px accent ring 2 px outside the circle (the TextColor swatch precedent); composing - the event being written has a hollow circle at alpha 0.3 and its fields; read-only - no hover, no pointer, no add row, no form; editing - the row's title and description become fields in place. 120 ms colour animations; a multi-event check fills top-down with a 25 ms stagger (at most 250 ms).

THE FORM ('Add new event'): opened by Enter or Space on the add row, a click on it, typing a character on it (the character goes into the title), Ctrl+Enter anywhere in the note, or the palette's Add Event. It appends an event in compose mode at the end and focuses its title. Fields: title - ChromeTextField, single line, maximumLength 500, placeholder 'Event title', note font; description - new ui/ChromeTextArea.qml (QQC.TextArea on ChromeControlStyle), grows with its text, placeholder 'Description (optional)', refuses input past 10,000 characters with a message instead of truncating. Under them a hint in Style.font.caption secondary ink - compose: 'Enter to add · Shift+Enter for a new line · Esc to discard'; edit: 'Enter to save · Shift+Enter for a new line · Esc to cancel' - replaced by a message in Color.urgent when needed ('Give the event a title', 'Descriptions hold up to 10,000 characters'), and an Add / Done button (focusable: false). ToolForm conventions: no Cancel button, no labels above fields. SEMANTICS: the form edits the note live - the event being composed is part of the document as soon as it holds any text (an empty one is left out of every snapshot, save, progress and count), so switching notes, closing the window or a crash never loses what was typed. Enter in either field: both fields empty -> close the form; title empty, description not -> the message; otherwise the event is committed (text normalised) and a fresh form opens below for the next one (rapid entry). Esc: compose -> the event is discarded (one undo step brings it back) and the cursor goes to the add row; edit -> the event gets back its text from before the edit. Edit mode: Enter, a double-click or the context menu on an event opens the same fields filled in; Enter or leaving the fields finishes; emptying both fields and pressing Enter deletes the event (undoable). One event is in edit or compose mode at a time. Compose mode does not close on blur (clicking around keeps the form); edit mode finishes on blur.

DELETE: the Delete key on the cursor event, or the context menu: removed at once, status 'Deleted “...” · Ctrl+Z brings it back' - no dialog. REORDER: Alt+Up / Alt+Down move the cursor event (the cursor follows, the Column animates y in 120 ms); context menu Move up / Move down; drag-and-drop later. CONTEXT MENU (right-click an event; ui/RowMenu.qml reused with a row-shaped object): Edit (U+F03EB), Move up (U+F005D), Move down (U+F0045), Delete (U+F01B4).

KEYBOARD (event list focused): Up/Down move the cursor (Down past the last event reaches the add row; Up from the first event goes to the note title); Home/End first event / add row; PageUp/PageDown by a page; Space toggles (on the add row: opens the form); Enter edits (on the add row: opens the form); Ctrl+Enter / Ctrl+NumEnter add an event (workspace action addEvent); Alt+Up/Alt+Down move; Delete deletes; Ctrl+Z, Ctrl+Shift+Z, Ctrl+Y undo/redo; Escape is not claimed (the app's 'back'). The list's Keys.onPressed calls the pane's shortcut(event) first (app bindings win, as in the TextEdit), then handles its own keys. FORM FIELDS use specific Keys handlers, which Qt runs before onPressed: Return/Enter commit (Shift+Return falls through to the TextArea's newline), Escape discards or cancels, Tab/Backtab and Down/Up move between title and description; every other key goes to shortcut(event) (Ctrl+N, Ctrl+Up/Down...) and then to the field. Note title: Return/Enter/Down -> the timeline, cursor on the next event (an empty writable timeline opens the form). Opening a note (row click, search, Ctrl+Up/Down) focuses the list with the cursor on the next event (or the add row).

SHORTCUT CONTEXT: a focused timeline is the 'workspace' context - bodyFocused stays the TextEdit's, so formatting-tool and rich-paste bindings never match there; timeline keys are local handling (bare keys cannot be registry bindings - resolve.js:137-148); only Add Event and New Timeline are registry actions (D15).

ACCESSIBILITY (a new precedent): TimelineBody Accessible.role List, name 'Timeline'; each event ListItem; each circle CheckBox with name = title (or 'Untitled event'), description = description, checkable, checked, and onToggleAction/onPressAction -> toggle; add row Button 'Add new event'; fields 'Event title' / 'Event description'.

OBJECT NAMES: timelineBody, timelineEvent-<i>, timelineCheck-<i>, timelineAddEvent, timelineEmpty, timelineComposer, timelineEventTitle, timelineEventDescription, timelineHint, timelineMenu.

THEME: no new tokens - everything derives from the pane's editor.foreground / editor.background, the accent, input.* and border.focus (ChromeControlStyle), Color.urgent, Util.alpha and Style's fill helpers; only Style keys both hosts define (spacing xxs..xxxl, md, lg, panelPadding; font caption, bodySmall, body, iconSmall, icon; Style.space()); glyphs drawn in Style.fontFamily; checks are drawn shapes, not glyphs, so they look the same in both hosts.

**Rationale.** Business goals: never needs the mouse, no modal dialog between the user and the text, never lose a note. A stepper look (done = filled with a tick, next = ring, future = hollow) reads as progress and keeps the 'radiobox' circles the user asked for. Every visual and keyboard convention is an existing house one (checkbox face, accent ink add rows, ToolForm hints, fill helpers, shortcut-first key routing), so the timeline feels native in both hosts.

**Rejected.** A modal or centred dialog (business goal 2); a popover form (the house rule is that a click outside cancels it, which loses a typed description); a form whose text lives outside the document (lost on note switch unless more session hooks); filled-dot radio visuals (read as 'selected', not 'done'); strikethrough for done events (reads as 'cancelled'); a single-line description; Enter = newline in the description (breaks the app's Enter-submits convention); a ListView (destroys off-screen delegates mid-edit); a confirm dialog on delete (undo instead).

**Evidence.** docs/business-requirements.md:29-31, 82; ui/NoteEditor.qml:1890-1914 (title keys), 2219-2291 (checkbox face recipe); ui/NoteList.qml:73-79 (accentInk), 440-492 (add-row look); ui/tools/TextColor.qml:49-75 (focus ring); ui/editing/ToolForm.qml:27-88 and docs/editing-tools.md:345-364 (form conventions); ui/SidebarAction.qml:89-132; ui/ChromeTextField.qml; ui/ChromeControlStyle.qml; ui/RowMenu.qml:10-40; design/Style.qml:20-47, 60-77; Workspace.qml:2135-2176 (handleShortcut, shortcutContext); services/shortcuts/resolve.js:10-12, 137-148; services/shortcuts/defaults.js:20 (Escape = back); docs/engine-notes.md:42-58 (replacing a model resets the scroll; focus inside a Loader via Qt.callLater); ui/NoteEditor.qml:1223 (a ListModel precedent); glyph code points verified in assets/fonts/nerd-symbols/SymbolsNerdFont-Regular.ttf.

### D11 - List and search integration

**Decision.** NoteSummary (shared by the list and search results) gains 'glyph' - drawn before the title in Style.fontFamily at Style.font.iconSmall, Style.secondaryText(fg, 0.55); only timelines have one (U+F1533), so Markdown and plain-text rows look exactly as today - and 'progress' - when set, the second line shows NoteTypes.progressText(progress) instead of the preview: 'No events yet' / 'Done' (one event) / 'All 7 done' / '3 of 7 · Next: Pack the kitchen' ('Untitled event' stands in for an empty title). NoteList and SearchResults pass both with unchanged geometry. sidebar.js row() carries noteType and progress. Providers compute progress { done, total, next } with the codec's summary() (local: list.py for each timeline note, and the save answer) and keep 'preview' as their generic first-line text, so the in-memory search still matches the first event and the untitled-title fallback reads '☑ Book the van' (Workspace.qml:1316-1317). LIVE: Workspace.displayProgress(row) returns editor.progress for the open timeline (always the fresher one) and row.progress otherwise; NoteList/SearchResults get it as progressFor, like titleFor. VIEW BAR: countText from the pane - '3 of 7 done' / 'No events' for a timeline, 'N words' for text (ViewBar.wordCount becomes countText; the label keeps objectName 'wordCount'). BODY SEARCH: local search.py already matches the raw body, so event titles and descriptions are found; no change.

**Rationale.** The host owns presentation (docs/README.md:44-45): providers send numbers, the host words them; rows carry only what the list draws (docs/decisions.md:444-448); the open note's progress updates as you click, the precedent being unsaved titles (commit 7162589).

**Rejected.** Putting '3 of 7...' into preview (provider-worded, searchable 'of'/'Next', and the untitled fallback would read '3 of 7...'); host-computed progress for unopened notes (the host never reads provider data); the first event as the only summary (says nothing about where you are); a mini progress bar per row (visual noise; possible later without a contract change).

**Evidence.** ui/NoteSummary.qml:6-58; ui/NoteList.qml:447-461; ui/SearchResults.qml:104-117; services/notes/sidebar.js:19-31, 59-70; Workspace.qml:1302-1324 (displayTitle), 2721 (titleFor), 2916-2921 (ViewBar); services/notes/NoteSession.qml:48-62 (unsavedTitles); ui/ViewBar.qml:125-134; plugins/org.note-note.local/list.py:147-153, 253; plugins/org.note-note.local/search.py:31-54.

### D12 - Provider support matrix

**Decision.** local: noteTypes ['markdown', 'timeline'] - full support (D13). examples/hello: ['markdown', 'timeline'] - it keeps bodies verbatim in memory, so it can; create honours options.noteType, the load answer and rows carry noteType, its footer gains New Timeline, timeline rows send no progress (optional) and an empty preview (no raw Markdown in the list), and it still loads through the legacy directory. OneNote: ['markdown']; no New Timeline; the unread per-page 'markdown=True' (onenote.py:1380, 1387) is removed. Deferred until a durable page marker is verified live in OneNote's apps (data-id wrapper div) and onenote_md maps indented task-item paragraphs to to-do + margin-left paragraphs; the codec already reads OneNote's current shapes. Notion: ['markdown']; deferred until the user picks a visible marker (page icon vs marker block) and notion_md keeps paragraph children under to_do; the codec already reads Notion's tight shape. Sticky Notes: ['text']; unsupported (plain text, no title; Microsoft's clients would show the syntax raw). External providers without noteTypes: unchanged (legacy flag).

**Rationale.** Declare only what the backend keeps faithfully (docs/providers.md:54; decisions.md:557-561, 660-697); the readers' probes show no invisible durable marker for OneNote or Notion today, and their UIs do not keep the in-order rule.

**Rejected.** Enabling OneNote/Notion now with a title or icon convention (a visible product decision the user has not made, and a user rename silently drops the type); a Sticky Notes timeline syntax (invented behaviour the backend cannot keep).

**Evidence.** plugins/org.note-note.local/Provider.qml:20; plugins/org.note-note.sticky/Provider.qml:14-19; plugins/org.note-note.notion/Provider.qml:17-28; plugins/org.note-note.onenote/Provider.qml:19-37, onenote.py:1380, 1387; examples/hello/Provider.qml:14, 63, 90-105; onenote map section 3-5; notion-sticky map probes and recommendations; scratchpad/experiments/roundtrip.py (cases A, C, K, L).

### D13 - Local provider details

**Decision.** KEY: 'note-note-type: <id>' in the front matter - written once, at creation, for non-Markdown types only (Markdown notes never get the line, so no existing note is ever rewritten); read as the first column-0 'note-note-type:' line; the value must match the id grammar, and 'markdown' or a malformed value reads as Markdown (the line stays verbatim); it remains an unowned 'extra' line, so every save keeps it without a code change. notefile.py owns it: TYPE_KEY, TYPE_ID, note_type(extra) -> '' | id, type_line(id); MAX_NOTE_BYTES (2 MiB) moves here from operations.py so list.py shares it; the docstring becomes 'The app owns title and note-note-type ...'. list.py: head_of returns (title, preview, note_type, progress); for a timeline note it reads the whole file (read_capped MAX_NOTE_BYTES, same deadline) and imports the codec lazily (services/markdown on sys.path, as operations.py does); the N record grows to 10 fields: N key path title preview size mtime_ns noteType done/total next ('' when absent); docstring updated. operations.py: create takes payload.noteType (validated id the provider creates, else an error) and writes serialize('', '', [type_line(id)]) -> '---\ntitle: \nnote-note-type: timeline\n---\n'; read returns noteType ('markdown' by default) and runs qthtml.unkept only for Markdown notes (a typed note is judged by its own body codec in the host); save returns progress for timeline notes (type taken from the current file's extra lines). Provider.qml: noteTypes ['markdown', 'timeline'] replaces markdown: true (:20); notebookActions (:106-112) adds New Timeline after New Note; action('newTimeline') -> host.newNote(root.id, target, 'timeline') with the same target rule as New Note (:275-279); loadList (:429-446) parses fields 8-10 into entry.noteType and entry.progress; folderRows (:213) and searchable (:226-230) carry noteType and progress; load (:509-511) adds noteType: result.noteType (trap 1); the save commit (:548-549) becomes Object.assign({}, note, { title, preview, size, version, progress }) so later fields survive (trap 2); create(target, cb, options) (:555-575) sends options.noteType and seeds the entry (noteType, progress { 0, 0, '' }). Preview: unchanged generic first line. Search: unchanged (search.py matches the body).

**Rationale.** The front matter is the format's own metadata place: read in the 4 KiB listing head with no load, preserved by today's save path, ignored by search, shown as a property by outside tools; the one-format-module rule (notefile.py:10-15) keeps every reader agreeing; the namespaced key cannot collide with the 'type:' or 'note-type:' properties other tools write.

**Rejected.** A bare 'type:' key (Hugo layouts and many Obsidian vaults use it; a user's own 'type: timeline' would flip a note into a timeline); 'note-type:' (common in Zettelkasten templates); a file extension (changes identity, .order names and five .md filters); a sidecar file (blocks folder delete, triggers relists); a body marker (raw HTML turns notes read-only); owning the line like title in split's return value (changes split's signature for every reader for no gain).

**Evidence.** plugins/org.note-note.local/notefile.py:1-86; list.py:5-11, 58-64, 147-153, 253; operations.py:16-31, 104-141; Provider.qml:20, 106-112, 200-230, 275-279, 429-446, 499-513, 538-575; search.py:31-54; local map (traps at 509-511 and 548-549; 4096-byte head; verified that a hand-written type line survives saves); tests/test_regressions.py:86-110.

### D14 - Save, merge, conflict and recovery

**Decision.** SERIALIZATION: requestBody(callback) (renamed from requestMarkdown; the session is its only production caller) -> body.request -> for a timeline Markdown.fromTimeline(events) -> python3 services/markdown/timeline write -> callback(markdown, ok); framed: a dead process, a malformed answer or a write refusal answers ('', false) and NoteSession finishes the save with 'the note could not be read for saving' - the draft is kept, nothing is written (NoteSession.qml:493-506 unchanged in shape). STORED / isStored: the timeline's snapshot body is capture() = JSON of the events in fixed key order [{ title, description, checked }], leaving out an empty event being composed - deterministic, so two clicks that cancel out send no save; isStored also compares noteType (NoteSession.qml:364-367 gains known.noteType === document.noteType). DRAFTS AND RECOVERY: snapshotDocument() carries noteType, so draft.document (:478-488), recovered drafts (:278) and deletion recovery (:420, :455-458) restore into the right body through restoreDocument - no conversion, no re-resolution. SAVE OPTIONS: { view, resolution, noteType } - informational now (local ignores it; its type line is kept by the save path), reserved for conversion (D5). LOAD: NoteSession looks the provider up at the start of load(), blanks the editor with setNote('', '', null, Capabilities.of(provider).defaultNoteType), resolves the answer's type with Capabilities.noteTypeOf, calls setNote(title, body, shown, noteType), and in shown(ok, refusal) calls noteReady(result.editable === false || type refusal || body refusal, the first non-empty of the provider reason, the type refusal, the body refusal). CONFLICTS: local and hello are not merge-aware, so no timeline conflict can arise in this release; when a merge-aware provider declares timelines, MergeConflict shows the raw Markdown passages (title / body) as for any note, and notemerge's per-entry checkbox alignment fits task-list bodies - a timeline-aware review is later work. A refused body is read-only and never saved.

**Rationale.** Keeps every guarantee the session already gives Markdown notes - framed conversion, no-op detection, drafts that outlive the editor, recovery after a failed delete - by making the type part of the document instead of new session state.

**Rejected.** Serialising timelines synchronously in JS (a second grammar to keep in step with the Python one used by providers); a session-level type property or path map (another thing replacePath must migrate); comparing Markdown strings for isStored (would need a conversion before every no-op check).

**Evidence.** services/notes/NoteSession.qml:37-43, 210-305, 362-367, 402-469, 471-542; ui/NoteEditor.qml:112-134, 318-332; docs/decisions.md:489-555; lib/notemerge/README.md:8-27; ui/MergeConflict.qml:62-130; commit 5887a8f (no-op saves).

### D15 - Commands, shortcuts and the palette

**Decision.** services/shortcuts/defaults.js gains { id: 'newTimeline', workspace: true, keys: ['Ctrl+Shift+T'], context: 'notes', group: 'Notes', description: 'A new timeline in the open notebook' } and { id: 'addEvent', workspace: true, keys: ['Ctrl+Enter', 'Ctrl+NumEnter'], context: 'workspace', group: 'Notes', description: 'Add an event to the open timeline' } - the 'workspace' context keeps Ctrl+Enter away from the Markdown TextEdit (the 'editor' context) and from search. services/commands/WorkspaceActions.qml: handlers newTimeline -> host.newNote('', undefined, 'timeline') and addEvent -> host.addEvent(); state gains noteType (host.currentNoteType) and editorWritable (host.editorWritable) so the palette follows them; canCreateNote(noteType) - a footer row with the type's shortcut, else a destination provider whose noteTypes hold it; unavailable: newTimeline -> 'Open a notebook that can hold timelines.', addEvent -> 'Open a timeline you can edit.'. Workspace.qml: readonly currentNoteType (editor.noteType) and editorWritable (also feeding contextState.editorWritable), addEvent() and timelineToggle(index) (IPC helpers, one argument each), displayProgress(row), debugState gains noteType and progress. Palette: plugins/org.note-note.workspace/plugin.json adds 'new-timeline' ('New Timeline', Notes, keywords create, add, timeline, steps, progress, workspaceAction newTimeline) and 'add-event' ('Add Event', Notes, keywords timeline, step, new, workspaceAction addEvent). Footer shortcut vocabulary: newNote, newNotebook, newTimeline. docs/commands.md:61-62 and skills/note-note-plugin/references/commands.md:31, 170 list the two ids and their availability; services/extensions/selftest.py:44-47 pins seven workspace commands. The timeline's own keys (Space, arrows, Enter, Delete, Alt+arrows, Home/End, undo/redo) are local handling, documented in the README's Keys table and the form hint, like the TextEdit's own keys.

**Rationale.** One executor for keys, palette and plugin commands (WorkspaceActions); mnemonic keys that pair with existing ones (Ctrl+Shift+N new notebook / Ctrl+Shift+T new timeline; Enter adds in the form, Ctrl+Enter adds from anywhere); free of every default and tool binding (tools use Ctrl+B/I/U/S/1/./ and Ctrl+Shift+H).

**Rejected.** A parameterised 'newNoteOfType' action (workspace bindings and manifest commands pass no parameters - Workspace.qml:2192-2202, manifest.py:62-72); Ctrl+Alt+N (used as the documented override example, docs/commands.md:145); a bare key such as 'A' for add (no bare-letter shortcuts anywhere in the app); binding addEvent in 'notes' (would steal Ctrl+Enter inside Markdown notes and say 'unavailable' there).

**Evidence.** services/shortcuts/defaults.js:7-33; services/shortcuts/resolve.js:10-12 (scopes), 66-93 (aliases), 137-148 (refusals); services/commands/WorkspaceActions.qml:10-98; plugins/org.note-note.workspace/plugin.json:8-60; Workspace.qml:2182-2203 (runBinding), 2543-2548 (blocked), 2575-2584 (contextState); ui/tools/*.qml shortcut keys (Bold, Italic, Underline, Strikethrough, Checkbox, BulletList, NumberedList, Highlight); services/extensions/selftest.py:44-47; docs/commands.md:49-77.

### D16 - Prerequisite fixes

**Decision.** BEFORE the feature: F1 (high) - replacePath keeps permanent one-way aliases, so renaming a local section A->B->A silently stops the open note's saves and strands its folder's notes (NoteSession.qml:75-76); fix: delete pathAliases[next] and re-point aliases whose value is 'previous', plus a transition case. The feature changes NoteSession more than any other file and a timeline in a renamed section would stop saving like any note. F17 - suite names live in two lists (tests/transition_selftest.py:18, CMakeLists.txt:99): the feature adds a 'timeline' suite that would run under tests/selftest.py and silently not under CTest; fix: SUITES is the one list, transition_selftest.py --list-suites prints it, CMake reads it with execute_process, tests/selftest.py builds argv tuples. ALONGSIDE (recommended before the local-provider phase): F2 + F21 - runRowAction calls rowAction right after flushSave starts an async save, and locks on trust (a provider answering cb() never unlocks); timelines save on every check, so renaming a section right after a check hits F2 more often; fix: lock, flush, wait until session.saveInFlight(currentPath) is false, then rowAction; result = result || {} and an unconditional unlock. F13 folds into the contract-doc commit (the skill's row shape lacks count). IN THE FIRST FEATURE COMMIT: the capability-defaults defect (absent hasTitle keeps the previous note's value with a QML warning at Workspace.qml:2841-2844; newNote treats it as false) - fixed by capabilities.js (D2). NOT NEEDED: F14 (stored pruning - unchanged growth), F15 (TimelineBody binds readOnly from the pane, no new push site), F16 (TimelineBody is a direct child, not a third Loader), F10 (rows rebuild a little more often under an open rename field; fix independently), F20 (typed notes skip the local unkept render; the shown(ok, refusal) channel added here is exactly what F20's proposed fix needs to make Markdown editability host-side later).

**Rationale.** Fix what sits on the feature's own paths and would make its failures silent (F1, F17); fix what the feature makes more likely (F2/F21) next to it; leave the rest to their own commits so the feature's diff stays reviewable.

**Rejected.** Fixing all 21 findings first (delays the feature without reducing its risk); shipping without F17 (the new suite silently skipped by CTest); folding F1 into the feature commit (a high-severity data-loss fix deserves its own reviewable commit and test).

**Evidence.** CODE-REVIEW-2026-10-11.md:52-66 (F1, F2), 130-133 (F13), 135-150 (F14-F16), 152-156 (F17), 169-180 (F20, F21); services/notes/NoteSession.qml:63-114; Workspace.qml:2105-2132, 2841-2844, 1932-1936; tests/transition_selftest.py:18; CMakeLists.txt:99; tests/selftest.py:15-55.

### D17 - Test plan

**Decision.** PYTHON CODEC - services/markdown/timeline/selftest.py (plain check() script like the provider selftests; registered in tests/selftest.py SUITES and as CTest 'timeline-codec'): exact canonical bytes for the three-event example; seeded fuzz round trips (titles and descriptions built from Markdown metacharacters, entities, emoji, backslashes - 3,000 cases); write fixpoint; tolerant reads (tight hard and soft breaks, plain titles, * and + bullets, [X], sibling paragraphs, NBSP-indented siblings, empty title, empty body, CRLF, BOM); every refusal name; the three limits on read and on write; summary() (done/total/next, None when refused, '' next when all done); CLI framing (read/write over stdin, bad JSON -> { error }, input over 8 MiB -> exit 1, unknown verb -> usage); the compatibility property: qthtml.unkept(write(e)) == [] and read(qthtml round trip of write(e)) == read(write(e)). PURE JS - tests/transitions.qml pureCases: TimelineModel toggled/changed/nextIndex/progress/moved (prefix, holes, idempotence), capture determinism and the empty-composer exclusion, parse/validate bounds; notetypes.js known() refuses '__proto__', 'constructor', 'toString', glyphOf/bodyOf/footerShortcutOf/progressText strings; capabilities.js hasTitle default true, canImages strict, tools undefined/array/string, noteTypes legacy mapping (markdown true/false/absent), unknown and duplicate ids, noteTypeOf refusals. SESSION - tests/transitions.qml (fake editor gains noteType, a 4-argument setNote that records the type, requestBody, snapshot noteType; fake provider gains noteTypes): the load answer's type reaches setNote before show; legacy flags; unknown type -> text, read-only, reason; body refusal -> read-only, reason; draft restore keeps the type; isStored compares the type; save options carry noteType; failed delete restores a typed draft; A(markdown, slow) -> B(timeline, fast) race; host suite: newNote(id, target, 'timeline') passes options.noteType, a provider without timeline gets no create call. REAL KEYS - tests/EditorKeys.qml new suite 'timeline' (resetEditor also resets noteType and the timeline): Space checks everything above; Space on a checked event unchecks it and everything below; Up/Down/Home/End/PageUp/PageDown; Down from the last event reaches the add row, Up from the first reaches the title; Enter/Space/typing on the add row opens the form; typing makes the event live; Enter adds and opens the next form; Shift+Enter makes a description line; empty title says so; Esc discards and Ctrl+Z restores; Enter edits and Esc reverts; Alt+Up/Down move; Delete + Ctrl+Z; read-only refuses every edit with the status; title Enter focuses the next event or opens the form; the saved Markdown is the canonical form (quietProvider); toggling twice sends no save (unchanged-note precedent); the form's text is saved on a note switch; the hidden TextEdit stays read-only and tools, paste and undo do nothing while a timeline is shown; a refused timeline opens read-only as Markdown; CheckFace round radius == side / 2; accessibility role/name/checked on circles. LOCAL - plugins/org.note-note.local/selftest.py: create with the type writes exact bytes; read reports noteType and skips unkept for typed notes; list emits 10-field records with type and progress; a type line beyond the 4096-byte head lists as Markdown while read sees it; save keeps the type line (CRLF/BOM in, LF out); unknown valid id reported verbatim, malformed value as markdown; search finds event text; the save answer carries progress. tests/test_regressions.py: notefile.note_type cases and the split/serialize property with a type line; TimelineModel.js limits equal the codec's (constants-agreement precedent at :551-570). tests/transitions.qml localCases: create a timeline through the real provider; loadList record() fixtures with 10 fields. services/extensions/selftest.py: seven workspace commands. tests/standalone_selftest.py: hello (now declaring noteTypes) still loads through the legacy directory. LINT: docs/testing.md's qmllint set gains ui/timeline/*.qml. REGISTRATION: the 'timeline' suite only in transition_selftest.SUITES (after F17 CMake and tests/selftest.py follow); the codec selftest in tests/selftest.py and CMakeLists.txt.

**Rationale.** Every level where a regression could hide gets a test in the suite that already owns that level; the rule 'a case for every provider-script / formatting bug' extends naturally; registering in both runners closes the F17 gap for the new suites.

**Rejected.** Only end-to-end tests (slow, and they cannot pin the grammar's corners); a new QML test harness (the existing EditorKeys and transitions harnesses already drive a real editor and a fake session); joining the 'keys' suite (one suite's deadline would grow with every timeline case).

**Evidence.** tests/selftest.py:15-43; CMakeLists.txt:71-131; tests/transition_selftest.py:18, 217-222 (noise gates); tests/transitions.qml:250-252, 375-414, 785-965; tests/EditorKeys.qml:300-366, 3051-3059, 3336-3346; plugins/org.note-note.local/selftest.py:78-112, 423-493, 524-582; tests/test_regressions.py:86-110, 551-570; services/markdown/qthtml/selftest.py:32, 233-260; docs/testing.md:91-99, 369, 488.

### D18 - Docs and decisions

**Decision.** docs/providers.md: Properties table - noteTypes (new row), markdown re-labelled 'legacy shorthand: true = [markdown], false or absent = [text]', hasTitle default true stated, tools normalisation stated; a new 'Note types' section (vocabulary, per-note noteType on rows / notes / load, create options, save options, unknown types open read-only, the timeline body format with the grammar, limits and progress { done, total, next }); row shape and notes shape gain noteType and progress; footer shortcut vocabulary gains newTimeline; host.newNote(id, target, noteType); create(target, cb, options); load fields gain noteType and the drift is fixed (retry; save's merged and version); a compatibility paragraph modelled on :170-175. skills/note-note-plugin/references/providers.md mirrors all of it in the same commit (plus F13's count) and its minimal provider declares noteTypes; references/commands.md lists newTimeline and addEvent. docs/commands.md:61-62 and the availability text. README.md: Notebooks (timelines, the front-matter key, what other tools see), Keys (Ctrl+Shift+T, Ctrl+Enter and the timeline keys), Providers (which hold timelines), Writing plugins (noteTypes). plugins/org.note-note.local/getting-started.md: a 'New Timeline' line and a Ctrl+Shift+T row. docs/business-requirements.md: the non-goal gains 'Note types are ways to edit a note, not templates or databases: a type adds no fields, queries or content of its own, and every type stays a plain Markdown file on disk'; the product-decision row 'Sticky Notes are plain text; OneNote and Notion are Markdown' becomes 'A note has a type ... local notebooks also hold timelines'; a new row for the in-order check rule. docs/technical-requirements.md: editor format (:14) per type, data model rows (:105-117, also fixing the stale row shape), limits (:170-188) gain 1,000 events / 500-character titles / 10,000-character descriptions / 8 MiB codec input. docs/decisions.md: 'A note has a type; the provider stores it, the host edits it', 'A timeline is a task list on disk', 'Checks run in order', 'The add-event form is part of the note', 'Timeline events are a ListModel', 'Note types are the app's own, not yet a plugin kind', 'A tool acts only on a Markdown note'. docs/testing.md: the codec selftest, the timeline suite, IPC addEvent / timelineToggle, the lint set, how to check a saved timeline file. docs/security.md: the codec's read-time bounds, PlainText rendering of event text, strict JSON for write input. docs/editing-tools.md: tools act on Markdown notes only. docs/plugins.md: no change (no new package kind). Release: manifest.json and the metainfo release notes.

**Rationale.** The contract is the API other people write against and changes additively and visibly (technical-requirements.md:99-101); docs ship in the same commit as the behaviour (release-process.md:36-37); the skill mirror changes with its contract (plugins.md:50-53) and has drifted before.

**Rejected.** A separate docs/timelines.md (the contract belongs in providers.md, the product in README and business-requirements, the why in decisions.md - a fourth home would drift); documenting conversion or a plugin kind now (no unused API in the contract).

**Evidence.** docs/providers.md:41-60, 84-94, 170-213, 257-357, 493-507; skills/note-note-plugin/references/providers.md:55-56, 229-247, 267-286, 304-328, 342-353; docs/business-requirements.md:57-58, 66-78; docs/technical-requirements.md:14, 99-117, 170-188; docs/release-process.md:25-37; docs/plugins.md:46-53; README.md:185-241, 269-289, 325-345; plugins/org.note-note.local/getting-started.md.

### D19 - Phasing

**Decision.** Order (details in 'phases'): Phase 0 prerequisites in three commits - F1, F17, F2+F21. Phase 1 note types in the contract and the pane with no visible change - capabilities/notetypes modules and the hasTitle fix, the NoteEditor body seam, session typing, typed creation plumbing, built-ins declaring noteTypes, contract docs and mirror. Phase 2 the timeline in local notebooks as reviewable commits 2a codec, 2b model rules, 2c UI and pane wiring with the real-key suite, 2d local provider, 2e list and view bar, 2f commands, 2g hello, 2h docs - each keeping both runners green and carrying its docs. Phase 3 release 1.1.0 (manifest.json and the leading metainfo release together, validate, ctest, tests/selftest.py, package.py, security checklist). Ships: timelines in local notebooks and the example provider with keyboard and mouse, list progress and palette commands; OneNote, Notion and Sticky unchanged. Phase 4 later: conversion, OneNote/Notion opt-in, a plugin kind, drag-and-drop, event dates, timeline-aware conflict review. Commits happen when the author asks (release-process.md:25); 'graphify update .' after code changes.

**Rationale.** Phase 1 is behaviour-neutral, so the riskiest refactor (the pane seam and session typing) lands and is tested before any new UI; the timeline then arrives on proven plumbing. A new note type and an additive contract are a feature, which the documented rule makes a minor bump.

**Rejected.** One big commit (unreviewable, and docs-with-behaviour per commit becomes impossible to check); shipping OneNote/Notion support in the same release (needs live verification and product choices); a patch bump (contradicts docs/release-process.md:26-27 for a feature).

**Evidence.** docs/release-process.md:25-37, 26-27; manifest.json:5; packaging/desktop/io.github.andreivinca.note-note.metainfo.xml:36-60; packaging/package.py:70-77; docs/security.md:286-325; docs/testing.md:763-775.

### D20 - Risks and user decisions

**Decision.** Risks and mitigations are listed in 'risks'; the product decisions the user must make are listed in 'user_decisions', each with options and a recommended default the plan already assumes: in-order unchecking, the 'note-note-type:' key, multi-paragraph descriptions, a provider footer 'New Timeline' row plus Ctrl+Shift+T and the palette, Ctrl+Enter for Add Event, the list progress line, filled circle with a tick for done, dimmed (not struck-through) done events, delete without a dialog, conversion later, OneNote/Notion later, version 1.1.0.

**Rationale.** Every choice that is a product judgement rather than an engineering consequence is surfaced with a default, so implementation can start while the user confirms or changes them.

**Rejected.** Leaving the choices implicit in the design (the user cannot see what was decided for them); blocking the plan on answers (each has a safe default).

**Evidence.** See 'risks' and 'user_decisions'; maps/brief.md open questions for every area.

## Architecture overview

COMPONENTS. Provider side: each Provider.qml declares noteTypes; the local provider's Python (notefile.py owns the 'note-note-type:' front-matter line; list.py emits it with progress; operations.py creates, reads and saves typed notes) and examples/hello. Shared codec: services/markdown/timeline (read / write / summary on the vendored mistune via parse.py and mdtext.py; CLI with framed JSON). Host vocabulary: services/notes/notetypes.js (ids, bodies, glyphs, footer shortcuts, progress text) and services/notes/capabilities.js (every provider capability with its default; noteTypeOf). Session: NoteSession (unchanged machinery; the type rides in the document). Pane: NoteEditor with two bodies behind one interface - textBody (the existing TextEdit, for text and markdown) and TimelineBody (ui/timeline: TimelineBody.qml, TimelineEvent.qml, TimelineEditor.qml, TimelineModel.js; shared ui/CheckFace.qml and ui/ChromeTextArea.qml). List: sidebar.js row() -> NoteList / SearchResults -> NoteSummary (glyph + progress line). Commands: defaults.js, WorkspaceActions, the workspace plugin.json.

LIST FLOW. list.py reads each note's head (and a timeline note whole) -> N record with noteType, done/total, next -> Provider.loadList -> entries -> rows and sections[].notes with noteType and progress -> sidebar.js row() keeps known noteType and normalised progress -> NoteSummary draws the timeline glyph and '3 of 7 · Next: ...' (for the open note Workspace.displayProgress substitutes editor.progress, live).

OPEN FLOW. Row click -> Workspace.choosePath -> NoteSession.selectPath -> flushSave -> load(): editor.setNote('', '', null, Capabilities.of(provider).defaultNoteType) blanks the pane -> provider.load answer { title, body, noteType, editable, reason, version, base } -> Capabilities.noteTypeOf(provider, result.noteType) -> editor.setNote(title, body, shown, noteType) -> NoteEditor.useType switches to TimelineBody before the document goes in -> Markdown.toTimeline -> python3 services/markdown/timeline/__main__.py read -> { events, refusal } -> ListModel -> shown(true, '') -> NoteSession.noteReady -> stored[path] = snapshot { title, body: events JSON, base, noteType }. A refusal: the pane shows the same Markdown in textBody, read-only -> shown(true, refusal) -> noteReady(read-only, reason). Unknown type: textBody as plain text, read-only, reason.

EDIT/SAVE FLOW. Space/click/typing in TimelineBody -> TimelineModel.js computes -> ListModel setProperty/move/remove/append -> edited() -> NoteEditor.edited -> Workspace.onEdited -> NoteSession.onEdited -> local noteEdited (500 ms) -> saveRequested -> flushSave -> snapshotDocument -> isStored? (title, body JSON, noteType) -> setDraft -> editor.requestBody -> Markdown.fromTimeline -> python3 ... write (verified re-read) -> provider.save(path, title, markdown, cb, { view, resolution, noteType }) -> operations.py save (keeps the type line; answers preview and progress) -> Provider commit (Object.assign keeps noteType) -> rows rebuild -> finishSave -> stored.

CREATE FLOW. Ctrl+Shift+T / palette 'New Timeline' -> WorkspaceActions.newTimeline -> Workspace.newNote('', undefined, 'timeline') -> activateFooterShortcut('newTimeline') -> local footer 'New Timeline' -> Provider.action('newTimeline') -> host.newNote('local', 'section:<key>', 'timeline') -> newNoteDestination filters by type -> p.create(target, cb, { noteType: 'timeline' }) -> operations.py create writes '---' / 'title: ' / 'note-note-type: timeline' / '---' -> choosePath -> load (as above, empty timeline) -> focusTitle -> Enter -> focusBody -> the add-event form.

## File changes

| Phase | File | Change |
|---|---|---|
| 0 | `services/notes/NoteSession.qml` | F1: replacePath deletes pathAliases[next] and re-points aliases whose value is 'previous' (an alias key is never a live path). |
| 0 | `Workspace.qml` | F2/F21: runRowAction locks, flushes, waits for session.saveInFlight(currentPath) to clear, then calls rowAction; the callback treats a missing result as {} and always unlocks. |
| 0 | `tests/transitions.qml` | F1 case (rename a section A->B->A, then open, edit and save a note in it) and F2/F21 cases (delayed converter; provider answering cb()). |
| 0 | `tests/transition_selftest.py` | F17: --list-suites prints SUITES; SUITES stays the only list of suite names. |
| 0 | `CMakeLists.txt` | F17: read the transition suite names with execute_process(... tests/transition_selftest.py --list-suites) instead of the hand list at :99. |
| 0 | `tests/selftest.py` | F17: suites as argv tuples; the core suite recognised by its last element. |
| 1 | `services/notes/notetypes.js (new)` | Host vocabulary table for 'text' and 'markdown' (timeline added in phase 2): known() via own properties, bodyOf, glyphOf, labelOf, footerShortcutOf. |
| 1 | `services/notes/capabilities.js (new)` | of(provider) with every default (hasTitle true, canImages strict, tools null/array/[] fail-closed, noteTypes, defaultNoteType); noteTypes(); canCreate(); noteTypeOf(provider, reported) -> { noteType, refusal }. |
| 1 | `services/notes/sidebar.js` | row(): hasTitle through Capabilities (same meaning, one source). |
| 1 | `ui/NoteEditor.qml` | Body seam: noteType property; plain/rich derived; textBody adapter (show/restore/capture/request/clear/viewState/restoreViewState/focusEditor/focusBody/undo/redo/wordCount/countText); body selection and useType(); setNote(t, body, shown, noteType); snapshot/restore noteType; requestMarkdown -> requestBody; shown(ok, refusal) with the Markdown read-only fallback; delegation of focus/view/undo/counts; applyReadOnly forces the TextEdit read-only when inactive; paste/pastePlain/hoveredLink only for textBody. |
| 1 | `ui/editing/EditorApi.qml` | writable requires host.rich instead of !host.plain (tools and toolbar for Markdown notes only). |
| 1 | `ui/ViewBar.qml` | countText (string) replaces wordCount; the label keeps objectName 'wordCount'. |
| 1 | `services/notes/NoteSession.qml` | Provider looked up at load start; blank with the provider's default type; Capabilities.noteTypeOf on the answer; setNote with the type; noteReady with type/body refusals; isStored compares noteType; requestBody; save options carry noteType. |
| 1 | `Workspace.qml` | Editor bindings via Capabilities (fixes the absent-hasTitle binding; removes the plain: binding); newNote/newNoteDestination(..., noteType) with create options always passed and focus via Capabilities; currentNoteType, editorWritable (also in contextState); countText wiring; debugState noteType; IPC editorUndo through the pane. |
| 1 | `plugins/org.note-note.local/Provider.qml` | noteTypes ['markdown'] replaces markdown: true; create(target, cb, options) accepts options (type used in phase 2). |
| 1 | `plugins/org.note-note.sticky/Provider.qml` | noteTypes ['text'] replaces markdown: false. |
| 1 | `plugins/org.note-note.notion/Provider.qml` | noteTypes ['markdown'] replaces markdown: true. |
| 1 | `plugins/org.note-note.onenote/Provider.qml` | noteTypes ['markdown'] replaces markdown: true. |
| 1 | `plugins/org.note-note.onenote/onenote.py` | Drop the unread per-page markdown=True at :1380 and :1387 (superseded by noteType). |
| 1 | `examples/hello/Provider.qml` | noteTypes ['markdown']; create(target, cb, options); noteType in the load answer and rows; braces/one-statement-per-line in touched functions. |
| 1 | `tests/transitions.qml` | Fake editor: noteType, 4-argument setNote recording the type, requestBody, snapshot noteType; fake provider noteTypes; session cases (legacy flags, unknown type, body refusal, drafts, stored, save options, failed delete, A/B race); pure cases for notetypes.js and capabilities.js. |
| 1 | `tests/EditorKeys.qml` | editor.plain = X becomes editor.noteType = X ? 'text' : 'markdown' (:1089, :1103, :1367, :1369, :3342); requestMarkdown -> requestBody (:1248, :2454). |
| 1 | `tests/extensions.qml` | requestMarkdown -> requestBody (:279). |
| 1 | `tests/audio.qml` | requestMarkdown -> requestBody (:211). |
| 1 | `docs/providers.md` | Contract: noteTypes property, legacy markdown shorthand, stated defaults, Note types section (without the timeline body), noteType on rows/notes/load, create options, save options noteType, host.newNote type, compatibility paragraph, retry/merged/version drift fixed. |
| 1 | `skills/note-note-plugin/references/providers.md` | Mirror of the contract change in the same commit, plus F13 (row shape count); minimal provider declares noteTypes. |
| 1 | `docs/technical-requirements.md` | Editor format per type (:14); data model rows (:105-117) refreshed. |
| 1 | `docs/decisions.md` | Entry 'A note has a type; the provider stores it, the host edits it' and 'A tool acts only on a Markdown note'. |
| 2a | `services/markdown/timeline/__init__.py (new)` | read(markdown) -> { events, refusal }; write(events) -> markdown (verified, strict fallback, ValueError); summary(markdown); MAX_EVENTS 1000, MAX_TITLE 500, MAX_DESCRIPTION 10000. |
| 2a | `services/markdown/timeline/__main__.py (new)` | CLI 'read' \| 'write': payload on stdin capped at 8 MiB, write input via lib/jsondata.py, one framed JSON answer. |
| 2a | `services/markdown/timeline/selftest.py (new)` | Codec tests (D17). |
| 2a | `services/markdown/Markdown.qml` | toTimeline(markdown, cb(answer, ok)) and fromTimeline(events, cb(markdown, ok)); run() takes the script. |
| 2a | `tests/selftest.py` | Register services/markdown/timeline/selftest.py. |
| 2a | `CMakeLists.txt` | add_test(NAME timeline-codec ...) for the codec selftest. |
| 2b | `ui/timeline/TimelineModel.js (new)` | Pure rules: toggled, changed, nextIndex, progress, moved, capture (fixed key order, empty composer excluded), parseCapture/valid (bounded), countText; limits mirrored. |
| 2b | `services/notes/notetypes.js` | timeline entry (body 'timeline', glyph U+F1533, footerShortcut 'newTimeline'); progressText; normalizedProgress. |
| 2b | `tests/test_regressions.py` | TimelineModel.js limits equal the codec's; notefile.note_type cases and the split/serialize property with a type line. |
| 2c | `ui/CheckFace.qml (new)` | The drawn check face (accent fill, cut-out tick, alpha border) extracted from NoteEditor's overlay, with round and emphasized (next ring). |
| 2c | `ui/ChromeTextArea.qml (new)` | Multi-line field on ChromeControlStyle (QQC.TextArea, grows with text, placeholder colour, focus border). |
| 2c | `ui/timeline/TimelineBody.qml (new)` | The body: ListModel of events, Flickable + Column + Repeater, rail and add row, empty state, cursor and keyboard model, compose/edit modes, undo stacks, statuses, accessibility, the body interface. |
| 2c | `ui/timeline/TimelineEvent.qml (new)` | One event row: rail segments, CheckFace circle with focus ring and hover, title and description texts, tap/double-tap/right-click handlers, editor loader. |
| 2c | `ui/timeline/TimelineEditor.qml (new)` | Title ChromeTextField + description ChromeTextArea + hint/message + Add/Done button; specific Keys handlers before shortcuts. |
| 2c | `ui/NoteEditor.qml` | TimelineBody in the sheet (visibility, readOnly, codec, noteToken, keyHook, edited/statusRequested/leaveTop); checkbox overlay uses CheckFace; addEvent(), toggleEvent(index). |
| 2c | `ui/RowMenu.qml` | Comment generalised: any row-shaped { menu } object (reused for the event menu). |
| 2c | `tests/EditorKeys.qml` | New 'timeline' suite (D17); resetEditor resets noteType and the timeline. |
| 2c | `tests/transition_selftest.py` | SUITES gains 'timeline'. |
| 2d | `plugins/org.note-note.local/notefile.py` | TYPE_KEY 'note-note-type:', TYPE_ID, note_type(extra), type_line(id); MAX_NOTE_BYTES moved here; docstring. |
| 2d | `plugins/org.note-note.local/operations.py` | create with noteType; read returns noteType and runs unkept only for Markdown; save answer progress for timelines; MAX_NOTE_BYTES from notefile. |
| 2d | `plugins/org.note-note.local/list.py` | head_of returns type and progress (whole-file read for timelines, lazy codec import); 10-field N record; docstring. |
| 2d | `plugins/org.note-note.local/Provider.qml` | noteTypes ['markdown','timeline']; New Timeline footer action and action('newTimeline'); loadList fields 8-10; rows and searchable carry noteType/progress; load answer noteType; save commit via Object.assign with progress; create sends options.noteType and seeds the entry. |
| 2d | `plugins/org.note-note.local/selftest.py` | Local cases (D17). |
| 2d | `plugins/org.note-note.local/getting-started.md` | A 'New Timeline' line and a Ctrl+Shift+T row in the shortcut table. |
| 2d | `tests/transitions.qml` | localCases: create a timeline through the real provider; loadList record() fixtures with 10 fields. |
| 2e | `services/notes/sidebar.js` | row(): noteType (known ids) and progress (normalised) for note rows. |
| 2e | `ui/NoteSummary.qml` | glyph before the title; progress line in place of the preview. |
| 2e | `ui/NoteList.qml` | progressFor function property; pass glyph and progress to NoteSummary. |
| 2e | `ui/SearchResults.qml` | Same pass-through as NoteList. |
| 2e | `Workspace.qml` | displayProgress(row) and progressFor wiring; addEvent(); timelineToggle(index); debugState progress. |
| 2f | `services/shortcuts/defaults.js` | newTimeline (Ctrl+Shift+T, notes) and addEvent (Ctrl+Enter, Ctrl+NumEnter, workspace). |
| 2f | `services/commands/WorkspaceActions.qml` | newTimeline and addEvent handlers; state noteType and editorWritable; canCreateNote(noteType); reasons. |
| 2f | `plugins/org.note-note.workspace/plugin.json` | Commands new-timeline and add-event (workspaceAction). |
| 2f | `services/extensions/selftest.py` | Pin seven workspace commands. |
| 2f | `docs/commands.md` | Supported action ids and availability for newTimeline and addEvent. |
| 2f | `skills/note-note-plugin/references/commands.md` | Mirror of the action ids (:31) and availability (:170). |
| 2g | `examples/hello/Provider.qml` | noteTypes ['markdown','timeline']; New Timeline footer action; timeline rows with noteType and an empty preview. |
| 2h | `README.md` | Notebooks (timelines, front-matter key), Keys (Ctrl+Shift+T, Ctrl+Enter, timeline keys), Providers (who holds timelines), Writing plugins (noteTypes). |
| 2h | `docs/providers.md` | Note types: the timeline body format, limits and progress; footer shortcut newTimeline. |
| 2h | `skills/note-note-plugin/references/providers.md` | Mirror of the timeline body format and progress. |
| 2h | `docs/business-requirements.md` | Non-goal clarification for note types; product-decision rows for types and the in-order check rule. |
| 2h | `docs/technical-requirements.md` | Limits: 1,000 events, 500-character titles, 10,000-character descriptions, 8 MiB codec input. |
| 2h | `docs/decisions.md` | Entries: timeline is a task list on disk; checks run in order; the add-event form is part of the note; events are a ListModel; note types are not yet a plugin kind. |
| 2h | `docs/testing.md` | Codec selftest, timeline suite, IPC addEvent/timelineToggle, qmllint set gains ui/timeline/*.qml, checking a saved timeline file. |
| 2h | `docs/security.md` | Codec read-time bounds, PlainText rendering of event text, strict JSON for write input. |
| 2h | `docs/editing-tools.md` | Tools act on Markdown notes only. |
| 3 | `manifest.json` | version 1.1.0. |
| 3 | `packaging/desktop/io.github.andreivinca.note-note.metainfo.xml` | Leading <release version="1.1.0"> with user-facing notes. |

## Phases

### Phase 0 - Prerequisites

**Goal.** Remove the open defects that sit on the paths the feature extends, and make sure a new test suite cannot silently skip a runner.

Steps:

1. Commit 1 (F1): NoteSession.replacePath keeps the invariant 'an alias key is never a live path' (delete pathAliases[next]; re-point aliases whose value is 'previous'); transition case renaming a local section A->B->A, then opening, editing and saving a note there.
2. Commit 2 (F17): tests/transition_selftest.py --list-suites; CMakeLists.txt reads it at configure time; tests/selftest.py uses argv tuples.
3. Commit 3 (F2 + F21): runRowAction drains the open note's save before rowAction and unlocks unconditionally; transition cases with a delayed converter and a provider answering cb().
4. Run graphify update . after the code changes.

Exit criteria:

- python3 tests/selftest.py and ctest both green; ctest lists exactly transition_selftest's SUITES.
- The F1, F2 and F21 cases pass and fail on the parent commit.

### Phase 1 - Note types in the contract and the pane (no visible change)

**Goal.** A note's type flows provider -> session -> pane -> save, with Markdown and plain-text notes behaving exactly as today and every external provider unchanged.

Steps:

1. Add services/notes/notetypes.js (text, markdown) and services/notes/capabilities.js; route Workspace's editor bindings, newNote's focus choice and sidebar.js hasTitle through Capabilities (fixes the absent-hasTitle binding).
2. NoteEditor body seam: noteType, plain/rich derived, textBody adapter, useType(), setNote 4th argument, snapshot/restore noteType, requestBody, shown(ok, refusal) with the Markdown read-only fallback, delegated focus/view/undo/counts, rich-only guards; EditorApi.writable on host.rich; ViewBar countText.
3. NoteSession: type resolution with Capabilities.noteTypeOf, blank with the provider default, noteReady with refusals, isStored compares noteType, requestBody, save options noteType.
4. Workspace: newNote/newNoteDestination(..., noteType) with create options always passed; currentNoteType, editorWritable, debugState noteType.
5. Built-ins declare noteTypes; onenote.py drops markdown=True; hello declares noteTypes and takes create options.
6. Tests: fake editor and session cases, pure cases, renames in EditorKeys/extensions/audio.
7. Docs in the same commit: providers.md and the skill mirror (+F13), technical-requirements data model, decisions.md entry.
8. Run graphify update . after the code changes.

Exit criteria:

- Both runners green; qmllint silent on the documented set; no QML warning lines (the noise gates).
- A fake provider with only markdown: true opens Markdown, with markdown: false or absent opens plain text, with an unknown noteType opens read-only with the reason (tests).
- Opening, editing and saving local, Sticky, OneNote and Notion notes behaves as before (existing suites unchanged in meaning).
- debugState reports noteType.

### Phase 2 - The timeline in local notebooks

**Goal.** Users create, read, check, add, edit, reorder and delete timeline events in local notes - keyboard-only if they like - and the files stay plain GitHub task lists.

Steps:

1. 2a: services/markdown/timeline codec + CLI + selftest; Markdown.qml toTimeline/fromTimeline; register the selftest in both runners.
2. 2b: ui/timeline/TimelineModel.js with pure cases; timeline entry in notetypes.js; constants-agreement regression test.
3. 2c: extract ui/CheckFace.qml (rich overlay pixel-identical); ui/ChromeTextArea.qml; TimelineBody/TimelineEvent/TimelineEditor; pane wiring; EditorKeys 'timeline' suite; SUITES gains 'timeline'.
4. 2d: local provider - notefile type helpers, operations create/read/save, list.py 10-field records with progress, Provider.qml (noteTypes, New Timeline, loadList, rows, load mapping, save commit, create options), selftests, getting-started.md, transitions localCases.
5. 2e: list glyph and progress line, live progress for the open note, view bar countText.
6. 2f: defaults.js keys, WorkspaceActions handlers/state, workspace plugin.json commands, extensions selftest pins, commands docs and skill mirror.
7. 2g: examples/hello timeline support.
8. 2h: README, providers.md timeline section and mirror, business and technical requirements, decisions, testing, security, editing-tools docs; qmllint set gains ui/timeline/*.qml.
9. Run graphify update . after each code commit.

Exit criteria:

- Both runners green, qmllint and ruff silent, no QML warning lines.
- Manual check per docs/testing.md:763-775 in both hosts, light and dark: Ctrl+Shift+T -> title -> Enter -> three events with descriptions -> Space and clicks check everything above -> Delete + Ctrl+Z -> Alt+Up -> reload; the .md file holds exactly the canonical form with 'note-note-type: timeline'.
- Ticking an item of the file in another editor (or with sed) shows up live in the open, unedited timeline; an out-of-order state is shown as stored.
- A timeline file opened by the 1.0.40 build reads as a checklist and, edited and saved there, still opens as the same timeline.
- The list shows the glyph and '3 of 7 · Next: ...' and updates as events are checked; search finds event text.

### Phase 3 - Release 1.1.0

**Goal.** Ship the feature with its documentation and release checks.

Steps:

1. Bump manifest.json to 1.1.0 and add the leading metainfo <release> with user-facing notes, together.
2. omarchy plugin validate .; Release build; ctest; python3 tests/selftest.py; python3 packaging/package.py.
3. Walk the security pre-release checklist (docs/security.md:286-325).
4. Commit and release only when the author asks (docs/release-process.md:25).

Exit criteria:

- package.py passes its version, layout and validate checks.
- Release notes describe timelines, the keys and which notebooks hold them.

### Phase 4 - Later (not in this release)

**Goal.** Grow the type system once the first type has been used.

Steps:

1. Convert Markdown <-> timeline: save with options.noteType (providers that declare several types write it), palette commands, reload in place.
2. OneNote opt-in: verify a data-id wrapper marker live in desktop, web and mobile apps (dated docs/onenote-*.md section), map indented task-item paragraphs to to-do + margin-left paragraphs, fix the to-do edge cases.
3. Notion opt-in: the user picks the marker (page icon vs marker block); notion_md keeps paragraph children under to_do; optional targeted checked updates.
4. Note types as the sixth plugin kind (manifest kind, NoteType contract, NoteTypeRegistry, qualified ids).
5. Drag-and-drop reordering, event dates, a timeline-aware conflict review, ListView virtualisation if 1,000-event timelines measure slow.

Exit criteria:

- Each item lands with its own decision record, contract text and tests.

## Risks

| Risk | Mitigation |
|---|---|
| The editor body chosen from a late or wrong type (a note rendered and saved in the wrong form). | The type is an argument of setNote and a field of every snapshot, applied before the body sees the document; the load answer is the single authority; session cases cover drafts, recovery, unknown types and an A/B race. |
| A timeline save writes something that reads back differently (lost or altered events). | write() re-reads its output and must reproduce the normalised events, falls back to strict escaping once, else refuses; the answer is framed so a failure keeps the draft; a seeded 3,000-case fuzz test pins it (the prototype passed with 0 failures). |
| An older Note Note, or a host without the timeline, opens a timeline note as Markdown and rewrites it. | The canonical body passes qthtml.unkept and its qthtml round trip reads back the same events (verified on HEAD); the type line is an unowned front-matter line every save keeps; checked in the phase 2 manual test against the 1.0.40 build. |
| The front-matter key collides with user metadata. | Namespaced 'note-note-type:'; values outside the id grammar or equal to 'markdown' read as Markdown and stay verbatim; Markdown notes never get the line. |
| Notes edited elsewhere arrive with out-of-order checks or extra content. | Out-of-order states are shown as stored and never repaired on open; anything outside the grammar opens read-only as Markdown with a named reason. |
| Local is last-writer-wins: a check made elsewhere while the timeline has unsaved edits is overwritten. | Existing documented behaviour for every local note; a clean open note reloads on the external change; noted in README; merge-aware storage is out of scope. |
| The hidden rich TextEdit acts on input while a timeline is shown (tools, paste, undo via keys or IPC). | applyReadOnly forces it read-only whenever the text body is inactive; EditorApi.writable requires a Markdown note; paste/pastePlain/undo/redo route to the active body; an EditorKeys case asserts nothing changes. |
| Keyboard conflicts or swallowed keys (Ctrl+Shift+T, Ctrl+Enter, Escape in the form). | Both keys are free of every default and tool binding (checked against defaults.js and ui/tools); addEvent is bound in the 'workspace' context only; the form's specific Keys handlers claim Escape and Enter before the app's shortcuts; a test compiles the registry and asserts no diagnostics. |
| The coupled check rule surprises users (one click checks or unchecks many events). | A status line names what happened when more than one event changes; the top-down fill animation shows it; one Ctrl+Z undoes it; re-checking the last done event restores everything above. |
| The live form saves half-typed events. | That is the intent (nothing typed is lost); the event being written is visibly in compose style; Esc discards it with one undo step to bring it back; an empty form contributes nothing. |
| Large timelines (up to 1,000 events) are slow to open or to list. | Bounded at read time; Column + Repeater creates every row once - measure a 1,000-event fixture in the timeline suite and switch to a virtualised view with a pinned editing row if it exceeds the budget; list.py reads whole files only for timeline notes and only while the window is visible. |
| The first ListModel-based list goes against the 'prefer arrays' engine note. | A decision record explains why (uniform roles, in-place edits keep focus and scroll); the pure rules stay array-based in TimelineModel.js and are tested there. |
| A new suite or test silently does not run in one runner. | F17 lands first; the codec selftest is registered in both tests/selftest.py and CTest. |
| Noise gates fail suites on any QML warning from the new components. | No undefined assignments in bindings (Capabilities normalises every capability); qmllint over ui/timeline; the suites themselves are the gate. |
| The contract and the skill mirror drift again. | Both change in the same commit as the behaviour, with a review checklist of every section (properties, rows, notes, load, create, save, footer shortcuts); F13 fixed in the same pass. |
| Accessibility roles are a new precedent and may be wrong on some platforms. | Use only standard Qt Accessible roles (List, ListItem, CheckBox, Button) with names and checked state; an EditorKeys case asserts them; no behaviour depends on them. |
| Theme or host differences make the timeline look broken in one host. | Only tokens, Style helpers and Style keys both hosts define; checks are drawn shapes, not glyphs; manual screenshots in both hosts, light and dark. |
| Unknown note types from future versions or other tools lock users out of editing. | They open read-only with a reason that names the type, never rewritten; the marker is kept; a later conversion or plugin kind can open them. |

## Decisions for the user

### What does unchecking an event do?

- Uncheck it and every event below it (checked events stay a prefix: 'you are here')
- Uncheck only that event (holes appear above checked events)
- Allow unchecking only the last checked event; clicks on others do nothing

**Recommended:** Uncheck it and every event below it. It mirrors 'check one, check everything above', keeps the timeline an ordered path, and a mistaken click is one click or one Ctrl+Z to undo.

### Which front-matter key marks a local timeline note?

- note-note-type: timeline
- type: timeline
- note-type: timeline

**Recommended:** note-note-type: timeline The key is permanent on disk; 'type:' is used by Hugo and many Obsidian vaults and 'note-type:' by Zettelkasten templates, so either could flip a user's own note into a timeline.

### May an event description hold several paragraphs?

- Yes: Shift+Enter makes lines, a blank line makes paragraphs
- One paragraph only (line breaks allowed)
- A single line

**Recommended:** Yes, several paragraphs. Local Markdown keeps them faithfully; the limit only matters for OneNote and Notion, which are not in this release and would need converter work anyway.

### How is a timeline created with the mouse?

- A provider-supplied 'New Timeline' footer row next to 'New Note' (plus Ctrl+Shift+T and the palette)
- A type chooser added by the host to the provider's 'New Note' row (amends the 'host adds no creation buttons' rule)
- Palette and shortcut only

**Recommended:** A 'New Timeline' footer row plus Ctrl+Shift+T and the palette. It stays inside the documented creation rules and costs one footer row; a chooser becomes worthwhile when a third type arrives.

### Which keys create a timeline and add an event?

- Ctrl+Shift+T for New Timeline, Ctrl+Enter for Add Event
- Ctrl+Alt+N for New Timeline, Ctrl+Shift+Enter for Add Event
- No default keys (palette only), user-bindable

**Recommended:** Ctrl+Shift+T and Ctrl+Enter. Both are free of every existing binding, pair with Ctrl+Shift+N and with Enter-to-add in the form, and remain rebindable.

### What does a timeline row show in the sidebar?

- A timeline glyph and '3 of 7 · Next: Pack the kitchen'
- The first event, like any note's preview
- A small progress bar and the count

**Recommended:** The glyph and '3 of 7 · Next: ...'. It tells you where you are without opening the note, updates live for the open note, and needs no visual noise in other rows.

### How does a done event look?

- Filled accent circle with a tick; title and description dimmed
- Filled dot (radio style); title dimmed
- Filled circle; title struck through

**Recommended:** Filled circle with a tick, dimmed text. A tick reads as 'done' (a dot reads as 'selected', strikethrough as 'cancelled'), and it matches the editor's own checkboxes.

### Should deleting an event ask for confirmation?

- No dialog; a status line and Ctrl+Z undo
- A confirmation dialog

**Recommended:** No dialog, with undo. Business goal 2 rules out modal dialogs between the user and their text; undo is faster and safer.

### Ship converting notes between Markdown and timeline in the first release?

- Later (the design leaves room)
- In the first release

**Recommended:** Later. Not requested; it needs a provider operation, UI and tests; nothing in the design blocks it.

### Timelines in OneNote and Notion?

- Later, after a durable marker is verified (OneNote: data-id wrapper; Notion: page icon or marker block - your choice)
- Now, with a visible title or icon convention

**Recommended:** Later. No invisible durable marker exists today, their apps do not keep the in-order rule, and a user rename would silently drop the type.

### Which version number?

- 1.1.0 (minor, per docs/release-process.md)
- 1.0.41 (patch, as recent features shipped)

**Recommended:** 1.1.0. A new note type and an additive contract change are a feature; the documented rule says minor.
