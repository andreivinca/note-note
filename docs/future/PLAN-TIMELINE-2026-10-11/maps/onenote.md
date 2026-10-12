# Map: the OneNote provider (area `onenote`), for the content-type + timeline plan

Repository `/home/andrei/Projects/note-note`, HEAD `e2cdc4e`. Every claim below cites `file:line` at HEAD.
Nothing in the repository was changed. Converter and planner behaviour marked **[run]** was confirmed by running
the pure functions (`python3 -B`, no network, no repo writes) with the scripts in
`/tmp/claude-1000/-home-andrei-Projects-note-note/b40cb580-758c-4153-b2d0-b8e9d5523701/scratchpad/experiments/`
(`roundtrip.py`, `planner.py`, `edge.py`, `multitag.py`, `shape.py`, `indent.py`).

## Summary

- OneNote is a `LaneProvider` (`Provider.qml:13`). It declares `markdown: true` and `hasTitle: true` (`Provider.qml:19-20`), `canImages: true` (`Provider.qml:27`) and a `tools` list without quote, code, codeblock or rule (`Provider.qml:35-37`). The content type is per provider. The host reads it in exactly one place: `plain: !p.markdown` (`Workspace.qml:2837-2840`).
- `onenote.py page` already puts `markdown: true` on every page answer (`onenote.py:1380-1381, 1387`). Nothing in the host reads that per-load field. The only `markdown` consumer is `Workspace.qml:2839`, and the host's load handler (`services/notes/NoteSession.qml:252-299`) never touches it.
- **Loading a page.** `GET …/content?includeIDs=true` (`onenote.py:1350`) → `onenote_md.html_to_markdown` (`onenote_md.py:441-451`) → the merge journal `open()` (`onenote.py:1386`). The journal normalises the note through `normalize_note`, which runs Markdown → OneNote HTML → Markdown (`onenote.py:1286-1306`, `store.py:37-38`).
- **Saving a page.** `refuse_unkept_formatting` runs first (`onenote.py:1684-1691`). Then the draft is staged, the page is read fresh and the three versions are merged (`onenote.py:1700-1712`). Next `write_body` (`onenote.py:1617-1667`) does three things:
  - the planner `onenote_patch.plan` turns the change into element-level `PATCH` commands addressed by generated IDs;
  - the result is checked by simulation;
  - blank lines are removed first, through OneNote's undocumented web revision service.
  
  The title is written last, in its own `PATCH` (`onenote.py:1714-1724`).
- **Creating a page.** A `POST` of XHTML whose head holds only `<title>` (`onenote.py:1743`). It is never retried (`onenote.py:1762-1763`). The provider always creates with an empty title and body (`Provider.qml:1159-1160`).
- **To-do tags.**
  - Reading: `data-tag="to-do"` / `"to-do:completed"` on a `<p>` becomes `- [ ] ` / `- [x] ` (`onenote_md.py:223-226`); on a `<span>` in a list item it becomes `[ ] ` / `[x] ` (`onenote_md.py:213-214`).
  - Writing: a top-level list made only of task items becomes `<p data-tag="to-do[:completed]">` paragraphs (`onenote_md.py:635-641`); otherwise `<li><span data-tag=…>` (`onenote_md.py:647-649`).
  - Changing only a checkbox keeps the original HTML carrier and flips only its `:completed` suffix (`onenote_patch.py:143-161`).
- **Timeline shape.** A to-do paragraph with a bold title, followed by a paragraph indented 36px holding a one-line description, already round-trips losslessly and saves surgically today **[run]**.
- **No documented durable page-level marker exists:**
  - a custom `<meta>` is undocumented, and `meta`/`head` support no update actions;
  - custom note tags are unsupported by Graph;
  - a note tag on the title is not returned in output;
  - the page resource has no custom properties;
  - Graph's documented CSS has no way to hide an element.
  
  `data-id` survives Graph updates (measured, `engine-notes.md:622-623`). Microsoft does not document whether it survives edits in the OneNote apps, and there is a public report of `data-id` vanishing.

## 1. How page HTML maps to Markdown and back

### What the provider declares

| Declaration | Value | Where |
|---|---|---|
| `markdown` | `true` | `Provider.qml:19` |
| `hasTitle` | `true` | `Provider.qml:20` |
| `canCreate` / `canDelete` | `true` / `true` | `Provider.qml:21-22` |
| `canReorder` / `canCreateSection` | `false` / `false` | `Provider.qml:23-24` |
| `canImages` | `true` ("a pasted one is uploaded with the save") | `Provider.qml:25-27` |
| `tools` | `bold italic underline strikeout highlight textColor h1 h2 h3 p ul ol todo indent outdent table link currentMonth nextMonth customMonth` | `Provider.qml:35-37` |
| Why `tools` omits four constructs | "Not a quote, a code block, inline code or a rule: onenote_md.py writes each as a look its reader has no reading for … a save holding one is refused" | `Provider.qml:31-34` |
| `microsoftScopes` | `Notes.ReadWrite`, `Files.ReadWrite` | `Provider.qml:30` |
| Lane | `laneKey: "graph-onenote"` | `Provider.qml:55` |

- The contract says `markdown`: "bodies are Markdown (rendered); false = plain text" (`docs/providers.md:47`). The mirror for plugin authors says the same (`skills/note-note-plugin/references/providers.md:236`).
- `tools` is per provider (`docs/providers.md:54`).
- The host turns `markdown` into `editor.plain` (`Workspace.qml:2837-2840`), `canImages` into `editor.canImages` (`Workspace.qml:2831-2834`), `hasTitle` into `editor.hasTitle` (`Workspace.qml:2841-2844`) and `tools` into `editor.enabledTools` (`Workspace.qml:2845-2848`).

### Reading: HTML to Markdown (`Converter`, `onenote_md.py:84-414`)

**Note tags**
- Tag-to-emoji table (`onenote_md.py:30-36`): important ⭐, question ❓, idea 💡, critical ❗, remember-for-later 📌, contact 👤, address 🏠, phone-number 📞, web-site-to-visit 🔗, definition 📖, to-do-priority-1 🔴, to-do-priority-2 🟡.
- On a paragraph (`onenote_md.py:223-231`): `para_prefix` returns `- [x] ` when the tag starts with "to-do" and ends with "completed", and `- [ ] ` otherwise. It checks `startswith("to-do")` before looking up the emoji table. Any other non-empty tag calls `read_only()` **with no reason**.
- On inline `span/code/font/s/strike/del/cite` (`onenote_md.py:192-217`): to-do tags become `[x] ` / `[ ] `, and known tags become their emoji prefix. Styled spans become `**`, `*`, `_`, `~~`, `==` and text colour.

**Paragraphs** (`onenote_md.py:262-286`)
- `margin-left` in px or pt becomes four U+00A0 per 36px of indent (`onenote_md.py:269-272`, `INDENT_PX = 36` at `onenote_md.py:44`).
- Consecutive plain paragraphs are joined with hard breaks (`onenote_md.py:280-281`).
- A blank line separates text from list items (`onenote_md.py:282-283`).

**Other elements**
- Headings (`onenote_md.py:287-294`) never look at `data-tag`, so a to-do or other tag on `h1`–`h6` is silently dropped.
- `<head>`, `<title>`, `<style>`, `<script>` and `<meta>` are skipped (`onenote_md.py:242-243`).
- `<div>` is descended into, with a separator line added before it (`onenote_md.py:244-249`). The div's attributes, `data-id` included, are ignored.
- A table that contains to-do paragraphs is written as a rich (HTML) table (`onenote_md.py:358-366`).

**What the reader returns**
- `html_to_markdown` returns `{title, body, editable, reason, images, recordings}`. The title is the text of `<title>` (`onenote_md.py:441-451`).

### Writing: Markdown to OneNote HTML

- Markdown is parsed by the shared `services/markdown/parse.py` (vendored mistune). `onenote_md.py:454-457` is only a renderer.
- **Leading markers.** `_tagged` / `_tag_prefix` turn a leading `[ ]` / `[x]` or a tag emoji in the first text token into a `data-tag` (`onenote_md.py:540-559`).
- **Lines.** `_paragraphs` splits paragraphs at hard breaks, one OneNote `<p>` per line (`onenote_md.py:562-576`).
- **Paragraph element.** `_p` writes `<p data-tag=…>` with zero margins, and turns leading NBSP×4 into `margin-left` of 36px per level (`onenote_md.py:579-587`).
- **Task lists** (`_render_list`, `onenote_md.py:632-659`):
  - A top-level, unordered list made only of task items, with no sublists, becomes `<p data-tag="to-do[:completed]">` paragraphs (`onenote_md.py:635-641`).
  - Otherwise task items become `<li><span data-tag="…">…</span></li>` (`onenote_md.py:647-649`).
- **Item text.** `_item_inline` joins all of an item's paragraphs and hard-broken lines with spaces, and throws away any tag from a leading emoji (`onenote_md.py:666-671`).
- **Refused constructs.** `UNKEPT_KINDS` lists `block_quote`, `block_code`, `codespan` and `thematic_break` (`onenote_md.py:896-897`); `unkept_formatting` (`onenote_md.py:900-914`) names them. Task items with continuation lines are not on that list.
- **Runs.** `markdown_to_runs` returns text and media runs for the planner and for page creation (`onenote_md.py:864-889`).
- **Empty page.** `markdown_to_onenote_html` writes an empty styled `<p>` (`onenote_md.py:917-920`).

## 2. Creating and updating pages, and the merge

### Create

**In `Provider.qml`**
- `create(target, cb)` accepts only targets of the form `"section:<id>"` (`Provider.qml:1134-1147`).
- It lists a draft row at once and enqueues `onenote.py create <section> -` with `{title: "", body: ""}` (`Provider.qml:1148-1166`).
- `finishCreation` swaps the draft for the real page and replays queued saves with the new `view` (`Provider.qml:1186-1241`).
- **The create contract carries no content type.**

**In `onenote.py`** (`cmd_onenote_create`)
- Builds `<!DOCTYPE html><html><head><title>…</title></head><body>…</body></html>`, with the body from `wrap_runs` (`<div>` per text run, media beside them) (`onenote.py:1743`, `onenote.py:1584-1592`).
- Sends it as `application/xhtml+xml`, or multipart with media (`onenote.py:1744-1757`).
- The `POST` uses `RetryPolicy.NEVER` (`onenote.py:1762-1763`).
- Records the page as top level, `level 0`, at the end of its section (`onenote.py:1773-1785`).
- Indexes it for search (`onenote.py:1786-1791`).
- Opens a merge journal with the posted body (`onenote.py:1792-1794`).

### Update

**Path in**
- `Provider.save` sends `{title, body, view, resolution}` on stdin (`Provider.qml:1086-1092`).
- `cmd_onenote_update` (`onenote.py:1694-1726`) runs: `require_writable` → `refuse_unkept_formatting` (before staging, because the store normalises drafts) → `journal.stage` → `read_page` → `journal.prepare` (three-way merge). A conflict is returned as `{error, conflict}`.

**Checks and writes**
- `normalize_note(note) != note` fails (`onenote.py:1711-1712`).
- `write_body` runs, then the title (the body is committed first with `accepted_fields=("body",)`), then `journal.commit` (`onenote.py:1713-1726`).

**`write_body`** (`onenote.py:1617-1667`)
- Skipped when the merged body equals `normalize_note(remote)` (`onenote.py:1622`).
- Otherwise `markdown_to_runs` with upload resolvers, then `onenote_patch.plan(current, desired, project)`, where `project` re-renders each source element through normalisation (`onenote.py:1635-1645`).
- `UnsupportedEdit` or `InvalidPlan` fails with "… — your draft was kept" (`onenote.py:1644-1645`).
- The simulated page must convert back to exactly the merged body (`onenote.py:1646-1649`).
- Blank-line removal through `blank_lines.py` happens first (`onenote.py:1654-1657`), then one `PATCH` (`onenote.py:1658-1666`).
- `patch_page` sends a `PATCH` made only of replaces with `RetryPolicy.RESTART`; inserts and uploads use `NEVER` (`onenote.py:1571-1581`).
- `write_title` uses `target: "title"`, `action: "replace"` (`onenote.py:1670-1681`). Some older pages answer 500 to title writes (`docs/engine-notes.md:532-536`).

### Planner (`onenote_patch.py`)

**Building blocks**
- Constants `REPLACEABLE = {p, li, h1-h6, ul, ol, table, img, object}`, `LISTS`, `LAYOUT = {html, body, div}` (`onenote_patch.py:17-19`).
- `children()` drops `head`, `title`, `meta`, `style` and whitespace (`onenote_patch.py:76-79`).
- `elements()` flattens layout divs (`onenote_patch.py:82-90`).
- `document_elements()` trims boundary `<br>` (`onenote_patch.py:93-107`).

**Targets**
- Only generated IDs `tag:{…}`, or `data-id` on `img`/`object` (`onenote_patch.py:127-140`).

**Checkbox carrier**
- `replacement()` (`onenote_patch.py:143-161`): when only checkbox state differs, the original element is kept and only the carrier's `data-tag` `:completed` suffix flips.
- `checkbox_carriers` finds every descendant whose `data-tag` starts with `to-do` (`onenote_patch.py:164-165`).

**`sequence()`** (`onenote_patch.py:185-227`)
- Fast path: when the existing content is an unchanged prefix, the additions are appended after it (`onenote_patch.py:189-193`).
- Otherwise `notemerge.align(before, after, identity)` runs.
- Text typed on a blank line removes the `<br>` and inserts the text in its place (`onenote_patch.py:200-205`).
- Deletions become `replace` with `<div></div>`, or with `<p><br/></p>` in table cells (`onenote_patch.py:222-225`).

**Other steps**
- `insert()` anchors before or after a neighbour that has an ID, else at a layout boundary, else appends to an empty body, div or list (`onenote_patch.py:265-287`).
- `update()` handles lists recursively, nested items and tables, and refuses restructures that would replace nested elements (`onenote_patch.py:322-342`).
- `finish()` simulates the commands and requires every retained ID, tag and attribute (and every unchanged subtree) to be identical (`onenote_patch.py:420-435`).
- `preserve_projected()` keeps a source element whose normalised projection is unchanged (`onenote_patch.py:493-529`).

**`UnsupportedEdit` cases** (draft kept, nothing written)

| Line | Message |
|---|---|
| `onenote_patch.py:140` | OneNote supplied no editable target for this `<tag>` element |
| `onenote_patch.py:153` | this checkbox has no unique state carrier |
| `onenote_patch.py:160` | this checkbox state cannot be changed without altering its content |
| `onenote_patch.py:245` | OneNote supplied no editable target for this br element |
| `onenote_patch.py:283` | OneNote supplied no target for this empty container |
| `onenote_patch.py:286` | OneNote supplied no insertion target at this position |
| `onenote_patch.py:340` | this restructure would replace nested elements; edit it in OneNote |
| `onenote_patch.py:351` | this list text has no separate target from its nested list; edit it in OneNote |
| `onenote_patch.py:362` | OneNote cannot change this table's rows without rebuilding it |
| `onenote_patch.py:372, 408` | OneNote cannot change this table's columns without rebuilding it |
| `onenote_patch.py:381` | this table cell has no editable paragraph; edit it in OneNote |
| `onenote_patch.py:543-544` (from `lib/notemerge/alignment.py:62-63`) | cannot identify which repeated entry was inserted, removed, or renamed |

**`InvalidPlan` cases**

| Line | Message |
|---|---|
| `onenote_patch.py:432` | an unchanged element lost its identity |
| `onenote_patch.py:434` | an unchanged element was modified |
| `onenote_patch.py:445` | a blank line has no unique preceding element |
| `onenote_patch.py:452` | blank lines no longer separate their neighbouring elements |
| `onenote_patch.py:473` | an operation targets a missing or repeated element |
| `onenote_patch.py:489` | unsupported operation |

### Merge (`lib/notemerge`)

- **Snapshots** hold only `title` and `body` text (`merge.py:106-117`). Any other field, such as a content type, is not journalled or merged.
- **`merge_note`** (`merge.py:169-199`) is a three-way line merge with word-level refinement. Conflicts come back structured, never as markers.
- **`text_key`** ignores checkbox state (`alignment.py:27-38`). Checkbox changes merge per entry: "Entry labels align independently of checkbox states" (`lib/notemerge/README.md:8-14`).
- **`align`** raises `AmbiguousAlignment` when the count of a repeated key changes (`alignment.py:50-65`).
- **`MergeStore`** (`store.py:26-159`): `open` (`store.py:102-110`), `stage` (`store.py:112-121`), `prepare` (`store.py:123-131`), `commit(saved, accepted_fields)` (`store.py:133-159`), all normalised through `note()` (`store.py:37-38`).
- OneNote uses `stale_seconds=120` (`onenote.py:1333-1336`).
- "Checkbox state changes preserve the existing HTML carrier" (`lib/notemerge/README.md:98-100`).
- "OneNote currently has no verified conditional page-content write" (`lib/notemerge/README.md:159-162`).

## 3. Can a OneNote page carry a durable "this is a timeline" marker?

Evidence from Microsoft Learn (fetched 2026-10-11) and from this repository:

| Candidate | Round-trips through Graph? | Survives OneNote app edits? | Can be added to an existing page? | Verdict |
|---|---|---|---|---|
| Custom `<meta>` in head | Not documented. Create-page lists only "`<title>` and `<meta>` that set the page title and creation date"; "If a tag's not listed there, it'll probably be ignored." The input/output example's output head shows only `<title>`. | Not documented | **No**: "The following elements do not support any update actions … meta, head" (update-page) | Not viable |
| `data-id` on a div or paragraph | Yes. A documented input and output attribute on div, img, object, p/h1-h6, ul/ol/li and table. "The div would have been preserved if it defined any semantic information, such as a data-id." This repo measured that "`data-id` attributes we write **do** survive an update" (`engine-notes.md:622-623`). | **Not documented.** A Microsoft Q&A thread (#543009, 2021, unresolved) reports `data-id`s missing from content fetched later, without any `PATCH`. | Yes: `insert` or `append` an element carrying it (div within a div supports append and insert) | The only plausible machine marker. Live verification on desktop, web and mobile is needed first. |
| Custom note tag | No: "Adding or updating custom tags using Microsoft Graph is not supported." / "Custom tags are not supported." | n/a | n/a | Not viable. Today an unknown `data-tag` also makes the page read-only with no reason (`onenote_md.py:229-230`) **[run]**. |
| Note tag on `<title>` | Input only: "The `title` element doesn't return any note tag information." | n/a | n/a | Not viable |
| Built-in tag on a dedicated paragraph | Yes, native content | Yes, native | Yes | Visible and user-editable; misuses a tag's meaning; a hack |
| Hidden element | Documented CSS covers background-color, color, font-family, font-size, font-style, font-weight, text-decoration, text-align only. "JavaScript code, included files, and CSS are removed." | n/a | n/a | Not viable |
| Title convention (prefix or suffix) | Yes. The title is in every listing (`onenote.py:195-197`, `onenote.py:228`), so it is known before any content read. | Yes, but users can rename the page | Yes, via the title `PATCH`, which fails on some old pages (`engine-notes.md:532-536`) | Durable but user-visible convention. The planners must decide whether it counts as a "hack". |
| Graph page property | The onenotePage resource has no custom properties. `createdByAppId` is read-only; only `title` is not read-only. | n/a | n/a | Not viable |
| Local registry keyed by page ID | n/a | n/a (this device only) | Yes | Does not roam across devices; invisible in OneNote |
| Web revision service | Undocumented, personal notebooks only, needs `Files.ReadWrite` (`docs/onenote-page-order.md:51-56`, `64-70`) | ? | ? | Not suitable |

If the timeline body is an ordinary to-do checklist (section 4), losing the marker degrades gracefully: the page opens as a checklist note and no content is lost.

## 4. What a timeline should look like inside OneNote

The natural shape, per event: `<p data-tag="to-do[:completed]"><b>Title</b></p>`, optionally followed by `<p style="margin-left:36px">Description</p>`. OneNote shows a checklist of bold items, each with an indented note, and all OneNote apps can toggle the boxes.

**What round-trips today [run]**
- Event shape → Markdown `- [x] **Kickoff**\n\n    Meet the team\n\n- [ ] **Design**…` and back with no change (`roundtrip.py` case A).
- An unindented plain description also round-trips (case C).

**What the planner does with it [run]** (`planner.py`)

| Change | Commands produced |
|---|---|
| Check event k and every event above it | k `replace`s, each keeping the original inline HTML (e.g. `<span style="font-weight:bold">`) |
| Append an event with a description at the end | one `insert after` holding both paragraphs |
| Insert an event between two others | one `insert before` |
| Edit a description | one `replace` |
| Delete an event | `replace` with `<div></div>` per element |
| Reorder events | `insert` + `replace` with `<div></div>`; the moved event loses its identity |
| Append an event whose title repeats an existing one | works (unchanged-prefix path) |
| Insert that repeated title in the middle | **UnsupportedEdit** (ambiguous alignment) |

**Pre-existing lossy or wrong cases [run]**

| Case | What happens | Cause |
|---|---|---|
| Description of 2+ consecutive indented paragraphs | Lines after the first lose their indent at load normalisation. The next unrelated save rewrites them without `margin-left` (`indent.py`). | `onenote_md.py:280-281` joins them with hard breaks; the shared parser drops the NBSPs after a hard break |
| `<br/>` inside a to-do paragraph (title + description in one paragraph) | Toggling the checkbox flattens it to "Title Description" (`edge.py`) | `_item_inline`, `onenote_md.py:666-671`; `replacement()` falls back to the new node because the `text_key` differs |
| Markdown task item with a continuation line or second paragraph | Silently joined into one line when the draft is staged; `unkept_formatting` does not flag it (`roundtrip.py` K, L) | `_item_inline` |
| Task item title starting with a tag emoji (⭐, 📌…) | The emoji is silently dropped on write | `_item_inline` discards the tag |
| `to-do-priority-1` / `to-do-priority-2` | Reads as a plain checkbox. Toggling keeps the priority; a text edit writes plain `to-do`. | `startswith("to-do")` wins over the emoji table at `onenote_md.py:213, 225` |
| Multiple tags, e.g. `to-do:completed, important` | Reads as **unchecked**. Checking it writes `data-tag="to-do:completed, important:completed"` (`multitag.py`). | `endswith` / `removesuffix` applied to a multi-tag string |
| `data-tag` on a heading | Tag invisible in the app and dropped on edit (`edge.py`) | `onenote_md.py:287-294` |
| `definition` tag | Written back as `definition`, but Graph returns it as `remember-for-later` (note-tags doc), so the 📖 becomes 📌 on the next read | Graph behaviour |

The "check everything above" rule cannot be enforced in OneNote: its apps toggle each to-do independently. The three-way merge combines checkbox changes per entry (`merge_selftest.py:1117-1123`), so states that break the rule will arrive.

## 5. Recommendation

**Defer OneNote timelines in the first release.** Ship the content-type contract with OneNote declaring only its current Markdown type, and do not offer "New timeline" in OneNote notebooks.

Reasons:
1. No documented, durable, machine-readable page marker exists. `data-id` is the only candidate, its survival across OneNote apps is undocumented, and there is a public report of it disappearing.
2. A marker could only be added through a `PATCH`, never in the head.
3. The "check everything above" rule cannot be kept by OneNote's apps or by the per-entry merge.
4. Several pre-existing to-do and indent losses (section 4) would hit timeline content.
5. The project's rules forbid workarounds and lossy writes.

The content shape already round-trips, so the follow-up costs little: pick the marker, verify it live, document it in `docs/onenote-*.md` with a "Verification on <date>" section, fix the converter edge cases, then enable.

## Integration points (if and when OneNote supports timelines)

| Where | What changes | Why |
|---|---|---|
| `Provider.qml:16-37` | Declare which content types OneNote supports, through the new contract instead of the single `markdown` flag | The type moves from per provider to per note |
| `Provider.qml:983-993`, `995-1029` | `cacheBody` and `load` carry the page's type | The host needs the type on load |
| `onenote.py:1373-1387` | `cmd_onenote_page` emits the type on both the recovered and the normal path; the unused `markdown: true` field gives way to it | Python is the only place that sees the page HTML |
| `onenote_md.py:441-451` and `onenote_md.py:244-249` | The reader detects the marker (for example the div's `data-id`) and reports it | Today the div's attributes are ignored |
| `onenote.py:1729-1794` and `Provider.qml:1134-1167` | Creation carries the requested type; `cmd_onenote_create` writes the marker in the `POST` (for example `wrap_runs` with a `data-id` div) | Today `create(target, cb)` and the `POST` carry no type, and the body is empty |
| `Provider.qml:252-263`, `267` | Rows, `new` rows and `notes` may carry the type, or a "New timeline" target | Lets the sidebar tell types apart and create one; the listing has no content, so the type comes from a cache or the title |
| `onenote.py:1694-1726` and `1617-1667` | The save keeps the marker, and refuses a timeline body the page cannot hold | `unkept_formatting` does not cover task-item continuation lines |
| `onenote_md.py:213-231`, `287-294`, `632-671` | Fix the to-do edge cases: multi-tag, priority, headings, multi-line items, leading emoji | Timeline correctness |
| `Provider.qml:1384-1394` | `applyCheck` also compares the type | A poll must notice a lost or added marker |
| `lib/notemerge/merge.py:106-117` | Decide whether the type is journalled | Snapshots hold only title and body |
| `onenote.py:328-363`, `search_index.py:252-267` | Optionally record the type per page while indexing | Lets the listing show types without extra requests |
| `docs/providers.md:41-59`, `260`, `350-357`; `skills/note-note-plugin/references/providers.md:236-242` | Contract text for the type, additively | `technical-requirements.md:99-101`: change it additively, never silently |
| `docs/engine-notes.md` OneNote quirks; new `docs/onenote-timeline.md` | Record the marker evidence and the live verification | The house style for undocumented behaviour (`onenote-blank-lines.md:55-78`) |
| `plugins/org.note-note.onenote/merge_selftest.py:822-915` | New save tests using the fake Graph harness | The proven harness |

## Constraints (documented)

- Never lose, duplicate or corrupt notes; when in doubt open read-only (`docs/README.md:40-41`; `business-requirements.md:29-31`).
- Be honest about limits in the UI (`business-requirements.md:42-44`); read-only rather than lossy writes (`decisions.md:660-697`).
- The host must not branch on provider id (`technical-requirements.md:85-91`); the provider contract changes additively (`technical-requirements.md:99-101`).
- A construct the backend flattens must not be offered, and a save holding one must fail rather than lose it (`docs/providers.md:54`; `onenote.py:1684-1691`).
- A save keeps its draft on any unsupported edit; there is no whole-page rebuild fallback (`notemerge/README.md:76-77, 88-91`; `decisions.md:217-252`).
- An unchanged image is never sent back (`security.md:74` rule 4; `engine-notes.md:624-634`).
- Uncertain inserts and creates are never retried (`onenote.py:1571-1581`, `1758-1763`; `engine-notes.md:638-639`).
- Every Graph request goes through the lane and the `graph-onenote` budget of 100/min and 350/hr (`onenote.py:56-59`; `technical-requirements.md:162-166`, `181`).
- Page content is hostile input; bound everything (`security.md:16`, `327-337`).
- Round-trip stability is the converter property to test (`testing.md:525-530`); the planner invariants are at `testing.md:549-568`.
- Code style (`CLAUDE.md`): no hacks or workarounds, braces on every block.

## Reusable pieces

- `onenote_md.Converter` / `html_to_markdown` / `markdown_to_runs` / `markdown_to_onenote_html` (`onenote_md.py:84`, `441`, `864`, `917`).
- To-do paragraph rendering: `_p` and `_render_list` (`onenote_md.py:579-587`, `632-659`).
- Checkbox carrier preservation: `replacement()` and `checkbox_carriers()` (`onenote_patch.py:143-165`).
- `onenote_patch.plan` with `preserve_projected` (`onenote_patch.py:493-545`).
- `notemerge`: `MergeStore`, `merge_note`, `align`, `text_key` (`lib/notemerge/__init__.py:6-8`).
- `normalize_note` (`onenote.py:1286-1306`).
- Test harness: `SaveTests` `setUp` / `graph` / `load` / `save` and `page_html` / `note` (`merge_selftest.py:29-44`, `822-915`).
- The live-verification doc pattern (`docs/onenote-blank-lines.md:55-78`).
- Search-index page reads (`onenote.py:328-363`).

## Open questions

- Does a `data-id` written via Graph survive edits in OneNote for Windows, Mac, web, iOS and Android? Does copy-paste duplicate it?
- Does a custom `<meta name=…>` in the head survive even a Graph round trip?
- How does an indented paragraph made in a OneNote app come back from Graph (`margin-left`)? Does the output order of several outlines match their visual order?
- What should the app do with timeline pages whose check states break the "everything above" rule after OneNote or merge edits: show them as is, repair, or refuse?
- What does unchecking mean (does it uncheck everything below)? The request does not say.
- Should OneNote ever convert an existing page into a timeline, and how (marker insert, title)?
- Where does the type live for a note whose marker is lost: is it a Markdown note again, or remembered locally?

## Risks

- A marker lost in the OneNote apps silently changes a timeline back into a checklist.
- Non-monotone check states will arrive.
- Inserting a repeated title in the middle refuses to save; reordering re-creates elements.
- The multi-line description and to-do tag edge cases silently lose formatting today.
- The listing cannot know a page's type without reading its content.
- `createdByAppId` and the title cannot carry the type safely.
- Rate budget: each check is one `GET` plus one `PATCH`; fast repeated clicks are coalesced by the lane's `replace` mode (`Provider.qml:1091`).
