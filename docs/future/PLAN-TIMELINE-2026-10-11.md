# Plan: per-note content types and the timeline note type

> **Review status:** an adversarial review found 76 issues in this plan (11 high, 41 medium, 24 low), listed with corrections in `PLAN-TIMELINE-2026-10-11/review-issues.md`. They have not been applied or independently verified; read them before implementing.

Base: `master` at `e2cdc4e` (app 1.0.40). Written 2026-10-11/12 for the developer who will build it.

Line numbers are HEAD's unless marked **WT** (the working tree, which holds uncommitted
fixes for most findings of `CODE-REVIEW-2026-10-11.md`). Phase 0 commits those fixes first,
so after Phase 0 every later step is applied to the post-fix tree. Find the code by the
function or property named in each step, and use the line numbers to find your place.

Every code sketch follows CLAUDE.md. Every `if`, `else`, `for` and `while` has braces and its
body on its own lines, and there is one statement per line. Where existing code breaks this
rule (one-line function bodies in `examples/hello/Provider.qml`, `tests/transitions.qml` and
local `Provider.qml`), the function is reformatted when this plan touches it.

Commits happen only when the author asks for them (`docs/release-process.md:25`). The
"commits" below are units of review: each one leaves `python3 tests/selftest.py` and `ctest`
green and ships its own docs. After every code change, run `graphify update .`
(`/home/andrei/CLAUDE.md`).

The working tree's `CLAUDE.md` adds a rule: code quality comes first, and a change that would
need a workaround or a hack, or would lower the code's quality, **stops and asks** before going
on, saying what breaks the rule and what the alternatives are. Where an implementer finds
that a step of this plan cannot be done cleanly as written, that rule applies. Ask; do not bend
the step.

---

## 1. Summary

**What the user gets (release 1.1.0)**

- **Every note has a type.** There are three of them:
  - **Plain text**: Sticky Notes. Every newline counts.
  - **Note**: Markdown, rendered. Local, OneNote and Notion.
  - **Timeline**: new.
- **What a timeline is.** A list of events down a vertical line.
  - Each event has a round check in front of it, a one-line title and an optional description of several lines.
  - Checking an event checks every event above it. Unchecking an event unchecks every event below it, so the done events always read as "how far along you are".
  - An **Add new event** row under the list opens an inline title + description form. It is not a dialog. You can also edit, delete, move (Alt+↑/↓) and undo.
  - Everything works from the keyboard.
- **Where timelines live.** Local notebooks, plus the `examples/hello` provider that shows plugin authors how. OneNote, Notion and Sticky Notes are unchanged.
- **How to make one.** Any of:
  - the **New Timeline** row at the bottom of a local notebook;
  - `Ctrl+Shift+T`;
  - the palette command **New Timeline**.
- **On disk.** A timeline is an ordinary Markdown checklist, written exactly as Note Note's own Markdown editor would write it, plus one front-matter line:

  ```
  ---
  title: Trip to Lisbon
  note-note-type: timeline
  ---
  - [x] Book flights

    Return on the 14th
  - [ ] Pack the bags
  ```

  Any Markdown tool shows it as a checklist. Note Note 1.0.40 opens it as an editable checklist and saves it without losing an event.
- **In the list.** A timeline row shows a timeline glyph (U+F1533) and `2 of 4 · Next: Pack the bags`. The open note's row updates as you check, before the save lands.

**What keeps notes safe**

- A note of a type this version does not know opens **read-only as plain text**, with the reason. Nothing is written.
- A timeline whose text another tool turned into something that is not a timeline opens **as the Markdown it is**, with the reason on the status line. Markdown's own lossless-or-read-only rule then applies.
- The type marker is written **once, at creation**. No save ever writes or changes a type.
- Nothing is written without a user action. Check states that break the order (from another editor) are shown as stored and never repaired on open.
- The timeline codec is the editor's own Markdown parser (`services/markdown/parse.py`) and writer (`qthtml.convert`). Each written body is checked by re-reading it, and anything that does not read back identically is refused, never saved. This property was verified on 3000 random timelines through the pure converter and on 19 samples through Qt, with 0 failures after the prerequisite fixes.

**Before the feature: release 1.0.41**

1.0.41 commits the review fixes already in the working tree. It also fixes two pre-existing ways the Markdown editor loses text, both found while planning:

- a line that is just `+` cannot be saved;
- a link definition no link uses is deleted on the first save.

And it gives provider capabilities one reader, which fixes the title-field warning for providers without `hasTitle`.

**Not in this release (later work, §10)**

- converting a note to or from a timeline;
- drag-and-drop reordering, and dates on events;
- timelines in OneNote, Notion or Sticky Notes;
- note types contributed by plugin packages;
- a type chooser on New Note;
- bold titles on disk.

**Phases**

| Phase | Content | Visible change | Release |
|---|---|---|---|
| P0 | Prerequisites | — | 1.0.41 |
| P1 | The contract | none | — |
| P2 | The pane/body seam | none | — |
| P3 | The codec | none | — |
| P4 | The local type marker | none | — |
| P5 | The timeline body | not yet creatable | — |
| P6 | Creation, list and commands | timelines | 1.1.0 |

---

## 2. The request as understood

The paste lost its first words. Bracketed text is reconstructed:

> [A new note type:] timeline, [each event shown on a vertical timeline,] and will have some
> kind of radiobox in front of it. When the user checks one, we will check everything above.
> So this will be useful for the user to follow a timeline and it will check one by one in
> order. If he checks one, we will check all above. There will be a button below 'add new
> event' that will open the form for title and description. For this, we will have to change
> the providers in order to set some kind of content type. Like one is simple text, one is md,
> one is... timeline, and we will have other note types in the future. Create a very detailed
> plan.

Assumptions the plan makes (each one is visible in §3 where the user may decide otherwise):

| # | Assumption |
|---|---|
| A1 | A "timeline" is a **note type** chosen when the note is created, not a block inside a Markdown note. |
| A2 | "Radiobox" means a **round check control** in front of each event. Several events can be checked at once, so it is not a radio group. Done = a filled accent circle with a tick, matching the editor's own checkboxes (U3). |
| A3 | "Above" means earlier in the list. A timeline runs top (first) to bottom (last). |
| A4 | Unchecking is unspecified. The plan unchecks the event **and every event below it**, the mirror rule (U1). |
| A5 | "A button below 'add new event'" means an **Add new event** row below the events. It opens an **inline** form with a single-line **title** (required) and a multi-line **description** (optional), with no dialog, because business goal 2 forbids modal dialogs between the user and their text (`docs/business-requirements.md:29-31`). |
| A6 | "Change the providers to set some kind of content type" means the provider contract gains a per-note type that providers declare and report, **additively**: existing providers keep working unchanged (`docs/technical-requirements.md:99-101`). |
| A7 | "Simple text, md, timeline" are the type ids `text`, `markdown`, `timeline`. |
| A8 | "Other note types in the future" means the host gets a real seam: a type table, one body contract and one pane protocol. Note types are **not** opened to plugin packages in this release (U14). |
| A9 | Events have no dates in v1. Order is the order the user gives them. |
| A10 | First release: local notebooks only, plus the hello example. The remote backends have no safe place for the type (§5.11, U11). |
| A11 | Editing, deleting and reordering events (with the keyboard) belong in v1. Without them a typo sends the user to another app (U10). |
| A12 | Keyboard-complete, theme-native, no new colour tokens (`docs/business-requirements.md:82`). |

---

## 3. Decisions you need to make

Each row is a product choice the codebase cannot settle for you. The plan assumes the
**default** and says where a different answer would change it.

| # | Question | Options | Default the plan assumes | Why |
|---|---|---|---|---|
| U1 | What does unchecking event *k* do? | (a) uncheck *k* and every event below it; (b) uncheck only *k*; (c) only the last done event can be unchecked | **(a)** | It mirrors "check everything above", so your own clicks never leave holes. One `Ctrl+Z` undoes a mistaken click, and the status line says how many events changed. |
| U2 | Which front-matter key marks a local note's type? | (a) `note-note-type: timeline`; (b) `type: timeline`; (c) `note-type: timeline` | **(a)** | The key is permanent on disk. Hugo and many Obsidian vaults already use `type:`, and Zettelkasten templates use `note-type:`. A namespaced key cannot flip one of your existing notes into a timeline, so an unknown value can safely open read-only. |
| U3 | How does a done event look? | (a) filled accent circle with a tick, text dimmed; (b) radio dot, text dimmed; (c) filled circle, title struck through | **(a)** | A tick reads as "done", a dot as "selected" and a strikethrough as "cancelled". (a) matches the editor's own checkboxes (`ui/NoteEditor.qml:2242-2284`). |
| U4 | What may a description hold? | (a) several lines of plain text (Shift+Enter makes a line), stored one paragraph per line; (b) one paragraph; (c) Markdown formatting | **(a)** | You asked for a description, and a list of things to bring is the obvious use. One paragraph per line is the editor's own fixpoint, verified, and needs no trailing-space hard breaks (§5.6). Formatting is refused on read, so it is never rewritten. |
| U5 | Are titles plain or bold in the file? | (a) plain (`- [ ] Pack the bags`); (b) bold (`- [ ] **Pack the bags**`) | **(a)** | Plain is what the editor itself writes, and the codec stays a pure fixpoint. Bold would need the Qt `font-weight:700` path and would refuse plain titles typed elsewhere. Title and description are still told apart elsewhere, because the description is a separate indented paragraph. |
| U6 | Is a half-typed event part of the note? | (a) yes: once it has a title it is saved with the note, Esc discards it and Ctrl+Z brings it back; (b) no: held by the form until Enter, lost if you switch notes | **(a)** | "Never lose a note" (goal 2). A crash, a note switch or a window close keeps what you typed. |
| U7 | A timeline that another tool turned into something else (added a heading, bold, a nested list) opens how? | (a) as the Markdown it is, editable under the usual Markdown rules, with the reason on the status line; (b) read-only until fixed elsewhere | **(a)** | The Markdown path is already lossless-or-read-only: the local provider's read opens a note read-only when the editor would not write all of it back (`operations.py`, `qthtml.unkept`). You can fix the text in place, and the note is a timeline again the next time it opens. |
| U8 | How strictly are hand-edited timelines read? | (a) anything that renders the same (blank lines between items, `*`/`+` bullets, `[X]`, CRLF, wrapped lines), normalised only when you next change it; (b) byte-exact only | **(a)** | With (b), every harmless edit in Obsidian or vim turns the timeline into Markdown. Normalisation changes only whitespace and markers that render identically. |
| U9 | How is a timeline created? | (a) a **New Timeline** row in each local notebook's footer + `Ctrl+Shift+T` + palette; (b) palette + key only; (c) a host-drawn type chooser on the New Note row (amends `docs/providers.md:185`) | **(a)** | Discoverable with the mouse, one step with the keyboard, and inside the documented rule that providers supply every creation button. A chooser pays off from the third creatable type, and is recorded as the path then (§10). |
| U10 | Which event operations ship first? | (a) add, edit, delete, move (`Alt+↑/↓`) and undo; drag later; (b) add and check only; (c) (a) plus drag | **(a)** | Typos and forgotten steps are everyday needs. Drag is costly and can follow. |
| U11 | Which providers hold timelines in v1? | (a) local + hello example; (b) also Notion (page icon as the marker); (c) also OneNote (data-id marker after live verification) | **(a)** | Neither remote has an invisible, durable place for the type, and their apps let users break the order. Sticky Notes is plain text with no title (`docs/decisions.md:557-561`). |
| U12 | What does a timeline row show in the list? | (a) glyph + `2 of 4 · Next: Pack the bags`; (b) glyph only; (c) neither | **(a)** | "Where am I" across all timelines without opening them. The open note's row updates as you check. |
| U13 | Conversion between Markdown and timeline? | (a) later, lossless directions only; (b) in v1 | **(a)** | Not requested. It needs a new provider operation. Nothing in this design blocks it (§10). |
| U14 | May plugin packages contribute note types now? | (a) not now: an internal table, with a recorded trigger and template; (b) a sixth catalog kind now | **(a)** | A public body API frozen from one example, and type ids written into users' files, cannot be taken back. |
| U15 | Which keys? | (a) `Ctrl+Shift+T` New Timeline; Add Event has no global key (`Ctrl+Enter` inside a timeline); (b) `Ctrl+Alt+N` (then move the override example in `docs/commands.md:145` and its fixtures `tests/ShortcutChecks.js:53-63`, `tests/extensions.qml:143`); (c) no default keys | **(a)** | `Ctrl+Shift+T` is free among the app's defaults and tool keys, and in Omarchy's Hyprland bindings (`~/.local/share/omarchy/default/hypr/bindings/*.lua` bind no `CTRL + SHIFT + T`). It pairs with `Ctrl+Shift+N`. `Ctrl+Alt+N` is the documented override example. |
| U16 | Releases | (a) 1.0.41 (prerequisites), then 1.1.0 (timelines); (b) one release | **(a)** | F1 is high severity and should not wait. A feature plus an additive contract change is a minor bump (`docs/release-process.md:26-27`). |

---

## 4. How it works today

Facts the plan rests on (HEAD `e2cdc4e` unless marked WT).

### 4.1 Content type is per provider

- Each provider declares `readonly property bool markdown`:
  - `plugins/org.note-note.local/Provider.qml:20` true;
  - `plugins/org.note-note.sticky/Provider.qml:14` false;
  - `plugins/org.note-note.notion/Provider.qml:17` true;
  - `plugins/org.note-note.onenote/Provider.qml:19` true;
  - `examples/hello/Provider.qml:14` true.
- The host reads it in exactly one place: `Workspace.qml:2837-2840`, `plain: p ? !p.markdown : false`. So an absent `markdown` means plain text, which `docs/providers.md:47` does not say.
- `hasTitle` has three different defaults:
  - the editor binding `Workspace.qml:2841-2844` yields `undefined` for an absent member, Qt warns "Unable to assign [undefined] to bool", and the previous note's value stays (verified on Qt 6.11.2 by the contract reader);
  - `services/notes/sidebar.js:26` treats absent as true;
  - `Workspace.qml:1932` treats it as false.
- OneNote sends a per-page `markdown: True` that nothing reads (`plugins/org.note-note.onenote/onenote.py:1380`, `:1387`).

### 4.2 The editor

- `ui/NoteEditor.qml` (2409 lines) is the whole note pane: toolbar, title, notices, provider views, conflict review, one `TextEdit` `area`, overlays and skeleton. There is one instance, `Workspace.qml:2824` (`id: editor`, `objectName: "noteEditor"`).
- `plain` (`:28`) switches the same `TextEdit` between PlainText and RichText through about 20 branches, and gates tools through `ui/editing/EditorApi.qml:13` (`writable: host.hasNote && !host.readOnly && !host.plain && !host.showingNotice`).
- The session-facing protocol:
  - `setNote(t, body, shown)` `:292-316`, which converts with `Markdown.toHtml`; `shown(ok)`.
  - `snapshotDocument()` `:318-321`, returning `{ title, body, base }`; the body is HTML or plain text.
  - `restoreDocument(snapshot)` `:323-332`.
  - `requestMarkdown(callback)` `:122-134`, framed `(body, ok)`, which converts the **live** `documentHtml()`.
  - `viewState()` and `restoreViewState()` `:1784-1789`.
  - `focusEditor()` `:377` and `focusBody()` `:380-383`.
- Host facts that hang off the rich editor:
  - `canColorText` `:787`, feeding the theme at `Workspace.qml:122-123` and `2520`;
  - `tools.actions`, feeding the key-binding registry at `Workspace.qml:2554`;
  - `toolbarHeight` and `toolbarRowHeight` `:1806-1807`, aligning the sidebar header at `Workspace.qml:2714-2715`;
  - `wordCount` `:1794-1797`, read by the view bar at `Workspace.qml:2920` and labelled at `ui/ViewBar.qml:129-131`;
  - `hoveredLink` `:84`.
- The drawn checkbox face is at `ui/NoteEditor.qml:2219-2291` (face `:2242-2284`). A click falls through to Qt's single-item toggle, which has no hook (`:2219-2223`).
- Keys:
  - the title field calls `root.shortcut(event)` in `Keys.onPressed`, with `Keys.onReturnPressed`, `Keys.onEnterPressed` and `Keys.onDownPressed` → `focusBody()` (`:1909-1914`);
  - the body calls `root.shortcut(event)` first (`:2112`);
  - `Workspace.handleShortcut` (`Workspace.qml:2135-2166`) resolves in context `shortcutContext()` (`:2168-2176`): `editor` only while `editor.bodyFocused` (= `area.activeFocus`, `ui/NoteEditor.qml:72`), otherwise `workspace`;
  - a content-level `Keys.onPressed` also runs `handleShortcut` for keys no item accepted (`Workspace.qml:2629-2635`, WT `:2643-2647`);
  - `Escape` is `back` in the `notes` context (`services/shortcuts/defaults.js:20`), and `notes` = workspace + editor + search (`services/shortcuts/resolve.js:10-12`).
- Qt runs a specific `Keys.on<Key>Pressed` handler **before** `Keys.onPressed` and treats the key as accepted (verified with qmltestrunner on Qt 6.11.2 by the product designer). A list that uses `onDownPressed` would therefore swallow `Ctrl+Down` before the app shortcut sees it.

### 4.3 The session

`services/notes/NoteSession.qml`:

- `load()` `:210-305`:
  - blanks the editor with `setNote("", "")` at `:226`;
  - restores a draft synchronously at `:237`;
  - otherwise calls `provider.load`, then `setNote` at `:263`.
- The load answer is consumed only here. It reads `error`, `version`, `base`, `title`, `body`, `view`, `editable`, `reason`, `recovered`, `conflict` and `retry`.
- `isStored` `:364-367` compares title and body strings. `stored` is a path map at HEAD and, in WT, `{ path, document }` or null (F14).
- `flushSave` `:471-507`: snapshot → `isStored` → draft → `editor.requestMarkdown` (`:493`) → `provider.save(path, title, body, cb, { view, resolution })`.
- Drafts, recovered drafts (`:278`) and deletion recovery (`:420`) are snapshots.
- The local provider decides a Markdown note's editability itself: `operations.py read` answers `editable: false` with a reason when `qthtml.unkept(body)` names something the editor would not write back (`operations.py:19-31`, `:111-120`), and its `load()` forwards `editable` and `reason` (`Provider.qml:509-511`). WT: F20 was first moved into the host and then **reverted**, so this is unchanged (`CODE-REVIEW-2026-10-11.md`, F20: "the host holds no provider's policy").
- WT (F15): the editor's `readOnly` is bound to `!session.writable` (WT `Workspace.qml:2849`).
- The test double: a 12-member fake editor, `tests/transitions.qml:375-400` (WT `:424-448`).

### 4.4 Creation

- One call site: `p.create(target, cb)` (`Workspace.qml:1912`), inside `newNote(providerId, target)` (`:1887-1938`).
- `newNote` without a provider first runs `activateFooterShortcut("newNote")` (`:1892-1894`, defined `:1690-1703`). Otherwise `newNoteDestination` (`:1873-1885`) takes `createTargetFor(currentPath)`.
- Local:
  - the footer action `newNote` targets `"section:" + sectionKey` in notebook-tab mode (`plugins/org.note-note.local/Provider.qml:275-279`);
  - `createTargetFor("")` is the **last** notebook (`:265`).
  - So a typed creation that skips the footer files the note in another notebook. This is the verified flaw judges found in one design.
- Footer contract: `docs/providers.md:181-213`. The host adds no creation buttons (`:185`), and the shortcut vocabulary is `newNote` and `newNotebook` (`:200-204`).
- Workspace actions take no parameters (`services/commands/WorkspaceActions.qml:18-34`). Defaults are in `services/shortcuts/defaults.js:21-23`, palette commands in `plugins/org.note-note.workspace/plugin.json`, and the pin is `services/extensions/selftest.py:44-47`.

### 4.5 The local provider

- `notefile.py` owns the format. `split` → `(title, body, extra)`, and every unowned front-matter line is kept verbatim (`:48-67`). `serialize` writes them back after the title (`:70-76`).
- A save re-reads the current file's extra lines (`operations.py:126-141`; the working tree leaves `operations.py` as at HEAD). So a hand-written `note-note-type:` line already survives every save (verified by the local reader).
- `create` writes `---\ntitle: \n---\n` (`operations.py:104-110`).
- `list.py`:
  - reads 4096 bytes of each note (`HEAD_BYTES`, `:64`) in `head_of` (`:147-153`);
  - emits `N key path title preview size mtime_ns` (`:9`, `:253`).
- `Provider.qml` rebuilds two things with explicit fields, so a new field would vanish without explicit propagation:
  - the load answer (`:509-511`, WT `:545-547`), which forwards `editable` and `reason`;
  - the saved note's entry (`:548-549`, WT `:587-588`).
- `search.py` matches the raw body, so event text is found.

### 4.6 The converter

- `parse.py` uses vendored mistune with `task_lists`, `strikethrough`, `table`, `mark`, underline, format tags, text colour and audio (`:72-74`). There is **no** URL autolink plugin, so a bare URL is text.
- Planner's checks against a clean HEAD copy:
  1. `mdtext.LINE_START` (`services/markdown/mdtext.py:27`, `[-+*](?=\s)`) misses a lone `+`. A paragraph or description line that is exactly `+` cannot be saved ("the document cannot be saved without changing its text"), and 14 of 3000 random timelines fail on it. With `[-+*](?=\s|$)`, 0 of 3000 fail, all 140 existing qthtml `CASES` stay fixpoints, and 19 of 19 samples are unchanged through Qt.
  2. mistune consumes a **link reference definition** without emitting a token. So `"Bookmarks\n\n[home]: https://example.com\n"` opens editable (`unkept` is `[]`), and the first save writes `"Bookmarks\n"`. This is a silent deletion in today's Markdown editor. A definition that a link uses is folded inline instead (`[t][g]` → `[t](url)`), and no information is lost. mistune keeps the definitions in `state.env["ref_links"]`, and reference links carry `ref`, the definition's key (verified).
  3. Entity references stay literal in mistune `text` tokens (`&amp;` reads as the five characters), and the writer does not escape `&`. Read and write agree.

### 4.7 The list, keys and tests

- **The list.**
  - `sidebar.js` `row()` (`:24-31`) copies a whitelist of fields. Search results use `sections[].notes` (`:62-70`).
  - `ui/NoteSummary.qml` (shared by `ui/NoteList.qml:447-461` and `ui/SearchResults.qml:104-117`) draws a bold title and a date + preview line. Note rows draw no icon.
  - The host compares rows with `JSON.stringify`, and a row carries only what the list shows (`docs/decisions.md:444-448`).
  - `displayTitle` (`Workspace.qml:1305-1324`) falls back to the preview, mapping `[ ]`/`[x]` to `☐`/`☑`.
- **Theme.** Style keys both hosts define are listed at `design/Style.qml:20-47`:
  - font: `caption bodySmall body subtitle title displayLarge iconSmall icon iconLarge`;
  - spacing: `xxs xs sm md lg xxxl hairline controlGap controlHeight controlPaddingX panelPadding popupRowHeight`.
- **Glyphs.** Verified present in `assets/fonts/nerd-symbols/SymbolsNerdFont-Regular.ttf`:
  - U+F1533 md-timeline_check_outline
  - U+F0F97 md-timeline_plus_outline
  - U+F0415 md-plus
  - U+F03EB md-pencil
  - U+F01B4 md-delete
  - U+F005D md-arrow_up
  - U+F0045 md-arrow_down
- **Test runners.**
  - `tests/selftest.py` lists the Python scripts, and CTest lists its own (`CMakeLists.txt:71-131`). CTest omits the local, qthtml and regression suites.
  - WT (F17): transition suite names come from `tests/transition_selftest.py` `SUITES` (`--list-suites`), which CMake reads at configure time.
  - EditorKeys suites are a map (`tests/EditorKeys.qml:3051-3059`).
  - The noise gates fail a suite on any "TypeError:", "ReferenceError:", "Binding loop", "Unable to assign", "Error:" or "ERROR" line (`tests/transition_selftest.py:217-222`).
- **ListView focus (planner's qml6 check).** A `ListView` model swap gives the new current item focus and **takes focus from a field in the ListView's footer**. A field **outside** the ListView keeps focus and text. A JS-array swap resets `contentY` to 0, and saving `contentY - originY`, then `forceLayout()`, then restoring brings it back (`docs/engine-notes.md:42-45`).

### 4.8 The working tree (uncommitted, as of 2026-10-12)

`CODE-REVIEW-2026-10-11.md` "Fixes": all 21 findings fixed in the working tree, none committed. The tree kept moving while this plan was written (F20 was reverted, F10 redone with `NoteList` holding its rows while a rename is open). Re-read the table before P0.

| Finding | State | What changed |
|---|---|---|
| F1 | code done | alias keys are never live paths |
| F2 | code done | `session.whenSaved(provider, ready)`; `runRowAction` waits |
| F3–F10, F12, F16, F18, F19 | code done | including F10: `NoteList` holds the rows it draws while a title is renamed in place (`heldRows`/`shownRows`), so a save that rebuilds rows (every timeline check) no longer ends a rename |
| F14 | code done | `stored` is `{ path, document }` |
| F15 | code done | `readOnly: !session.writable`; `updateReadOnly` gone |
| F17 | code done | `--list-suites`; CMake reads it; `tests/selftest.py` uses argv tuples |
| F20 | no code change | the `unkept` check stays the local provider's own (`operations.py`); the reason is recorded in `docs/decisions.md`. A first fix that moved it into `NoteSession` behind a `storesMarkdownVerbatim` flag was reverted |
| F21 | code done | `result \|\| {}` before the bookkeeping |
| F11 | done | tests for the destructive operations |
| F13 | done | `count` in the skill's row shape |

---
## 5. Target design

Where each of the twenty decision points is answered. "Source" names the design each answer
takes from, and the judges' amendments it carries.

| D | Answer, in one line | Where | Source |
|---|---|---|---|
| D1 | `noteType` and `noteTypes` in the contract; `documentType` for the pane's held form; unqualified core ids `text`/`markdown`/`timeline`; qualified package ids reserved | §5.1 | guardian; architect's grammar; judges: one grammar pinned in JS and Python |
| D2 | `noteTypes` with the default first, legacy `markdown` shorthand, every default in `Capabilities.of`; built-ins drop `markdown`, hello keeps it | §5.2, §5.5 | guardian; architect (drop dead flags); judges (`tools` fails closed; the `storesMarkdownVerbatim` flag they named no longer exists, F20 having been reverted) |
| D3 | The load answer decides; rows draw; unknown or undeclared types open read-only as text; read only from declaring providers | §5.2, §5.3 `opened()` | guardian; judges (bounded quoted id, prototype-free) |
| D4 | Provider footer **New Timeline** + `Ctrl+Shift+T` + palette, always through the provider's own row and target; `create(target, cb, { noteType })`, exactly that type or `{ error }` | §5.9 | product; guardian's exact-type rule; architect's chooser kept for the third type |
| D5 | No conversion in v1; later only through a separate, feature-detected `setNoteType`, lossless directions only | §10 | guardian; architect's lossless rule |
| D6 | `NoteEditor` stays the pane; `NoteBody` contract; permanent `documentBody` adapter; typed bodies in kept Loaders; `documentActive` gating; `requestBody(document)` | §5.4 | architect; guardian's `requestBody(document)` and snapshot type; product's focus move and clearing of the inactive body |
| D7 | Pure table `services/notes/notetypes.js` + one QML contract `NoteBody.qml`; no plugin kind; trigger and template recorded | §5.3 | architect, as amended by the judges (no QML registry) |
| D8 | Markdown task list written by `qthtml.convert`, read by `parse.py`, re-read on write; plain titles; one paragraph per description line; bounded, fail-closed | §5.6 | guardian; delivery judge (multi-line, verified here); product's self-check; **new**: link definitions refused |
| D9 | Check *k* checks above it, uncheck *k* unchecks below it; out of order shown as stored; status line; 200-step undo | §5.7 | architect; guardian/product status line and wording |
| D10 | ListView rows patched in place from an array, the add area outside it, an inline form that is part of the note, full keyboard map, accessibility | §5.8 | product; architect's empty-timeline flow; judges (one `onPressed`, form state out of delegates); **new**: verified focus behaviour |
| D11 | Glyph from the table; structured `progress` worded by the host; live for the open note; bounded 64 KiB shared helper | §5.10 | product (structured, live), guardian (bound, one helper) |
| D12 | Local and hello hold timelines; OneNote and Notion deferred; Sticky unsupported; declaration rule | §5.11 | all three; guardian's rule |
| D13 | `note-note-type:` front-matter line owned by `notefile.py`, written once, unreadable → read-only; 10-field `N` record; explicit load and `Object.assign` commit | §5.11.1 | guardian; judges (`Object.assign`); the `unkept` check stays in `operations.py read` (F20 as finally decided) |
| D14 | Type in every snapshot; deterministic JSON form; framed failures keep the draft; no type on save | §5.12 | guardian, on architect's protocol and F14 |
| D15 | Workspace actions `newTimeline` (`Ctrl+Shift+T`) and `addTimelineEvent` (palette only) | §5.9 | guardian/product; delivery and safety judges on the key |
| D16 | P0: commit the WT review fixes (all 21), the lone-`+` fix, the link-definition fix, `Capabilities.of`, CTest gaps | §6 P0 | guardian; judges (rebase on WT, F10); **new**: link definitions |
| D17 | Tests at every level, registered in both runners | §7 | guardian; architect's capability, fake-editor and inert-document cases; product's form and accessibility cases |
| D18 | Every doc in the commit with its behaviour; `docs/note-types.md`; 14 decision entries | §8 | architect; guardian's security entry; product's editing-tools line |
| D19 | P0 (1.0.41) → contract → seam → codec → local marker → body → creation and list (1.1.0) | §6 | guardian's order; architect's commit granularity |
| D20 | Risks with mitigations; 16 user decisions | §9, §3 | all three |


### 5.1 Content-type model and vocabulary

**Two concepts, two names.**

| Name | Where it lives | Meaning |
|---|---|---|
| `noteType` | provider contract: note rows, `sections[].notes`, the `load()` answer, `create` options | the type the **provider stores** for a note |
| `noteTypes` | provider property | the types a provider stores and creates, its default first |
| `documentType` | `NoteEditor.documentType`, every editor snapshot `{ documentType, title, body, base }` | the form the **pane holds** the open document in. It is the body that edits it: `text`, `markdown` or `timeline` |

`documentType` equals `noteType` except in two cases:

- a timeline whose text is not in timeline form is held as `markdown` (U7);
- a note of an unknown or undeclared type is held as `text`, read-only.

Keeping the two apart means a snapshot never claims timeline form for a body it does not
hold in that form, and a draft is always restored into the body that made it.

**Core ids.** Unqualified, reserved for the app:

| id | Label (title case) | Noun (in sentences) | Today's equivalent |
|---|---|---|---|
| `text` | Plain Text | plain-text notes | `markdown: false` |
| `markdown` | Note | notes | `markdown: true` |
| `timeline` | Timeline | timelines | new |

**Id grammar.** It is defined once in JS and once in Python, as the same pattern text. A
regression test pins the two as equal:

```
^(?:[a-z][a-z0-9-]{0,31}|[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+/[a-z][a-z0-9-]{0,63})$     and at most 128 characters
```

The first branch is a core id. The second, `<package-id>/<local-id>`, is reserved for package
types in a later release. It always contains `.` and `/`, so no package can take a core
name, and a later built-in cannot capture a package type's notes.

**Not `kind`.** Rows already use `kind` (`note|new|action|tree`). **Not `type`.** It is
generic, so an external provider may already send it. `noteType` appears nowhere in the
repository today (grep), so reading it changes nothing for existing providers. On top of
that, it is read only from providers that declare `noteTypes` (§5.2).

### 5.2 Provider contract changes

All changes are additive under `apiVersion: 1`. They follow the `canReorder` → `reorder`
precedent: the legacy shorthand stays, the explicit declaration wins, and the host feature-detects.

#### 5.2.1 What changes

| Member | Change |
|---|---|
| `noteTypes` (new property) | `readonly property var noteTypes: ["markdown", "timeline"]`: the types the provider stores and creates, **default first**. Valid when it is an array of 1–16 distinct ids that match the grammar, and when every type with a fallback (only `timeline`, whose fallback is `markdown`) has that fallback declared beside it. An invalid declaration is ignored as if absent, with one `console.warn` when the provider loads (`Workspace.addProvider`). Unknown-but-valid ids stay declared. |
| `markdown` | Becomes the legacy shorthand: true = `["markdown"]`, false or absent = `["text"]`. Ignored when `noteTypes` is valid. |
| `hasTitle` | Absent = true (documented, and now true everywhere). |
| `noteType` (row and `notes` field) | Optional. The note's type when it is not the default. Read only from declaring providers. |
| `progress` (row and `notes` field) | Optional `{ done, total, next }` for a note whose type has steps (a timeline). The list words it. |
| `load()` answer | Gains optional `noteType` (absent = default). Also documents the existing `retry`. |
| `save()` | Unchanged signature. The docs gain the existing answer fields `merged` and `version`, and "a save never carries or changes a type". |
| `create(target, cb, options)` | `options = { noteType }`, always passed by hosts from 1.1.0, always a type the provider declares. Create exactly that type or answer `{ error }`. |
| `host.newNote(id, target, noteType)` | Optional third argument. |
| footer `shortcut` | Vocabulary gains `newTimeline` (Ctrl+Shift+T). |

#### 5.2.2 Text to add to `docs/providers.md`

The skill mirror `skills/note-note-plugin/references/providers.md` changes in the same commit
(`docs/plugins.md:50-53`).

Properties table (`docs/providers.md:47-48`): replace the `markdown` row and extend the
`hasTitle` row, adding `noteTypes`:

```markdown
| `noteTypes`         | list   | optional: the note types you store and create, by id, your default first — `["markdown"]`, `["text"]`, `["markdown", "timeline"]`. See "Note types". Leave it out and `markdown` stands for it |
| `markdown`          | bool   | legacy shorthand for `noteTypes`: true is `["markdown"]`, false or absent is `["text"]` (plain text). Ignored when `noteTypes` is given; keep it beside `noteTypes` if your provider must also run on Note Note 1.0.40 or older |
| `hasTitle`          | bool   | notes have a separate editable title (absent = true); false also uses normal text weight for the first-line label in the list and search results |
```

New section `### Note types`, placed after "Properties the host reads":

```markdown
### Note types

Every note has a type, and the type decides how the host shows and edits the note.
This version knows three: `text` (plain text, every newline counts), `markdown`
(Markdown, rendered) and `timeline` (events checked off in order; its body is a Markdown
task list in one shape, see "The timeline format"). An id is lowercase letters, digits and
hyphens, at most 32 characters; ids of the form `<package-id>/<local-id>` are reserved for
types a later version may let packages contribute.

Declare the types you store as `noteTypes`, your default first. A note you report without
a type is of your default type, and Ctrl+N makes one. The host uses the declaration when it
is a list of 1 to 16 distinct ids; anything else is ignored — `markdown` then decides, as
before — and a warning is logged when the provider loads. A declaration holding `timeline`
must hold `markdown` too: a timeline whose text has stopped being one opens as Markdown, and
what is then written must be something you store.

Report a note's type as `noteType` on its row, on its `sections[].notes` entry and in
`load()`'s answer; leave it out for your default type. The load answer decides how the note
opens; a row's type only draws it. The host reads `noteType` only from a provider that
declares `noteTypes`: one without the declaration is never asked, and a field of that name it
already sends changes nothing.

A note whose type this version of Note Note does not know, or whose type you do not declare,
opens read-only as plain text, its reason said on the status line. Nothing of it is written,
so whatever marks its type stays as it is.

The host never changes a note's type. `save()` is never told one, and whatever marks the type
must survive every save. The type is given once, to `create()`.

Declare `timeline` only if `save()` stores the body exactly as given (line endings aside) and
merges nothing into it. A merge-aware provider must first show that its merge keeps a
timeline's text a timeline.
```

Compatibility paragraph, after the `canReorder` paragraph (`docs/providers.md:170-175`):

```markdown
For compatibility, a provider without `noteTypes` works as before: `markdown: true` declares
`["markdown"]`, false or absent `["text"]`; all its notes are of that type, its
`create(target, cb)` is asked for nothing else, and a `noteType` it sends is ignored. An
explicit `noteTypes` takes precedence over `markdown`.
```

Row shape (`docs/providers.md:89`). Fix the shape, and add the two fields:

```markdown
A row is `{ kind, path, title, preview, icon, level, expanded, count, menu, reorder, version, modified, noteType, progress }` …
`noteType` (optional, note rows and `notes` entries) is the note's type when it is not your
default (see "Note types"). `progress` (optional) is `{ done, total, next }` for a note whose
type has steps — a timeline: how many are done, how many there are, and the title of the
first one not done (`""` when none). The list shows "2 of 4 · Next: Pack the bags" in place
of the preview. Leave it out when you cannot say; never estimate it from part of the note.
```

Footer shortcut (`docs/providers.md:200-204`):

```markdown
The optional `shortcut` names a shared keyboard action — `newNote`, `newNotebook` or
`newTimeline` — connecting Ctrl+N, Ctrl+Shift+N or Ctrl+Shift+T to that same footer row.
Creation handlers call `host.newNote(id, target, noteType)` — `noteType` optional, your
default when left out — or `host.newNotebook(value, id)`.
```

Functions:

- `load` (`:260`): add `noteType` to the answer list and add one sentence: "`retry: true` asks the host to save the recovered draft again once it is shown."
- `save` (`:282`): the answer becomes `cb({ error, warning, conflict, merged, version })`. "`merged: true` says you hold more than this draft (a merge); `version` is the note's new change marker. A save never carries a type."
- `create` (`:350`) becomes:

```markdown
- `create(target, cb, options)` → `cb({ path, error })`. `options` is `{ noteType }`: one of
  the types you declare, given by every host from 1.1.0. Create exactly that type or answer
  `{ error }`; never another. A provider without `noteTypes` is only ever asked for its one
  type and may keep `create(target, cb)`. A provisional note (one you list before the backend
  has created it) reports the requested `noteType` in its row and its `load()` answer, and
  keeps it across `notePathChanged`. …
```

New subsection `### The timeline format`:

- the canonical grammar and the tolerated reading rules from §5.6;
- the limits;
- "read and write it with `services/markdown/timeline.py` (`read`, `write`, `summary`); store the body exactly as given".

`## Limits` (`:493`) gains the timeline row. The local format paragraph (`:713`) gains: "The
note's type is one more front-matter line, `note-note-type: timeline`, written when the note is
made and never by a save; a note without it is Markdown."

### 5.3 The note-type table and extensibility

**One pure table: `services/notes/notetypes.js` (new, `.pragma library`).**

- It is read by `sidebar.js`, `capabilities.js`, `NoteSession.qml`, `NoteEditor.qml`, `WorkspaceActions.qml` and `Workspace.qml`, so nothing reaches into the editor for type facts.
- There are no `NoteType.qml` objects, no QML registry and no runtime definition checks, because the three entries are static and pinned by pure tests. This was the judges' amendment to the architect's registry.
- The only QML contract is `ui/notetypes/NoteBody.qml` (§5.4).

```js
.pragma library

// The kinds of note this version of Note Note shows and edits (docs/note-types.md).
// A provider stores each note's type; what a type means is the host's: the body that
// edits it (`body`, a file under ui/), the format the document editor holds it in
// (`format`), the type its text opens as when it is not in this type's form
// (`fallback`), and how it is named and drawn. Ids come from providers and files, so a
// lookup never reaches Object.prototype: "constructor" is no type.
var ID_PATTERN = "^(?:[a-z][a-z0-9-]{0,31}|[a-z][a-z0-9-]*(?:\\.[a-z][a-z0-9-]*)+/[a-z][a-z0-9-]{0,63})$"
var ID = new RegExp(ID_PATTERN)
var MAX_ID = 128
var MAX_SHOWN_ID = 64

var TYPES = {
  "text": { id: "text", label: "Plain Text", noun: "plain-text notes", glyph: "", body: "",
            format: "plain", fallback: "", footerShortcut: "" },
  "markdown": { id: "markdown", label: "Note", noun: "notes", glyph: "", body: "",
                format: "markdown", fallback: "", footerShortcut: "" },
  // Phase 5:
  "timeline": { id: "timeline", label: "Timeline", noun: "timelines", glyph: "󱔳" /* U+F1533 */,
                body: "notetypes/timeline/TimelineBody.qml", format: "", fallback: "markdown",
                footerShortcut: "newTimeline" }
}

function validId(id) {
  return typeof id === "string" && id.length <= MAX_ID && ID.test(id)
}

function entry(id) {
  if (typeof id !== "string" || !Object.prototype.hasOwnProperty.call(TYPES, id)) {
    return null
  }
  return TYPES[id]
}

function known(id) {
  return entry(id) !== null
}
// glyph(id), label(id), noun(id), fallback(id), footerShortcut(id): the field, or "".

// The typed bodies the pane may host, in table order: [{ typeId, url }].
function typedBodies() {
  return Object.keys(TYPES).filter(function(id) {
    return TYPES[id].body !== ""
  }).map(function(id) {
    return { typeId: id, url: TYPES[id].body }
  })
}

// How a loaded note opens (NoteSession.load). `capabilities` is Capabilities.of(provider),
// `answer` the provider's load answer: { documentType, readOnly, reason }.
function opened(capabilities, answer) {
  var reported = capabilities.declaresTypes ? answer.noteType : undefined
  if (reported === undefined || reported === null || reported === "") {
    reported = capabilities.defaultType
  }
  if (!validId(reported)) {
    return refused("This note is of a kind this version of Note Note cannot show, so it opened read-only")
  }
  if (!known(reported)) {
    return refused("This note is a “" + shownId(reported)
                   + "” note, which this version of Note Note cannot show, so it opened read-only")
  }
  if (capabilities.noteTypes.indexOf(reported) < 0) {
    return refused("This notebook reported a kind of note it does not keep, so it opened read-only")
  }
  return { documentType: reported, readOnly: false, reason: "" }
}

function refused(reason) {
  return { documentType: "text", readOnly: true, reason: reason }
}

function shownId(id) {
  return id.length > MAX_SHOWN_ID ? id.substring(0, MAX_SHOWN_ID) + "…" : id
}

// A row's `progress`, made safe to draw: { done, total, next } or null.
// Integers 0 ≤ done ≤ total ≤ 100000 and `next` a string cut to 256 characters; anything else
// is null, so a provider's bad answer draws the plain preview instead.
function progressOf(value) {
  if (!value || typeof value !== "object" || !isCount(value.done) || !isCount(value.total)
      || value.done > value.total || typeof value.next !== "string") {
    return null
  }
  return { done: value.done, total: value.total, next: value.next.substring(0, 256) }
}

function isCount(value) {
  return typeof value === "number" && value % 1 === 0 && value >= 0 && value <= 100000
}

// "No events yet" · "Done" · "All 4 done" · "2 of 4 · Next: Pack the bags"
function progressText(progress) {
  if (progress.total === 0) {
    return "No events yet"
  }
  if (progress.done === progress.total) {
    return progress.total === 1 ? "Done" : "All " + progress.total + " done"
  }
  var next = progress.next ? " · Next: " + progress.next : ""
  return progress.done + " of " + progress.total + next
}
```

**No plugin kind now (U14).**

- **Where the trigger is recorded.** `docs/decisions.md`, entry "Note types are the app's own, not a plugin kind yet".
- **The trigger.** All three must hold:
  1. a second non-document core type exists;
  2. a concrete external type is wanted;
  3. `NoteBody` has been unchanged for one release.
- **The template.** Commit `2c5920f`'s file list:
  - `services/extensions/manifest.py` `KINDS`, `BUILDERS` and `executable`;
  - a `PluginCatalog` property;
  - `extensions/NoteNote/Extensions/NoteBody.qml` with its `qmldir` line;
  - the table taking catalog descriptors;
  - `docs/plugins.md`, `skills/note-note-plugin/SKILL.md`, a `references/note-types.md` and `check.py`;
  - an example package and tests.
- **What a package type will need in addition.** A Python-side codec channel, because provider previews and progress run in Python and cannot call a package's QML.
- **Rules that hold already.**
  - Package types use qualified ids.
  - Core types can never be disabled.
  - A note of a disabled or removed package's type opens read-only as text, which is today's unknown-type rule.

**Why not a plugin kind now.**

- An older app rejects a whole package that declares an unknown kind (`services/extensions/manifest.py:142-144`).
- Type QML would run unsandboxed in the shell's engine.
- A built-in type package could be disabled, which would strand every timeline.
- The body API would be frozen from one example.

### 5.4 The note pane and the body interface

**Decision.** `ui/NoteEditor.qml` stays the single pane (`id: editor`, `objectName: "noteEditor"`).

- **What the pane keeps:**
  - toolbar row, modified date, title, notices, provider views and conflict review;
  - skeleton, `readOnly`, `noteToken` and `documentBase`;
  - every Workspace `editor.*` reference.
- **Bodies.** It hosts one body at a time, and each implements one protocol:
  - `documentBody` is a `QtObject` adapter over the existing rich/plain `TextEdit`. The TextEdit stays **permanently instantiated**, so `canColorText`, `tools.actions` and the toolbar heights never change with the open note.
  - Typed bodies are created on first use and then kept.
- **Not threaded through `plain`.** The type is not a third flag threaded through `plain`'s branches.
- **Rejected:**
  - swapping `NoteEditor` per type at the Workspace level, which orphans about 50 references and makes theming and key bindings flap;
  - extracting the rich editor now, which is about 1000 test references for no user value;
  - creating the rich editor per note.

**The body contract: `ui/notetypes/NoteBody.qml` (new).**

```qml
import QtQuick

// What the note pane (ui/NoteEditor.qml) asks of the body that shows and edits one note
// type. The pane keeps the title, the notices, the toolbar row and read-only; the body keeps
// the note's text, its own keys and its own undo. Every function has a refusing default, so a
// body that leaves one out never shows an editable blank (docs/note-types.md).
FocusScope {
  id: body
  readonly property int apiVersion: 1
  // The pane's narrow API (NoteEditor.qml, bodyHost): read-only state, ink and fonts, the
  // conversion service, shortcut(event), edited(), status(text), focusTitle(), current(token).
  required property var host
  // What the view bar shows: "12 words", "2 of 4 done".
  property string countText: ""
  // { done, total, next } for a type with steps, else null: the open note's row shows it live.
  property var progress: null
  // A form of the body has the keyboard.
  property bool formOpen: false
  readonly property bool hasFocus: body.activeFocus

  // Puts a stored body in. done({ ok, fallback }) once it shows or cannot:
  // ok false = it could not be read (the note is then unavailable, never a blank);
  // fallback "<reason>" = it is not in this type's form (the pane shows it as the type's
  // fallback and says the reason). `token` is the pane's; host.current(token) is false once
  // a newer note has taken the pane.
  function show(text, token, done) {
    done({ ok: false, fallback: "" })
  }
  // Puts back a form snapshot() gave: "" when it is back, else why not.
  function restore(form, token) {
    return "This note could not be shown"
  }
  // The body's own canonical form of what it holds: equal strings mean equal notes.
  function snapshot() {
    return ""
  }
  // A snapshot's body as the provider stores it, from the snapshot alone (never the live
  // state). callback(body, ok); ok false sends nothing.
  function request(document, callback) {
    callback("", false)
  }
  // Drops the note: text, cursor, undo history, any open form.
  function clear() {
  }
  function viewState() {
    return null
  }
  // Ignores a state it did not make.
  function restoreViewState(state) {
  }
  function focusEditor() {
    body.forceActiveFocus()
  }
  // From the title (Enter, Down): the body's start.
  function focusBody() {
    body.forceActiveFocus()
  }
  function undo() {
  }
  function redo() {
  }
  // A named action of the type ("addEvent", "toggle"): true when done.
  function act(action, argument) {
    return false
  }
}
```

**`bodyHost`.** A `QtObject` inside `NoteEditor.qml`, and the only thing typed bodies receive:

| Member | Value |
|---|---|
| `readOnly` | `root.readOnly \|\| !root.hasNote` |
| `foreground`, `background`, `accent` | the pane's (fed from `editor.foreground`/`editor.background` tokens and the accent) |
| `fontFamily`, `noteFontFamily`, `bodyFontSize` | the pane's |
| `markdown` | the conversion service (`services/markdown/Markdown.qml`): the type's codec runs under the pane's token |
| `hasTitle` | `root.hasTitle` |
| `current(token)` | `token === root.noteToken` |
| `shortcut(event)` | `root.shortcut(event)` (app bindings first; sets `event.accepted`) |
| `edited()` | `root.edited()` |
| `status(text)` | `root.statusRequested(text)` |
| `focusTitle()` | `root.focusTitle()` when `root.hasTitle` |

**The pane protocol.** The members NoteSession and Workspace use. Every other existing member
is unchanged.

| Member | Kind | Behaviour |
|---|---|---|
| `documentType` | `property string`, default `"markdown"` | written only by `activate()` |
| `body` | `property QtObject`, default `documentBody` | written only by `activate()` |
| `documentActive` | `readonly bool` | `root.body === documentBody` |
| `plain` | `readonly bool` (was settable) | `NoteTypes.entry(root.documentType).format === "plain"`: the ~20 internal branches keep reading it |
| `countText` | `readonly string` | `root.body.countText` (view bar) |
| `progress` | `readonly var` | `root.body.progress` |
| `formOpen` | `readonly bool` | `root.body.formOpen` |
| `setNote(document, shown)` | function | `document = { documentType, title, body, base }`; `shown({ ok, fallback })` once the body holds it (see below) |
| `clearNote()` | function | replaces `setNote("", "")`: bumps the token, empties title and base, `body.clear()`; the active body stays |
| `restoreDocument(snapshot)` | function → string | activates `snapshot.documentType`, sets title and base, returns `body.restore(snapshot.body, token)` (`""` = restored) |
| `snapshotDocument()` | function | `{ documentType, title, body: body.snapshot(), base: documentBase }` |
| `requestBody(document, callback)` | function | `bodyFor(document.documentType).request(document, callback)`; replaces `requestMarkdown` |
| `viewState()` / `restoreViewState(s)` | function | dispatched to `body` |
| `focusEditor()` / `focusBody()` | function | dispatched to `body` |
| `undo()` / `redo()` | function | dispatched to `body` (IPC `editorUndo`) |
| `bodyAction(action, argument)` | function → bool | `root.hasNote && !root.readOnly && root.body.act(action, argument)` |
| `wordCount`, `hoveredLink`, `tools`, `canColorText`, `toolbarHeight`, `toolbarRowHeight` | unchanged | document facts (`hoveredLink` is `""` unless `documentActive`) |

**Activation: type before body, by construction.**

```js
  // The body for a document type: the document editor for `text` and `markdown`, a type's
  // own body (created the first time, kept after) otherwise; null for no such type.
  function bodyFor(documentType) {
    var type = NoteTypes.entry(documentType)
    if (!type) {
      return null
    }
    if (type.body === "") {
      return documentBody
    }
    for (var i = 0; i < typedBodies.count; i++) {
      var slot = typedBodies.itemAt(i)
      if (slot.typeId === documentType) {
        return slot.create()
      }
    }
    return null
  }

  // Makes `documentType`'s body the one on screen. The body it replaces drops its note, so no
  // hidden document keeps a recording, an undo history or a form; the keyboard follows when
  // the old body had it.
  function activate(documentType) {
    var next = root.bodyFor(documentType)
    if (!next) {
      return false
    }
    var hadFocus = root.body.hasFocus
    if (next !== root.body) {
      root.body.clear()
    }
    root.documentType = documentType
    root.body = next
    if (hadFocus) {
      Qt.callLater(root.focusEditor)
    }
    return true
  }

  function setNote(document, shown) {
    var token = ++root.noteToken
    if (!root.activate(document.documentType)) {
      root.answer(shown, { ok: false, fallback: "" })
      return
    }
    root.settingText = true
    titleField.text = document.title
    titleField.cursorPosition = 0
    root.settingText = false
    root.documentBase = document.base || ""
    root.body.show(document.body, token, function(answer) {
      if (token !== root.noteToken) {
        return
      }
      if (answer.ok && answer.fallback) {
        root.showAsFallback(document, token, answer.fallback, shown)
        return
      }
      root.answer(shown, { ok: answer.ok, fallback: "" })
    })
  }

  // A body that cannot hold the note it was given: the same text in its type's fallback
  // body (a timeline that is no longer one, as the Markdown it is), the reason passed on.
  function showAsFallback(document, token, reason, shown) {
    if (!root.activate(NoteTypes.fallback(root.documentType))) {
      root.answer(shown, { ok: false, fallback: "" })
      return
    }
    root.body.show(document.body, token, function(answer) {
      if (token !== root.noteToken) {
        return
      }
      root.answer(shown, { ok: answer.ok, fallback: reason })
    })
  }

  function answer(shown, result) {
    if (shown) {
      shown(result)
    }
  }
```

**The `documentBody` adapter.** It calls the existing document code. The renames are:

- today's `viewState` and `restoreViewState` become `documentViewState` and `restoreDocumentViewState`, used by the adapter and `applyReadOnly`;
- the TextEdit's own undo and redo keys call `replayHistory` directly;
- `requestMarkdown` is removed;
- `resetAudio()` and `editing.clearPending()` move into `show`, `restore` and `clear`.

```qml
  QtObject {
    id: documentBody
    readonly property string countText: root.wordCount + (root.wordCount === 1 ? " word" : " words")
    readonly property var progress: null
    readonly property bool formOpen: false
    readonly property bool hasFocus: area.activeFocus
    function show(text, token, done) {
      root.resetAudio()
      editing.clearPending()
      if (root.plain || !root.markdown || !text) {
        root.showBody(text || "", token)
        done({ ok: true, fallback: "" })
        return
      }
      root.markdown.toHtml(text, function(html, ok) {
        if (token !== root.noteToken) {
          return
        }
        root.showBody(ok ? html : "", token)
        done({ ok: ok, fallback: "" })
      }, root.documentBase)
    }
    function restore(form, token) {
      root.resetAudio()
      editing.clearPending()
      root.showBody(form, token)
      return ""
    }
    function snapshot() {
      return root.plain ? root.plainText() : root.documentHtml()
    }
    function request(document, callback) {
      if (NoteTypes.entry(document.documentType).format === "plain" || !root.markdown) {
        callback(document.body, true)
        return
      }
      root.markdown.toMarkdown(document.body, function(markdown, map) {
        callback(map.ok ? map.note : "", map.ok)
      }, document.base)
    }
    function clear() {
      root.resetAudio()
      editing.clearPending()
      root.showBody("", root.noteToken)
    }
    function viewState() {
      return root.documentViewState()
    }
    function restoreViewState(state) {
      root.restoreDocumentViewState(state)
    }
    function focusEditor() {
      area.forceActiveFocus()
    }
    function focusBody() {
      root.showTop()
      area.forceActiveFocus()
    }
    function undo() {
      root.replayHistory(false)
    }
    function redo() {
      root.replayHistory(true)
    }
    function act(action, argument) {
      return false
    }
  }
```

`documentViewState()` keeps returning `{ cursor, scroll }`. `restoreDocumentViewState(state)`
ignores a state that is null, that lacks a numeric `cursor` and `scroll`, or that carries
`timeline: true`. A timeline's state is `{ timeline: true, cursor, scroll }`, and the timeline
body ignores any state without `timeline: true`. So a reload that changes a note's type never
moves a caret or a cursor by the other body's state.

**Typed bodies in the sheet.** These are siblings of `flick` (`ui/NoteEditor.qml:2001`), after it.

```qml
      Repeater {
        id: typedBodies
        model: NoteTypes.typedBodies()
        delegate: Loader {
          required property var modelData
          readonly property string typeId: modelData.typeId
          width: parent.width
          height: visible ? parent.height - y : 0
          visible: root.documentType === typeId && !root.showingNotice
          // Created once, the first time a note of the type opens, then kept: a body is
          // never destroyed while a request it started is still running.
          function create() {
            if (!item) {
              setSource(Qt.resolvedUrl(modelData.url), { host: bodyHost })
            }
            return item
          }
        }
      }
```

`Loader.setSource(url, { host })` sets the required property synchronously and without a
warning. The architect verified this with `qml6` at HEAD's Qt.

**Keeping the hidden document inert.** `documentActive` is added to:

- `EditorApi.writable` (`ui/editing/EditorApi.qml:13`), which becomes `host.hasNote && !host.readOnly && host.documentActive && !host.plain && !host.showingNotice`. Tools, the toolbar and tool shortcuts stand down; the strip keeps its row height (`ui/editing/ToolBar.qml:46`).
- `applyReadOnly()` (`:371-375`): `area.readOnly = !root.hasNote || root.readOnly || !root.documentActive`, re-run by `onDocumentActiveChanged`.
- `paste()` (`:388`), `pastePlain()` (`:514`) and `replayHistory()` (`:720`), each of which returns at once unless `root.documentActive`. IPC reaches all three.
- `flick.visible` (`:2002`): `!root.showingNotice && root.documentActive`.
- `hoveredLink` (`:84`).
- `Workspace.keyActions` paste guards (`Workspace.qml:2245-2250`): `!editor.documentActive || editor.plain || editor.readOnly ? false : editor.paste()`.

`bodyFocused` stays `area.activeFocus`, so a focused timeline is the `workspace` shortcut
context. Editor-context bindings (tools, `Ctrl+V`) can never match there.

**Workspace changes for the seam.**

- Remove the `plain:` binding (`Workspace.qml:2837-2840`).
- The view bar binds `countText: editor.countText` (`:2920`). `ui/ViewBar.qml` replaces `property int wordCount` with `property string countText`, and the label keeps `objectName: "wordCount"`.
- `debugState()` (`:1576-1619`) gains `"documentType"`, `"count"`, `"progress"` and `"formOpen"`.
- IPC `editorUndo` (`:1729-1733`) returns `editor.countText`.

### 5.5 How the session threads the type

`services/notes/NoteSession.qml` gains `import "capabilities.js" as Capabilities` and
`import "notetypes.js" as NoteTypes`, and changes in five places. No new per-path state
appears, so `replacePath` (F1) and `stored` (F14) need nothing new.

1. **`load()` start** (`:221-227`).
   - `editor.documentBase = ""` and `editor.setNote("", "")` become the following. A reload keeps the old document on screen until the answer, as today.

     ```js
     if (!reload) {
       editor.clearNote()
     }
     ```

   - `var capabilities = Capabilities.of(provider)` is taken once the provider is known.
   - The separate `editor.documentBase = result.base || ""` before `setNote` (`:262`, WT `:265`) is removed, because the document passed to `setNote` carries `base`.
2. **Draft branch** (`:236-245`):

   ```js
   var refusal = editor.restoreDocument(draft.document)
   session.editingView = draft.view || null
   session.noteReady(refusal !== "", refusal)
   ```

3. **Answer branch** (`:263-300`, WT `:266-303`):

   ```js
   var opened = NoteTypes.opened(capabilities, result)
   editor.setNote({ documentType: opened.documentType, title: result.title || "",
                    body: result.body || "", base: result.base || "" }, function(shown) {
     if (!session.ownsLoad(path, generation)) {
       return
     }
     if (!shown.ok) {
       session.noteUnavailable(session.notDisplayable)
       return
     }
     if (view) {
       editor.restoreViewState(view)
     }
     session.editingView = result.view || (session.resolvedPath(path) !== path ? session.editingView : null)
     // A note opens read-only when its provider says so (the local provider when the editor
     // would not write all of it back) or when its type cannot be shown here.
     if (result.editable === false) {
       session.noteReady(true, result.reason || "")
     } else if (opened.readOnly) {
       session.noteReady(true, opened.reason)
     } else {
       session.noteReady(false, "")
       if (shown.fallback) {
         session.report(shown.fallback)
       }
     }
     … recovered / stored branches unchanged: both take editor.snapshotDocument(), which now
       carries documentType …
   })
   ```

4. **`isStored`** (`:364-367`, WT `:405-409`) compares `documentType` too:

   ```js
   return !!known && known.path === path && known.document.documentType === document.documentType
     && known.document.title === document.title && known.document.body === document.body
   ```

5. **`flushSave`** (`:493`, WT `:538`): `editor.requestMarkdown(function(body, ok) {…})` becomes
   `editor.requestBody(draft.document, function(body, ok) {…})`. The conversion runs on
   exactly the snapshot registered as the draft, not on live state.

**What this preserves.**

- `noteToken` still decides races.
- Drafts, recovered drafts and deletion-recovery documents are snapshots, so each carries its `documentType` and restores into the body that made it.
- `stored` holds the snapshot, so a check followed by an uncheck sends no save (the timeline's snapshot form is deterministic, §5.6.6).
- Framed conversion failures keep the draft ("the note could not be read for saving").

**Workspace (Phase 0 capabilities, extended in Phase 1).**

- `readonly property var openCapabilities: Capabilities.of(root.providerOf(root.currentPath))`.
- The editor binds:
  - `canImages: root.openCapabilities.canImages`;
  - `hasTitle: root.openCapabilities.hasTitle`, which fixes the absent-`hasTitle` warning;
  - `enabledTools: root.openCapabilities.tools`.
- `newNote` focuses through `Capabilities.of(p).hasTitle` (`:1932`).

### 5.6 The timeline body format

#### 5.6.1 Model

A timeline is an ordered list of at most **500** events. An event is
`{ checked: bool, title: string, description: string }`.

| Field | Rule |
|---|---|
| `title` | One line of plain text, 1–256 UTF-16 code units (JS `.length`, Python `len(t.encode("utf-16-le")) // 2`). No control characters (U+0000–U+001F, U+007F–U+009F, U+2028, U+2029), no leading or trailing whitespace (Python `str.strip`). |
| `description` | `""`, or 1–40 **lines** joined by `"\n"`, at most 4096 code units in all. Each line follows the title's rules. There are no empty lines. |
| `checked` | Boolean. |

Text is plain: no Markdown, links or formatting. An event's text is drawn with
`Text.PlainText`.

#### 5.6.2 Canonical form

Canonical form is the only thing the codec writes. It is exactly what the editor's own writer
produces for `<ul><li class="checked|unchecked"><p>title</p><p>line</p>…</li></ul>`:

```
body        = "" | event { event }
event       = marker " " escaped(title) LF { LF "  " escaped(line) LF }
marker      = "- [ ]" | "- [x]"
```

- One event per task item, with no blank line between events.
- The title is the item's first paragraph.
- Each description line is its own paragraph, after a blank line, indented two spaces.
- LF endings, and the body ends with one LF. An empty timeline is the empty string.
- There are **no** trailing-space hard breaks, so an editor that strips trailing spaces cannot merge a title and its description.
- `escaped` is not the codec's own. The writer is `qthtml.convert(html)["note"]` (`services/markdown/qthtml/reader.py`), which escapes with `mdtext.escape_inline`/`escape_line_start` as it does for every note. Examples, verified:

| Title or description line | Written as |
|---|---|
| `2 * 3 = 6 [draft] #1` (title) | `2 * 3 = 6 [draft] #1` |
| `+` (description line) | `\+` (with the P0 fix) |
| `- not a list` | `\- not a list` |
| `1. not ordered` | `1\. not ordered` |
| `use a_b and *stars*` | `use a_b and \*stars\*` |

#### 5.6.3 Worked example: before and after a check

The whole local file is shown, with the front matter written by `notefile.py`:

```
---
title: Trip to Lisbon
note-note-type: timeline
---
- [x] Book flights

  Return on the 14th
- [x] Reserve hotel
- [ ] Pack the bags

  Passport, adapters

  Chargers
- [ ] Go to the airport
```

Space on "Pack the bags" checks events 1–3. Events 1 and 2 are already checked, so only
event 3 changes and no status is said. Body after the save:

```
- [x] Book flights

  Return on the 14th
- [x] Reserve hotel
- [x] Pack the bags

  Passport, adapters

  Chargers
- [ ] Go to the airport
```

Both bodies were produced by the prototype at HEAD with the P0 fix
(`scratchpad/plan/exp/codec_check.py`). Space on "Reserve hotel" afterwards unchecks events 2–4:
`- [x] Book flights …`, `- [ ] Reserve hotel`, `- [ ] Pack the bags …`, `- [ ] Go to the airport`.
The status line says `Unchecked 2 events, from “Reserve hotel” down`; event 4 was already
unchecked.

#### 5.6.4 Reading (tolerant, structural)

`services/markdown/timeline.py`, `read(markdown) -> [event]`, raises `NotTimeline(reason)`.

1. `tokens, definitions = parse.parse_with_definitions(markdown)` (a new `parse.py` function, P0). `parse.py` already drops `\r`, so CRLF and lone CR read as LF.
2. If `definitions` is non-empty, refuse with **"a link definition"**. mistune consumes them without a token (§4.6), so a reader that rebuilt the body from tokens would drop them.
3. Blocks are the tokens minus `blank_line`. None means an empty timeline, `[]`.
4. There must be exactly one block, of type `list`, with `attrs.ordered` false. Otherwise refuse with **"text outside its list of events"**. This covers a heading, a paragraph before or after the list, two lists, an ordered list, a table, a rule, HTML, a quote or a code block at top level.
5. At most 500 items, else **"more than 500 events"**.
6. Each item must be a `task_list_item`, else **"an item without a checkbox (item N)"**.
7. Each item's children minus `blank_line` must all be `paragraph` or `block_text`, else **"an event holding more than text (event N)"** (a nested list, quote, code block or heading). There may be 1 + at most 40 of them, else **"more than 40 description lines (event N)"**.
8. A paragraph's inline children must be `text` or `softbreak` only. A soft break reads as one space, so a wrapped line renders and reads as one line. Anything else refuses with words for the token: `strong` → **"bold text"**; `emphasis` → **"italic text"**; `link` → **"a link"**; `image` → **"a picture"**; `codespan` → **"inline code"**; `linebreak` → **"a line break"**; `strikethrough` → **"struck-through text"**; `mark` → **"highlighted text"**; `inline_html` → **"HTML"**; `audio` → **"a recording"**; any other → **"formatting"**, each followed by " (event N)".
9. The title is paragraph 1's text, stripped. Empty refuses with **"an event without a title (event N)"**. Over 256 units refuses with **"a title longer than 256 characters (event N)"**. A control character refuses with **"a control character (event N)"**.
10. The description is paragraphs 2…, each stripped, joined by `"\n"`, over 4096 units refusing with **"a description longer than 4096 characters (event N)"**.
11. `checked` is `item.attrs.checked`, so `[x]` and `[X]` both read as checked.

**Tolerated variants.** These are accepted, and written canonically only when the user next changes something.

| Variant | Canonical rewrite |
|---|---|
| blank lines between items | none between items |
| `*` or `+` bullets | `-` |
| `[X]` | `[x]` |
| CRLF | LF |
| a soft-wrapped title (`- [ ] Pack the\n  bags`) | `- [ ] Pack the bags` |
| a soft-wrapped description paragraph | one line |
| a description indented four spaces | two spaces |
| entity text | kept literal, as the editor does |

**Refused.** These open as Markdown with **"This timeline holds <reason>, so it opened as Markdown"**:

- a heading, or a paragraph before or after the list;
- a plain bullet item;
- a nested list;
- bold, italic, a link or an autolink, inline code, inline HTML;
- a backslash or two-space hard break;
- an empty task (`- [ ]`);
- an HTML comment;
- a link definition;
- two lists;
- an ordered list.

All of these outcomes were verified with the planner's prototype on a clean HEAD copy.

#### 5.6.5 Writing (fail-closed)

`write(events) -> markdown`, raises `ValueError`.

1. Validate each event: a dict with exactly `checked` (bool), `title` and `description` (str) under the model rules, at most 500 events. Any violation raises `ValueError("the timeline could not be written: <why>")`.
2. Build `<ul>` + `<li class="checked|unchecked"><p>{title}</p>` + `<p>{line}</p>`… + `</li>` + `</ul>`, with `html.escape(text, quote=False)`.
3. `markdown = qthtml.convert(html)["note"]`, the editor's reader. The output is therefore the editor's own fixpoint by construction.
4. Self-check: `read(markdown) == events`, else `ValueError("the timeline could not be written as it is")`. The save then fails with the draft kept, and nothing is written.

`summary(events) -> {"done", "total", "next"}`. `done` counts checked events. `next` is the
title of the first unchecked event, or `""`.

**CLI.** `python3 services/markdown/timeline.py read|write`.

- The payload is on stdin, capped at `MAX_BYTES = 8 MiB` like qthtml. Over the cap means exit 1 and no frame.
- `read` answers `{"events": [...]}` or `{"notTimeline": "<reason>"}`.
- `write` reads JSON `{"events": [...]}` through `lib/jsondata.parse` (strict, depth-bounded) and answers `{"markdown": "..."}`. An invalid model answers `{"error": "..."}` with exit 1.
- An unknown verb prints the usage and exits 2.
- A crash prints nothing, so there is no frame. The host treats any answer without its key as a failure.

**Guarantees, each tested (§7).**

1. `read(write(m)) == m` for every valid model.
2. `qthtml.to_markdown(qthtml.to_html(write(m))) == write(m)`, so the editor round trip is a fixpoint, both in the pure path and through Qt.
3. `qthtml.unkept(write(m)) == []`.
4. `read(to_markdown(to_html(write(m)))) == m`. An older Note Note, or a host that opens the note as Markdown, saves it without changing an event.
5. Text that `read` refuses is never written by the timeline body.
6. No timeline save writes the type marker.

Verified at HEAD with the P0 `mdtext` fix:

- 3000 random models with multi-line descriptions over a pool of Markdown metacharacters, entities, emoji and NBSP gave 0 failures for 1–4;
- 53 edge lines (55 tried; a tab and a leading NBSP are refused by the model before any write) as titles and as description lines gave 0 problems;
- 19 of 19 samples were unchanged through Qt.

Without the fix, 14 of 3000 fail, all of them on a lone `+`. Each failure is fail-closed.

#### 5.6.6 The snapshot form (host side)

`TimelineModel.form(events)` = `JSON.stringify(events.map(e => [e.checked ? 1 : 0, e.title, e.description]))`.

- It is deterministic, so equal events give an equal string, and `isStored` is exact without a conversion.
- `TimelineModel.fromForm(text)` parses it back and validates every rule above, giving `null` on any violation.
- The pending event of an open form is part of the form (§5.8.4).

#### 5.6.7 Limits

| Limit | Value | Enforced |
|---|---|---|
| events | 500 | `read`, `write`, `fromForm`, the add row ("A timeline holds at most 500 events") |
| title | 256 UTF-16 units | `read`, `write`, `fromForm`, title field `maximumLength: 256` |
| description | 4096 units, 40 lines | `read`, `write`, `fromForm`, the description field refuses input past it, with a message |
| codec input | 8 MiB | `timeline.py` stdin |
| list progress read | 64 KiB of file | `notefile.TIMELINE_PREVIEW_BYTES` (§5.11) |

A maximal timeline can exceed the local 2 MiB note limit. The save then fails with "note
exceeds the 2 MB limit" and the draft is kept (§9 R17).

### 5.7 Check semantics

**Rule (U1).** These are pure functions in `ui/notetypes/timeline/TimelineModel.js`:

```js
// Checking event `index` checks it and every event above it; unchecking it unchecks it and
// every event below it. Events the rule does not reach keep their state, so an order broken
// elsewhere is mended exactly as far as the user's own action reaches.
function setChecked(events, index, checked) {
  return events.map(function(event, at) {
    var reached = checked ? at <= index : at >= index
    if (!reached || event.checked === checked) {
      return event
    }
    return { checked: checked, title: event.title, description: event.description }
  })
}

function toggle(events, index) {
  return setChecked(events, index, !events[index].checked)
}
```

**Truth table.** Five events. `x` = checked, `-` = not.

| Before | Action | After | Changed | Status line |
|---|---|---|---|---|
| `x x - - -` | Space on 4 (unchecked) | `x x x x -` | 2 | `Checked 2 events, up to “4”` |
| `x x - - -` | Space on 3 | `x x x - -` | 1 | — |
| `x x x x -` | Space on 2 (checked) | `x - - - -` | 3 | `Unchecked 3 events, from “2” down` |
| `x x x x x` | Space on 5 (checked) | `x x x x -` | 1 | — |
| `- - - - -` | Space on 5 | `x x x x x` | 5 | `Checked 5 events, up to “5”` |
| `x - x - -` (out of order) | Space on 2 (unchecked) | `x x x - -` | 1 | — |
| `x - x - -` | Space on 3 (checked) | `x - - - -` | 1 | — |
| `x - x - -` | Space on 5 | `x x x x x` | 3 | `Checked 3 events, up to “5”` |
| `- x - - -` | Space on 1 (unchecked) | `x x - - -` | 1 | — |

(“4” stands for event 4's title.)

**Out-of-order states.** These come from another editor, a phone or a sync.

- They are shown exactly as stored: each circle shows its own state, and a spine segment is accent only between two checked events.
- `progress` counts checked events, and `next` is the first unchecked one.
- They are never repaired on open, and nothing is written until the user acts.

**Undo.**

- The body keeps its own stack of `{ form, cursor }` (`form` = the snapshot string), at most 200 steps.
- There is one step per user action: check, uncheck, add, edit session, delete, move and discard.
- `Ctrl+Z` undoes. `Ctrl+Shift+Z` and `Ctrl+Y` redo (`services/shortcuts/stroke.js` `redoes`).
- A new action clears redo. Both stacks clear when another note is shown.
- Each undo or redo is an edit: it emits `edited()` and is saved.

### 5.8 The timeline view

#### 5.8.1 Files

| File | What it is |
|---|---|
| `ui/notetypes/timeline/TimelineBody.qml` (new) | The `NoteBody`. Holds the events array (the truth), a `ListModel` of rows patched in place, the cursor, the form state, the undo stacks and the key handling. |
| `ui/notetypes/timeline/TimelineEvent.qml` (new) | One row: rail (spine segments, check circle), title, description, or the edit form in place. |
| `ui/notetypes/timeline/EventForm.qml` (new) | The inline form: title, description, hint or message, one button. |
| `ui/notetypes/timeline/TimelineModel.js` (new) | Pure model: `setChecked`, `toggle`, `changedCount`, `append`, `replace`, `remove`, `move`, `withPending`, `form`, `fromForm`, `validEvents` (an answer from the codec, checked against every model rule), `patch`, `cleanTitle`, `cleanDescription`, `problem`, `progress`, `nextIndex`, `countText`, the limits. |
| `ui/CheckFace.qml` (new) | The drawn check face extracted from `ui/NoteEditor.qml:2242-2284`, with `round`. |
| `ui/ChromeTextArea.qml` (new) | A multi-line input on `ChromeControlStyle` (`QQC.TextArea`), the design system's first. |

#### 5.8.2 Structure and model

```
TimelineBody (NoteBody, FocusScope, objectName "timelineBody")
└─ Column
   ├─ ListView  id: list, objectName "timelineList"   model: rows (ListModel: checked, title, description)
   │    height: Math.min(contentHeight, parent.height - addArea.height)   ← short lists end at their last event
   │    delegate: TimelineEvent      scroll bar: QQC.ScrollBar "timelineScrollBar", ListWheel { flick: list }
   └─ AddArea (FocusScope) — the "Add new event" row, the empty state, or the add form (EventForm)
```

**Why the add area sits outside the ListView.** A ListView model reset gives its new current
item focus and takes it from a field in the ListView's own footer (planner's `qml6` check,
§4.7). A field outside the ListView keeps focus and text. The add form therefore never loses
focus when events change.

**Why a `ListModel` mirror.** The array `events` is the truth (pure functions, snapshot,
undo). The `ListModel` `rows` is patched in place by
`TimelineModel.patch(before, after) -> [{ op: "set"|"insert"|"remove", index, event }]`, the
fewest row changes. Rows that did not change keep their delegate (planner's `qml6` check: `set`, `setProperty`, `append`, `remove` and `move` on other rows leave a focused field in a delegate the same item, focused, with its text), which keeps:

- an open edit form;
- the hover state;
- the 120 ms colour transitions;
- the scroll position.

An array swap would destroy them and reset the scroll. The roles are uniform (three, always
present), so the engine note's reason to prefer arrays (`docs/engine-notes.md:47`: roles fixed
at the first insert) does not apply. `show()` and a multi-step undo may use a full reset
(clear, then append), which saves `contentY - originY`, calls `forceLayout()` and restores it
(`docs/engine-notes.md:42-45`). This is recorded in `docs/decisions.md` (§8).

```js
// The fewest row changes that turn `before` into `after`.
function patch(before, after) {
  var start = 0
  while (start < before.length && start < after.length && same(before[start], after[start])) {
    start++
  }
  var endBefore = before.length
  var endAfter = after.length
  while (endBefore > start && endAfter > start && same(before[endBefore - 1], after[endAfter - 1])) {
    endBefore--
    endAfter--
  }
  var common = Math.min(endBefore, endAfter) - start
  var ops = []
  for (var i = start; i < start + common; i++) {
    if (!same(before[i], after[i])) {
      ops.push({ op: "set", index: i, event: after[i] })
    }
  }
  for (var r = endBefore - 1; r >= start + common; r--) {
    ops.push({ op: "remove", index: r })
  }
  for (var n = start + common; n < endAfter; n++) {
    ops.push({ op: "insert", index: n, event: after[n] })
  }
  return ops
}
```

#### 5.8.3 Layout and states

The view uses only Style keys both hosts define, and no new theme tokens. Ink derives from the
pane's `foreground`, `background` and `accent` (`bodyHost`), `ChromeControlStyle`'s `input.*`
and `border.focus`, `Color.urgent`, `Util.alpha`, and Style's fill helpers. Glyph `Text`s use
`Style.fontFamily`. Checks are drawn shapes, not glyphs.

**Geometry**

| Element | Spec |
|---|---|
| Circle side | `Math.round(host.bodyFontSize * 1.1)` |
| Rail width | `side + 2 * Style.spacing.lg`. The circle is centred in the rail and on its title's first line. |
| Spine | Width `Math.max(2, Math.round(side * 0.12))`, centred. Each row draws a segment above its circle (none on the first row) and one below (to the next row, or to the add row's circle), so rows abut into one line. |
| Row padding | `Style.spacing.md` top and bottom; text column after the rail |
| Title | `host.noteFontFamily`, `host.bodyFontSize`, `Text.PlainText`, wraps |
| Description | Under the title. `host.noteFontFamily`, `Math.round(host.bodyFontSize * 0.92)`, `lineHeight: 1.2`, `Text.PlainText`, wraps. One text line per description line. |

**Rows**

| State | Circle | Text | Row |
|---|---|---|---|
| unchecked | border `Util.alpha(fg, 0.4)`, width `Math.max(1.2, side / 9)`, no fill | title full ink | — |
| unchecked, hovered | border alpha 0.75; pointing-hand cursor over the circle | — | fill `Style.hoverFillFor(fg, accent)` |
| checked | `CheckFace` round: accent fill, tick cut out in `host.background` | title `Style.secondaryText(fg, 0.55)`, description `0.45`; no strikethrough (U3) | — |
| next (first unchecked) | accent ring, border `Math.max(1.5, side / 7)` in accent | title bold, full ink | — |
| cursor (list has active focus) | 2 px accent ring 2 px outside the circle (the `ui/tools/TextColor.qml:65` swatch precedent) | — | fill `Style.selectedFillFor(fg, accent)` |
| editing | — | title and description become the `EventForm` in place | — |
| read-only | inert: no hover, no pointer, no menu | — | — |

**Spine segments.** A segment between events *i* and *i+1* is accent ink
(`Qt.tint(fg, Util.alpha(accent, 0.6))`) when both are checked, and `Util.alpha(fg, 0.18)`
otherwise.

**Motion.** Circle fill, circle border and spine colours animate over 120 ms. On a check or
uncheck that reaches several events, each row's animation waits
`Math.min(250, 25 * Math.abs(index - acted))` ms, so the fill runs from the acted event outward.
The body records `acted` (the event acted on) for the delegates.

**Add area** (writable only)

- Each element sits on the rail: the "Add new event" row, the form, or nothing, followed by the empty state.
- The **Add new event** row (`objectName: "timelineAddEvent"`):
  - a hollow circle (border alpha 0.3) on the rail holding `+` (U+F0415) in accent ink;
  - the label "Add new event" in accent ink;
  - both dimmed to `Style.secondaryOpacity(0.65)` until hovered or under the cursor, the `+ New note…` look (`ui/NoteList.qml:453-498`);
  - a right-aligned hint `Ctrl+Enter` in `Style.font.caption`, `Style.secondaryText(fg, 0.45)`.
- At 500 events the row reads "A timeline holds at most 500 events" and cannot be opened.
- **Empty state** (`objectName: "timelineEmpty"`): when there are no events and no form, a faint hollow circle and "No events yet" in `Style.secondaryText(fg, 0.55)`, `Style.font.bodySmall`, above the add row.
- A writable empty timeline that is reached from the title (`focusBody()`) opens the form at once (§5.8.5).

**Read-only.** No add area, no form, no menu, circles inert. The cursor still moves.

**Loading.** The pane's existing skeleton.

#### 5.8.4 The form

`EventForm.qml` is used in the add area (adding) and inside a row (editing).

| Part | Spec |
|---|---|
| Title | `ChromeTextField`, `objectName "timelineFormTitle"`, placeholder "Event title", `iconText` U+F1533, `maximumLength: 256`, note font, `Accessible.name: "Event title"`. |
| Description | `ChromeTextArea`, `objectName "timelineFormDescription"`, placeholder "Description (optional)", 1 line tall growing to 8 then scrolling, `Accessible.name: "Event description"`. Input past 4096 units or 40 lines is refused: the field reverts to its last accepted text and the message says "A description holds up to 4096 characters and 40 lines". |
| Footer | `objectName "timelineFormMessage"`. A hint in `Style.font.caption`, `Style.secondaryText(fg, 0.45)`: adding, "Enter to add · Shift+Enter for a new line · Esc to discard"; editing, "Enter to save · Shift+Enter for a new line · Esc to cancel". Replaced by a message in `Color.urgent` while one applies. |
| Button | One `Button` "Add" or "Save", `objectName "timelineFormSubmit"`, focusable: false. There is no Cancel button and no labels above fields: the `ToolForm` conventions (`docs/editing-tools.md:350-358`). |

**Semantics (U6).**

- **The form is part of the note.**
  - Form state lives in the body: `form = { mode: "add"|"edit", index, title, description, checked }`. It never lives in a delegate.
  - Every text change updates `form` and calls `host.edited()`.
  - `snapshot()` is `TimelineModel.form(TimelineModel.withPending(events, form))`. While adding, the pending event is appended once its cleaned title is non-empty and valid. While editing, the edited event shows the typed text while its title is non-empty and valid, and keeps its old text otherwise.
  - So a note switch, a window close or a crash keeps what was typed, and the snapshot is never invalid.
- **Enter in either field (or the button).**
  - Adding, both fields empty: close the form.
  - Title empty but description not: the message "Give the event a title".
  - Otherwise commit: one undo step, the event appended, the form cleared and **kept open** for the next event, so typing several events in a row is fast.
  - Editing: commit the edit, close the form, and put the cursor on the event. Emptying both fields and pressing Enter deletes the event (undoable).
- **Shift+Enter** in the description inserts a line. The `TextArea` does it, and on commit the text is cleaned: lines trimmed, empty lines dropped.
- **Esc.**
  - Adding: discard the pending event (one undo step brings it back as an event when it had a title), close the form, and put the cursor on the add row.
  - Editing: the event gets back its text from before the edit, and the form closes.
- **Focus leaving.**
  - Adding: nothing happens. The form stays open with its text.
  - Editing: the edit finishes as if Enter were pressed (valid) or Esc (invalid).
- **One form at a time.** Opening the add form commits an open edit. A change elsewhere (a click on another circle) commits an open edit first.

#### 5.8.5 Keyboard map

Every key handler is **one** `Keys.onPressed`. Specific `Keys.on<Key>Pressed` handlers are not
used, because Qt runs them before `onPressed` (§4.2).

**List focused** (`list` holds the keyboard). First `host.shortcut(event)`: if the app took the
key (`Escape` = back, `Ctrl+Up/Down` = other note, `Ctrl+K`, `Ctrl+N`, `Ctrl+Shift+T`, …),
stop. Then:

| Key | Action |
|---|---|
| `Up` / `Down` | Previous or next event. `Down` past the last event reaches the add row. `Up` from the first event focuses the note's title (`host.focusTitle()`). |
| `Home` / `End` | First event / add row (the last event when read-only). |
| `PageUp` / `PageDown` | Move by the events visible in the list (`list.indexAt` at its top and bottom edges), at least one. |
| `Space` | Toggle the cursor event (§5.7). |
| `Return` / `Enter` | Edit the cursor event in place. |
| `Ctrl+Return` / `Ctrl+Enter` | Open the add form. |
| `Delete` | Delete the cursor event. Status: `Deleted “Pack the bags” · Ctrl+Z brings it back`. |
| `Alt+Up` / `Alt+Down` | Move the cursor event up or down. The cursor follows. |
| `Ctrl+Z` / `Ctrl+Shift+Z`, `Ctrl+Y` | Undo / redo. |
| `Menu` (the context-menu key) | Open the event's menu. |

**Add row focused.** `host.shortcut` first, then:

| Key | Action |
|---|---|
| `Return`, `Enter`, `Space`, `Ctrl+Enter` | Open the form. |
| A printable character (`event.text` non-empty, no Ctrl/Alt/Meta) | Open the form with that character in the title. |
| `Up` | Last event. |
| `Home` | First event. |

**Form fields focused.** In this order:

1. `Escape` → discard or cancel (accepted, so `back` never sees it).
2. `Return`/`Enter`:
   - without Shift → commit;
   - with Shift in the description → let the `TextArea` insert a newline;
   - with Shift in the title → commit.
3. `Tab` / `Backtab` → switch field.
4. `Down` in the title → description. `Up` on the description's first line (cursor y < its line height) → title.
5. `host.shortcut(event)`.
6. The field's own handling. `Ctrl+Z` is the field's text undo, because no binding takes reserved keys.

**From the note's title.** `Return`, `Enter` and `Down` call `focusBody()`:

- an empty writable timeline opens the add form;
- otherwise the cursor goes to the next unchecked event (the add row when all are done), and the list scrolls it to the centre.

**Opening a note** (row click, search, `Ctrl+Up/Down`). `focusEditor()` focuses the list, with
the cursor on the next event. `activate()` moves the keyboard to the new body when the old one
had it.

**Shortcut context.** A focused timeline is `workspace`: `bodyFocused` stays the TextEdit's
(`ui/NoteEditor.qml:72`), so tool and paste bindings never fire there. Timeline keys are local
handling, as the TextEdit's own keys are. Bare keys could not be registry bindings anyway
(`services/shortcuts/resolve.js:137-148`).

#### 5.8.6 Mouse

| Gesture | Action |
|---|---|
| Click a circle (`TapHandler`) | Toggle (§5.7). The circle does not take focus. |
| Click a row's text | Cursor there; the list takes focus. |
| Double-click the text | Edit in place. |
| Right-click a row | The event menu: `ui/RowMenu.qml` reused with a row-shaped object `{ index, menu: [...] }`, `objectName "timelineMenu"`. Items: Edit (U+F03EB), Move up (U+F005D), Move down (U+F0045), Delete (U+F01B4); the items that cannot apply are left out. `RowMenu.qml`'s header comment is generalised to "a row-shaped `{ menu }`". |
| Click the add row | Open the form. |
| Wheel | `ListWheel { flick: list }`, the shared feel. |

Drag reordering is later work.

#### 5.8.7 Accessibility

This is a new precedent, documented in `docs/note-types.md`.

| Item | Accessible properties |
|---|---|
| list | `Accessible.role: Accessible.List`, `name: "Timeline"` |
| each row | `Accessible.role: Accessible.CheckBox`, `name: title`, `description: description`, `checkable: true`, `checked: checked`, `onToggleAction` and `onPressAction` → `body.toggle(index)` |
| add row | `Accessible.role: Accessible.Button`, `name: "Add new event"`, `onPressAction` → open the form |
| form fields | named "Event title" and "Event description" |

#### 5.8.8 Object names (for tests)

| Object name | Item |
|---|---|
| `timelineBody` | the body |
| `timelineList` | the list |
| `timelineScrollBar` | the list's scroll bar |
| `timelineEvent-<i>` | row *i* |
| `timelineCheck-<i>` | row *i*'s circle |
| `timelineTitle-<i>` | row *i*'s title text |
| `timelineDescription-<i>` | row *i*'s description text |
| `timelineAddEvent` | the add row |
| `timelineEmpty` | the empty state |
| `timelineForm` | the form |
| `timelineFormTitle` | the title field |
| `timelineFormDescription` | the description field |
| `timelineFormMessage` | the hint or message |
| `timelineFormSubmit` | the button |
| `timelineMenu` | the event menu |

#### 5.8.9 Body behaviour

How the body implements the protocol.

**Displaying a note**

| Member | Behaviour |
|---|---|
| `show(text, token, done)` | `clear()`. An empty text shows an empty timeline and answers ok. Otherwise `host.markdown.toTimeline(text, …)`. A stale token (`!host.current(token)`) is dropped. A failed run answers ok false. `notTimeline` answers `{ ok: true, fallback: "This timeline holds " + reason + ", so it opened as Markdown" }`. `events` failing `TimelineModel.validEvents` answers ok false. Otherwise the events are shown, the cursor goes to `nextIndex`, the view goes there, and ok. |
| `restore(form, token)` | `fromForm(form)`, then show those events. Answers `"This timeline could not be put back"` when it is `null`. |
| `snapshot()` | `form(withPending(events, form))`. |
| `request(document, callback)` | `fromForm(document.body)`: `null` → `callback("", false)`; else `host.markdown.fromTimeline(events, callback)`. Body state is not used, so a request outlives any later note. |
| `clear()` | events `[]`, `rows.clear()`, cursor -1, form null, undo and redo `[]`. |

**View and focus**

| Member | Behaviour |
|---|---|
| `viewState()` | `{ timeline: true, cursor, scroll: list.contentY - list.originY }` |
| `restoreViewState(s)` | Only for `s.timeline`. The cursor is clamped; `forceLayout()`, then `contentY` is restored. |
| `focusEditor()` | The form's title when a form is open; else the list (cursor `nextIndex` when unset). |
| `focusBody()` | §5.8.5. |
| `countText` | "No events" · "Done" · "All 4 done" · "2 of 4 done", from `withPending`. |
| `progress` | `TimelineModel.progress(withPending(events, form))` |
| `formOpen` | `form !== null` |

**Editing**

| Member | Behaviour |
|---|---|
| `undo()` / `redo()` | Pop the stack. `fromForm`, then patch the rows, then `host.edited()`. |
| `act("addEvent")` | Open the add form; `true` when writable. |
| `act("toggle", i)` | Toggle event `i`; `true` when it exists and is writable. |
| `commit(next, cursor, status)` | Every user change. Returns early when read-only. Pushes an undo step, clears redo, patches the rows, sets the cursor, calls `host.edited()`, and says the status when there is one. |

### 5.9 Creation UX and commands

**Surfaces (U9, U15).**

| Surface | Path |
|---|---|
| Local footer **New Timeline** (U+F0F97), after New Note in every notebook footer and in the folded-tree footer | `{ path: "newTimeline", title: "New Timeline", icon: "󰾗" /* U+F0F97 */, shortcut: "newTimeline" }` → local `action("newTimeline", "", sectionKey)` → `host.newNote(root.id, target, "timeline")`, with the **same target rule as New Note** (`notebookTabs ? "section:" + sectionKey : createTargetFor(host.currentPath)`) |
| `Ctrl+Shift+T` | workspace action `newTimeline` → `host.newNote("", undefined, "timeline")`, which runs `activateFooterShortcut("newTimeline")` first: the provider's own row and target. A notebook tab with no note open files the timeline in that tab. |
| Palette **New Timeline** | `plugins/org.note-note.workspace/plugin.json` command `new-timeline`, `workspaceAction: "newTimeline"` |
| Palette **Add Timeline Event** | command `add-timeline-event`, `workspaceAction: "addTimelineEvent"`, with no default key |
| hello example | its own New Timeline footer row and `action("newTimeline")` |

`+ New note…` rows (kind `new`) keep making the default type. There are no row-menu items: row
menus are pointer-only, and `runRowAction` locks the session.

**Host code (`Workspace.qml`).**

```js
  function newNoteDestination(providerId, target, noteType) {
    var p = providerId ? providerById(providerId) : activeProvider()
    if (p && noteType && !Capabilities.creationType(Capabilities.of(p), noteType)) {
      if (providerId) {
        return { provider: p, target: "", refusal: p.name + ": this notebook cannot hold " + NoteTypes.noun(noteType) }
      }
      p = null
    }
    if (p && target === undefined) {
      target = p.createTargetFor(root.currentPath)
    }
    if (!providerId && (!p || !target)) {
      p = root.providers.find(function(candidate) {
        var holds = !noteType || Capabilities.creationType(Capabilities.of(candidate), noteType) !== ""
        return candidate.canCreate && holds && candidate.createTargetFor("")
      })
      target = p ? p.createTargetFor("") : ""
    }
    return { provider: p, target: target, refusal: "" }
  }
```

**`newNote(providerId, target, noteType)`** (replaces `:1887-1938`):

1. If `!providerId`: `var shortcut = noteType ? NoteTypes.footerShortcut(noteType) : "newNote"`. If the shortcut is set and `activateFooterShortcut(shortcut)` runs, return.
2. Flush the save and clear the filter, as today.
3. Call `newNoteDestination(providerId, target, noteType)`.
   - A `refusal` is said on the status line, and the function returns.
   - No provider or no target, typed: status "No notebook here can hold timelines" (`NoteTypes.noun`).
   - No provider or no target, untyped: `startNewNotebook()` as today.
4. Compute `var type = Capabilities.creationType(Capabilities.of(p), noteType)`. If it is `""`, say "<name>: this notebook cannot hold <noun>" and return.
5. Call `p.create(target, cb, { noteType: type })`. The callback is unchanged except that focus goes to the title through `Capabilities.of(p).hasTitle` (`:1932`).

**`services/commands/WorkspaceActions.qml`**

```js
    newTimeline: function() {
      host.newNote("", undefined, "timeline")
    },
    addTimelineEvent: function() {
      host.runBodyAction("addEvent")
    },
```

`state` gains `documentType: host.documentType` and `editorWritable: host.editorWritable`,
where Workspace defines:

- `readonly property string documentType: editor.documentType`;
- `readonly property bool editorWritable: session.writable`;
- `function runBodyAction(name)` → `editor.bodyAction(name)`.

`canCreateNote(noteType)`:

- `var shortcut = noteType ? NoteTypes.footerShortcut(noteType) : "newNote"`;
- available when that footer exists;
- or, untyped, when a `newNotebook` footer exists;
- or when `host.newNoteDestination(undefined, undefined, noteType)` yields a provider that creates, a target and no refusal.

`unavailable()` gains:

| Action | When unavailable | Reason |
|---|---|---|
| `newTimeline` | `!canCreateNote("timeline")` | "Open a notebook that can hold timelines." |
| `addTimelineEvent` | `state.documentType !== "timeline" \|\| !state.editorWritable` | "Open a timeline you can edit." |

`blocked` is **not** gated on `formOpen`. The form is part of the note, every app shortcut is
safe under it, and the form claims `Escape` itself.

**`services/shortcuts/defaults.js`**

```js
  { id: "newTimeline", workspace: true, keys: ["Ctrl+Shift+T"], context: "notes", group: "Notes", description: "A new timeline in the open notebook" },
  { id: "addTimelineEvent", workspace: true, keys: [], context: "workspace", group: "Notes", description: "Add an event to the open timeline" },
```

**`plugins/org.note-note.workspace/plugin.json`**

```json
{ "id": "new-timeline", "title": "New Timeline", "category": "Notes",
  "keywords": ["create", "add", "timeline", "steps", "checklist"], "workspaceAction": "newTimeline" },
{ "id": "add-timeline-event", "title": "Add Timeline Event", "category": "Notes",
  "keywords": ["timeline", "event", "step", "add"], "workspaceAction": "addTimelineEvent" }
```

`services/extensions/selftest.py:44-47` pins seven workspace commands.
`docs/commands.md:61-62` and `skills/note-note-plugin/references/commands.md:31,170` list the
two action ids and their availability. `docs/commands.md:145` (the `Ctrl+Alt+N` example) is
unchanged.

**Later (third creatable type).** One type-agnostic `newNoteOfType` action and palette command
(`commandPalette.pick` over `Capabilities.of(p).creatableTypes`, `ui/commands/CommandPalette.qml`)
replaces per-type actions and per-type footer rows (§10).

### 5.10 List and search integration

**Row fields.** `services/notes/sidebar.js` `row()` (`:24-31`) gains two fields, computed once
per provider in `build()` (`var capabilities = Capabilities.of(provider)`, passed to `row()`):

- `noteType: kind === "note" ? Capabilities.rowType(capabilities, source) : ""`. A row carries a type only when it is a declaring provider's non-default type, so ordinary rows stay identical and the `JSON.stringify` row comparison (`docs/decisions.md:444-448`) does not churn.
- `progress: kind === "note" ? NoteTypes.progressOf(source.progress) : null`.

`hasTitle` comes from `capabilities.hasTitle` (Phase 0).

**Drawing.** `ui/NoteSummary.qml` (`:6-58`) gains `property string glyph` and
`property var progress: null`.

- When `glyph` is set, the first line is a `Row`: a glyph `Text` (`Style.fontFamily`, `Style.font.iconSmall`, `Style.secondaryText(foreground, 0.55)`, `Style.spacing.sm` gap), then the title. With no glyph, the title alone, unchanged.
- When `progress` is set, the second line shows `NoteTypes.progressText(progress)` instead of the preview, same font and ink.

`ui/NoteList.qml` (`:447-461`) and `ui/SearchResults.qml` (`:104-117`) pass
`glyph: root.glyphFor(row)` and `progress: root.progressFor(row)`. Both are new
function-valued properties, like `titleFor` (`ui/SearchResults.qml:28-29`). Workspace sets
them beside `titleFor` (`Workspace.qml:2721`):

```js
  function glyphFor(row) {
    return NoteTypes.glyph(row.noteType)
  }

  // The open timeline's progress as it is in the editor, unsaved checks included; every
  // other row's as its provider last listed it (the way displayTitle shows a typed title).
  function displayProgress(row) {
    if (row.path === root.currentPath && !root.loadingNote && editor.progress !== null) {
      return editor.progress
    }
    return row.progress
  }
```

The binding reads `editor.progress` only for the open note's row, so other rows do not depend
on it.

**Wording.** All wording is in the host, and providers send numbers
(`docs/README.md:44-45`, "providers know nothing about the UI"):

| Where | Function | Wording |
|---|---|---|
| list | `NoteTypes.progressText` | "No events yet" · "Done" · "All 7 done" · "3 of 7 · Next: Pack the bags" |
| view bar | `TimelineModel.countText` | "No events" · "Done" · "All 7 done" · "3 of 7 done" |

The definition of `{ done, total, next }` is the same in Python (`timeline.summary`) and JS
(`TimelineModel.progress`). The same golden bodies pin it on both sides (§7).

**Preview and title.**

- The provider's `preview` stays the generic first line (`notefile.preview`), so the host's title and preview matching keeps matching the first event.
- An untitled timeline's list title stays the existing fallback (`☑ Book flights`, `Workspace.qml:1316-1317`).

**Search.** Local `search.py` matches the raw body, so event titles and descriptions are found
with no change. Event text is written with minimal escaping (§5.6.2), so most text matches as
typed.

**Live update.** The open note's row and view bar follow the editor at once, and every other
row follows its provider: local answers a save with `progress` (§5.11.1), about 500 ms after a
check.

### 5.11 Provider support matrix

| Provider | `noteTypes` (v1) | Timeline | Exact changes |
|---|---|---|---|
| local | `["markdown", "timeline"]` (P6; `["markdown"]` in P1–P5) | **yes** | §5.11.1 |
| examples/hello | `["markdown", "timeline"]` (P6; `["markdown"]` in P1), keeps `markdown: true` | **yes** | §5.11.2 |
| OneNote | `["markdown"]` | deferred | drop `markdown: true` (`Provider.qml:19`); drop the unread per-page `markdown=True` (`onenote.py:1380`, `:1387`) |
| Notion | `["markdown"]` | deferred | drop `markdown: true` (`Provider.qml:17`) |
| Sticky Notes | `["text"]` | unsupported | drop `markdown: false` (`Provider.qml:14`) |

**Why the built-ins drop `markdown`.** Built-in providers ship in the same package as the
host, so no older host ever reads their flag. Two declarations of one fact would drift. hello
keeps it, as the documented example of a provider that also runs on 1.0.40.

**Rule for any provider declaring `timeline`.** Its `save()` stores the body exactly as given
(line endings aside), and it merges nothing into it (§5.2.2).

**Deferred, with the opt-in path in §10.**

- **OneNote.**
  - Microsoft documents no durable page marker. A `data-id` wrapper is the only candidate, and its survival in the OneNote apps is unverified (OneNote map §3–5).
  - OneNote's apps check each to-do independently.
  - The format is kept OneNote-compatible: a title paragraph plus description paragraphs map to a to-do paragraph plus indented paragraphs.
- **Notion.**
  - There is no invisible metadata, so any marker (the page icon, a marker block) is a visible product choice.
  - Every check would be a whole-page rewrite.
  - Its writer refuses multi-paragraph items today (`notion_md.py:440-467`), so opting in also needs a converter change.
- **Sticky Notes.** Plain text with no title. Any syntax would show raw in Microsoft's apps (`docs/decisions.md:557-561`).

#### 5.11.1 Local provider, in full

**Key (U2).** `note-note-type:` in the front matter.

- It is read as column-0, case-sensitive lines starting with exactly `note-note-type:`, value trimmed.
- It stays an **unowned extra line**, so every save writes it back verbatim with no new code (`operations.py:136`).
- It is written once, by `create`, and only for non-default types. Markdown notes never get the line, so no existing file is ever rewritten.

**`plugins/org.note-note.local/notefile.py`** (it owns the key, `:10-15`):

```python
import os
import re
import sys

# The shared Markdown modules (services/markdown): a timeline's progress is read by the
# codec there, the one reader of the format (timeline.py). Imported only when a timeline
# needs it (progress), so a listing of plain notes never loads the Markdown parser.
# Appended, not inserted first: a module of the same name in the provider's own folder or in lib/ wins.
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "services", "markdown"))

TYPE_KEY = "note-note-type:"
# The same pattern text as services/notes/notetypes.js ID_PATTERN (tests/test_regressions.py).
TYPE_ID = re.compile(r"^(?:[a-z][a-z0-9-]{0,31}|[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+/[a-z][a-z0-9-]{0,63})$")
MAX_TYPE_ID = 128
# A type line the app cannot read: two that disagree, an empty value, a value that is no id.
UNREADABLE = "?"
# What `create` writes; the same list as Provider.qml's noteTypes (tests/test_regressions.py).
CREATABLE_TYPES = ("markdown", "timeline")
# A timeline's progress is read from the whole note, up to this size.
TIMELINE_PREVIEW_BYTES = 64 * 1024


def note_type(extra):
    """The note's type from its front-matter lines: "" when no line names one, the value
    every type line agrees on, or UNREADABLE."""
    values = [line[len(TYPE_KEY):].strip() for line in extra if line.startswith(TYPE_KEY)]
    if not values:
        return ""
    if len(set(values)) != 1 or len(values[0]) > MAX_TYPE_ID or not TYPE_ID.match(values[0]):
        return UNREADABLE
    return values[0]


def type_line(note_type):
    """The front-matter lines a new note of this type is written with: none for Markdown."""
    if note_type == "markdown":
        return []
    if note_type not in CREATABLE_TYPES:
        raise ValueError("this notebook cannot hold that kind of note")
    return [TYPE_KEY + " " + note_type]


def progress(body):
    """{done, total, next} of a timeline body, or None when it is not one
    (services/markdown/timeline.py decides)."""
    import timeline
    try:
        return timeline.summary(timeline.read(body))
    except timeline.NotTimeline:
        return None
```

The docstring (`:10-15`) becomes: "The app owns `title`, and `note-note-type`, which it writes
once, when a note of a type other than Markdown is made, and never changes. Every other line
inside the fences is not the app's to understand…".

**`plugins/org.note-note.local/list.py`**

- Docstring (`:5-11`): `N<TAB>key<TAB>path<TAB>title<TAB>preview<TAB>size<TAB>mtime_ns<TAB>noteType<TAB>done/total<TAB>next`. The type is `""` for Markdown and for a type line the app cannot read. `done/total` and `next` are empty unless the note is a timeline of at most 64 KiB in timeline form.
- `head_of(path, deadline)` (`:147-153`) becomes:

```python
def head_of(path, size, deadline):
    """(title, preview, note type, progress) from a note's first bytes; a timeline small
    enough is read whole, for its progress. The front matter sits at the top, so the head
    holds the type."""
    text = read_capped(path, HEAD_BYTES, deadline).decode("utf-8", "replace")
    title, body, extra = notefile.split(text)
    kind = notefile.note_type(extra)
    progress = None
    if kind == "timeline" and size <= notefile.TIMELINE_PREVIEW_BYTES:
        whole = read_capped(path, notefile.TIMELINE_PREVIEW_BYTES + 1, deadline)
        if len(whole) <= notefile.TIMELINE_PREVIEW_BYTES:
            title, body, extra = notefile.split(whole.decode("utf-8", "replace"))
            progress = notefile.progress(body)
    return title, notefile.preview(body), "" if kind == notefile.UNREADABLE else kind, progress
```

- The record (`:252-253`): `title, preview, kind, progress = head_of(path, size, deadline)`, then `emit("N", key, path, title, preview, str(size), str(mtime), kind, "%d/%d" % (progress["done"], progress["total"]) if progress else "", progress["next"] if progress else "")`. Old parsers read `p[1]`–`p[6]` only.

**`plugins/org.note-note.local/operations.py`** (HEAD shape; `unkept` stays here, F20)

- `create` (`:104-110`):
  - `note_type = payload.get("noteType", "markdown")`;
  - `text = notefile.serialize("", "", notefile.type_line(note_type))` (raises for an uncreatable type);
  - the answer adds `"noteType": "" if note_type == "markdown" else note_type`. `""` means the default type throughout the contract and the listing.
  - A timeline is `---\ntitle: \nnote-note-type: timeline\n---\n`.
- `read` (`:111-120`):
  - `title, body, extra = notefile.split(...)` and `kind = notefile.note_type(extra)`;
  - `kind == notefile.UNREADABLE` → answer `"editable": False, "reason": "This note names its kind (note-note-type) in a way Note Note cannot read, so it opened read-only"`, with no `noteType`;
  - otherwise `"noteType": kind`, and `editable`/`reason` from `unkept(body)` exactly as today, for every note: a timeline in timeline form has nothing unkept, and one that is not opens as Markdown under the same check. `""` (no type line) and an explicit `markdown` both mean the default.
- `save` (`:126-141`):
  - `extra = notefile.split(current["text"])[2]` and `kind = notefile.note_type(extra)`;
  - the answer adds `"noteType": "" if kind == notefile.UNREADABLE else kind`;
  - and `"progress": notefile.progress(body) if kind == "timeline" and len(text.encode("utf-8")) <= notefile.TIMELINE_PREVIEW_BYTES else None`. This is the same helper and the same bound as the listing, so the two never disagree.

**`plugins/org.note-note.local/Provider.qml`**

| Location | Change |
|---|---|
| `:20` | `readonly property bool markdown: true` → `readonly property var noteTypes: ["markdown", "timeline"]` (P1: `["markdown"]`). |
| `notebookActions(key)` (`:106-112`) | after New Note: `{ path: "newTimeline", title: "New Timeline", icon: <U+F0F97>, shortcut: "newTimeline" }` (P6) |
| `action(id, value, sectionKey)` (`:275-279`) | The New Note target rule becomes `function newNoteTarget(sectionKey)`. `newNote` → `host.newNote(root.id, root.newNoteTarget(sectionKey))`; `newTimeline` → `host.newNote(root.id, root.newNoteTarget(sectionKey), "timeline")`. |
| `loadList` (`:429-446`, WT `:462-478`) | `entries.push({ …existing…, noteType: p[7] \|\| "", progress: root.progressField(p[8], p[9]) })`. `progressField("2/4", "Pack")` → `{ done: 2, total: 4, next: "Pack" }`; malformed or empty → `null`. |
| `folderRows` note rows (`:211-216`, WT in `folderRows` `:234`) and `searchable()` (`:226-230`, WT `:257`) | add `noteType: n.noteType \|\| ""` and `progress: n.progress \|\| null` |
| `load()` (`:499-513`, WT `:535-549`) | Explicit fields. Trap 1: `cb({ title: result.title, body: result.body, version: result.version, base: …, noteType: result.noteType \|\| "", editable: result.editable !== false, reason: result.reason \|\| "" })` |
| `save()` commit (`:548-549`, WT `:587-588`) | Trap 2: `return Object.assign({}, note, { title: title.trim(), preview: result.preview, size: result.bytes, version: result.version, noteType: result.noteType \|\| "", progress: result.progress \|\| null })`. Later fields survive. |
| `create(target, cb, options)` (`:555-575`, WT `:594-614`) | `var noteType = options && options.noteType ? options.noteType : root.noteTypes[0]`. If `root.noteTypes.indexOf(noteType) < 0`, `cb({ error: "this notebook cannot hold that kind of note" })` and return. The payload is `{ action: "create", key: key, noteType: noteType }`. The entry adds `noteType: result.noteType || ""` and `progress: result.noteType === "timeline" ? { done: 0, total: 0, next: "" } : null`. |
| any one-line function an edit above touches | reformatted with its body on its own lines (CLAUDE.md) |

**Known limit.** A front matter over 4 KiB pushes the type line beyond the listing's head. The
row then shows no glyph and no progress, while `read` sees the type and the note opens as a
timeline: the load answer decides (§5.2). Titles behave the same today. Creation writes the
type on line 3.

#### 5.11.2 examples/hello

- Keep `markdown: true`, and add `readonly property var noteTypes: ["markdown", "timeline"]`.
- Notes become `{ id, title, body, noteType }`. `restoreState` treats a missing `noteType` as `"markdown"`.
- Rows (`rebuild`) add `noteType: n.noteType === "markdown" ? "" : n.noteType`. No `progress`: hello has no Markdown reader, and the field is optional.
- `load` answers `{ title, body, editable: true, noteType }`. It is reformatted: braces, one statement per line.
- `create(target, cb, options)` honours `options.noteType` when it is one of `root.noteTypes`, else `cb({ error: "this notebook cannot hold that kind of note" })`.
- The footer adds `{ path: "newTimeline", title: "New Timeline", icon: <U+F0F97>, shortcut: "newTimeline" }`, and `action("newTimeline")` → `host.newNote(root.id, "new", "timeline")`.
- It still loads through the legacy providers directory (`tests/standalone_launch.qml:38-40`, `tests/standalone_selftest.py:190`).

### 5.12 Save, merge, conflict and recovery

**Save.**

1. `flushSave` takes `editor.snapshotDocument()`. For a timeline, `body` is the JSON form, including a valid pending event.
2. `isStored` compares `documentType`, `title` and `body`, so toggling twice sends nothing.
3. A draft is registered.
4. `editor.requestBody(draft.document, cb)` → `TimelineBody.request(document, cb)` → `Markdown.fromTimeline(events)` → `python3 services/markdown/timeline.py write` → `cb(markdown, true)`.
5. `provider.save(path, title, markdown, cb, { view, resolution })`. The signature is unchanged and carries no type.
6. A codec failure (dead process, `{error}`, a self-check refusal) answers `("", false)`. The session finishes with "the note could not be read for saving" and keeps the draft (WT `NoteSession.qml:554-565`). The draft stays, nothing is written.
7. Local `operations.py save` re-reads the current file's extra lines, so the type line stays, and writes atomically. The answer includes `preview`, `version`, `noteType` and `progress`. The provider's commit keeps `noteType` (`Object.assign`), and the rows rebuild.

**Drafts and recovery.**

- Drafts (`draft.document`), recovered drafts (`result.recovered`), deletion-recovery snapshots (`remove`, `finishDeletion`) and `stored` are all `snapshotDocument()`, so each carries `documentType`.
- `restoreDocument` activates that body before restoring. A timeline draft is a JSON form restored with no conversion.
- `replacePath` (F1, WT) moves drafts and `stored` under the new path, and needs no type map.

**Merge and conflict.**

- No provider that declares `timeline` is merge-aware in v1 (local is last-writer-wins; hello is in memory). So no timeline conflict can arise.
- If one ever does, `ui/MergeConflict.qml` shows the raw stored passages (title and body Markdown), which read as checklist lines. Resolving re-enters `flushSave`, and a merged body that is no longer in timeline form opens as Markdown on the next load (U7).
- The declaration rule (§5.11) keeps merge-aware providers out until they prove their merge keeps timelines.

**External changes.** Local reloads a clean open note on an external change
(`NoteSession.reconcile`). A dirty one is overwritten by the next autosave. That is today's
last-writer-wins policy, documented as a known limit and listed as later work.

**Older apps.**

- 1.0.40 opens a timeline file as a Markdown checklist: the canonical body is its own writer's fixpoint and `unkept` is empty (verified).
- Its saves keep the type line, an unowned extra line.
- It cannot save a description line that is exactly `+` (the bug fixed in P0). It fails closed and keeps the draft.

---

## 6. Implementation steps

Every commit:

- keeps `python3 tests/selftest.py`, `ctest` (Release build), `qmllint` over the documented set (`docs/testing.md:91-94`, extended in P2 and P5) and `uvx ruff check .` silent;
- adds no QML warning line, since the noise gates fail on any;
- updates its docs in the same commit (`docs/release-process.md:36-37`);
- is followed by `graphify update .`.

### Phase 0 — Prerequisites (release 1.0.41)

**Goal.** Land the defects on the paths this feature extends before any type exists, and
release them on their own.

**C0.1–C0.18: commit the review fixes already in the working tree.** One commit per finding,
named by its F-number, each with the tests the working tree already holds:

- F1 (`renameBackCases`)
- F2 + F21 (`whenSavedCases`)
- F3, F4, F5, F6, F7, F8, F9
- F10 (rename text kept across row rebuilds; every timeline check is a save that rebuilds rows)
- F12
- F14 (`storedCases`)
- F15
- F16 (`ui/SlotLoader.qml`)
- F17 (`--list-suites`)
- F18, F19
- F20 (no code change: the decision record in `docs/decisions.md`; the local `test_unkept_opens_read_only` as before)

Then:

- **F11** (the tests for the destructive operations) and **F13** (`count` in the skill's row shape), both done in the working tree as of 2026-10-12.

Do not re-implement any of these fixes. Review the diff against the finding's fix text in
`CODE-REVIEW-2026-10-11.md`.

**C0.19 "Escape a lone plus sign at a line start"**

1. `services/markdown/mdtext.py:27`: `LINE_START = re.compile(r"^(\s*)([#>]|[-+*](?=\s|$)|[-=](?=[-=\s]*$)|\|)")`.
2. Add `services/markdown/qthtml/selftest.py` `CASES` entries:
   - "a lone plus sign is text": the paragraph `\+`;
   - "a lone plus after a paragraph": `"a\n\n\\+\n"`.
   Both run in the pure leg and the Qt leg.
3. `tests/test_regressions.py`, beside `test_text_shapes_the_parser_would_consume_stay_text` (`:422`): `convert("<p>+</p>")["note"] == "\\+\n"`, and it reads back as a paragraph holding `+`.

Exit: all 140 existing `CASES` stay fixpoints (verified with the planner's prototype), and
the new ones pass both legs.

**C0.20 "Name a link definition the editor would drop"** (a new finding, §4.6)

1. `services/markdown/parse.py`: add `parse_with_definitions(markdown) -> (tokens, definitions)`.
   - It calls `_md.parse(markdown.replace("\r", ""))`, which returns `(tokens, state)`, then applies `_absorb_image_widths` and `_read_html_blocks` like `parse()`.
   - `definitions` is `dict(state.env.get("ref_links") or {})`.
   - `parse()` becomes `return parse_with_definitions(markdown)[0]`.
2. `services/markdown/qthtml/writer.py` `unkept()` (`:84-95`) parses with `parse_with_definitions`. After `renderer.document(tokens)`, a definition whose key is the `ref` of no `link` or `image` token anywhere in the document calls `renderer.cannot_keep("a link definition no link uses")`. A used definition is folded inline by the editor and loses nothing, so it is not named. `to_html` is unchanged.
3. Tests:
   - qthtml `UNKEPT` case: `"Bookmarks\n\n[home]: https://example.com\n"` → `["a link definition no link uses"]`;
   - `"See [the guide][g].\n\n[g]: https://example.com\n"` → `[]`;
   - a local selftest case: `operations.py read` answers `editable: False` with "This note holds a link definition no link uses, …" for such a note.
4. `docs/decisions.md` "Read-only rather than lossy writes" gains one sentence about link definitions.

**C0.21 "Read every provider capability one way"**

1. New `services/notes/capabilities.js` (`.pragma library`), with the defaults of §5.5. In this phase it has no types:

   ```js
   function of(provider) {
     return {
       hasTitle: !provider || provider.hasTitle !== false,
       canImages: !!provider && provider.canImages === true,
       canCreate: !!provider && provider.canCreate === true,
       tools: toolsOf(provider)
     }
   }

   function toolsOf(provider) {
     if (!provider || provider.tools === undefined || provider.tools === null) {
       return null
     }
     if (!Array.isArray(provider.tools)) {
       return []
     }
     return provider.tools.filter(function(id) {
       return typeof id === "string"
     })
   }
   ```

2. `Workspace.qml`:
   - `readonly property var openCapabilities: Capabilities.of(root.providerOf(root.currentPath))`;
   - the editor bindings `canImages`, `hasTitle` and `enabledTools` (`:2831-2848`) read it;
   - the `plain:` binding stays until P1;
   - `newNote`'s focus (`:1932`) uses `Capabilities.of(p).hasTitle`.
3. `services/notes/sidebar.js` `row()`: `hasTitle: Capabilities.of(provider).hasTitle`, with `build()` computing `Capabilities.of(provider)` once per provider.
5. Tests, in `tests/NoteTypeChecks.js` (new, `run(verify)`, the `tests/ShortcutChecks.js` pattern) called from `tests/transitions.qml` `pureCases()`:
   - absent `hasTitle` → true; `false` → false;
   - `canImages` strict;
   - `tools`: undefined → null, an array → its strings, a string → `[]`.

   Plus a host case: a provider without `hasTitle` shows the title field and logs no "Unable to assign" (the noise gate).
6. Docs: `docs/providers.md` and the skill mirror state the defaults: absent `hasTitle` = true, absent `markdown` = plain text, `tools` must be a list.

**C0.22 "Run the converter and local selftests under CTest"**

`CMakeLists.txt` gains `add_test` for:

- `services/markdown/qthtml/selftest.py` (`ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QPA_PLATFORMTHEME=generic"`);
- `plugins/org.note-note.local/selftest.py`;
- `tests/test_regressions.py`.

These are where this feature's guarantees live, and CTest omits them today.

**C0.23 "Release 1.0.41"**

- `manifest.json:5` → `1.0.41`, with a leading `<release version="1.0.41">` in `packaging/desktop/io.github.andreivinca.note-note.metainfo.xml`. User notes:
  - renaming a section back no longer stops its notes saving;
  - row actions wait for saves;
  - a line that is just "+" saves;
  - notes with unused link definitions open read-only rather than losing them.
- Run `omarchy plugin validate .`, `ctest`, `python3 tests/selftest.py`, `packaging/package.py` and the security checklist.

**Exit criteria P0**

- [ ] `CODE-REVIEW-2026-10-11.md`'s table shows every finding done and committed.
- [ ] A paragraph `+` saves and reloads unchanged. The orphaned-definition note opens read-only, and the used-definition note stays editable.
- [ ] A provider without `hasTitle` logs no "Unable to assign".
- [ ] CTest runs exactly `tests/transition_selftest.py --list-suites` plus the new Python tests.
- [ ] Re-derive every line number this plan cites, from the committed tree.

### Phase 1 — The contract (no visible change)

**C1.1 "Let providers say which note types they keep"**

1. **New `services/notes/notetypes.js`** (§5.3), holding `text` and `markdown` only:
   - `ID_PATTERN`, `ID`, `validId`, `entry`, `known`;
   - `glyph`, `label`, `noun`, `fallback`, `footerShortcut`;
   - `typedBodies`, `opened`, `refused`, `shownId`, `progressOf`, `progressText`.
2. **`services/notes/capabilities.js`** gains:
   - `.import "notetypes.js" as NoteTypes`;
   - `MAX_TYPES = 16`, `declarationProblem(provider)` and `legacyTypes(provider)` (no provider → `["markdown"]`; `markdown === true` → `["markdown"]`; else `["text"]`);
   - `of()` adds `declaresTypes`, `noteTypes`, `defaultType: noteTypes[0]` and `creatableTypes: noteTypes.filter(NoteTypes.known)`;
   - `creationType(capabilities, requested)` and `rowType(capabilities, source)` (§5.9, §5.10).
3. **`Workspace.addProvider`** (`:694`): after the provider passes `providerRefusal`, `var problem = Capabilities.declarationProblem(p)`; when non-empty, `console.warn("note-note: provider", p.id, "noteTypes ignored:", problem)`. The provider still loads, as legacy.
4. **`Workspace.qml` editor `plain:` binding** (`:2837-2840`) becomes transitional: true when the table entry for `root.openCapabilities.defaultType` exists and has `format === "plain"`, and false otherwise (an unknown default type is not plain text). It is removed in P2.
5. **Creation plumbing.**
   - `Workspace.newNoteDestination(providerId, target, noteType)` and `newNote(providerId, target, noteType)` as in §5.9.
   - In this phase no caller passes a type, so `create` always receives `{ noteType: Capabilities.creationType(Capabilities.of(p), undefined) }`, the provider's first known type.
   - `WorkspaceActions.canCreateNote(noteType)` gets the signature, but calls stay untyped.
6. **Built-ins declare `noteTypes` and drop `markdown`** (§5.11 table):
   - local `["markdown"]`;
   - sticky `["text"]`;
   - onenote `["markdown"]`;
   - notion `["markdown"]`.

   `onenote.py:1380` and `:1387` drop `markdown=True`. No selftest reads it (grep).
7. **`examples/hello/Provider.qml`**: add `noteTypes: ["markdown"]` and keep `markdown: true`. `create(target, cb, options)` accepts and ignores `options` (only one type). Reformat `create`.
8. **Local `create(target, cb, options)`** accepts `options` (it holds only `markdown` in this phase).
9. **Docs**, in `docs/providers.md` and the skill mirror:
   - the properties rows and the "Note types" section without the timeline sentences (§5.2.2);
   - the compatibility paragraph;
   - `noteType` on rows, notes and load;
   - `create` options;
   - `host.newNote(id, target, noteType)`;
   - the existing drift: `retry`; save `merged` and `version`.
10. **Tests.**
    - `tests/NoteTypeChecks.js`:
      - `validId` accepts `text`, `timeline` and `com.example.kanban/board`, and rejects `Timeline`, `a/b`, `1x`, `-x`, a 129-character id, `__proto__`, `constructor`, `""`, `null` and `42`;
      - `entry("constructor")`, `entry("__proto__")` and `entry("toString")` → null;
      - `declarationProblem` for not an array, empty, 17 entries, a duplicate, a bad id, and `timeline` without `markdown` (this last one once the timeline entry exists, P5);
      - `of()` for legacy `markdown` true, false and absent; explicit wins; an invalid declaration falls back to legacy;
      - `creationType` and `rowType`;
      - `opened()` for legacy, absent, `""`, a known declared type, an unknown valid id (reason names it), an unknown 100-character id (cut to 64 + "…"), a non-string, and a known undeclared type.
    - `tests/transitions.qml` host cases:
      - Ctrl+N passes `{ noteType: "markdown" }` to local `create`;
      - a fake provider with a two-argument `create(target, cb)` and no `noteTypes` still creates and loads (the third argument is ignored), and the hello example still loads through the legacy directory (`tests/standalone_launch.qml:38-40`);
      - a provider whose `noteTypes` is `"markdown"` (a string) loads as legacy with one warning that does not match the noise patterns.
    - `tests/test_regressions.py`: `test_type_id_grammar_agrees` extracts `ID_PATTERN` from `notetypes.js` with `re.search(r'var ID_PATTERN = ("(?:[^"\\]|\\.)*")', js)`, reads it with `json.loads`, and compares it to `notefile.TYPE_ID.pattern`. This lands in P4, when `TYPE_ID` exists; in P1 compare to a constant in the test.

**Exit P1**

- Every suite is green, with no visible change in either host.
- The legacy hello still loads.
- Sticky still opens plain, and the others rich.
- `providers.md` and the skill reference agree line for line on every member touched.

### Phase 2 — The pane/body seam (no behaviour change)

**C2.1 "Show each note through the body of its type"**

1. **New `ui/notetypes/NoteBody.qml`** (§5.4).
2. **`ui/NoteEditor.qml`.** All of §5.4:
   - `import "../services/notes/notetypes.js" as NoteTypes`;
   - `documentType`, `body`, `documentActive`;
   - `plain` becomes readonly-derived (`:28`);
   - `countText`, `progress`, `formOpen`;
   - `bodyHost`, `documentBody`, the `typedBodies` Repeater (empty model in this phase), `bodyFor`, `activate`;
   - `setNote(document, shown)` (replacing `:292-316`), `showAsFallback`, `answer`, `clearNote()`, `restoreDocument(snapshot)` returning a refusal (`:323-332`), `snapshotDocument()` with `documentType` (`:318-321`), `requestBody(document, callback)`, which removes `requestMarkdown` (`:122-134`);
   - the dispatchers `viewState`, `restoreViewState`, `focusEditor`, `focusBody`, `undo`, `redo` and `bodyAction`;
   - the renames `documentViewState` and `restoreDocumentViewState` (`:1784-1789`);
   - the area's undo and redo keys (`:2118`, `:2123`) call `replayHistory`;
   - `documentActive` guards in `applyReadOnly`, `paste`, `pastePlain`, `replayHistory`, `hoveredLink`, `flick.visible` and `onDocumentActiveChanged`.
3. **`ui/editing/EditorApi.qml:13`**: `writable` requires `host.documentActive`.
4. **`ui/ViewBar.qml`**: `property string countText` replaces `wordCount` (`:36`, `:131`). The label keeps `objectName: "wordCount"`.
5. **`services/notes/NoteSession.qml`**: §5.5 items 1–5.
6. **`Workspace.qml`**:
   - remove the `plain:` binding;
   - `countText: editor.countText` (`:2920`);
   - paste guards (`:2245-2250`);
   - `debugState` gains `documentType`, `count`, `progress` and `formOpen`;
   - `editorUndo` returns `editor.countText`;
   - add `documentType` and `editorWritable` properties and `runBodyAction(name)` (§5.9).
7. **Tests.**
   - `tests/transitions.qml` fake editor (WT `:424-448`), reformatted with braces and one statement per line:
     - `property string documentType: "markdown"`;
     - `property string fallback: ""` and `property string refusal: ""`;
     - `clearNote()`;
     - `setNote(document, shown)`, which records `documentType`, `title` and `body`, and calls `shown({ ok: true, fallback: fallback })`;
     - `restoreDocument(snapshot)`, which sets the fields and returns `refusal`;
     - `snapshotDocument()` → `{ documentType, title, body, base }`;
     - `requestBody(document, callback)`, which pushes `{ document, callback }` onto `conversions`.

     Every existing case that read `conversions[i]` as a function calls `conversions[i].callback`.
   - New `noteTypeSessionCases()` (§7.3, items 1–14).
   - `tests/EditorKeys.qml`:
     - `setNote` call sites (HEAD `:850`, `:852`, `:1091`; the working tree moves them, so find them by name) take a document;
     - `editor.plain = true/false` (HEAD `:1089`, `:1103`, `:1367`, `:1369`) becomes `editor.restoreDocument({ documentType: "text"|"markdown", title: "", body: "", base: "" })` before the scenario's `setNote`;
     - `requestMarkdown` (HEAD `:1248`, `:2454`) → `requestBody(editor.snapshotDocument(), …)`;
     - `resetEditor` (HEAD `:3336-3346`) replaces `editor.plain = false` with `editor.restoreDocument({ documentType: "markdown", title: "", body: "", base: "" })`;
     - the bound view bar (`:94`) uses `countText: editor.countText`.
   - `tests/audio.qml`: nine `setNote` calls (`:73`…`:423`) take a document, and their callbacks read `shown.ok`; `requestMarkdown` (`:211`) → `requestBody(editor.snapshotDocument(), …)`.
   - `tests/extensions.qml:279`: `requestMarkdown` → `requestBody(editor.snapshotDocument(), …)`.
   - Keys-suite cases:
     - a `text` note then a `markdown` note switch the TextEdit's format through `setNote` alone;
     - `snapshotDocument().documentType` follows;
     - `countText` is "1 word" / "2 words".
8. **Docs.**
   - New `docs/note-types.md`, the architecture part (§8).
   - `docs/technical-requirements.md:14`.
   - `docs/decisions.md` entries D-1, D-2 and D-3 (§8).
   - `docs/editing-tools.md` gains the sentence on tools only for Markdown notes.
   - `docs/testing.md`: debugState fields; the qmllint set gains `ui/notetypes/*.qml`.
   - `docs/README.md` index row.

**Exit P2**

- All existing suites are green with **no** new warning.
- Opening, editing, saving, recovering and deleting local, Sticky, OneNote and Notion notes behaves exactly as before.
- `canColorText`, `tools.actions` and the toolbar heights are unchanged when switching between plain and Markdown notes.
- The new session cases are green.

### Phase 3 — The codec (no UI)

**C3.1 "Read and write timelines as the editor writes Markdown"**

1. **New `services/markdown/timeline.py`**:
   - `read`, `write` and `summary`, `NotTimeline`;
   - `MAX_EVENTS = 500`, `MAX_TITLE = 256`, `MAX_DESCRIPTION = 4096`, `MAX_LINES = 40` and `MAX_BYTES = 8 * 1024 * 1024`;
   - `FORBIDDEN` (the control set), `units(text)`, the token-word table, and the CLI `main()` (§5.6.4–5.6.5).
   - Imports: `from parse import parse_with_definitions`, `from qthtml import convert` (run as a script, `services/markdown` is `sys.path[0]`), and `jsondata` (lib) inside `main()` only.
2. **New `services/markdown/timeline_selftest.py`** (§7.1). Register it in `tests/selftest.py` `SCRIPTS` and as CTest `add_test(NAME timeline-codec …)`.
3. **`services/markdown/Markdown.qml`.**
   - `run(args, payload, callback)` (`:112-114`) becomes `runScript(script, args, payload, callback)`, with `toHtml` and `toMarkdown` passing `root.script`.
   - Add `readonly property string timelineScript: dir + "/timeline.py"` and:

   ```js
   // Markdown -> a timeline's events.  callback(answer, ok)
   // `answer` is { events } or { notTimeline: reason }; `ok` is false only when the codec
   // failed, framed like toHtml: a failure never reads as an empty timeline.
   function toTimeline(markdown, callback) {
     if (!markdown) {
       callback({ events: [] }, true)
       return
     }
     runScript(root.timelineScript, ["read"], markdown, function(answer) {
       if (answer && typeof answer.notTimeline === "string" && answer.notTimeline !== "") {
         callback({ notTimeline: answer.notTimeline }, true)
         return
       }
       if (!answer || !Array.isArray(answer.events)) {
         console.warn("note-note: could not read the timeline")
         callback(null, false)
         return
       }
       callback({ events: answer.events }, true)
     })
   }

   // A timeline's events -> its Markdown.  callback(markdown, ok)
   function fromTimeline(events, callback) {
     runScript(root.timelineScript, ["write"], JSON.stringify({ events: events }), function(answer) {
       if (!answer || typeof answer.markdown !== "string") {
         console.warn("note-note: could not write the timeline")
         callback("", false)
         return
       }
       callback(answer.markdown, true)
     })
   }
   ```

4. **qthtml `CASES`**:
   - "timeline: events with and without descriptions" (the §5.6.3 body);
   - "timeline: escaped lines" (the §5.6.2 table).

   They run in the pure leg and the Qt leg.
5. **Docs.**
   - `docs/note-types.md` "The timeline format".
   - `docs/providers.md` "The timeline format" (§5.2.2).
   - `docs/security.md` rule 7 gains a paragraph (§8), and the checklist gains a line.
   - `docs/technical-requirements.md` limits row.
   - `docs/decisions.md` D-5 and D-6.

**Exit P3.** `timeline_selftest.py` is green in both runners, with 0 failures in the 3000-model
property test, both legs.

### Phase 4 — The local type marker (local still declares only `markdown`)

**C4.1 "Keep a local note's type in its front matter"**

1. `notefile.py`, `list.py`, `operations.py` and `Provider.qml`, as in §5.11.1, except:
   - `noteTypes` stays `["markdown"]`;
   - no `newTimeline` footer row;
   - `action("newTimeline")` is not added yet.
2. The result: a hand-written `note-note-type: timeline` opens **read-only as text**, because local does not declare `timeline` (the undeclared rule).
3. **Tests.**
   - Local selftests (§7.4).
   - `tests/test_regressions.py`:
     - `note_type` cases;
     - the split/serialize property with a type line;
     - `test_type_id_grammar_agrees` against `notefile.TYPE_ID`;
     - `test_local_creatable_types_agree`: `Provider.qml`'s `noteTypes` literal is a subset of `notefile.CREATABLE_TYPES`, and equal from P6 on.
   - `tests/transitions.qml` `localCases`:
     - `record()` fixtures (`tests/transitions.qml` `localCases`) emit 10 fields;
     - `loadList` reads 7-field and 10-field `N` records;
     - `load` forwards `noteType`, `editable` and `reason`.
4. **Docs.** The `docs/providers.md` local format paragraph (`:713`), and `docs/decisions.md` D-10.

**Exit P4.** The local selftest is green. A note keeps its type line byte-exact through any
number of saves, among foreign front-matter lines, with CRLF/BOM input.

### Phase 5 — The timeline body (not creatable yet)

**C5.1 "Draw check faces in one place"**

1. New `ui/CheckFace.qml`, the face `Rectangle` and its two tick `Rectangle`s from `ui/NoteEditor.qml:2242-2284`, with:
   - `property bool checked`, `property bool hovered`, `property real side`, `property bool round`;
   - `property color foreground`, `accent`, `background`;
   - `radius: round ? side / 2 : Math.max(3, Math.round(side * 0.3))`.
2. The overlay (`:2219-2291`) uses `CheckFace { round: false … }`. The output is pixel-identical.
3. Test: existing keys/tools/lists suites stay green, plus one property check of the radius.

**C5.2 "Add a multi-line chrome field"**

1. New `ui/ChromeTextArea.qml`: `QQC.TextArea` on `ChromeControlStyle` (fill, border, focus border, radius, padding as `ui/ChromeTextField.qml`).
2. Properties:
   - `placeholderText`;
   - `property int maximumLength: 0` and `property int maximumLines: 0` (0 = none), enforced in `onTextChanged` by reverting to the last accepted text and cursor, then emitting `limitReached()`;
   - `property int minimumLines: 1` and `property int maximumVisibleLines: 8`, giving the height from `contentHeight`;
   - `wrapMode: TextEdit.Wrap`, `textFormat: TextEdit.PlainText`.
3. Test: a keys-suite case that types past the limit and sees the text unchanged and `limitReached` emitted.

**C5.3 "Add the timeline note type"**

1. New `ui/notetypes/timeline/TimelineModel.js` (§5.7, §5.8.2, §5.8.9). Limits: `var MAX_EVENTS = 500`, `var MAX_TITLE = 256`, `var MAX_DESCRIPTION = 4096`, `var MAX_LINES = 40`, `var MAX_UNDO = 200`.
2. New `TimelineBody.qml`, `TimelineEvent.qml` and `EventForm.qml` (§5.8).
3. `notetypes.js` gains the `timeline` entry (§5.3). `NoteEditor`'s `typedBodies` model then holds it.
4. `ui/RowMenu.qml` header comment generalised.
5. Tests:
   - `tests/NoteTypeChecks.js` model cases (§7.2);
   - EditorKeys `timeline` suite: add to `suites` (HEAD `:3051`) a `timeline` entry whose function returns `test.timelineCases()`, written with its body on its own line (CLAUDE.md), and add `"timeline"` to `tests/transition_selftest.py` `SUITES` (`:18`). CMake and `tests/selftest.py` follow through F17;
   - `test_regressions`: `test_timeline_limits_agree` (`TimelineModel.js` `var MAX_*` vs `timeline.MAX_*`) and `test_note_type_bodies_exist` (every `body:` path in `notetypes.js` exists under `ui/`).
6. Docs:
   - `docs/note-types.md` "The timeline view": keys, accessibility, objectNames;
   - `docs/decisions.md` D-7, D-8 and D-9;
   - `docs/testing.md`: the suite, the qmllint set gains `ui/notetypes/timeline/*.qml`, and the IPC helpers.

**Exit P5**

- The timeline suite is green, including the hidden-document-inert case and the 500-event timing case.
- A local file hand-marked `timeline` still opens read-only (undeclared).

### Phase 6 — Creation, the list, commands (release 1.1.0)

**C6.1 "Keep timelines in local notebooks"**

- Local: `noteTypes: ["markdown", "timeline"]`, the `newTimeline` footer row, `newNoteTarget(sectionKey)` and `action("newTimeline")` (§5.11.1).
- hello timeline support (§5.11.2).
- `docs/providers.md`: the footer `newTimeline`, and the timeline declaration rule. Skill mirror.
- Tests: transitions `localCases` (§7.3 items 18–21).

**C6.2 "Show a note's type and progress in the list"**

- `sidebar.js` `row()` fields.
- `NoteSummary` `glyph` and `progress`.
- `NoteList` and `SearchResults` `glyphFor` and `progressFor`.
- Workspace `glyphFor` and `displayProgress` (§5.10).
- `docs/providers.md` row fields (§5.2.2). Skill mirror.
- Tests §7.3 items 22–24.

**C6.3 "New Timeline on Ctrl+Shift+T and in the palette"**

- `defaults.js`, `WorkspaceActions.qml`, Workspace `runBodyAction` and IPC helpers, `plugin.json`, and the `services/extensions/selftest.py` pin (§5.9).
- `tests/ShortcutChecks.js`: `Ctrl+Shift+T` resolves to `app/newTimeline` in `notes`, and the compile has no diagnostics.
- Docs: `docs/commands.md` and the skill `references/commands.md`; README Keys; `plugins/org.note-note.local/getting-started.md` ("**New Timeline** starts a list of steps you check off in order." and a `Ctrl+Shift+T | New timeline` row; new roots only).

**C6.4 "Describe timelines"**

- README Notebooks and Providers.
- `docs/business-requirements.md` amendments.
- `docs/technical-requirements.md` data model and layout.
- `docs/decisions.md` D-11 to D-14.
- `docs/testing.md` manual checklist (§7.7).

**C6.5 "Release 1.1.0"**

- `manifest.json` → `1.1.0`, with a leading metainfo `<release version="1.1.0">`. Notes: "Timelines: a new kind of note in local notebooks…".
- Run `omarchy plugin validate .`, a Release build with `ctest`, `python3 tests/selftest.py`, `python3 packaging/package.py`, and walk the security checklist (`docs/security.md:286-325`).

**Exit P6.** §7.7's manual checklist passes in both hosts, light and dark. Every runner is green.

---

## 7. Test plan

Each guarantee is tested at the lowest level that can observe it. Registration is in §7.8.

### 7.1 Codec: `services/markdown/timeline_selftest.py` (new, P3)

This is a plain `check()` script like the provider selftests. Its name contains `selftest`, so
it is excluded from installs and packages.

1. **Golden bytes.** The §5.6.3 body before and after the check. The §5.6.2 escape table, written exactly.
2. **Property.** 3000 seeded models: 0–6 events; titles and description lines from a pool of letters, digits, `*_` `` ` `` `~=[]()<>!#&\|{}-+.:;'"/@$%^`, NBSP, `é`, `☕` and an astral emoji; 0–4 description lines. For each model:
   - `read(write(m)) == m`;
   - the pure fixpoint `to_markdown(to_html(md)) == md`;
   - `unkept(md) == []`;
   - the old-editor property `read(to_markdown(to_html(md))) == m`.
3. **Edge lines.** The 55 strings from the planner's prototype (53 the model accepts) (`+ - * # > 1. 1) | = == --- *** ___`, `* * *`, `_ _ _`, `- - -`, `+ x`, `[x]`, `[ ] x`, `&amp;`, `&copy;`, `a\`, `` ` ``, `<b>`, `<!-- c -->`, a URL with `_`, `a  b`, `[a](b)`, `**x**`, `x_y_z`, `2 * 3`, `---|---`, `[name]: http://x`, NBSP at the edges, …), as titles and as description lines: written, fixpoint.
4. **Tolerated variants**, with the exact events and the exact canonical rewrite (§5.6.4 table).
5. **Refusals**, with exact reasons:
   - a heading, a trailing paragraph, a plain bullet, a nested list, ordered, two lists;
   - an HTML comment, bold, italic, a link, an autolink, inline code, inline HTML, a backslash break, a two-space break;
   - an empty task;
   - a link definition (used and unused);
   - a control character;
   - 501 events, a 257-unit title, a 4097-unit description, 41 description lines.
6. **`write` refusals.** A missing key, a wrong type, a title with an edge space, a description with an empty line, and each over-limit case raise `ValueError`.
7. **`summary`.** In order, out of order, all done, empty.
8. **CLI.**
   - `read` and `write` round trip over stdin.
   - Bad JSON → `{"error"}`, exit 1.
   - Duplicate keys → `{"error"}` (`jsondata`).
   - Input over 8 MiB → exit 1 and no stdout.
   - An unknown verb → exit 2 and usage.
9. **Qt leg.** The golden body and 20 property samples through `qthtml.selftest.through_qt`: stable, and saved == written. It runs as qthtml's own Qt leg does.

### 7.2 Pure JS: `tests/NoteTypeChecks.js` (new; `run(verify)`, called from `tests/transitions.qml` `pureCases()`)

**Capabilities** (P0, P1)

- defaults: `hasTitle`, `canImages`, `canCreate`, `tools`;
- the legacy mapping;
- explicit wins;
- each `declarationProblem` (including `timeline` without `markdown` from P5);
- `creationType` with and without a request, and with an unknown first type;
- `rowType` (legacy → `""`, default → `""`, invalid → `""`).

**NoteTypes** (P1, P5)

- `validId` table (§6 C1.1);
- prototype-free `entry`;
- `opened()` table;
- `progressOf`, which clamps and refuses bad shapes;
- `progressText` strings;
- `typedBodies()` (P5: one entry);
- `glyph("timeline")` is U+F1533;
- `footerShortcut`.

**TimelineModel** (P5)

- `setChecked` and `toggle`: every row of the §5.7 truth table;
- `changedCount`;
- `append`, `replace`, `remove` and `move` at the bounds (first, last, out of range is a no-op);
- `withPending`: add with empty, valid and over-limit text, and edit with an empty title keeping the old text;
- `form` determinism: equal events give an equal string; `[1, …]`/`[0, …]`;
- `fromForm`: bad JSON, not an array, a wrong arity, a non-0/1 flag, an uncleaned title, over-limit → `null`;
- `cleanTitle` and `cleanDescription`: controls, CRLF, blank lines, NBSP, U+FEFF;
- `problem` messages;
- `progress` and `nextIndex` (in order, out of order, all done, empty);
- `countText`;
- `patch`: toggle → sets, append → insert, delete → remove, move → two sets, arbitrary → sets plus inserts/removes, and applying the ops to a copy reproduces `after` for 500 random pairs;
- titles `__proto__` and `constructor`.

### 7.3 Session and host: `tests/transitions.qml`, core suite

**`noteTypeSessionCases()`** (P2; fake editor and fake provider)

1. A declaring provider's load answer `noteType: "markdown"` reaches `setNote` as `documentType: "markdown"`. An absent one gives the default.
2. A legacy provider (`markdown` absent) answering `noteType: "timeline"`: `documentType` is `"text"` from the flag, and the field is ignored.
3. An unknown valid type (`"kanban"`) → `documentType: "text"`, read-only, the reason reported once, naming "kanban".
4. A known undeclared type → read-only.
5. `editor.fallback` set → editable, the fallback reason reported.
6. Fallback plus the provider's `editable: false` (local's `unkept` verdict) → read-only with the provider's reason, and the fallback reason is not said.
7. The snapshot carries `documentType`. `isStored` is false when only `documentType` differs.
8. A slow save, then switching away and back: the draft is restored with its `documentType` through `restoreDocument`.
9. `restoreDocument` returning a refusal → `noteReady(true, refusal)`.
10. A recovered answer's draft carries `documentType`.
11. A failed delete restores a typed draft.
12. `replacePath` (a provisional note) keeps a typed draft. Loading the new path restores it with its type.
13. A(markdown) → B(timeline, slow `shown`) → A: B's late `shown` is dropped (`ownsLoad`).
14. `flushSave` calls `requestBody` with `draft.document` (recorded), not live state.

**Host cases** (P1, P6; real Workspace and providers in the core suite)

15. Ctrl+N passes `{ noteType: <default> }` to `create`.
16. `host.newNote(id, target, "timeline")` to a provider that does not declare it gives the status "…cannot hold timelines" and no `create` call.
17. A two-argument `create` provider still works.

**Local cases** (`localCases()`, P4 and P6)

18. Create a timeline through the real provider: the file bytes are `---\ntitle: \nnote-note-type: timeline\n---\n`, and the entry has `noteType: "timeline"` and `progress: {0,0,""}`.
19. `loadList` reads 7-field and 10-field `N` records, `progressField` included.
20. **Regression for the misfiling flaw.** In notebook-tab mode with **no note open**, on notebook "Work" (not the last notebook), invoking `newTimeline` (the action `Ctrl+Shift+T` runs, `workspaceActions.invoke("newTimeline")`) files the timeline in "Work".
21. A timeline's footer row exists in every notebook tab and in the folded-tree footer.

**List and commands** (P6)

22. `sidebar.js` `row()` carries `noteType` only for a declaring provider's non-default type, and `progress` normalised. Rows of Markdown notes are byte-identical to before (JSON).
23. `displayProgress` returns the editor's progress for the open note only after its load, and the row's otherwise.
24. `WorkspaceActions` availability:
    - `newTimeline` unavailable with only Sticky configured ("Open a notebook that can hold timelines.");
    - `addTimelineEvent` unavailable unless a writable timeline is open;
    - both available otherwise.

### 7.4 Local provider: `plugins/org.note-note.local/selftest.py` (P4)

- `FIELDS["N"] = 10` (`:347`, today 7).
- `test_note_type_round_trip`: create a timeline → exact bytes; list → the type field; read → `noteType`; save → the line kept byte-exact; CRLF/BOM input → LF out with the line kept.
- `test_type_marker_survives_foreign_front_matter`: `tags:` before and after the line, several saves.
- `test_conflicting_or_malformed_type_opens_read_only`: two disagreeing lines, an empty value, `Timeline`, `a/b` → read answers `editable: False` with the reason; the listing type is `""`.
- `test_unknown_type_reported_verbatim`: `kanban` → `noteType: "kanban"`.
- `test_create_refuses_an_unknown_type`: `noteType: "kanban"` → error, and no file.
- `test_timeline_progress_and_its_bound`: listing and save answers carry `progress` for a 2 KiB timeline. A 70 KiB timeline gets none, and so does one not in timeline form. Listing and save agree.
- `test_type_beyond_the_head`: a 5 KiB front matter → the listing type is `""`, while read sees `timeline`.
- `test_search_finds_event_text`.
- `test_markdown_notes_never_get_a_type_line`: create markdown → no line; save → still none.

### 7.5 Real keys: `tests/EditorKeys.qml`

**`timeline` suite (new, P5).** These use the real `NoteEditor`, the real `Markdown` service and
the codec, and wait with `keys.tryVerify` as the suite does for `toHtml`.

1. `setNote({ documentType: "timeline", … })` with the §5.6.3 body shows four rows (`timelineEvent-0..3`):
   - `countText` is "2 of 4 done";
   - `progress.next` is "Pack the bags";
   - the snapshot is the JSON form.
2. Space on row 4 (cursor) checks rows 1–4. There is one `edited()`, and the status is `Checked 2 events, up to “Go to the airport”`.
3. Space on checked row 2 unchecks 2–4, with the status.
4. A click on `timelineCheck-2` checks everything above it.
5. Ctrl+Z restores, and Ctrl+Shift+Z and Ctrl+Y redo.
6. Ctrl+Enter opens the form:
   - typing a title makes the event part of the snapshot;
   - Enter commits, and the form stays open and empty;
   - `requestBody(editor.snapshotDocument(), …)` gives the expected Markdown through the real codec.
7. Shift+Enter in the description adds a line. The saved Markdown has one paragraph per line.
8. Enter with an empty title and a description shows "Give the event a title". Enter on an empty form closes it.
9. Esc while adding discards the pending event and Ctrl+Z brings it back. **Esc never reaches the host**: a `shortcutHandler` stand-in counts calls, and `back` is not run.
10. Enter on a row edits it in place. Typing changes the snapshot live, and Esc restores the old text.
11. Delete removes the cursor row with the status, and Ctrl+Z restores it.
12. Alt+Up and Alt+Down move the cursor row, and the cursor follows.
13. Up, Down, Home, End, PageUp and PageDown move the cursor:
    - Down past the last row lands on `timelineAddEvent`;
    - Up from row 1 focuses the title;
    - **Ctrl+Down is the app's** (the stand-in sees it), proving the single-`onPressed` rule.
14. The note title's Enter and Down land on the next unchecked event. On an empty writable timeline they open the form.
15. Read-only: Space, Delete, Enter and Ctrl+Enter change nothing and emit no `edited()`. There is no `timelineAddEvent`.
16. A body with a heading opens as Markdown: `documentType` is `"markdown"` and `shown.fallback` names "text outside its list of events".
17. An out-of-order body shows as stored and emits no `edited()` without an action.
18. Toggling the same event twice leaves a snapshot equal to the first (no save).
19. **The hidden document is inert** with a timeline open:
    - `editor.tool("bold")` is false;
    - `editor.paste()` changes nothing;
    - `editor.undo()` reaches the timeline, not the TextEdit;
    - `keys.findChild(editor, "noteBody").readOnly` is true;
    - Ctrl+B and Ctrl+1 change nothing.
20. Timeline → Markdown note → timeline:
    - the TextEdit is writable again;
    - the tools are available;
    - with the list focused before the switch, focus lands in the TextEdit after it.
21. While composing, a click on another row's circle checks it, and the form keeps its text and focus.
22. `Accessible.role` of `timelineEvent-0` is `Accessible.CheckBox`, its `Accessible.checked` follows the state, and its `Accessible.name` is the title.
23. A 500-event body opens. A check on event 250 finishes `setChecked` + `patch` within 200 ms (measured with `Date.now()` around the call). The add row says "A timeline holds at most 500 events".
24. `CheckFace` round radius is `side / 2`.

**`keys` suite additions** (P2):

- per-note `text`/`markdown` format switching;
- `countText` wording;
- the description field limit (C5.2).

### 7.6 Pins and regressions

| Test | Pins |
|---|---|
| `tests/test_regressions.py` (P0) | a lone `+` stays text |
| `tests/test_regressions.py` (P4) | `note_type` table; the split/serialize property with a type line; `test_type_id_grammar_agrees` (`notetypes.js` `ID_PATTERN` == `notefile.TYPE_ID.pattern`); `test_local_creatable_types_agree` |
| `tests/test_regressions.py` (P5) | `test_timeline_limits_agree` (`TimelineModel.js` == `timeline.py`); `test_note_type_bodies_exist` |
| `services/extensions/selftest.py:44-47` (P6) | seven workspace commands, including `new-timeline` → `newTimeline` and `add-timeline-event` → `addTimelineEvent` |
| `tests/ShortcutChecks.js` (P6) | `Ctrl+Shift+T` → `app/newTimeline` in `notes`; no compile diagnostics |
| `tests/standalone_selftest.py:190` (unchanged) | hello, now declaring `noteTypes`, still loads from the legacy directory |
| `services/markdown/qthtml/selftest.py` (P0, P3) | `CASES`: lone `+`, timeline shapes. `UNKEPT`: orphaned link definitions |

### 7.7 Manual checklist (`docs/testing.md`, P6)

Run in both hosts, light and dark themes:

1. `Ctrl+Shift+T` in a local notebook tab with no note open creates "Untitled" in **that** tab, with the title focused.
2. Type a title, Enter → the add form opens. Add three events, one with a two-line description (Shift+Enter).
3. Space on event 3 checks 1–3. Space on event 2 unchecks 2–3, with the status. Ctrl+Z.
4. Edit event 1 (Enter), Delete event 2, Ctrl+Z, Alt+↑ on event 3. No mouse used.
5. The list row shows the glyph and "1 of 3 · Next: …", updating as you check.
6. `cat` the file: the canonical form with `note-note-type: timeline` (§5.6.3).
7. Open the file in another editor:
   - toggle a box there → the open, clean timeline reloads with the new state;
   - add a heading there → it opens as Markdown with the reason;
   - remove the heading in Note Note → reopen → it is a timeline again.
8. Open the same file in the 1.0.40 build → an editable checklist. Edit and save there → it is still a timeline in 1.1.0.
9. Sticky, OneNote and Notion notes behave exactly as in 1.0.41. `Ctrl+Shift+T` on a Sticky tab files the timeline in a local notebook and switches to its tab.

### 7.8 Registration

| Suite | `tests/selftest.py` | CTest |
|---|---|---|
| `services/markdown/timeline_selftest.py` | `SCRIPTS` (P3) | `add_test(NAME timeline-codec COMMAND ${Python3_EXECUTABLE} …/services/markdown/timeline_selftest.py)` (P3) |
| `services/markdown/qthtml/selftest.py` | already | `add_test(NAME qthtml …)` (P0, C0.22) |
| `plugins/org.note-note.local/selftest.py` | already | `add_test(NAME local-provider …)` (P0) |
| `tests/test_regressions.py` | already | `add_test(NAME regressions …)` (P0) |
| EditorKeys `timeline` | via `SUITES` (F17) | via `--list-suites` (F17) |
| `tests/NoteTypeChecks.js` | inside the `core` suite | inside `native-transitions-core` |

---

## 8. Documentation and decision records

Each change lands in the commit with the behaviour it describes.

| File | Section | Gist | Phase |
|---|---|---|---|
| `docs/providers.md` | properties table, "Note types", row shape, footer shortcuts, `load`/`save`/`create`, compatibility paragraph, "The timeline format", Limits, local format | exact text in §5.2.2; also the existing drift (`retry`, `merged`, `version`) | P0 (defaults), P1, P3, P4, P6 |
| `skills/note-note-plugin/references/providers.md` | mirror of all of the above; F13 `count`; its minimal provider declares `noteTypes` | P0, P1, P3, P4, P6 |
| `skills/note-note-plugin/references/commands.md` | `:31` action ids, `:170` availability: `newTimeline`, `addTimelineEvent` | P6 |
| `docs/commands.md` | `:61-62` supported action ids and their availability | P6 |
| `docs/note-types.md` (new) | What a note type is; the table (`notetypes.js`); `NoteBody` (exact members) and `bodyHost`; the pane protocol; `documentType` vs `noteType`; unknown, undeclared and fallback rules; how to add a type (one body folder plus one table line); why not a plugin kind yet, the trigger and the 2c5920f template; "The timeline format"; "The timeline view" (keys, accessibility, objectNames) | P2, P3, P5 |
| `docs/README.md` | index row: "[Note types](note-types.md) — adding a kind of note, or changing how one is shown" | P2 |
| `docs/technical-requirements.md` | `:14` editor format ("Every note has a type: Markdown notes are rich text converted at both ends by qthtml; plain-text notes are plain text; a timeline is events read and written by `services/markdown/timeline.py` through the same converter; every body crosses the contract as a string"); layout list gains `ui/notetypes/` and `services/markdown/timeline.py`; data model `:107-109` row shape fixed (`count`, `menu`, `reorder`, `modified`, `noteType`, `progress`); Limits gains "Timeline: 500 events; a title 256 characters; a description 4096 characters on 40 lines; progress read from a local file of 64 KiB or less; codec input 8 MiB" | P2, P3, P6 |
| `docs/business-requirements.md` | non-goal `:57-58` gains "Note types are ways to edit one note, not templates or databases: a type adds no fields, queries or links between notes, and every type is text its provider stores." Goal 3 `:32-34` gains "a timeline is a Markdown checklist plus one front-matter line." Product decision `:74` becomes "Every note has a type: Sticky Notes hold plain text; OneNote and Notion Markdown; local notebooks Markdown and timelines \| a provider offers only the types its backend keeps; a timeline needs a place for its type other apps leave alone, which only local files have so far". New rows: "Checking a timeline event checks every event above it; unchecking one unchecks every event below \| a timeline is a path: what is done is the top of the list" and "A note of a type this version cannot edit opens read-only as text \| its text and its type stay as they are until a version that knows it" | P6 |
| `docs/editing-tools.md` | "Tools act on Markdown notes only: with a plain-text note or a timeline open, `EditorApi.writable` is false and the strip keeps only its row." | P2 |
| `docs/security.md` | rule 7 gains: "The timeline codec (`services/markdown/timeline.py`) decodes note text: stdin capped at 8 MiB, events, titles and descriptions bounded while reading, refused rather than truncated; the write input is parsed by `lib/jsondata.parse`; event text is drawn as `Text.PlainText`." Checklist gains: "Every note type's reader bounds counts and sizes at read time and refuses rather than truncates." | P3 |
| `docs/testing.md` | `debugState` fields; IPC `addEvent ""` and `toggleEvent <i>`; qmllint set gains `ui/notetypes/*.qml ui/notetypes/timeline/*.qml`; the codec selftest; the timeline suite; the §7.7 checklist | P2, P3, P5, P6 |
| `README.md` | Notebooks (`:185-204`): timelines, the `note-note-type` line, the file example, "other tools see a checklist". Keys (`:325-345`): `Ctrl+Shift+T` and the in-timeline keys (Space, Enter, Ctrl+Enter, Delete, Alt+↑/↓). Providers (`:269`): which hold timelines. Writing plugins (`:38-58`): `noteTypes`. | P6 |
| `plugins/org.note-note.local/getting-started.md` | a New Timeline sentence and a `Ctrl+Shift+T` row | P6 |
| `packaging/desktop/…metainfo.xml` | 1.0.41 and 1.1.0 releases | P0, P6 |

**`docs/decisions.md` entries.** These form a dated section, "## 2026-10: note types and timelines", with these `###` entries:

| Id | Entry | Gist |
|---|---|---|
| D-1 | A note has a type; the provider stores it, the host edits it | `noteTypes`/`noteType`; load decides, rows draw; read only from declaring providers |
| D-2 | Note types are the app's own, not a plugin kind yet | the trigger, the 2c5920f template, qualified ids, the Python codec channel a package type would need |
| D-3 | The note pane hosts one body per type | `NoteBody`; the permanent rich editor behind `documentBody`; why not swap `NoteEditor`, a third flag or an early extraction |
| D-4 | A note opens in the form it can be held in | `documentType` vs `noteType`; unknown → read-only text; not in form → Markdown with the reason (U7) |
| D-5 | A timeline is a Markdown task list the editor itself writes | the format; written through `qthtml.convert`, re-read and refused on mismatch; plain titles, one paragraph per description line; why not bold, hard breaks, YAML, JSON or an HTML comment |
| D-6 | A timeline is read when it renders the same | tolerated variants normalised only on a user action; refusals; link definitions |
| D-7 | Checking checks everything above; unchecking, everything below | out-of-order shown as stored, never repaired on open; status line; undo |
| D-8 | The add-event form is part of the note | live compose; Esc discards with undo; never lost |
| D-9 | Timeline rows are a ListModel patched from an array | why it departs from "prefer arrays" (`docs/engine-notes.md:47`); the add area sits outside the ListView (focus) |
| D-10 | A local note's type is one front-matter line, written once | `note-note-type`; namespaced; never by a save; unreadable lines open read-only |
| D-11 | A new timeline comes from the provider's footer, Ctrl+Shift+T and the palette | why no host chooser yet; the chooser at the third type; why not Ctrl+Alt+N |
| D-12 | OneNote, Notion and Sticky Notes do not hold timelines yet | the evidence; the opt-in paths |
| D-13 | A tool acts only on a Markdown note | `EditorApi.writable` requires the document editor |
| D-14 | Changing a note's type is a separate operation, later | saves never carry types; only lossless directions |

The existing entry "Read-only rather than lossy writes" (`:660`) gains the link-definition sentence (P0).

---

## 9. Risks and mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | The pane refactor (P2) regresses the rich or plain editor. | Document code is only renamed and wrapped. P2 changes no behaviour, and every existing suite (core, keys, tools, lists, blocks, toolbar, diacritics, tables, qthtml) must stay green with no new warning. |
| R2 | The hidden TextEdit acts while a timeline is shown (tools, paste, IPC undo, keys). | `documentActive` gates `EditorApi.writable`, `applyReadOnly`, `paste`, `pastePlain`, `replayHistory`, `flick.visible`, `hoveredLink` and the Workspace paste guards. A focused timeline is the `workspace` context. EditorKeys timeline case 19 proves it. |
| R3 | A note is shown in the wrong body: a late type, a draft, a race. | The type is an argument of `setNote` and a field of every snapshot, activated before the body is touched. `noteToken` guards both async paths (including the fallback). Session cases 1–14 cover it. |
| R4 | A codec bug writes a corrupted timeline. | The writer is the editor's own reader. Every write is re-read and refused on mismatch, and refusals are framed failures that keep the draft. The property test runs 3000 models × 4 properties, plus a Qt leg. |
| R5 | A foreign edit is restyled or restructured on the next save. | The reader accepts only text that renders the same (tolerated variants are whitespace and markers). Anything else opens as Markdown and is never rewritten by the timeline body. Nothing is written without a user action. |
| R6 | A link definition is silently deleted (found while planning). | The timeline reader refuses definitions. The Markdown editor names unused ones read-only (C0.20). |
| R7 | A lone `+` cannot be saved, in 1.0.40 and the codec. | `mdtext.LINE_START` is fixed in P0. In 1.0.40 the failure is closed and the draft kept. |
| R8 | Note Note 1.0.40 or a host without types opens a timeline. | The canonical body is that editor's fixpoint and `unkept` is empty (verified). The type line survives its saves as an extra line. |
| R9 | The front-matter key collides with user metadata. | It is namespaced (U2). An unreadable or conflicting line opens read-only, and an unknown value opens read-only and is kept verbatim. Markdown notes never get the line. |
| R10 | Check states out of order (Obsidian, a phone, a merge). | They are shown as stored, never repaired on open, and the next action applies the rule over its reach. |
| R11 | One click unchecks many events by mistake. | The status line names the count and the range, and one `Ctrl+Z` restores. |
| R12 | Half-typed events are saved. | That is intended (U6). The pending row looks like a form, and Esc discards with undo. An empty or invalid form contributes nothing. |
| R13 | Local is last-writer-wins: a phone check races a desktop check. | Existing policy. A clean note reloads on an external change. Documented, with a version check in §10. |
| R14 | Listing cost. | Whole reads only for timeline-marked notes of 64 KiB or less, the codec imported lazily, under the existing 10 s deadline and output budget. |
| R15 | JS and Python drift: limits, id grammar, the progress definition, creatable types. | Regression pins (§7.6). Python validates every write and fails closed. JS cleaning is a superset of Python's whitespace rules. |
| R16 | Keys: Escape in the form reaching `back`; Ctrl+Up/Down swallowed by the list; `Ctrl+Shift+T` taken. | The form claims Escape first. Every handler is one `onPressed` with `host.shortcut` first (Qt's order trap, §4.2). `Ctrl+Shift+T` is free in app defaults, tools and Omarchy's bindings. EditorKeys 9 and 13 cover the first two. |
| R17 | A maximal timeline exceeds local's 2 MiB note limit. | The save fails with "note exceeds the 2 MB limit" and the draft is kept. The limits are documented side by side. |
| R18 | The noise gates fail on new QML warnings. | `Capabilities.of` removes the `hasTitle` warning. Bodies get `host` through `Loader.setSource` initial properties (verified warning-free). `console.warn` texts avoid the gate words. qmllint covers the new folders. |
| R19 | Docs and the skill mirror drift. | Both change in the same commit. P1 reconciles the existing drift. A review checklist covers every touched member. |
| R20 | An external provider already sends `noteType`. | It is read only from providers that declare `noteTypes` (a gated read). |
| R21 | A provider declares `timeline` but cannot keep Markdown verbatim, or merges. | The declaration rule in the contract. `timeline` requires `markdown`, so the fallback is storable. |
| R22 | Performance at 500 events. | ListView virtualisation, `patch` in place (no delegate rebuilds), and a timed EditorKeys case (23). |
| R23 | Accessibility roles are a new precedent. | Only standard roles are used, an EditorKeys assertion covers them, and no behaviour depends on them. |
| R24 | A glyph shows as a box, or a Style key exists in one host only. | The glyphs are verified in the bundled font and drawn with `Style.fontFamily`. Only the intersection keys (`design/Style.qml:20-47`) are used. |
| R25 | The working tree moves under this plan. | P0 commits it first. Re-derive the cited lines after P0, and steps name functions, not only lines. |
| R26 | ListView focus: a model reset steals focus from a field in its footer (verified). | The add area is outside the ListView, and rows are patched in place. EditorKeys 21 covers it. |
| R27 | Later package types capture ids or core names. | Qualified ids are reserved now, and core types cannot be removed. |
| R28 | A provider's progress is untrusted: huge numbers, a long `next`. | `NoteTypes.progressOf` clamps and refuses bad shapes. The text is drawn `PlainText`. |
| R29 | A new type folder is put under `ui/tools/` by mistake and loaded as a tool. | Bodies live under `ui/notetypes/`. Every `*.qml` in `ui/tools` is loaded as a tool (`ui/editing/ToolRegistry.qml:72`). |

---

## 10. Later work

| Item | What it takes |
|---|---|
| **Convert a note's type** | Lossless directions only. Timeline → Markdown is always lossless. Markdown → timeline is offered only when `timeline.read` accepts the body and `write(read(body)) == body`. Contract: an optional, feature-detected `setNoteType(path, noteType, cb)`. Local: an `operations.py` `retype` that rewrites only the type line through `write_atomic`, behind the mutation queue. Host: palette commands "Convert to Timeline" and "Convert to Note" that flush, retype and reload in place. Saves still never carry types. |
| **A type chooser** (when a third creatable type exists) | One `newNoteOfType` workspace action and palette command, `commandPalette.pick` over `Capabilities.of(p).creatableTypes`, running the provider's New Note footer action with `options.noteType`. Contract: `action(path, value, sectionKey, options)` for the `newNote` row. It replaces per-type actions and per-type footer rows. |
| **OneNote timelines** | Verify a `data-id` wrapper-div marker live in OneNote for Windows, Mac, web, iOS and Android, recorded in a dated `docs/onenote-*.md` section. Map events to to-do paragraphs plus margin-left description paragraphs in `onenote_md`. First fix the to-do converter edge cases the OneNote map lists: multi-tag values, priority tags, continuation lines, leading emoji, NBSP after hard breaks. |
| **Notion timelines** | The user picks the marker (page icon or marker block). `notion_md` keeps paragraph children under `to_do`. Optional targeted `checked` updates through Update-a-block, so a check is not a whole-page rewrite. |
| **Drag reordering, dates, timeline-aware conflict review** | As separate designs. Dates would be an additive grammar change, a trailing `@YYYY-MM-DD` read by a new codec version, with older versions falling back to Markdown. |
| **Bold titles** (U5 b) | Written through the Qt `font-weight:700` span. The judges' fuzz gave 0 mismatches in 1500. Plain titles stay accepted on read. |
| **Note types as a plugin kind** | When the D-2 trigger is met, following commit 2c5920f, with a Python codec channel for previews and progress. |
| **A local save version check** | So that a phone check is never overwritten (R13). |

---

## Appendix A — File-by-file change index

**NEW** marks a new file. Phases are in brackets.

| File | Change | Phase |
|---|---|---|
| `services/markdown/mdtext.py` | `LINE_START` escapes a lone `+` | P0 |
| `services/markdown/parse.py` | `parse_with_definitions`; `parse` wraps it | P0 |
| `services/markdown/qthtml/writer.py` | `unkept` names unused link definitions | P0 |
| `services/markdown/qthtml/selftest.py` | `CASES` lone `+`; `UNKEPT` definitions; timeline shapes | P0, P3 |
| `services/notes/capabilities.js` **NEW** | `of`, `toolsOf` (P0); `declarationProblem`, `legacyTypes`, `creationType`, `rowType`, types in `of` (P1) | P0, P1 |
| `services/notes/notetypes.js` **NEW** | the type table, `validId`, `entry`, `opened`, `progressOf`, `progressText`, … (P1); `timeline` entry (P5) | P1, P5 |
| `services/notes/sidebar.js` | `row()` `hasTitle` via Capabilities (P0); `noteType`, `progress` (P6) | P0, P6 |
| `services/notes/NoteSession.qml` | `clearNote`, `NoteTypes.opened`, `setNote(document)`, `shown` object, `restoreDocument` refusal, `isStored` with `documentType`, `requestBody(draft.document)` (P2) | P2 |
| `Workspace.qml` | `openCapabilities` and editor bindings, `newNote` focus (P0); `addProvider` warning, transitional `plain`, `newNote`/`newNoteDestination(…, noteType)` with create options (P1); `plain` removed, `countText`, paste guards, `debugState`, `editorUndo`, `documentType`, `editorWritable`, `runBodyAction` (P2); `glyphFor`, `displayProgress`, IPC `addEvent`/`toggleEvent` (P6) | P0, P1, P2, P6 |
| `ui/NoteEditor.qml` | the pane protocol, `documentBody`, `bodyHost`, `typedBodies`, `activate`, `bodyFor`, `documentActive` gating, renames (P2); overlay uses `CheckFace` (P5) | P2, P5 |
| `ui/editing/EditorApi.qml` | `writable` requires `documentActive` | P2 |
| `ui/ViewBar.qml` | `countText` replaces `wordCount` | P2 |
| `ui/notetypes/NoteBody.qml` **NEW** | the body contract | P2 |
| `ui/notetypes/timeline/TimelineModel.js` **NEW** | pure model | P5 |
| `ui/notetypes/timeline/TimelineBody.qml` **NEW** | the timeline body | P5 |
| `ui/notetypes/timeline/TimelineEvent.qml` **NEW** | one row | P5 |
| `ui/notetypes/timeline/EventForm.qml` **NEW** | the inline form | P5 |
| `ui/CheckFace.qml` **NEW** | the shared check face | P5 |
| `ui/ChromeTextArea.qml` **NEW** | multi-line chrome field | P5 |
| `ui/RowMenu.qml` | header comment generalised | P5 |
| `ui/NoteSummary.qml` | `glyph`, `progress` | P6 |
| `ui/NoteList.qml` | `glyphFor`, `progressFor` passed to `NoteSummary` | P6 |
| `ui/SearchResults.qml` | the same | P6 |
| `services/markdown/timeline.py` **NEW** | the codec and its CLI | P3 |
| `services/markdown/timeline_selftest.py` **NEW** | codec tests | P3 |
| `services/markdown/Markdown.qml` | `runScript`, `timelineScript`, `toTimeline`, `fromTimeline` | P3 |
| `plugins/org.note-note.local/notefile.py` | `TYPE_KEY`, `TYPE_ID`, `UNREADABLE`, `CREATABLE_TYPES`, `TIMELINE_PREVIEW_BYTES`, `note_type`, `type_line`, `progress`; docstring | P4 |
| `plugins/org.note-note.local/list.py` | `head_of` → 4 values; 10-field `N`; docstring | P4 |
| `plugins/org.note-note.local/operations.py` | `create` `noteType`; `read` `noteType`/unreadable; `save` `noteType`/`progress` | P4 |
| `plugins/org.note-note.local/Provider.qml` | `noteTypes` (P1, P6); `create(target, cb, options)` (P1, P4); `loadList`, rows, `searchable`, `load`, `save` commit, `progressField` (P4); `newTimeline` footer, `newNoteTarget`, `action` (P6) | P1, P4, P6 |
| `plugins/org.note-note.local/selftest.py` | §7.4 | P4 |
| `plugins/org.note-note.local/getting-started.md` | New Timeline | P6 |
| `plugins/org.note-note.sticky/Provider.qml` | `noteTypes: ["text"]`, no `markdown` | P1 |
| `plugins/org.note-note.notion/Provider.qml` | `noteTypes: ["markdown"]`, no `markdown` | P1 |
| `plugins/org.note-note.onenote/Provider.qml` | `noteTypes: ["markdown"]`, no `markdown` | P1 |
| `plugins/org.note-note.onenote/onenote.py` | drop per-page `markdown=True` (`:1380`, `:1387`) | P1 |
| `examples/hello/Provider.qml` | `noteTypes: ["markdown"]`, create options (P1); timeline support (P6) | P1, P6 |
| `services/commands/WorkspaceActions.qml` | `newTimeline`, `addTimelineEvent`, `state`, `canCreateNote(noteType)`, reasons | P1 (signature), P6 |
| `services/shortcuts/defaults.js` | `newTimeline`, `addTimelineEvent` | P6 |
| `plugins/org.note-note.workspace/plugin.json` | `new-timeline`, `add-timeline-event` | P6 |
| `services/extensions/selftest.py` | seven commands pinned | P6 |
| `tests/NoteTypeChecks.js` **NEW** | pure checks | P0, P1, P5 |
| `tests/transitions.qml` | `pureCases` calls `NoteTypeChecks.run`; fake editor protocol; `noteTypeSessionCases`; host, local and list cases | P0–P6 |
| `tests/EditorKeys.qml` | call sites, `resetEditor` (P2); `timeline` suite and `suites` entry (P5) | P2, P5 |
| `tests/audio.qml`, `tests/extensions.qml` | `setNote(document)`, `requestBody` | P2 |
| `tests/transition_selftest.py` | `SUITES` gains `timeline` | P5 |
| `tests/selftest.py` | `SCRIPTS` gains the codec selftest | P3 |
| `tests/test_regressions.py` | §7.6 | P0, P4, P5 |
| `tests/ShortcutChecks.js` | `Ctrl+Shift+T` check | P6 |
| `CMakeLists.txt` | CTest: qthtml, local, regressions (P0); `timeline-codec` (P3) | P0, P3 |
| `docs/providers.md`, `skills/note-note-plugin/references/providers.md` | §5.2.2 | P0, P1, P3, P4, P6 |
| `docs/commands.md`, `skills/note-note-plugin/references/commands.md` | action ids | P6 |
| `docs/note-types.md` **NEW** | architecture, format, view | P2, P3, P5 |
| `docs/README.md` | index row | P2 |
| `docs/technical-requirements.md`, `docs/business-requirements.md`, `docs/decisions.md`, `docs/editing-tools.md`, `docs/security.md`, `docs/testing.md`, `README.md` | §8 | P0–P6 |
| `manifest.json`, `packaging/desktop/io.github.andreivinca.note-note.metainfo.xml` | 1.0.41, 1.1.0 | P0, P6 |
| `CODE-REVIEW-2026-10-11.md` and the WT fixes it lists | committed as F-numbered commits | P0 |

---

## Appendix B — Glossary

| Term | Meaning |
|---|---|
| **note type** | What kind of note a note is (`text`, `markdown`, `timeline`). It decides how the host shows and edits it. |
| **`noteType`** | The contract field: the type a provider stores for a note (rows, `notes`, `load()`, `create` options). |
| **`noteTypes`** | The provider property: the types it stores and creates, its default first. |
| **declaring provider** | One whose `noteTypes` is valid. Only these are read for `noteType`. |
| **legacy provider** | One without a valid `noteTypes`. Its type comes from `markdown` (true → `markdown`, else `text`). |
| **`documentType`** | The pane's held form: the body that edits the open document. Carried in every snapshot. |
| **pane** | `ui/NoteEditor.qml`: the title, notices, views, toolbar row and read-only state, hosting one body. |
| **body** | What shows and edits one type's document: `documentBody` (the rich or plain TextEdit) or a typed body (`TimelineBody`). Implements `NoteBody`. |
| **`bodyHost`** | The narrow API the pane gives typed bodies. |
| **type table** | `services/notes/notetypes.js`: every type this version knows, its body, format, fallback and wording. |
| **fallback** | The type a body hands its text to when the text is not in its form (timeline → markdown). |
| **unknown type** | A valid or invalid id this version does not know. The note opens read-only as text. |
| **undeclared type** | A known type the provider does not declare. The note opens read-only as text. |
| **canonical form** | The only body the timeline codec writes: the editor's own Markdown for the events. |
| **snapshot form** | A body's own deterministic string for the session (`snapshot()`). For a timeline, JSON `[[checked, title, description], …]`. |
| **pending event** | The event typed in the open form. Part of the snapshot once its title is valid. |
| **prefix rule** | Check *k* checks 0..*k*; uncheck *k* unchecks *k*..*n−1*. |
| **out of order** | A state where an unchecked event sits above a checked one. Shown as stored. |
| **progress** | `{ done, total, next }`: checked count, event count, the first unchecked event's title. |
| **marker / type line** | Local's `note-note-type: <id>` front-matter line. |
| **codec** | `services/markdown/timeline.py`: `read`, `write`, `summary`, CLI. |
| **unkept** | What the Markdown editor would not write back as it is (`qthtml.unkept`). The local provider opens such a note read-only (`operations.py read`). |
| **WT** | The working tree at the time of writing: uncommitted review fixes on top of `e2cdc4e`. |
