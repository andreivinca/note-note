# Judges' verdicts on the three designs

## Judge: fit

_Lens:_ architecture fit and maintainability

**Overall winner:** architect

### Scores

#### architect: 7.5/10

Strengths:
- Keeps NoteEditor as the single pane and the rich editor permanently instantiated, so the ~50 Workspace editor.* references, notices, conflict review, canColorText (Workspace.qml:122-123, 2520), tools.actions (:2554) and toolbar heights (:2714-2715) stay stable.
- One session-facing protocol built on document objects {type,title,body,base}, with clearNote() and restoreDocument returning a refusal. The type travels in every snapshot, draft and stored entry, so no path-keyed map is needed (avoids the F1 class of bug).
- Typed bodies are hosted in a Loader through a narrow bodyHost API (the EditorApi precedent). setSource(url,{host}) re-run on Qt 6.11.2: synchronous, status Ready, required property set, no warning.
- documentActive gates EditorApi.writable (EditorApi.qml:13), applyReadOnly (NoteEditor.qml:371) and paste/undo, and formOpen sits next to tools.panelOpen (Workspace.qml:2150, 2545-2546). The hidden document cannot act.
- Type-agnostic creation: one newNoteOfType action plus commandPalette.pick (CommandPalette.qml:116 verified). It reuses the provider's own newNote footer action, so the target matches Ctrl+N's (Workspace.qml:1892). There is no per-type action, footer row or shortcut word.
- One capability normaliser fixes the absent-hasTitle binding (Workspace.qml:2841-2844).
- No plugin kind now, with a recorded trigger, commit 2c5920f as the template, and qualified package ids reserved.
- Removes dead state: the built-in markdown bools and OneNote's unread per-page markdown=True (onenote.py:1381, 1387).

Weaknesses:
- The JS Markdown codec duplicates mdtext.py's escaping rules in a second language, and the local provider needs a Python twin (notefile.timeline_summary). So three partial grammars must be kept in step by a cross-language selftest.
- Its line-based reader cannot tell emphasis from text. Inline Markdown written by other tools comes back escaped as literal characters on the next check: a silent formatting rewrite.
- The canonical form relies on trailing two-space hard breaks. It is a fixpoint (verified), but once trailing spaces are stripped, a Markdown-editor save merges title and description into '- [x] **Book flights** Return on the 14th' (verified on HEAD's converter).
- A per-note `type` is honoured even from providers that declare no noteTypes, which has no legacy gating.
- NoteType.qml objects, a QML NoteTypeRegistry and runtime apiVersion/definition validation for three static app-owned entries is ceremony. Because the pane owns the registry, the list and actions must read editor.noteTypes.
- The footer chooser amends docs/providers.md:185 and relies on providers forwarding options through action().
- Ctrl+Alt+N is the documented override example (docs/commands.md:145) and a test fixture (tests/ShortcutChecks.js:53-63, tests/extensions.qml:143).

#### guardian: 6.5/10

Strengths:
- Single Markdown authority. timeline.read uses parse.py (mistune), and write builds editor-dialect HTML and returns qthtml.convert(html)['note'] (reader.py:58, 102). The canonical form is the editor's own fixpoint by construction (verified on HEAD), with no second escaper.
- Contract hygiene. `noteType` is unused anywhere in the repo, and a per-note type is read only from providers that declare noteTypes (the canReorder→reorder feature-detection precedent). Invalid declarations get one diagnostic in addProvider, not in bindings.
- NoteTypes.opened(capabilities, answer) is a pure, prototype-free decision function covering legacy, absent, unknown and undeclared types.
- requestBody(document, cb) converts the given snapshot. This removes today's hidden requirement that requestMarkdown run in the same turn as snapshotDocument (NoteSession.qml:480, 493).
- Found a real pre-existing bug: mdtext.py:27 LINE_START misses a lone '+'. Verified: a '+' paragraph raises 'the document cannot be saved without changing its text' at HEAD.
- Staged rollout: prerequisites ship as their own release, and the local marker lands before any UI can write a timeline. Conversion is later, through an explicit setNoteType, never through save.
- Summary preview from one shared host module, with a bounded 64 KiB read and an 'Untitled timeline' display title.

Weaknesses:
- NoteEditor switches on documentType inside each protocol function (setNote, restoreDocument, snapshotDocument, requestBody, focus, viewState, wordCount, paste/undo guards). That type switch grows with every future type.
- Two type concepts (noteType vs documentType), an editable-Markdown fallback, and a capability rule hard-wiring 'timeline requires markdown' into the generic normaliser.
- Typed creation skips the provider's newNote footer action and calls createTargetFor(currentPath). In local notebook tabs this files the timeline in another folder than Ctrl+N would (Provider.qml:265 vs :277).
- Per-type actions (newTimeline, addTimelineEvent) and a timeline-specific editor.openEventForm() on the generic pane.
- Keeps the markdown bools in built-ins (two sources of truth) and OneNote's unread markdown=True.
- Ctrl+Alt+N collides with the documented override example.

#### product: 5.5/10

Strengths:
- Real body seam: a textBody adapter and TimelineBody behind one interface, with a `body` selector. Focus moves to the new body and the hidden body is cleared.
- One Python codec under services/markdown, shared by host and provider.
- The host words the progress and providers send numbers, which respects 'providers know nothing about the UI'.
- Stays inside the documented creation model (provider footer rows), so targets are always the provider's own.
- Correct reading of Qt key order: specific Keys handlers run before onPressed (verified with qmltestrunner on Qt 6.11.2). Also spotted the Ctrl+Alt+N doc/test collision.

Weaknesses:
- Creation surfaces are per type: a footer row per type, the footer `shortcut` vocabulary, notetypes.js footerShortcut and one workspace action per type. The design itself says a chooser replaces them at the third type.
- The writer re-implements the verify-then-strict-retry that qthtml's reader already does. At HEAD it cannot write an event whose description is '+' (verified by running scratchpad/product/timeline_proto.py), and the design lists no mdtext fix.
- Permanent contract growth for one type: a timeline-specific `progress` on rows and notes, a 10-field N record, whole-file reads up to 2 MiB per timeline while listing, a live projection, and save options.noteType 'informational' with no reader.
- ListModel plus a non-virtualised Column/Repeater, against docs/engine-notes.md:47, with a planned later switch.
- The live-compose form makes the form's text part of the document (capture must drop the empty composing event). The type is a trailing optional argument of setNote, and blanking is setNote('', '', null, type).

### Winner per decision point

| D | winner | why | amendments |
|---|---|---|---|
| D1 | guardian | `noteType` appears nowhere in the repo, so it cannot collide with fields providers already emit. Paired with declaration gating, legacy providers stay untouched. Architect's bare `type` is honoured from any provider. Product's grammar admits 'a/b', a package part that is not reverse-DNS. Guardian's grammar has the same core/qualified split as architect's. | Use one concept: drop `documentType` unless the user explicitly picks guardian's editable-Markdown fallback. Use noteType on rows, sections[].notes, the load answer, create options, the snapshot {noteType,title,body,base} and NoteEditor.noteType. Pin the same id strings in JS and Python tests: core ^[a-z][a-z0-9-]{0,31}$, package ^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+/[a-z][a-z0-9-]{0,63}$, at most 128 characters. Labels are 'Note', 'Text note' and 'Timeline'. |
| D2 | guardian | Capabilities.of(provider) is the only reader. The legacy derivation keeps 'absent markdown = plain text' (Workspace.qml:2837-2840). A per-note type is honoured only when noteTypes is declared, which is the canReorder→reorder feature detection (docs/providers.md:170-175). Diagnostics happen once in addProvider, so binding noise cannot trip the noise gates. Architect's function set is equivalent but has no gating. Product silently filters ids it does not know. | Drop the 'timeline requires markdown' rule, which exists only for the editable fallback. Built-ins drop the markdown bool and OneNote's unread per-page markdown=True (architect). hello keeps markdown:true beside noteTypes as the legacy example. Fold in the uncommitted F20 flag storesMarkdownVerbatim (working tree: local Provider.qml:24, NoteSession.qml:281) so NoteSession reads no capability directly. The hasTitle binding becomes `p ? Capabilities.of(p).hasTitle : true`. |
| D3 | guardian | The load answer is authoritative; drafts restore without a load (NoteSession.qml:233-245). NoteTypes.opened(capabilities, answer) is a pure, testable decision covering legacy, absent, unknown and undeclared types, and its lookups are prototype-free. Rows are display-only and carry a type only when it is not the provider's default. | Return {noteType, readOnly, reason}, not a documentType. Unknown or undeclared types are shown read-only as plain text in the document body, with the reason. The save answer carries no type. |
| D4 | architect | There is one type-agnostic path, and it reuses the provider's own target choice by running its newNote footer action with options, as Ctrl+N does through activateFooterShortcut (Workspace.qml:1892). Guardian's direct newNoteDestination route is wrong: with no note open, createTargetFor returns the last notebook's section (local Provider.qml:265), while the footer action uses the open tab (:277). Product's per-type footer rows and shortcut words grow with every type, and the design admits they are throwaway. | Use noteType naming: options.noteType, and host.newNote(providerId, target, noteType) refuses undeclared or unknown types with a status message. Document that a provider declaring two or more creatable types must forward options.noteType from its newNote footer action, and pin it with hello, local and a transitions case. Make the host footer chooser, which amends providers.md:185, an explicit user decision: default to palette plus key only in v1. Never encode the type in target, and add no per-type footer rows or actions. |
| D5 | guardian | A future optional setNoteType(path, noteType, cb), feature-detected like reorder (a local 'retype' that rewrites only the marker), keeps the invariant that only creation writes the marker. Architect's future save options.type, and product's informational save options.noteType shipped now, would let saves change types. | Keep architect's rule that only lossless directions are offered (timeline→Markdown always; Markdown→timeline only when read() accepts the body). No save option carries a type in v1. |
| D6 | architect | The pane keeps every shared concern, the rich editor stays permanent, and the session's single protocol uses document objects. Typed bodies load in a Loader: setSource with initial properties re-run on Qt 6.11.2, synchronous and warning-free. documentActive gates EditorApi.writable and applyReadOnly (EditorApi.qml:13, NoteEditor.qml:371), and formOpen joins tools.panelOpen. A new type is a new body file with no NoteEditor edit. Guardian puts a documentType switch in every protocol function, and product needs a new always-instantiated sibling plus a mapping edit per type. | A timeline's snapshotBody is a deterministic JSON form. requestBody(document, cb) converts the given snapshot (guardian), and the session passes draft.document instead of relying on live state (NoteSession.qml:480, 493). bodyHost also exposes the markdown conversion service so the type's own codec runs under the pane's noteToken. On a type switch, move focus to the new body if the old one had it (product), focusing the Loader item from onLoaded via Qt.callLater (docs/engine-notes.md:55). Merge the uncommitted F20 shown(ok, unkept) into shown(ok, refusal). `plain` becomes private to the document adapter, and tests switch format through setNote({noteType:'text', ...}). |
| D7 | architect | Architect makes the right call: no sixth catalog kind now, a recorded trigger, 2c5920f as the template, qualified ids for packages, and unknown or disabled types open read-only with the marker untouched. | Hold the core type table in a pure .pragma library, services/notes/notetypes.js: id, label, description, glyph U+F1533, the body QML file or '', documentFormat and the untitled label. Then sidebar.js, Capabilities and WorkspaceActions read it without reaching into editor.noteTypes. Keep only ui/notetypes/NoteBody.qml as a QML contract. Drop NoteType.qml objects, the QML registry and runtime apiVersion/definition validation for three static entries, and pin the table with pureCases. |
| D8 | guardian | One Markdown authority and no second escaper. read() runs on parse.py. write() builds editor-dialect HTML and returns qthtml.convert(html)['note'], so the canonical form is the editor's own fixpoint (verified on HEAD) with no trailing-space dependency. Architect's form merges title and description once spaces are stripped (verified), and its JS reader turns inline Markdown into escaped literals. Product's re-implemented verify-and-strict-retry cannot write a '+' description (verified). | Land the mdtext.py:27 fix ([-+*](?=\s\|$)) first. JS TimelineModel.js holds only model operations and mirrored limits, with equality pinned in test_regressions. Text not in timeline form opens read-only with the reason by default; editable Markdown only if the user picks it. Accept a whole-title bold run on read (product's tolerance) and normalise it on the next save. Multi-line descriptions are a later additive grammar change. |
| D9 | architect | A pure setChecked(events, index, checked): check 0..k, uncheck k..n-1. Out-of-order states are shown as stored and never repaired on open, and undo is owned by the body. It is minimal and unit-testable; the other two designs have the same semantics with more machinery. | Add the status line when more than one event changes (guardian/product). The undo stack holds the JSON snapshot forms, at most 200 steps, cleared when another note is shown. |
| D10 | architect | Inline non-modal EventForm, a ListView over a plain array (docs/engine-notes.md:47 prefers arrays), CheckMark extracted from NoteEditor.qml:2242-2284, objectNames, Accessible roles, and formOpen gated like tools.panelOpen. Product's ListModel with a non-virtualised Column/Repeater goes against the engine note and plans a later rewrite. | Descriptions are one paragraph in v1 (D8), so Enter submits from both fields. Keep the form's text in the body, not in a delegate that ListView virtualisation can destroy. Handle every list key in one Keys.onPressed that calls host.shortcut(event) first: Qt 6.11.2 runs Keys.onDownPressed/onReturnPressed before onPressed (verified with qmltestrunner), which would swallow Ctrl+Up/Down. Restore contentY on model swaps (engine-notes.md:42-45). |
| D11 | guardian | No new row contract field. The glyph comes from the host type table, and the preview is a summary string from one shared host module (services/markdown/timeline.summary) used by both the listing and the save answer, with a bounded 64 KiB read. Architect puts a second parser and the wording in local notefile.py. Product adds a timeline-specific progress field, a 10-field record and 2 MiB reads while listing. | The summary wording lives only in services/markdown. Rows carry noteType only when it is not the default. displayTitle shows 'Untitled timeline' from the type table. If live progress is wanted later, project it from the open note's snapshot through the type table, not through a row field. |
| D12 | architect | The same support matrix as the others: local and hello yes, OneNote and Notion deferred, Sticky unsupported. Architect also removes the duplicate and dead declarations: built-in markdown bools and onenote.py:1381, 1387. | Use noteType naming. Add guardian's declaration rule: declare timeline only if save stores the body byte-for-byte and the provider is not merge-aware. hello declares ['markdown','timeline'], keeps markdown:true and forwards options. |
| D13 | guardian | notefile.py owns note-note-type (one format owner, notefile.py:10-15), and conflicting lines are UNREADABLE and open read-only. The marker is written only at creation and survives as an extra line on save (operations.py:126-141). The type is an 8th N field. The timeline read is bounded and lazily imports the shared codec, on operations.py's sys.path precedent. Both traps (Provider.qml:509-511, 545-549) are handled explicitly. | Use Object.assign for the save commit entry (architect/product) and explicit fields for the load answer. Align with the uncommitted F20 change, which moves unkept out of operations.py read into the converter frame. |
| D14 | guardian | The type is inside every snapshot. The deterministic JSON form makes isStored exact (NoteSession.qml:364-366) with no conversion, requestBody(document) converts exactly the draft that was registered, and framed failures keep the draft. | Express it on architect's protocol (clearNote, document objects) and on F14's single stored {path, document}, already in the uncommitted working tree. |
| D15 | architect | A single type-agnostic newNoteOfType action (WorkspaceActions handlers take no parameters, WorkspaceActions.qml:18-34). There is no registry action for addEvent, and timeline keys are the body's own, as the TextEdit's are. Per-type actions (guardian, product) mean four host edits for every new type. | Ctrl+Alt+N is the override example in docs/commands.md:145 and the fixture in tests/ShortcutChecks.js:53-63 and tests/extensions.qml:143. Move those to another key in the same commit, or choose a different default. Pin the action in services/extensions/selftest.py:44-47 and in both commands docs. |
| D16 | guardian | It fixes what the feature's paths run through. The mdtext '+' bug is verified at HEAD: a '+' paragraph cannot be saved. F1 matters for timelines in renamed sections. F2/F21 matter once saves wait on an async codec. F17 registers the new suites in one list. Capability defaults and F13 complete the set. | The working tree already holds uncommitted fixes for F1, F2 (whenSaved), F5, F6, F8, F12, F14, F15 and F21, and F20 is in progress (CODE-REVIEW-2026-10-11.md:9-25). Phase 0 lands and tests those rather than re-designing them, then adds F17 and the mdtext fix. |
| D17 | guardian | It tests the single codec where it lives: Python property tests, converter CASES, the real converter in the EditorKeys timeline suite, constant-agreement tests, and session cases with the type in snapshots. | Add architect's capabilityCases (no 'Unable to assign' noise), the fake-editor protocol update (transitions.qml:375-400), a keys case proving tools, paste and undo stay inert on the hidden document, and pure cases for the type table. No cross-language codec selftest is needed. Register suites once, after F17. |
| D18 | architect | Docs ship with the behaviour. docs/note-types.md documents the internal type framework the way docs/editing-tools.md documents tools. Business-requirements amendments are explicit, not contradicted. | Put the timeline grammar in providers.md or link it from there, since a provider declaring timeline must store it verbatim. Add guardian's security.md entry for the codec as a hostile-input decoder, and note in docs/editing-tools.md that tools act on Markdown notes only (product). |
| D19 | guardian | Staged, each phase shippable. The prerequisites go out as their own release, the format lands before any UI can write it, and 1.1.0 for the feature follows release-process.md:26-27. | Phase 0 is the in-progress review fixes plus F17 plus mdtext, released as 1.0.41. Then follow architect's order and commit granularity: contract and capabilities (no visible change), then the seam (no behaviour change), then the codec, then the type table with the timeline body, then the local marker together with typed creation and the list. CheckMark extraction is its own commit. |
| D20 | architect | The most complete register of architecture risks: hidden document acting, wrong body, early public API, noise gates, glyph tofu, performance at the limit. Every user decision comes with a recommended default. | Add guardian's risks: older app versions, normalisation of outside edits, last-writer-wins. Add product's Qt key-order and model-replacement notes. Add user decisions for the non-timeline-form fallback (read-only vs editable Markdown) and for the host footer chooser. |

### Fatal flaws

- **guardian**: The claim that typed creation is 'aimed at the destination Ctrl+N would use' is false against the code. In local notebook tabs a New Timeline is filed in a different folder than Ctrl+N, and newNote then switches tabs.<br>_Evidence:_ Ctrl+N first runs activateFooterShortcut('newNote') (Workspace.qml:1892 at HEAD). Local's footer action targets 'section:' + sectionKey in notebook-tab mode (plugins/org.note-note.local/Provider.qml:277). Guardian's typed path skips that route and calls newNoteDestination → p.createTargetFor(currentPath) (Workspace.qml:1876). That returns the open note's own folder, or with no note open the LAST notebook's section (Provider.qml:265). newNote then calls showSection(home) (Workspace.qml:1922).
- **product**: The timeline writer cannot save a valid event whose description is exactly '+', so every autosave of that note fails. The design lists no prerequisite fix.<br>_Evidence:_ Its writer escapes description lines with mdtext.escape_line_start, whose LINE_START `[-+*](?=\s)` (services/markdown/mdtext.py:27) misses a lone '+', and its strict retry cannot help because STRICT (mdtext.py:34) does not escape '+'. Running scratchpad/product/timeline_proto.py against HEAD's services/markdown: write([{title:'Pack', description:'+'}]) raises 'the timeline could not be written as it is'. HEAD's own converter also refuses a '+' paragraph: 'the document cannot be saved without changing its text'.
- **architect**: The JS line-based reader treats inline Markdown written by other tools as literal characters and writes it back escaped on the next change. Checking an event therefore silently turns a user's *emphasis* or `code` into visible \*asterisks\* in every other tool, contrary to the rule to open read-only rather than risk a bad write.<br>_Evidence:_ Architect D8 itself: 'Inline Markdown typed elsewhere (*socks*, `x`) reads as its characters ... and is written back escaped on the next change'. docs/README.md rule 1: 'Never lose, duplicate or corrupt them. When in doubt, open read-only rather than risk a bad write.' The false positives architect cites ('5 * 3', '[draft]') are exactly what the real parser already distinguishes (mdtext.py ADJACENT rule; parse.py), so using the repo's parser removes the trade-off.
- **architect**: A per-note `type` is honoured from providers that declare no noteTypes. Any existing external provider whose load answers or rows already carry a `type` key would, after upgrading, have every note open read-only as an unknown type: a silent contract change. It is latent: no built-in emits `type` (grep verified).<br>_Evidence:_ Architect D3: 'A provider may report a type it does not declare; the note opens according to the registry', with no declaration gate in D2. NoteSession.load reads answer fields directly with no whitelist (NoteSession.qml:252-300). Provider-script answers reach the host unfiltered (onenote.py:1381, 1387 out(dict(result, ..., markdown=True))). docs/technical-requirements.md:101: 'change it additively, never silently'.

### Ideas to keep from the losing designs

- guardian: the Python timeline codec services/markdown/timeline.py. read() runs on parse.py (mistune), and write() builds editor-dialect HTML and returns qthtml.convert(html)['note'], so the canonical form is the editor's own fixpoint with no second escaper. JS TimelineModel.js holds only model operations and mirrored limits, pinned equal in tests/test_regressions.py.
- guardian: name the field `noteType`, and read a per-note type only from providers that declare noteTypes. An invalid declaration falls back to legacy with one diagnostic in Workspace.addProvider, never from a binding.
- guardian: NoteTypes.opened(capabilities, answer) as a pure, prototype-free decision function for legacy, absent, unknown and undeclared types.
- guardian: requestBody(document, callback) converts the given snapshot rather than live state. A timeline's snapshot body is a deterministic JSON form, so isStored is exact without conversion.
- guardian: fix mdtext.py:27 LINE_START to [-+*](?=\s|$) as a prerequisite, with qthtml CASES and test_regressions cases. Verified at HEAD: a '+' paragraph cannot be saved today.
- guardian: a later conversion goes only through an explicit, feature-detected setNoteType(path, noteType, cb). Saves never carry or change a type.
- guardian: one shared summary helper (timeline.summary) used by list.py and the save answer, bounded to a 64 KiB whole read; displayTitle shows 'Untitled timeline' for untitled timelines.
- guardian: conflicting or malformed note-note-type lines are UNREADABLE and open read-only with a reason. A provider may declare timeline only if its save stores the body byte-for-byte and it is not merge-aware.
- guardian: release the prerequisites on their own (1.0.41), and land the local marker reading before any UI can create a timeline.
- product: keep the core type table in a pure .pragma library (services/notes/notetypes.js) readable by sidebar.js, Capabilities and WorkspaceActions. On a body switch, move focus to the new body and clear the hidden one (no stray undo stack or recording).
- product: Qt runs specific Keys handlers (onDownPressed, onReturnPressed, onEscapePressed) before onPressed (verified on Qt 6.11.2). Timeline list keys therefore go through one onPressed that calls host.shortcut first.
- product: Ctrl+Alt+N is the documented override example (docs/commands.md:145) and a test fixture (tests/ShortcutChecks.js:53-63, tests/extensions.qml:143). Move them, or pick another default.
- product/architect: Object.assign for local's save-commit entry. Remove OneNote's unread per-page markdown=True and the built-in markdown bools.
- product: keep the add/edit form's text out of ListView delegates, which virtualisation can destroy.
- guardian/product: a status line naming how many events a check or uncheck changed, undoable in one step.

### Guidance for the synthesis

Build on architect's structure:
- NoteEditor stays the pane, with document objects through the session protocol (setNote(document, shown), clearNote(), restoreDocument returning a refusal, snapshotDocument(), requestBody).
- The rich/plain TextEdit stays permanent behind a documentBody adapter.
- Typed bodies load in a Loader with bodyHost.
- documentActive gates EditorApi.writable, applyReadOnly and paste/undo.
- countText for the ViewBar, and formOpen beside tools.panelOpen in handleShortcut and WorkspaceActions.blocked.
- One type-agnostic creation action routed through the provider's own newNote footer action with options.
- No plugin kind; record the trigger and the 2c5920f template.

Replace architect's codec and contract details with guardian's:
- Name the field noteType everywhere, as a single concept: drop documentType unless the user chooses an editable-Markdown fallback.
- Read per-note types only from providers that declare noteTypes.
- Capabilities.of in services/notes/capabilities.js as the only capability reader. Built-ins drop the markdown bool; hello keeps it.
- NoteTypes.opened as the pure decision function.
- The Python codec services/markdown/timeline.py: read on parse.py, write through qthtml.convert. Plain title paragraph plus one description paragraph in v1. Bounded, failing closed. Reached via Markdown.qml toTimeline/fromTimeline and imported lazily by local list.py and operations.py.
- A JSON snapshot body, and requestBody(document, cb) converting the snapshot.

The type table is services/notes/notetypes.js, a pure table naming each body file under ui/notetypes/<id>/. ui/notetypes/NoteBody.qml is the only QML contract. Drop architect's QML registry and runtime apiVersion checks.

A timeline whose text is not in timeline form, and unknown or undeclared types, open read-only with the reason. Offer guardian's editable fallback only as a user decision.

Local follows guardian's D13:
- notefile.py owns note-note-type, written only at creation; UNREADABLE for conflicting lines; an 8th N field.
- A 64 KiB summary via the shared helper.
- Explicit load mapping, and Object.assign for the save commit.

The list draws a glyph from the type table, and the preview is the shared summary string. No progress row field and no 10-field record.

Commands:
- One newNoteOfType action plus commandPalette.pick; no addEvent registry action.
- Ctrl+Alt+N only together with moving the docs/commands.md:145 example and its test fixtures.
- The host footer chooser is an explicit user decision that amends providers.md:185; the default is off in v1.
- Contract: a provider declaring two or more creatable types forwards options.noteType from its newNote footer action. Test it with hello and local.

Never route typed creation through createTargetFor; guardian's bug is verified.

The working tree is moving. Uncommitted fixes for F1, F2 (session.whenSaved), F5, F6, F8, F12, F14 (stored is now a single {path, document}), F15 (readOnly bound) and F21 exist, and F20 is in progress (CODE-REVIEW-2026-10-11.md:9-25). F20 changes setNote's callback to shown(ok, unkept) and adds the provider flag storesMarkdownVerbatim, read directly in NoteSession.load and set on local. So:
- Phase 0 = land those, plus F17, plus the mdtext '+' fix, then release 1.0.41.
- Fold storesMarkdownVerbatim into Capabilities.
- Merge shown(ok, unkept) into the pane's shown(ok, refusal).

Phase order after that:
1. Contract and capabilities (no visible change).
2. The pane seam (no behaviour change, all suites green).
3. The codec.
4. CheckMark extraction.
5. The timeline body and type table.
6. Local marker, typed creation and list, then release 1.1.0.

Implementation rules:
- All timeline list keys in one Keys.onPressed that calls host.shortcut(event) first.
- Form text kept outside ListView delegates.
- Restore the scroll on array-model swaps (engine-notes.md:42-45).
- Focus a Loader item via onLoaded and Qt.callLater (engine-notes.md:55).
- Every if/else/for/while braced, with bodies on their own lines.

Tests follow guardian's D17, plus architect's capability, fake-editor and hidden-document-inert cases. Docs follow architect's D18 (docs/note-types.md), with the timeline grammar linked from providers.md and a security.md codec entry.

Explicitly drop:
- product's per-type footer rows and footer shortcut words, progress row field, save options.noteType, and verify-then-strict-retry writer;
- guardian's per-function documentType switches, per-type actions and createTargetFor route;
- architect's JS escaper, local timeline_summary twin and trailing-space canonical form.

## Judge: safety

_Lens:_ DATA SAFETY AND COMPATIBILITY: can any path lose, duplicate or corrupt a note (unknown/disabled types, older app versions, outside editors and sync tools, non-canonical bodies, merge/conflict, drafts and recovery, provisional notes, row/load mismatch); do external providers written against today's contract keep working; is parsing bounded and fail-closed; is each guarantee pinned by a test. Decisive claims re-run against a clean `git archive e2cdc4e` copy at scratchpad/judge-safety/head (the working tree has uncommitted edits by another process). The judge scripts are in scratchpad/judge-safety/.

**Overall winner:** guardian

### Scores

#### guardian: 8.5/10

Strengths:
- Its canonical body is produced by the editor's own writer (qthtml.convert of editor-dialect HTML). Verified: the golden body is a byte fixpoint both in pure Python and through real Qt (judge-safety/verify_qt.py). With the one-character mdtext fix, its prototype re-run at HEAD gives 0 failures in 3000 models (read(write(m))==m, pure fixpoint, unkept empty), changes none of the existing qthtml CASES, and changes none of 8 Qt samples (judge-safety/g/proto_fixed.py).
- It found a live Markdown-editor bug and verified it: at HEAD a paragraph that is exactly '+' cannot be saved (mdtext.py:27 LINE_START misses `+` at end of line, and STRICT has no `+`). It fixes this in P0. Unfixed, its corpus fails 6 times in 3000, every one a lone-'+' description, and every failure is fail-closed.
- It reads through the shared mistune parser (parse.py). Anything that is not plain text inside task items (links, emphasis, HTML, hard breaks, nesting) falls back to the existing Markdown path instead of being rewritten. Soft breaks read as spaces, as every renderer shows them (verified: 'Pack the\n  bags' reads as the title 'Pack the bags').
- It reads the per-note noteType only from providers that declare noteTypes, so legacy providers cannot be affected. The name is collision-free: no `noteType` exists at HEAD. noteType (what the provider stores) is kept apart from documentType (what the editor holds), so a Markdown-fallback snapshot never claims to be a timeline.
- Unknown types and known-but-undeclared types both open raw and read-only. A local marker with conflicting or malformed values reads as UNREADABLE and opens read-only. Only create writes the marker, never a save, and a test pins that it survives byte-exact.
- requestBody(document, cb) converts the snapshot it is given, not the live editor state. That removes the implicit 'call this synchronously right after snapshotDocument' coupling.
- 'timeline' requires 'markdown' in a declaration, so the fallback can always be stored. An explicit rule says an external provider may declare timeline only if its save keeps bytes and it is not merge-aware.
- The data-loss fixes (lone '+', F1, F2/F21, F17, capability defaults) ship alone as 1.0.41. The codec lands with its property tests before any UI can write.
- It has the most data-specific test pins: marker byte-exact across saves; foreign front matter with tags, CRLF and BOM; conflicting markers; unknown ids reported verbatim; JS/Python limit equality; the Qt leg.

Weaknesses:
- Typed creation bypasses the provider's footer action. In local notebook-tab mode with no open note, createTargetFor('') returns the last notebook (plugins/org.note-note.local/Provider.qml:265), while the provider's own New Note uses the open tab's section (:277). A timeline is then filed in another notebook and the host switches tabs to it.
- Text typed into the add form lives outside the note and is dropped when the note changes.
- Default Ctrl+Alt+N is exactly the override example in docs/commands.md:145. User bindings outrank defaults (resolve.js:8, 300 > 200), so users who copied that example lose the new default to a 'conflicts with' diagnostic (resolve.js:226-249).
- The Markdown fallback is editable, so its safety rests on the provider's Markdown round-trip check. That holds for local through unkept (operations.py:118). For other providers, its own declaration rule covers it.
- The codec is an async Python process on every open and every save. It depends on the F2/F21 fix, which it schedules first.

#### product: 6.5/10

Strengths:
- It reads through mistune and refuses formatting, links and HTML in events, so it fails closed. Verified with its prototype at HEAD: links and emphasis give 'formatting in an event title'.
- write() re-reads its own output and refuses on any mismatch, after one strict retry, so a wrong body is never written.
- Old-editor compatibility holds. On 2000 random models through the HEAD editor round trip: 0 cannot-save cases, 0 read-only regressions, 0 changed events (judge-safety/product_fixpoint.py). Its codec tests include this compatibility property.
- Text typed into the add-event form is part of the note, so it survives a note switch, a window close or a crash.
- Creation stays inside the documented contract (providers.md:185, :204). The provider's own footer action computes the target.
- Per-note field `noteType`; unknown types open read-only; the type travels in every snapshot. Ctrl+Shift+T avoids the documented Ctrl+Alt+N override.

Weaknesses:
- Its D2 filters declared ids down to the ones the host knows, so the provider's default type silently becomes the first known one. A provider that declares ['kanban','markdown'] gets its untyped notes opened as editable Markdown, the lossy path its own D3 rejects.
- It misses the lone-'+' writer bug. A description paragraph whose first line is '+' cannot be written ('the timeline could not be written as it is', judge-safety/lone_plus.py; 8 of 2000 random models refused). Because a note being composed is part of the document, saves fail while the user types it. Drafts are in memory only.
- Its canonical form is not the editor's form. Every save by an older app drops the blank lines between events (verified through Qt), so files churn between versions.
- It normalises foreign content on the next save. A soft-wrapped title is split into title and description: verified, 'Pack the\n  bags' is saved as '**Pack the**' plus 'bags'. Top-level paragraphs after an event are absorbed into its description. Leading NBSP indentation is stripped.
- Save options carry an 'informational' noteType that the D5 plan later makes authoritative. A stale draft could then change a note's type.
- The listing reads whole timeline files up to 2 MiB and runs mistune on each, against the 10 s deadline (list.py:66). That risks partial listings. Progress fields in rows change on every check, and F10 (a rename field losing its text when rows rebuild) is not fixed.
- Ctrl+Enter is bound to addEvent in the 'workspace' context, which also covers a Markdown note's title field (Workspace.qml:2175).

#### architect: 4.5/10

Strengths:
- The type travels inside every snapshot: drafts, recovered drafts, deletion recovery and stored entries. isStored compares it, and no path-keyed type map is needed.
- Timeline saves are serialised synchronously in JS, so the F2 race (a row action overtaking an async conversion) cannot reach them.
- One capabilities.js normaliser fixes the absent-hasTitle binding at Workspace.qml:2843.
- Typed creation goes through the provider's own New Note footer action, so local notebook-tab mode files the note in the right section.
- The gating of the hidden TextEdit is the most complete: EditorApi.writable, applyReadOnly, flick visibility and the paste/pastePlain/undo/redo guards that IPC can reach.
- Unknown and ill-formed types open read-only as plain text and nothing is written. F1 and F17 are fixed first, and F10 alongside.

Weaknesses:
- Its D8 fixpoint and old-version claim is false at HEAD. The architect's own escapes.py prints ERROR for heading, list, ordered and plus description lines. Of 2000 models from its own serializer, the HEAD editor cannot save 65, and its reader refuses 324 after an older app saves them (judge-safety/arch_fixpoint.py).
- Its line-pattern reader turns foreign links, emphasis, HTML and soft wraps into escaped literal text on the first unrelated check. Local read also skips unkept for timeline notes.
- The per-note field is named `type` and is honoured for providers that never declared noteTypes ('A provider may report a type it does not declare'). That is a silent change for any external provider already sending a `type` key (technical-requirements.md:101). No built-in sends one (grep at HEAD).
- The add/edit form is cancelled when focus leaves it, losing the typed text.
- No status line tells the user when one action unchecks many events or deletes one.
- The registry lookup is not specified as prototype-free, yet 'constructor' passes its core-id grammar [a-z][a-z0-9-]{0,31}.
- Its default Ctrl+Alt+N is the override example in docs/commands.md:145.
- Its tests pin the editor fixpoint only for golden bodies, which would not catch the regressions above.

### Winner per decision point

| D | winner | why | amendments |
|---|---|---|---|
| D1 | guardian | `noteType` appears nowhere at HEAD, while `type` is generic. NoteSession.load reads a fixed set of answer fields today (NoteSession.qml:246-300), so any field the host starts to interpret must be opt-in. Guardian reads per-note noteType only from providers that declare noteTypes. It also separates noteType (stored) from documentType (what the editor holds), so a fallback snapshot never claims timeline form. The architect honours `type` even from providers that declared nothing. | Keep the qualified '<package-id>/<local-id>' grammar for future package types. Pin the JS and Python id grammars with the same test strings (architect). User labels: 'Plain text', 'Note', 'Timeline'. |
| D2 | guardian | One Capabilities.of normaliser holds every default and fixes the undefined hasTitle binding at Workspace.qml:2843. An explicit noteTypes wins over `markdown` (the canReorder precedent). An invalid declaration falls back to legacy, with a one-time diagnostic in addProvider rather than in bindings, so the noise gates stay quiet. 'timeline' requires 'markdown', so the fallback can always be stored. Unknown-but-valid ids stay declared, so a provider's default is never replaced. Built-ins keep `markdown` for hosts older than 1.1.0. The product drops unknown ids and so changes the default, which opens untyped notes of an unknown type as editable Markdown. | Refuse to create a type the registry does not know (architect) rather than create a note that opens read-only. State in providers.md and the skill that per-note noteType is read only from providers that declare noteTypes. |
| D3 | guardian | The load answer is the authority. Rows are display only, through Capabilities.rowType, which leaves out default, invalid and legacy values, so the JSON comparison of rows (Workspace.qml:1349-1362) does not churn. Unknown ids and known-but-undeclared ids both open raw and read-only with a reason. Lookups are prototype-free, and nothing is written to reconcile a mismatch. The architect opens undeclared types editable. | Name the id in the reason only when it matches the grammar, cut to 64 characters and shown as plain text. Document the rule in providers.md and the skill mirror in the same commit. |
| D4 | product | Typed creation goes through the provider's own footer action, so the provider computes the target. That keeps providers.md:185 ('does not add creation buttons') and :204 ('Providers choose their own target') intact. Local uses 'section:'+sectionKey (Provider.qml:277). Guardian's host-direct newNote('', undefined, 'timeline') instead falls back to createTargetFor(''), which returns the last notebook (Provider.qml:265) and misfiles a timeline in notebook-tab mode when no note is open. The architect's chooser targets correctly but amends the contract with a control drawn by the host. options are always passed, and two-argument create providers ignore them. | Add guardian's rule: a provider creates exactly the requested type or answers {error}, never another type silently. The host checks Capabilities.supports(provider, type) before it calls create. Contract text: a provider that answers create with a provisional note reports the requested noteType in that note's load answer and rows, and keeps it across notePathChanged. Providers without a typed footer row fall back to newNoteDestination filtered by type. '+ New note…' rows stay the default type. |
| D5 | guardian | Conversion comes later, as a separate operation the host feature-detects: setNoteType locally, a 'retype' that rewrites only the marker line behind the mutation queue. A save never carries or changes a type, so a stale draft can never undo a conversion, and every marker on disk was written by create, which is testable. The product and the architect would let ordinary saves change a note's type. | Offer only lossless directions (architect/guardian): Markdown to timeline only when the codec's read accepts the body without changing its bytes. |
| D6 | guardian | NoteEditor stays the pane, so about 50 Workspace references, the notices and the conflict review stay valid. The rich editor stays permanently, so canColorText and tools.actions do not change. The type is the first argument of setNote and part of every snapshot. An unknown documentType throws, which the noise gates catch. requestBody(document, cb) converts the given snapshot, which removes the hidden ordering coupling between flushSave's snapshot and its conversion (NoteSession.qml:478-493). | Take the architect's full documentActive gating: EditorApi.writable, applyReadOnly, flick visibility, and the paste/pastePlain/undo/redo guards that IPC reaches. Take the product's rule that switching bodies clears the inactive one: recording, undo stack, pending edits. bodyFocused stays the TextEdit's focus, so a focused timeline is the 'workspace' context. |
| D7 | guardian | Core types belong to the app, in a prototype-free registry; provider ids are untrusted, and 'constructor' passes the architect's grammar. With no plugin kind, a user cannot disable the editor of their own notes. A note of an unknown or disabled type opens raw and read-only, and its marker is never touched. | Record in decisions.md the architect's trigger and the commit-2c5920f template for a future 'noteTypes' kind. Package ids stay qualified, and core types cannot be removed. |
| D8 | guardian | Verified at HEAD. The canonical form is the editor's own fixpoint, pure and through Qt. With the mdtext fix, 0 of 3000 models fail and 0 of 8 Qt samples change. Reading through parse.py accepts only events that are plain text to mistune, so anything else falls back rather than being rewritten, in line with decisions.md:669 ('What decides it is the round trip'). The architect's line-pattern reader rewrites foreign formatting, and its fixpoint claim fails (65 of 2000 cannot be saved by the HEAD editor; 324 of 2000 become read-only after an older app saves them). The product reads through mistune, but it splits soft-wrapped titles, absorbs top-level paragraphs, strips NBSP indentation, and refuses lone-'+' descriptions. | Land the mdtext LINE_START fix first: it is a live bug in today's Markdown editor. Add the product's self-check to write(): re-read the output, refuse on any mismatch. Keep the 8 MiB stdin cap, the framed answers, single-paragraph descriptions and no bold titles. Multi-line descriptions come later as an additive grammar change, and only once the old-editor property holds for them. |
| D9 | guardian | Check-above and uncheck-below are pure functions. States out of order are shown exactly as stored, marked '· not in order', and never repaired without a user action. Each action is one undo step, up to 200. A status line appears whenever more than one event changes, which is the mitigation for a mis-click that unchecks many events and is saved 500 ms later. The architect has no such line. | Use the product's wording that names the range ('Unchecked 4 events, from “Pack the kitchen” down') and the delete status 'Deleted “…” · Ctrl+Z brings it back'. |
| D10 | product | It is the only design where text typed into the add form can never be lost. The event being composed is part of the document, so a note switch, a window close or a crash keeps it. Compose mode does not end on blur, and Esc discards with one undo step. The architect cancels the form when focus leaves, losing what was typed. The guardian keeps the text only until the note changes. | Under the guardian codec, a composing event enters the snapshot only once its title is non-empty. Descriptions are one paragraph: no Shift+Enter line breaks, and pasted breaks become spaces. Keep the formOpen gates on handleShortcut and WorkspaceActions.blocked. Keys as in the guardian/architect lists. |
| D11 | guardian | One Python summary helper serves both the listing and the save answer, so the two never disagree. Whole reads are bounded to 64 KiB, which keeps the listing's 10 s deadline and byte budget safe (list.py:13-21, :66); the product reads up to 2 MiB per timeline. An untitled timeline is listed as 'Untitled timeline', not as words from its progress text. The glyph appears only for non-default types. | Take the product's live progress for the open note, read from the editor (display only). |
| D12 | guardian | Same matrix as the others: local and hello hold timelines, OneNote and Notion are deferred, Sticky Notes is unsupported. It adds the one rule protecting providers the project does not control: declare 'timeline' only if save keeps the body byte for byte and the provider is not merge-aware. | Leave OneNote's unread per-page markdown:true alone in this feature, to avoid unrelated churn. |
| D13 | guardian | 'note-note-type:' stays an unowned extra line that every save writes back verbatim (notefile.py:48-67, operations.py:136). It is written only at create. Conflicting or malformed values read as UNREADABLE and open read-only. unkept still judges every note with a Markdown body at read (operations.py:118), so a timeline-marked file that holds raw HTML stays read-only; the architect drops this check for timelines. Both Provider.qml traps (load at :509-511, save commit at :548-549) carry noteType explicitly. | type_line raises on an invalid id (architect). Reconcile with the uncommitted F20 work that moves unkept into the converter frame: whichever lands, a timeline-marked note must still be judged by a round trip. |
| D14 | guardian | The type lives inside every snapshot (drafts, recovered drafts, deletion recovery, stored) with no path map. isStored compares documentType, title and body. A deterministic JSON form makes no-op detection exact. A failed conversion is framed, so the draft is kept. No type travels on save, and merge-aware providers are excluded in v1. | none |
| D15 | guardian | newTimeline and addTimelineEvent are WorkspaceActions whose availability follows state. addTimelineEvent has no global key; Ctrl+Enter works only inside the view. That avoids the product's 'workspace'-context Ctrl+Enter, which also fires from a Markdown note's title (Workspace.qml:2175). | Do not default to Ctrl+Alt+N: docs/commands.md:145 documents {"command": "app/newNote", "keys": ["Ctrl+Alt+N"]}, and user bindings outrank defaults (resolve.js:8, 226-249). Use Ctrl+Shift+T (product), or change that docs example in the same commit. |
| D16 | guardian | Before any type exists, it fixes everything on the feature's paths that can lose or strand data: the verified lone-'+' writer bug (mdtext.py:27), F1 (high), F2/F21 (needed because its codec is async), F17, the capability defaults and F13. They ship as 1.0.41. | Add F10 (architect): every check is a save that rebuilds the rows and wipes an open rename field. Rebase on the working tree, where CODE-REVIEW-2026-10-11.md 'Fix progress' shows F1, F2, F14, F15 and F21 code-done and F20 in progress, all uncommitted. Do not re-implement them, and adapt D13/D14 to F14's single {path, document} stored and F20's converter-frame unkept. |
| D17 | guardian | Every guarantee has a test at the lowest level that can see it. The 3000-model property test includes the editor fixpoint for every model, plus a Qt leg, accepted and refused variants with reasons, limits on read and write, and CLI framing. Local cases cover marker byte-exactness across saves, foreign front matter (tags, CRLF, BOM), conflicting markers, unknown ids reported verbatim and the create refusal. JS/Python limit equality is pinned. The architect pins the fixpoint only for golden bodies, which would miss the 16% read-only regression measured here. | Add the product's compatibility property: read of the old-editor round trip of write(e) equals e, over the whole corpus plus Qt samples. Add a replacePath/provisional typed-draft session case. Register the codec selftest and the timeline suite in both runners after F17. |
| D18 | guardian | It documents the data invariants: the marker is written only at create and never by a save; unknown types open raw and read-only; the codec is a decoder of hostile input, recorded in docs/security.md. providers.md and its skill mirror change together, and business goal 3 is restated. | Change the docs/commands.md:145 example if any Ctrl+Alt+* default is added. Add the provisional-note rule and 'noteType is read only from providers that declare noteTypes' to providers.md and the skill. |
| D19 | guardian | Data-loss fixes ship alone as 1.0.41. Then the type plumbing, with no visible change. Then the codec and its property tests, before any UI can write. Then the local marker, while local still declares only markdown, so a hand-written marker opens raw and read-only. Then the UI and 1.1.0. Every phase is safe to ship. | none |
| D20 | guardian | It has the most complete register of data risks, each with a tested mitigation: older versions, outside edits, normalisation on the first save, last-writer-wins, the 4 KiB listing head, the 2 MiB limit against a maximal timeline, the hidden editor, JS/Python drift, form text, uncheck surprise and noteType collision. | Add two risks: the misfiling if typed creation bypasses the provider's footer action, and the documented Ctrl+Alt+N override example. |

### Fatal flaws

- **architect**: D8 claims 'the canonical form is a fixpoint of the app's Markdown round trip ... (verified at HEAD), so a timeline opened by 1.0.40, or one that has lost its type line, is an ordinary editable checklist.' This is false for general content. The HEAD Markdown editor cannot save hard-broken description lines that start with -, #, 1., '+ x' or ---. After the editor saves '+', '*', '1.', '1)' or '|' unescaped at a description line start, the architect's own reader refuses the note. Everything fails closed: 0 events were changed. But the compatibility guarantee, its D20 mitigation and its golden-only D17 pin are all wrong.<br>_Evidence:_ The architect's designs/architect-exp/escapes.py, run on a clean HEAD copy, prints 'ERROR the document cannot be saved without changing its text' for 'heading desc', 'list desc', 'ordered desc' and 'plus desc'. scratchpad/judge-safety/arch_fixpoint.py feeds 2000 models from the architect's own serializer (architect-exp/proto.py) through to_markdown(to_html(b)) at HEAD: 173 byte fixpoints, 65 the editor cannot save, 324 refused by the architect's reader after the editor's save (e.g. '  |> …' left unescaped), 0 with changed events.
- **architect**: D8/D13 choose lossy normalisation of foreign content and remove the safety net. The reader decides by a list of line patterns. It treats inline Markdown and HTML written in another tool as literal text and escapes it on the next save, and local read skips unkept for timeline notes. One unrelated tick destroys links, emphasis and inline HTML in other events, and turns a soft-wrapped title into a title plus a description. This breaks 'when in doubt, open read-only' and 'what decides it is the round trip, not a list of block types'.<br>_Evidence:_ scratchpad/judge-safety/arch_foreign.py runs the architect's prototype at HEAD. Ticking only event 1 of '- [ ] **Read [the guide](https://example.com)**\n- [ ] **Buy *fresh* bread**' writes '\\[the guide\\](…)' and '\\*fresh\\*'. mistune's inline tokens go from strong, link, strong, emphasis to strong, strong. '<b>this</b>' becomes '\\<b>this\\</b>'. 'Pack the\n  bags' is saved as '**Pack the**  \n  bags'. Rules broken: docs/README.md:40-41; docs/decisions.md:660-676; docs/business-requirements.md:29-34. The architect's D13 says: 'lost = unkept(body) if note_type == markdown else []'.
- **product**: D2 drops declared ids the host does not know before choosing the default type ('noteTypes(provider) filters to known ids ... else the legacy derivation'), and D3 makes an untyped note take the provider's default. A provider that declares ['kanban','markdown'] has its untyped kanban notes opened as editable Markdown and rewritten by the Markdown writer. That is the very path the product's own D3 rejects ('opening unknown types as editable Markdown (a future type's body may not survive the Markdown writer)'). It is a forward-compatibility route to lossy writes for unknown types.<br>_Evidence:_ From the product's own decisions: D2 ('filters to known ids, de-duplicates, caps at 16, else the legacy derivation'), D3 ('absent means the provider's default') and D3's rejected alternative. Contrast: the guardian keeps unknown-but-valid ids and validates only the grammar, and the architect keeps them declared ('such notes open read-only'). Both therefore open such notes read-only.

### Ideas to keep from the losing designs

- From architect: send typed creation through the provider's own footer action, so the provider computes the target. Local notebook-tab mode needs 'section:'+sectionKey (Provider.qml:277), not the last-notebook fallback of createTargetFor('') (:265).
- From architect: the full documentActive gating list for the hidden TextEdit: EditorApi.writable, applyReadOnly, flick visibility, and the paste/pastePlain/undo/redo guards that IPC can reach.
- From architect: fix F10 alongside local timelines (every check is a save that rebuilds the rows). Refuse to create types the registry does not know. type_line raises on an invalid id. Record the plugin-kind trigger and the commit-2c5920f template.
- From architect: pin the JS and Python note-type id grammars with the same test strings.
- From product: the event being composed is part of the document, so typed text survives a note switch, a close or a crash. Under the guardian codec it enters the snapshot once its title is non-empty.
- From product: write() re-reads its own output and refuses on any mismatch. Add the compatibility property test: read(old-editor round trip of write(e)) == e over the whole corpus.
- From product: Ctrl+Shift+T for New Timeline, which avoids the docs/commands.md:145 Ctrl+Alt+N override example. Live progress for the open note, read from the editor. Clear the inactive body (recording, undo stack) when the type switches.
- From product: a status line naming the range when one action changes several events, and a 'Deleted “…” · Ctrl+Z brings it back' status for deletes.

### Guidance for the synthesis

Build on the guardian design. It is the only design whose central data claims survived re-running at a clean HEAD (scratchpad/judge-safety/*).

1. P0, release 1.0.41. Before any type code:
   - Fix mdtext.LINE_START to [-+*](?=\s|$). Add the qthtml CASE 'a lone plus sign is text' and a test_regressions case beside :422.
   - Fix F1, F2/F21, F17 and the capability defaults through services/notes/capabilities.js, plus F10.
   - First reconcile with the uncommitted working tree. CODE-REVIEW-2026-10-11.md 'Fix progress' marks F1, F2, F14, F15 and F21 code-done and F20 in progress. Commit or adopt those rather than re-implementing them, and fit D13/D14 to F14's single {path, document} and F20's converter-frame unkept.

2. Contract, additive under apiVersion 1:
   - Provider property noteTypes, default first. Keep unknown-but-valid ids. 'timeline' requires 'markdown'. Built-ins and docs keep `markdown` for older hosts.
   - Per-note noteType on note rows, sections[].notes and the load answer, read only from providers that declare noteTypes. Load is authoritative; rows are a display hint through rowType.
   - create(target, cb, {noteType}) is always passed. A provider creates exactly that type or answers {error}.
   - A provisional note reports its requested type and keeps it across notePathChanged.
   - Never send the type on save. Later conversion is a separate, feature-detected setNoteType/retype.

3. Codec (services/markdown/timeline.py):
   - Read with parse.py and structural validation: plain text and softbreaks only (a softbreak is a space); at most one description paragraph; no bold, links or hard breaks.
   - Write by building editor-dialect HTML and returning qthtml.convert(html)['note'], then re-read and refuse on mismatch (product).
   - 8 MiB stdin cap, framed JSON, limits enforced on both read and write.
   - A refusal falls back to the Markdown path, whose editability stays the round-trip verdict (unkept/F20).
   - Reject the architect's JS line-pattern codec and its 'inline Markdown becomes literal' policy. Reject the product's soft-break title split, paragraph absorption and NBSP stripping.

4. Pane:
   - Guardian's documentType protocol: setNote(documentType, title, body, shown), clearDocument(), snapshots {documentType, title, body, base}, requestBody(document, cb) converting the given snapshot, isStored comparing documentType.
   - Add the architect's documentActive gating list and the product's clearing of the inactive body.
   - formOpen gates handleShortcut and WorkspaceActions.blocked.

5. Unknown or undeclared types open raw and read-only with a reason, using prototype-free lookups. A local marker that is conflicting or not an id reads UNREADABLE and opens read-only. The marker is written only by create.

6. Creation:
   - A provider-supplied 'newTimeline' footer action and footer shortcut (product), so the provider computes its target.
   - A workspace action newTimeline on Ctrl+Shift+T plus the palette command. addTimelineEvent has no global key.
   - providers.md:185 stays unamended.

7. Form: the composing event becomes part of the document once it has a title. Esc discards with one undo step. A status line for multi-event changes and deletes.

8. Local:
   - Guardian D13: an unowned extra line; unkept kept at read; noteType carried explicitly through Provider.qml :509-511 and :548-549.
   - 8th N field, preview read bounded to 64 KiB, one summary helper for both listing and save.

9. Tests: guardian D17 plus the product's old-editor compatibility property (run on the Qt leg too) and a replacePath/provisional typed-draft case. Register everything in both runners after F17.

10. Phasing as the guardian sets it: 1.0.41, then plumbing, codec, local marker, and finally the UI in 1.1.0. Update providers.md and the skill mirror in the same commits, and change docs/commands.md:145 if any Ctrl+Alt+* default is ever added.

## Judge: delivery

_Lens:_ Spec fidelity, user experience, testability and delivery risk: does the plan deliver exactly what the user asked (radio-style circles, check one checks everything above, an 'Add new event' button below, a title + description form, per-note content types for text, Markdown, timeline and future types)? Is it keyboard-complete and consistent with the app's conventions? Can each phase ship on its own and be tested with tests/transitions.qml, tests/EditorKeys.qml and the provider selftests? Are the user decisions the right ones to ask?

**Overall winner:** guardian

### Scores

#### guardian: 7.7/10

Strengths:
- Its codec reads with the shared mistune parser and writes through qthtml's own reader, so canonical text is the editor's fixpoint by construction. The judge confirmed its example round-trips byte for byte with unkept == [] and that its reader refuses hand edits that would not render the same.
- It accepts only text that renders the same: soft-wrapped titles read as spaces; bold, links and trailing paragraphs are refused with a named reason. It never restyles or restructures a user's file.
- Its Markdown fallback opens a timeline whose text has left timeline form as the Markdown it is, with the reason, so the user can fix it in place. Requiring 'markdown' whenever 'timeline' is declared keeps that fallback storable.
- It found a real converter bug. The judge reproduced it: a paragraph or description that is just '+' fails with 'the document cannot be saved without changing its text' (services/markdown/mdtext.py:27).
- requestBody(document, cb) serialises the snapshot it is given, not the live document. The timeline snapshot is deterministic JSON, so no-op detection stays exact.
- Strict declaration rules: legacy providers' per-note fields are ignored, an undeclared known type opens read-only, and a provider may declare timeline only if it stores bodies byte for byte and is not merge-aware.
- The most delivery-safe staging: a 1.0.41 release for the fixes, plumbing with no visible change, the codec before any UI, the local marker read before local declares timelines.
- The strongest test plan for the data layer: seeded property tests through the real writer on both the pure and the Qt leg, refusal tables with reasons, limits pinned equal in JS and Python, host-level creation tests in --standalone.

Weaknesses:
- Typed creation skips the provider footer route. In the default notebook-tab mode with no note open, the timeline is filed in the last notebook, not the open one. This is a fatal flaw: its own claim about the destination is false against the code.
- Descriptions are a single paragraph with no line breaks. That is a reduction of the requested 'description' and is unnecessary: one paragraph per line is also an editor fixpoint.
- No mouse path to create a timeline (palette and shortcut only), and no reorder in v1, so a forgotten middle step cannot be inserted.
- The pane dispatches on documentType inside every editor function. Each future type would touch about nine NoteEditor functions, which goes against the user's plan for more types.
- Ctrl+Alt+N is the documented user-override example (docs/commands.md:145) and is bound to app/newNote in tests/extensions.qml:143.
- Plain titles only, and the progress line is the only cue for the next event. The UX is less rich than product's.

#### product: 7.5/10

Strengths:
- The most complete and conventional UX: hollow, ticked and 'next'-ringed circles on a spine; the 'Add new event' row below; an inline title and multi-line description form where Enter commits and Shift+Enter adds a line; edit in place, Delete with undo, Alt+Up/Down move; typing on the add row starts the form; a note opens scrolled to its next event.
- Discoverable creation that keeps the documented contract: a provider-supplied 'New Timeline' footer row with a newTimeline footer shortcut, Ctrl+Shift+T and a palette command. It lands where Ctrl+N would.
- The list shows host-worded progress from structured {done,total,next}, live for the open note from editor.progress before the save lands, while the generic preview keeps search and the untitled-title fallback intact.
- Asks the right spec-fidelity question the others miss: what a done 'radiobox' looks like (a tick, a radio dot or strikethrough).
- Never loses typed form text, in line with the app's autosave-everything model.
- Its body seam (a textBody adapter plus a TimelineBody) keeps the rich editor permanent and changes few existing test call sites.

Weaknesses:
- Its tolerant reader restructures hand-edited files on the first in-app change: a trailing paragraph is absorbed into the last event, a soft-wrapped title is split, plain titles are bolded. This is a fatal flaw, proven with its own prototype.
- Its canonical form is not the editor's fixpoint: the judge verified that the editor round trip drops the blank lines between events. Writing via mdtext + verify also inherits the lone '+' bug, so such a save is refused.
- Ctrl+Enter is a global 'workspace'-context binding. It also fires from a Markdown note's title field and the list, and shows 'Open a timeline you can edit.' (Workspace.qml:2168-2199; resolve.js:10-12).
- list.py reads whole timeline files up to 2 MiB and runs a mistune parse for every timeline note on every relist (inotify and the 20 s poll).
- Adds noteType to save options as 'informational' API no provider reads, contradicting its own 'no unused API' rule.
- Live compose (saving half-typed events), a ListModel with Column + Repeater at up to 1000 events, and a 10-field N record raise delivery and test complexity.
- One footer row and one workspace action per type does not scale past two or three types.

#### architect: 7/10

Strengths:
- The cleanest extensibility seam for 'other note types in the future'. The pane keeps its role; there is one versioned NoteBody contract, a narrow bodyHost and a permanent document editor behind an adapter. Typed bodies load through a Loader with initial properties (verified warning-free), and the type is activated inside setNote, so the type is always applied before the body.
- documentActive gating is spelled out for EditorApi.writable, applyReadOnly, flick visibility and the paste/undo/redo guards, and has a 'hidden document inert' test.
- Typed creation goes through the provider's own footer action, so the target is correct. A generic chooser (picker over creatable types) scales to future types without a host change per type.
- A complete keyboard model, including an empty timeline opening the add form straight from the title. It also gives the most concrete EditorKeys scenario list (17 cases).
- A pure synchronous JS codec that is trivially unit-tested, plus a cross-language check against mistune and qthtml. Its canonical example is an editor fixpoint with unkept == [] (judge-verified).
- A recorded plugin-kind trigger and the commit 2c5920f template, with qualified package ids reserved.

Weaknesses:
- The JS reader literalizes inline Markdown typed elsewhere, so one check in the app destroys a user's emphasis, links and code spans. This is a fatal flaw, proven with its own prototype.
- An untitled timeline's list title becomes its progress text ('3/7 · Pack the…'), because displayTitle falls back to the preview (Workspace.qml:1305-1324) and the design leaves that fallback unchanged.
- 'Focus leaving the form cancels it' throws away a typed title and description on a stray click.
- Creating a timeline takes two steps (open the chooser, then pick), the chooser is drawn by the host (it amends docs/providers.md:185), and Ctrl+Alt+N collides with docs/commands.md:145 and tests/extensions.qml:143.
- Hard-break descriptions depend on trailing spaces that many editors strip.
- The highest delivery risk: a registry, a Loader, an adapter and a hand-written CommonMark escaper in JS, with a Python twin for previews.

### Winner per decision point

| D | winner | why | amendments |
|---|---|---|---|
| D1 | guardian | noteType names the per-note field on rows, sections[].notes, load and create options, with noteTypes as the provider property. This avoids the row 'kind' versus 'type' confusion and any clash with a 'type' field an external provider may already emit. Guardian reads it only from providers that declare noteTypes. Its separate documentType (what the pane holds) is what keeps the Markdown fallback honest: a timeline note held as Markdown never snapshots as 'timeline'. Core ids stay unqualified, and package ids will be qualified later. | Use product's labels ('Plain text', 'Note', 'Timeline'). Pin one id grammar with identical test strings in capabilities.js and notefile.py (architect). Do not put noteType into save options (product): no provider reads it. |
| D2 | guardian | One normaliser, Capabilities.of(provider) in services/notes/capabilities.js, gives hasTitle !== false, canImages === true, tools, noteTypes and defaultType. The legacy markdown bool maps to ['markdown'] or ['text'] (absent means text, as the HEAD binding does), and an explicit noteTypes wins (the canReorder precedent). An invalid declaration counts as absent and is reported once in addProvider, so no binding spam trips the noise gates. 'timeline' requires 'markdown', so the fallback is always storable. This also fixes the absent-hasTitle binding (Workspace.qml:2841-2844). | Also normalise the in-flight storesMarkdownVerbatim capability (uncommitted F20 work in the working tree), and make a non-array tools fail closed (product). Expose validTypeId and typeOf (architect). Remove OneNote's unread per-page markdown=True (onenote.py:1380-1381, 1387) in the contract commit. |
| D3 | guardian | The load answer alone picks the body; rows are a display hint (rowType '' for the default type, so the JSON row comparison does not churn). Unknown or garbage ids open read-only as raw text with a bounded, quoted id. A known id the provider does not declare also opens read-only. Legacy providers' per-note fields are ignored. A timeline whose text is no longer in timeline form opens as the Markdown it is, with a named reason, so the user can fix it in place. Architect makes it read-only plain text; product makes it read-only rendered Markdown. | The fallback render must go through the in-flight host-side unkept check (setNote's shown(ok, unkept) plus storesMarkdownVerbatim), so a fallback note holding unkept constructs still opens read-only. Use prototype-free lookups so '__proto__' and 'constructor' are simply unknown. |
| D4 | product | The provider supplies a 'New Timeline' footer row with shortcut 'newTimeline'. Its action calls host.newNote(id, target, 'timeline') with the same target rule as New Note (local Provider.qml:275-277 uses 'section:'+sectionKey in notebook-tab mode), so a timeline lands exactly where Ctrl+N would put a note. The documented rule that the host adds no creation buttons (docs/providers.md:185) still holds. It is one click with the mouse, one chord (Ctrl+Shift+T) or one palette command. create(target, cb, {noteType}) follows the additive save-options precedent. Guardian's route skips the footer and misfiles the note; architect's chooser takes two steps and amends :185. | Keep guardian's rule that a provider creates exactly the requested type or answers {error}. Typed newNote with no providerId first calls activateFooterShortcut('newTimeline'), else newNoteDestination filtered to providers that support the type. '+ New note…' rows stay default-type. Record architect's generic newNoteOfType chooser (commandPalette.pick over the creatable types) as the planned path once a third creatable type exists. Add a regression test: Ctrl+Shift+T on a notebook tab with no open note files the timeline in that tab's notebook. |
| D5 | guardian | No conversion in v1, and no save ever carries or changes a type. Every marker on disk is then written by create, which is the simplest invariant to test and is safe for older app versions and sync tools. A later conversion is an explicit, feature-detected setNoteType or retype operation, never a save option. | Add architect's lossless-direction rule to decisions.md: timeline to Markdown is always lossless; Markdown to timeline is offered only when read() accepts the body without changing a byte. |
| D6 | architect | NoteEditor stays the pane, so the ~50 Workspace editor.* references, notices, the conflict review, toolbar alignment and IPC stay valid. Bodies implement one versioned NoteBody protocol. The rich TextEdit stays permanently instantiated behind a documentBody adapter, so canColorText, tools.actions and the toolbar height never change with the open note. Typed bodies load through a Loader with initial properties. The type is activated inside setNote and restoreDocument, so it is always applied before the body. documentActive gates EditorApi.writable, applyReadOnly, flick visibility and paste/undo/redo. It is the only answer where the next type is a folder rather than edits to every pane function; guardian dispatches on documentType in each one. | Use guardian's requestBody(document, cb), which serialises the snapshot it is given, not the live document. Merge the in-flight setNote callback shown(ok, unkept) with the body's refusal into one documented shape and update NoteSession once. Name the held type documentType (guardian), distinct from the note's noteType. Add undo()/redo() to the body protocol so IPC editorUndo reaches the active body (product). Gate handleShortcut and WorkspaceActions.blocked on formOpen only if the form is not part of the document (the D10 user decision). |
| D7 | architect | Core types stay app-owned, behind an internal versioned contract. NoteType holds typeId, label, description, icon, a body url and documentFormat, and NoteBody has apiVersion 1. Types are validated ToolRegistry-style and the registry is static, so loading a note never waits for the plugin catalog. There is no sixth catalog kind now; the trigger and the commit 2c5920f template are recorded in decisions.md. A note of an unknown or disabled type opens read-only, and its marker is never touched. | For v1, a prototype-free .pragma library table (guardian/product notetypes.js) is enough and can be tested in pureCases; keep NoteBody.qml as the contract. Record product's point that a future package type needs a Python-side codec channel, because provider previews run in Python. |
| D8 | guardian | The reader is services/markdown/parse.py (mistune). The writer builds editor-dialect HTML and returns qthtml.convert(html)['note'], so canonical text is the editor's fixpoint by construction; the judge verified guardian's example round-trips byte for byte with unkept == []. It accepts only text that renders the same (blank lines, * and + bullets, [X], CRLF, soft-wrapped lines read as spaces). Anything else is refused with a named reason and falls back to Markdown, so a hand-edited file is never restyled or restructured. Architect's JS reader literalizes inline Markdown and product's reader restructures files; both are proven in the fatal flaws. The CLI is bounded with framed answers, a pure TimelineModel.js handles edits, and the snapshot is deterministic JSON. | Allow multi-line descriptions, stored as one indented paragraph per line rather than guardian's single paragraph. The judge verified that '- [x] Kickoff\n\n  Agree the scope\n\n  Second line\n- [ ] Design\n' is an editor fixpoint with unkept == [] and has no trailing-space hard breaks. Make titles plain by default. Bold titles are safe only when written as Qt's font-weight:700 span: the judge's fuzz run gave 1500 random models, 0 mismatches and 2 refusals, both a lone '+'. Bold versus plain is a user decision. Fix mdtext.LINE_START first. Pin the JS and Python limits as equal in test_regressions. |
| D9 | product | A pure toggled(states, k): checking an unchecked k checks 0..k; unchecking a checked k unchecks k..n-1. What is done is always a prefix ('you are here'). Out-of-order states from other editors are shown as stored and never repaired on open. A status line names multi-event changes ('Checked 3 events, up to “Pack the kitchen”'). Each action is one undo step on Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y, which stroke.js reserves for the focused item. It matches 'check one, check everything above' exactly and is the easiest to unit-test. | Use a 200-step undo cap (architect/guardian). Guardian's '· not in order' progress hint is optional. Uncheck semantics stay a user decision, with this rule as the default. |
| D10 | product | The most complete keyboard-first, modeless view. Unchecked circles are hollow; checked ones are accent-filled with the tick cut out, using a shared check face extracted from NoteEditor.qml:2242-2284. The next event gets an accent ring and a bold title, and the spine is accented between checked events. The 'Add new event' row sits below, in the '+ New note…' look, with an empty state. The inline form has a single-line title (ChromeTextField) and a multi-line description (a new ChromeTextArea). Enter commits, Shift+Enter adds a line, Tab and Shift+Tab move between fields and Escape cancels, which keeps the app's Enter-submits convention. It adds edit in place, Delete with undo, Alt+Up/Down move, typing on the add row to start the form, accessibility roles and objectNames for tests. | Take architect's empty-timeline flow: Enter or Down in the title of an empty writable timeline opens the form. Take guardian's rule that Escape closes the form but keeps its text. Reject architect's 'focus leaving the form cancels it'. Keep Ctrl+Enter a local key of the view, with no global registry binding. Measure Column + Repeater at the event limit, and virtualise if it misses the budget. Whether a half-typed event is part of the saved note (product) or is held by the body and committed when the note changes is a user decision; the default is that typed text is never lost. |
| D11 | product | NoteSummary gains a glyph (only timelines have one) and a host-worded progress line from structured {done, total, next}. The provider's preview stays the generic first line, so search and the untitled-title fallback are unchanged ('☑ Book the van', verified through notefile.preview and displayTitle). The open timeline's row and the view bar update live from editor.progress before the save lands, as unsavedTitles does for titles. With architect's preview text, an untitled timeline's list title would read '3/7 · Pack the…'. | Bound summaries computed while listing to 64 KiB, falling back to the generic preview beyond that (guardian), instead of whole-file reads up to 2 MiB plus a mistune parse on every relist. Compute the summary with the same codec helper in the listing and in the save answer. |
| D12 | guardian | Local notebooks and examples/hello hold timelines. OneNote and Notion stay Markdown-only and Sticky Notes plain text, each for the reasons the provider maps verified. It adds a crisp contract rule: a provider may declare 'timeline' only if its save stores the body byte for byte and it is not merge-aware, unless it proves its merge keeps timeline form. | Remove OneNote's unread per-page markdown flag. Keep architect's later paths: OneNote after a data-id marker is verified live and documented; Notion after the user chooses a marker. hello must keep loading through the legacy directory (tests/standalone_launch.qml:38-40). |
| D13 | guardian | A namespaced 'note-note-type:' front-matter line, written once at creation and only for non-default types, and kept by today's extra-line save path. notefile.py owns TYPE_KEY, note_type and type_line; conflicting or malformed lines open read-only. list.py gains a trailing N field and a summary read bounded at 64 KiB. operations.py create refuses undeclared types. Both Provider.qml propagation traps are fixed, and the selftest list is complete. | Use Object.assign in the save commit so later fields survive (architect/product). If structured progress is adopted, emit done/total/next in the N record (product) under the 64 KiB bound. Add the provider's 'New Timeline' footer row and action('newTimeline'). Rebase on the uncommitted local Provider.qml: the load answer no longer forwards editable or reason, and folderRows is now folderRows(tree, key, level, rows). |
| D14 | guardian | flushSave keeps its order, and the snapshot carries the held type. A timeline's snapshot is deterministic JSON, so checking and unchecking the same event sends nothing. requestBody(draft.document, cb) serialises that exact snapshot through the framed Python writer, and a codec failure keeps the draft. Drafts, recovered answers and deletion recovery restore into the right body with no new path-keyed state. No timeline conflict can arise in v1. | Rebase on the in-flight F14 change: stored is now a single {path, document}. Do not send the type in save options. |
| D15 | guardian | Two workspace actions on the one executor: newTimeline (with a key) and addTimelineEvent (palette only, no global key; Ctrl+Enter is handled inside the view). WorkspaceActions.state gains the held type and editor writability, plus canCreateNote(noteType), reasons, the workspace plugin.json commands, the selftest pin and the commands docs. This avoids product's global Ctrl+Enter, which in the 'workspace' context also fires from a Markdown note's title and shows an 'unavailable' error (Workspace.qml:2168-2176, 2182-2199). | Bind newTimeline to Ctrl+Shift+T (product), not Ctrl+Alt+N: docs/commands.md:145 uses Ctrl+Alt+N as the user-override example, and tests/extensions.qml:143 binds it to app/newNote. newTimeline must go through activateFooterShortcut('newTimeline') first, which fixes guardian's misfiling. Check Ctrl+Shift+T against Omarchy's default compositor bindings. |
| D16 | guardian | The most complete prerequisite list, each item on a path the feature extends: the verified lone '+' converter bug (judge reproduced: a paragraph '+' gives 'the document cannot be saved without changing its text'), F1, F2/F21, F17, capability defaults and F13, with F14 and F15 alongside. | F1, F2/F21 (session.whenSaved, finishRowAction(result \|\| {})), F14, F15 (readOnly: !session.writable) and F20 (unkept from the to-html frame) are already implemented, uncommitted, in the working tree. Land them as their own commits and rebase the plan on them. What remains to plan is F17, the mdtext.LINE_START fix, Capabilities/hasTitle and F13. Recommend F10 (rename field versus row rebuilds), since every check rebuilds rows (architect). |
| D17 | guardian | Each guarantee is tested at the lowest level that can observe it:<br>- seeded property tests through the editor's writer, pure and through Qt;<br>- accepted and refused variant tables with their reasons, limits and CLI framing;<br>- qthtml CASES;<br>- pure JS for TimelineModel, Capabilities and the registry;<br>- fake-editor session cases: type through drafts, recovery, deletion recovery and replacePath; A→B→A races; unknown types;<br>- an EditorKeys 'timeline' suite with the real converter;<br>- local selftests;<br>- test_regressions limit agreement;<br>- the extensions pin;<br>- host-level creation in --standalone.<br>All are registered through F17's single list. | Graft architect's 17 EditorKeys scenarios and its 'hidden document inert' case (Ctrl+B, Ctrl+1 and paste do nothing while a timeline is shown). Graft product's tests that form text is never lost, that progress updates live, and that accessibility roles are right. Add one regression test per proven flaw: Ctrl+Shift+T on an empty notebook tab files the timeline there; inline formatting or a trailing paragraph opens as Markdown and is never rewritten. EditorKeys waits for the Python codec with keys.tryVerify, as it already does for toHtml. |
| D18 | guardian | A complete documentation list, each change in the commit with its behaviour:<br>- providers.md and the skill mirror together, with existing drift reconciled;<br>- a dated decisions.md section;<br>- business-requirements amendments: the non-goal clarified, a per-provider type row, goal 3 restated;<br>- technical-requirements: editor format, row shape, limits;<br>- README, getting-started.md and testing.md;<br>- security.md, treating the codec as a decoder of hostile input;<br>- the metainfo release. | Add product's docs/editing-tools.md line (tools act on Markdown notes only) and the testing.md IPC helpers. Document the internal NoteType/NoteBody contract, either as architect's docs/note-types.md or as a technical-requirements section. |
| D19 | guardian | The most delivery-safe staging:<br>- P0: the prerequisites, shipped as 1.0.41.<br>- P1: plumbing with no visible change.<br>- P2: the codec, before any UI can write it.<br>- P3: the local marker, read while local still declares only markdown, so a hand-written marker opens read-only (safe).<br>- P4: the view, creation, list and docs, released as 1.1.0 (minor, per docs/release-process.md:26-27).<br>Every phase is green in both runners and can ship on its own. | P1 carries architect's pane seam. Split P4 into reviewable commits the way product splits its 2a-2h: the check-face extraction alone, ChromeTextArea, TimelineModel and the view, the pane wiring, creation, the list, hello, the docs. Bump manifest.json and the metainfo release together. |
| D20 | product | Its user decisions are the ones the user can actually judge, and they include the spec-fidelity question the others miss: how a done event looks, given the user asked for a 'radiobox' (a filled circle with a tick, a radio dot, or strikethrough). It also asks about uncheck semantics, the on-disk key, multi-paragraph descriptions, creation surfaces and keys, the list preview, deleting without a dialog, conversion and remote providers later, and the version. | Add guardian's questions: a timeline whose text has left timeline form opens as Markdown; how strictly hand edits are read; 1.0.41 first, then 1.1.0. Add architect's plugin-kind question. Add two new ones: is a half-typed event part of the note, and are titles plain or bold on disk. |

### Fatal flaws

- **architect**: D8 rewrites users' inline formatting as escaped literals. The line-based JS reader accepts inline Markdown typed elsewhere as plain characters, and the serializer escapes them on the next change. One check in Note Note therefore destroys emphasis, links and code spans written in another app. This is a lossy write the project forbids, and it is not said in the UI.<br>_Evidence:_ Architect D8 states that inline Markdown typed elsewhere 'reads as its characters, shows as them, and is written back escaped on the next change'. Reproduced with its own prototype (scratchpad/designs/architect-exp/proto.py, driven by scratchpad/judge/arch_literal.py):
- input: '- [x] **Buy *wool* socks**\n- [ ] Read [the map](https://example.org/map)  \n  Bring `cash`\n' parses as an editable timeline;
- after checking event 2 it writes '- [x] **Buy \\*wool\\* socks**\n- [x] **Read \\[the map\\](https://example.org/map)**  \n  Bring \\`cash\\`\n';
- the mistune token kinds are emphasis, link and codespan before, and none of them after.
This contradicts docs/decisions.md:660-669 ('Read-only rather than lossy writes'; 'What decides it is the round trip'), docs/README.md rule 1 ('When in doubt, open read-only rather than risk a bad write') and business goals 2 and 7 (docs/business-requirements.md:29-31, 39-41).
- **guardian**: D4 and D15 claim that typed creation is 'a host command aimed at the destination Ctrl+N would use'. That is false. newTimeline calls host.newNote('', undefined, 'timeline') and, by design, skips the footer route Ctrl+N takes. In the default notebook-tab mode with no note open, which is the state a tab switch leaves unless the tab remembers a note, the timeline is filed in the LAST notebook rather than the open tab's, and the app jumps tabs.<br>_Evidence:_ - Workspace.qml at HEAD: :1892 sends only untyped Ctrl+N through activateFooterShortcut('newNote'); :1873-1885 newNoteDestination uses p.createTargetFor(root.currentPath).
- plugins/org.note-note.local/Provider.qml at HEAD: :265 createTargetFor('') returns 'section:' + root.notebooks[last].key, while :275-277 action('newNote') uses 'section:' + sectionKey when notebookTabs is on; :58 notebookTabs defaults to true.
- Workspace.qml:1123-1151: setActiveSection calls selectPath('') when switching tabs, so currentPath is '' unless the tab remembers a note.
- Guardian's amended doc text and D15 handler 'newTimeline: host.newNote('', undefined, 'timeline')' encode exactly this route.
- **product**: D8's tolerant reader restructures hand-edited files on the first in-app change. A top-level paragraph after the list is absorbed into the last event's description, a soft-wrapped title is split into title and description, and every plain title is bolded. The text survives, but the file's structure and rendering change without the user asking, which breaks the round-trip rule. Separately, a description line that is just '+' can never be saved (the inherited mdtext bug).<br>_Evidence:_ Product D8 says that 'top-level paragraphs that follow an event ... are its description' and that 'a soft or hard break inside it starts the description'. Reproduced with its own prototype (scratchpad/product/timeline_proto.py, driven by scratchpad/judge/product_restructure.py):
- input: '- [x] Book the van\n- [ ] Pack the kitchen\n- [ ] A long title wrapped\n  onto a second line\n\nRemember to call mum before Saturday.\n' reads as 3 events, event 3 having the description 'onto a second line\n\nRemember to call mum before Saturday.';
- after checking event 2 it writes '- [x] **Book the van**\n\n- [x] **Pack the kitchen**\n\n- [ ] **A long title wrapped**\n\n  onto a second line\n\n  Remember to call mum before Saturday.\n';
- write() of a description '+' raises 'the timeline could not be written as it is' (services/markdown/mdtext.py:27, LINE_START misses a lone '+').
This contradicts docs/decisions.md:660-669. Guardian's reader, run by the judge on the same body, refuses it ('more than one bulleted list of events') and reads the wrapped title as one title.

### Ideas to keep from the losing designs

- (architect) The pane seam: the NoteBody contract (apiVersion 1), a narrow bodyHost, a permanent documentBody adapter over the rich TextEdit, a Loader with initial properties for typed bodies, and documentActive gating of EditorApi.writable, applyReadOnly, flick visibility and paste/pastePlain/undo/redo. The type is activated inside setNote and restoreDocument, so the next note type is a folder plus a registry line.
- (architect) Typed creation always goes through the provider's own action, so the provider picks the target. Record the generic 'New Note of Type…' chooser (commandPalette.pick over the provider's creatable types) as the planned path once a third creatable type exists.
- (architect) Empty-timeline flow: Enter or Down in the title of an empty, writable timeline opens the add-event form at once.
- (architect) The 'hidden document inert' EditorKeys case (Ctrl+B, Ctrl+1, paste and IPC undo change nothing while a timeline is shown), and the 17 named timeline scenarios adapted to an async codec with keys.tryVerify.
- (architect) The plugin-kind trigger (a second non-document core type, a concrete external type wanted, and NoteBody unchanged for a release) and the commit 2c5920f file template, recorded in decisions.md, with package ids qualified as <package-id>/<local-id>.
- (architect) Extract the drawn check face (NoteEditor.qml:2242-2284) into a shared component, in its own commit that changes no behaviour, before the timeline uses it.
- (product) A provider-supplied 'New Timeline' footer row plus a 'newTimeline' footer shortcut vocabulary entry, which keeps docs/providers.md:185 true. Bind Ctrl+Shift+T rather than Ctrl+Alt+N, the documented override example.
- (product) Structured progress {done, total, next}, worded by the host in NoteSummary with a timeline glyph. The generic preview is kept, so search and the untitled fallback are unchanged. The open note's progress is live from editor.progress, and the view bar shows countText.
- (product) Stepper visuals: a ring and bold title on the next event, a spine accented between checked events, a top-down fill on a multi-event check, and a status line naming multi-event changes. A note opens scrolled to its next event. Typing on the add row starts the form. Enter commits and Shift+Enter adds a line. Alt+Up/Down move in v1. A context menu offers Edit, Move and Delete.
- (product) Typed form text is never lost: the form does not close on blur, and its text survives a note switch. Present this as a user decision with that default.
- (product) Ask the user how a done event looks, given they asked for a 'radiobox': a filled circle with a tick, a radio dot, or strikethrough.
- (product) docs/editing-tools.md says tools act on Markdown notes only. Add IPC test helpers (addEvent, timelineToggle) to Workspace and docs/testing.md, and add ui/timeline to the qmllint set.

### Guidance for the synthesis

Build on guardian's contract, data, test and phasing skeleton. Put architect's pane and registry seam in it, and product's user experience on top. Treat the three fatal flaws as amendments that must not survive.

1. Rebase first. The working tree holds uncommitted fixes that change files every design cites at HEAD:
- F1: replacePath aliases.
- F2/F21: session.whenSaved and finishRowAction(result || {}).
- F14: stored is one {path, document} or null.
- F15: readOnly: !session.writable, with updateReadOnly removed.
- F20: Markdown.toHtml answers (html, ok, unkept); NoteEditor.setNote answers shown(ok, unkept); NoteSession applies unkept when provider.storesMarkdownVerbatim; the local load no longer forwards editable or reason.
- Also: services.menus.deleteNote, and local treeIndex/folderRows(tree, key, level, rows).
Land these as their own commits in Phase 0, with F17, the mdtext.LINE_START fix ([-+*](?=\s|$), with a qthtml CASES entry and a test_regressions case), Capabilities/hasTitle and F13. Release that as 1.0.41, then re-derive every line citation.

2. Contract:
- noteTypes on the provider, default first; the markdown bool stays the legacy shorthand (absent means text).
- Per-note noteType on note rows, sections[].notes and the load answer, read only from providers that declare noteTypes.
- create(target, cb, {noteType}) and host.newNote(providerId, target, noteType); a provider creates exactly that type or answers {error}.
- 'timeline' requires 'markdown'.
- capabilities.js normalises everything, including storesMarkdownVerbatim, with one diagnostic in addProvider for an invalid declaration.
- No type in save answers or save options.

3. Authority:
- The load answer decides.
- An unknown or undeclared type opens read-only as raw text, with a bounded, quoted id.
- A timeline whose text is no longer in timeline form opens as the Markdown it is (documentType 'markdown'), with the reason on the status line, and is editable subject to the host-side unkept check.

4. Pane (architect):
- NoteEditor is the pane: NoteBody apiVersion 1, bodyHost, the documentBody adapter, a Loader for typed bodies, documentActive gating.
- Snapshots are {documentType, title, body, base}.
- requestBody(document, cb) serialises the snapshot given (guardian).
- One merged setNote callback shape that carries ok, unkept and a body refusal.
- The registry can be a prototype-free table: label, description, icon, body url, documentFormat.
- No plugin kind; record the trigger in decisions.md.

5. Codec (guardian), services/markdown/timeline.py:
- read() goes through parse.py and accepts only text that renders the same (one task list; blank lines; * and + bullets; [X]; CRLF; soft-wrapped lines read as spaces). Anything else is refused with a named reason.
- write() builds Qt-dialect HTML, <ul><li class=checked|unchecked><p>title</p><p>line</p>…</li></ul>, and returns qthtml.convert(html)['note'].
- Descriptions are multi-line, one indented paragraph per line (judge-verified fixpoint, unkept []), with no trailing-space hard breaks.
- Titles are plain by default; bold, if the user picks it, only through the Qt font-weight:700 span (judge fuzz: 0 mismatches).
- Bounded: 8 MiB stdin, framed JSON answers, event, title and description limits pinned equal to TimelineModel.js.
- Markdown.qml gains toTimeline and fromTimeline. The snapshot is deterministic JSON.

6. Local (guardian):
- A 'note-note-type:' line, written once at create time and only for non-default types, kept as an unowned extra line; conflicting or malformed lines open read-only.
- The N record gains the type and, if structured progress is adopted, done/total/next, computed under a 64 KiB bound.
- The save commit uses Object.assign; the load forwards noteType.
- The provider adds a 'New Timeline' footer row and action('newTimeline') with New Note's target rule.

7. Creation (product):
- The footer row; Ctrl+Shift+T on a newTimeline workspace action that first calls activateFooterShortcut('newTimeline'), else a destination filtered to providers that support the type; a palette 'New Timeline'.
- addTimelineEvent is palette-only; Ctrl+Enter is a local key of the view.
- No Ctrl+Alt+N. Verify Ctrl+Shift+T against Omarchy's compositor bindings.

8. View (product):
- Circles: hollow, then ticked when done, ringed on the next event; a spine; the 'Add new event' row below; an empty state.
- An inline form: a ChromeTextField title and a new ChromeTextArea description. Enter commits, Shift+Enter adds a line, Tab moves, Escape closes but keeps the text. It never cancels on blur.
- Edit in place, Delete with undo, Alt+Up/Down move, a 200-step undo; Space or a click toggles by the prefix rule (check 0..k, uncheck k..n-1); out-of-order states are shown as stored.
- Accessibility roles and objectNames.
- Gate handleShortcut and WorkspaceActions.blocked on formOpen unless the user picks the live-compose model.
- Measure the view at the event limit.

9. List (product, bounded):
- A glyph and host-worded progress; live progress for the open note; the preview stays generic.

10. Tests (guardian, plus grafts):
- Codec property tests on the pure and the Qt leg; refusal tables; pure JS; session cases; the EditorKeys 'timeline' suite (architect's 17 scenarios plus 'hidden document inert', product's form-text and accessibility cases); local selftests; regressions; extension pins; --standalone creation.
- One regression test per fatal flaw: an empty-tab Ctrl+Shift+T files the timeline in that notebook; inline formatting stays untouched; a trailing paragraph is not absorbed.
- Register every suite through the F17 single list.

11. Phases (guardian):
- P0 (1.0.41): the fixes.
- P1: the seam and the contract, with no visible change.
- P2: the codec.
- P3: the local marker, read while local still declares only markdown.
- P4: split into reviewable commits — check face, ChromeTextArea, TimelineModel and the view, pane wiring, creation, list, hello, docs — then 1.1.0, with manifest.json and the metainfo release bumped together.

12. User decisions (each with a default):
- uncheck rule: mirror (uncheck k and below);
- on-disk key: note-note-type;
- done look: filled circle with a tick;
- descriptions: multi-line;
- titles: plain on disk;
- half-typed event: never lost;
- text no longer in timeline form: opens as Markdown;
- reading strictness: renders-the-same;
- creation: footer row + Ctrl+Shift+T + palette;
- editing in v1: edit, delete and move;
- providers: local and hello only;
- list: glyph and progress;
- conversion: later;
- plugin kind: later;
- releases: 1.0.41, then 1.1.0.
