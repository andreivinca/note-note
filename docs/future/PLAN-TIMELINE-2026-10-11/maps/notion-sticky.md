# Map: notion-sticky (Notion and Microsoft Sticky Notes providers)

Repository `/home/andrei/Projects/note-note`, HEAD `e2cdc4e`, branch `master`. Every `file:line` is at HEAD.
Probe scripts (outside the repo, run with `PYTHONDONTWRITEBYTECODE=1`; `git status` stayed clean):
`scratchpad/probe/roundtrip.py`, `scratchpad/probe/edges.py`, `scratchpad/probe/childpage.py`.

## Summary

Both providers extend `services/providers/LaneProvider.qml`, which gives them the host hooks, a 1500 ms
save debounce (`noteEdited` -> `saveRequested`), one request lane per rate key, one Python process per job,
and a session guard that refuses answers landing after a sign-in change.

**Notion** declares `markdown: true`, `hasTitle: true`, `canCreate`/`canDelete: true`, no `canImages` (so false),
no `search()`, and a `tools` whitelist of 19 tool ids, including `todo` but not `table` or `textColor`.
`notion.py` (pinned to Notion-Version `2022-06-28`) lists pages through `/search`. It loads a page by fetching
every block recursively (300-block budget) and converting them to the editor's Markdown dialect in
`notion_md.py`. It saves by converting the Markdown back to blocks, appending all new top-level blocks first,
then deleting every old one: the page's whole content is replaced on every save, block ids included.

A page opens editable only if its blocks survive the round trip blocks -> Markdown -> blocks, compared
property by property (`notion_md.unwritable` / `essence`). The same check runs again on the live page right
before a save writes anything. The writer refuses Markdown it has no block for (`Unkept`).

`to_do` blocks map to `- [ ]` / `- [x]` task items. Their `checked` state is written back. Their children
nest as indented Markdown (only list items and to-dos may hold children). A line break inside the item's
rich text becomes a Markdown hard break.

Probes show what round-trips today, unchanged:
- One `to_do` per event, with "title\ndescription" in its rich text (bold title or plain).
- A `to_do` with a bulleted or to-do child.

Probes also show what does not:
- A `to_do` with a *paragraph* child opens read-only.
- A description of more than one paragraph is refused by the writer.
- A `callout` marker opens read-only.
- A parent page that holds a sub-page (`child_page`) opens read-only. Note Note creates new pages under the
  open page, so creating any note makes that parent read-only.

The Notion API gives no invisible place for a per-page content type:
- A page whose parent is a page may hold only the `title` property.
- Pages and blocks have no custom or app metadata field.

The candidate markers are all visible to the user, or not durable:
- The page `icon` (user-visible and user-editable).
- A marker block.
- A database property (database pages only).
- A local map kept by Note Note.

Notion's own UI shows `to_do` blocks as a checklist but never enforces "checking one checks all above".

**Sticky Notes** declares `markdown: false` (the host turns that into a plain-text editor with no tools)
and `hasTitle: false` (the subject is a copy of the first line). It has no `tools` and no images. Its
`search()` answers from memory over every listed body.
- `sticky.py` reads bodies as text (`Prefer: outlook.body-content-type="text"`).
- A save PATCHes `{body: {contentType: "text"}, subject: first non-empty line[:255]}`; the title argument is ignored.
- A create POSTs an empty message with `singleValueExtendedProperties` `String 0x001A = IPM.StickyNote`.

The only places a timeline could live are an invented plain-text syntax in the body (shown raw by
Microsoft's apps) or a custom named extended property on the message. Graph supports such a property on
messages, but nobody knows whether Microsoft's Sticky Notes clients preserve it.

---

## 1. Facts: Notion provider (QML)

| # | Claim | Where |
|---|---|---|
| N1 | The Notion provider is a `LaneProvider` (the shared request-lane base). | plugins/org.note-note.notion/Provider.qml:11 |
| N2 | Declarations: `id "notion"`, `name "Notion"`, `markdown: true`, `hasTitle: true`, `canCreate: true`, `canDelete: true`, `canReorder: false`, `canCreateSection: false`, `microsoftScopes: []`. | Provider.qml:14-23 |
| N3 | `tools: ["bold","italic","underline","strikeout","highlight","code","h1","h2","h3","p","ul","ol","todo","indent","outdent","quote","codeblock","rule","link"]`. Comment: "No table: Notion tables are not representable as Markdown tables here." `textColor` is absent. | Provider.qml:24-28 |
| N4 | No `canImages` property is declared, so it defaults to false (`p.canImages === true` in the host). | Provider.qml:14-28; Workspace.qml:2831-2834; docs/providers.md:53 |
| N5 | Script `notion.py`; `laneKey: "notion"`. | Provider.qml:30-34 |
| N6 | Model: `pages: [] // [{ id, title, parent, edited }]` and `bodies: ({}) // id -> { title, body, editable }`. | Provider.qml:38-39 |
| N7 | `integration` is the session; `environment: { NOTE_NOTE_NOTION_SESSION: root.integration }`. `switchIntegration` clears pages and bodies. | Provider.qml:43-58 |
| N8 | Note rows: `{ kind: "note", path, title, preview: "", version: edited, modified: edited, menu: noteMenu }`. The menu is Delete only (`command: "deleteNote"`). Footer: New Note (only when pages exist), Refresh, Settings. Single section `key "notion"`, color `#B8B0A8`. | Provider.qml:73-95 |
| N9 | Deliberately no `search()`: Notion's search endpoint matches titles only. | Provider.qml:97-101; docs/providers.md:401-404 |
| N10 | `createTargetFor(path)` gives `"parent:" + id of the open page`, otherwise the first page. Comment: "the API cannot create top-level pages". | Provider.qml:103-111 |
| N11 | Poll: a listing every third 20 s tick. `listPages` is enqueued with key `list`, mode dedupe/replace, priority 1. | Provider.qml:112-158 |
| N12 | `load()` answers from `bodies` when `cached.version === page.edited`. Otherwise it enqueues `page <id>` (key `load:<path>`, dedupe, priority 0) and caches `{title, body, editable, reason, version}`. The load answer carries no type field. | Provider.qml:161-200 |
| N13 | `save()` sends payload `JSON.stringify({ title, body })` to `update <id> -`, with key `page:<id>`, mode `replace`, `flush: true`. On success the model changes after the backend: `bodies[id] = {title, body, editable: true, version: ""}` and the page title is updated. A cancelled save answers `unsentSave(info)`. | Provider.qml:202-239 |
| N14 | `create()` resolves the parent from the target (`"new"` means the first page; `"parent:<id>"`). It always sends `{ title: "", body: "" }`, with key `create:<parent>`, mode append, flush. The new page is prepended to `pages`. | Provider.qml:241-279 |
| N15 | `remove()` enqueues `delete <id>` on the same key `page:<id>` as saves, so a delete never overtakes a save. | Provider.qml:281-306 |
| N16 | Setup is the provider's own view: a pasted integration secret, sent over stdin as `setup -`. | Provider.qml:383-414, 416-515 |

## 2. Facts: Notion script (`notion.py`)

| # | Claim | Where |
|---|---|---|
| S1 | Commands: `status`, `setup`, `logout`, `list [--cached\|--max-age S]`, `page <id>`, `update <id> <file>`, `create <parentId> <file>`, `delete <id>`, `clear-cache`. | notion.py:9-17, 414-445 |
| S2 | `VERSION = "2022-06-28"` is sent as the `Notion-Version` header. | notion.py:37, 147 |
| S3 | Limits: `MAX_PAGES = 1000`, `MAX_BLOCKS = 300` ("per page; more opens read-only"), `MAX_BODY = 4 MiB`. | notion.py:40-42 |
| S4 | Pacing: `RATE_KEY "notion"`, `RATE_WINDOWS [(1, 3)]`. | notion.py:47-48 |
| S5 | `api()`: a 429 is retried in place; a 503 on a GET is retried; a 503 or transient 5xx elsewhere follows `transient_5xx` (update: parked or re-run; create: `transient_5xx=False`, reported). A redirect is never followed (`NoRedirect`), and each attempt has a 30 s deadline. | notion.py:106-180 |
| S6 | `title_of(page)` returns the plain text of whichever property has `type == "title"`. | notion.py:187-192 |
| S7 | `parent_of(page)` returns `page_id`, else `database_id`, else `"workspace"`. Database pages are listed too. | notion.py:195-197 |
| S8 | `cmd_list` sends POST `/search` with `filter {property: object, value: page}`, sorted by `last_edited_time` descending, 100 per page, up to `MAX_PAGES`. It skips archived pages and keeps only `{id, title, parent, edited}`; the page `icon` is not read. | notion.py:253-277 |
| S9 | `fetch_children(block_id, budget)` recurses into every block with `has_children`, except `child_page`. The budget is decremented per block, nested blocks included; past the budget the result is truncated. | notion.py:280-301 |
| S10 | `cmd_page`: GET `/pages/<id>`, then `fetch_children(page, [300])`, then `blocks_to_markdown` (its own `editable` flag is discarded), then `reasons = unwritable(blocks)`. Truncation adds "more than 300 blocks". Answers `{title, body, editable: not reasons, reason}`, with reason "This page holds %s, which Note Note cannot write back, so it opened read-only". | notion.py:304-318 |
| S11 | Comment: "A save replaces the whole page with these blocks written back, so the page opens for editing only when that would put it back as it is." | notion.py:310-311 |
| S12 | `cmd_update` order of work. **(1)** Convert first, before any request: the title becomes `text_items` and is validated, and the body becomes `append_batches(markdown_to_blocks(body))`; a `ValueError` fails the save. **(2)** Fetch the old blocks with budget 301; more fails with "the existing page is too large to replace safely". **(3)** Run `unwritable(old)` again; any reason fails with "this page now holds %s, which Note Note cannot write back; edit it in Notion — your draft was kept". **(4)** GET the page, and PATCH the title property only if it changed. **(5)** PATCH `/blocks/<page>/children` once per batch of 100 (new blocks appended at the end). **(6)** DELETE `/blocks/<old id>` for every old top-level block. Answers `{ok: true}`. | notion.py:321-375 |
| S13 | Insert-then-delete rationale: "The worst case becomes the note twice over — visible, and something the user can fix." | notion.py:352-366 |
| S14 | `cmd_create` POSTs `/pages` with `{parent: {page_id}, properties: {title: {title: text_items(title)}}, children: markdown_to_blocks(body)}`, after `validate_payload`, with `transient_5xx=False`. It answers `{ok, page: {id, title, parent, edited}}` and updates the cache. | notion.py:378-401 |
| S15 | `cmd_delete` sends PATCH `/pages/<id>` with `{archived: true}`. | notion.py:404-411 |

## 3. Facts: Notion conversion (`notion_md.py`)

| # | Claim | Where |
|---|---|---|
| M1 | Docstring: supported both ways are paragraph, heading_1..3, bulleted_list_item, numbered_list_item, to_do, quote, code, divider, and nested children as indentation. Rich text supports bold, italic, underline, strikethrough, code, links and the yellow highlight. | notion_md.py:1-9 |
| M2 | `SUPPORTED`, `KEPT_COLORS = {default, yellow_background}`, `NESTING = {bulleted_list_item, numbered_list_item, to_do}`, `WRITTEN = {rich_text, children, checked, language}`. | notion_md.py:20-29 |
| M3 | `UNWRITTEN` is the table of block properties written at their default: `color`, `caption`, `is_toggleable`, `icon`, `list_start_index`, `list_format`. Any other truthy property counts as unwritable. | notion_md.py:34-54 |
| M4 | `rich_to_md`: code becomes backticks, bold `**`, italic `*`, underline `_`, strikethrough `~~`, any `*_background` colour `==…==`, href `[..](..)`. Adjacent runs with the same style are joined first. | notion_md.py:71-111 |
| M5 | `essence(blocks)` compares, per block: type, characters with their marks, `checked`, code language, unwritten properties, and children. The same shape is built for API answers and writer requests. | notion_md.py:133-152 |
| M6 | `unwritable(blocks)` first walks for unsupported types, text nested under a non-NESTING block, unwritten properties, non-text runs (mentions...) and coloured text. It then round-trips. An `Unkept` gives its `what`; any other `ValueError` gives "text a save could not write back"; an essence mismatch gives "formatting a save could not put back as it is". | notion_md.py:155-198 |
| M7 | to_do to Markdown: `pad + ("- [x] " if checked else "- [ ] ") + _item_text(text, pad + "  ")`. Line breaks in an item become hard breaks continued at the indent. | notion_md.py:201-205, 259-262 |
| M8 | Headings: `#` repeated n times, with blank lines around. Paragraphs: consecutive ones are joined with hard breaks; an empty one is written as `BLANK_PARAGRAPH`. Quote: `> `. Code: fenced, with its language. Divider: `---`. An unsupported block becomes `[unsupported: <type>]`. Children go at depth + 1 (two spaces per level). | notion_md.py:208-296 |
| M9 | `Unkept(ValueError)` produces the message "Notion cannot keep %s; take it out to save — your draft was kept". | notion_md.py:308-314 |
| M10 | Limits: `TEXT_LIMIT 2000`, `ARRAY_LIMIT 100`, `PAYLOAD_LIMIT 500 KiB`, `BLOCK_LIMIT 1000`. `text_items` splits text into chunks of 2000. `validate_payload` and `append_batches` check every request before the first mutation. | notion_md.py:332-386 |
| M11 | Inline: text, softbreak (written as a space), linebreak (`\n`), codespan, strong/emphasis/underline/strikethrough, mark (`yellow_background`), link. Anything else raises `Unkept`. | notion_md.py:389-416 |
| M12 | `_list_blocks` turns a `task_list_item` into `{to_do: {rich_text, checked: attrs.checked}}`. Nested lists and blocks become children. More than one paragraph raises `Unkept("a list item of more than one paragraph")`. | notion_md.py:440-467 |
| M13 | `_blocks`: a heading level above 3 raises `Unkept`; quote, list, code, divider and paragraph are handled; other tokens raise `Unkept`. `markdown_to_blocks(md) = _blocks(_parse(md))`, using the vendored mistune. | notion_md.py:479-517 |

### Probes (run against HEAD code)

| Shape | `unwritable` | Markdown |
|---|---|---|
| A: one `to_do` per event, rich text `"Title\nDescription"` | `[]` (round-trips) | `- [x] Kickoff  \n  Agree the scope` |
| B: bold title run + `"\nDescription"` run | `[]` | `- [x] **Kickoff**  \n  Agree the scope` |
| C: `to_do` with a **paragraph** child | `['formatting a save could not put back as it is']` (read-only) | `- [x] Kickoff\n  Agree the scope` (reads back as one item with a soft break) |
| D: `to_do` with a bulleted child | `[]` | `- [x] Kickoff\n  - Agree the scope` |
| E: `heading_2` + `to_do`s | `[]` | `## Timeline\n\n- [x] Kickoff` |
| F: `callout` + `to_do`s | `['a callout block']` (read-only) | `[unsupported: callout]…` |
| G: `to_do` with a `to_do` child | `[]` | `- [x] Kickoff\n  - [ ] Sub` |
| H: empty `to_do` | `[]` | `- [ ] ` |
| paragraph + `child_page` | `['a child page block']` (read-only) | `hi\n[unsupported: child_page]` |
| Markdown: a task item with a two-paragraph description | refused: `Unkept` "a list item of more than one paragraph" | n/a |

## 4. Facts: Notion selftests

| # | Claim | Where |
|---|---|---|
| T1 | Tests pin insert-before-delete, convert-before-write, quoted ids, create never re-run, read-only when the round trip fails, refusing a save over a page changed in Notion, refusing Unkept Markdown, integration session isolation, the 503/429 transport, secret not redirected, the drip-feed deadline, and logout. | plugins/org.note-note.notion/selftest.py:756-778 |
| T2 | The read-only cases cover toggle, coloured text, paragraph-nested text, mention, image, code caption, coloured block, toggle heading, list start, list format, paragraph icon and unknown property. The "plain" case includes `to_do` checked/unchecked and a `to_do` with an in-item line break. | selftest.py:300-355 |
| T3 | Reusable fakes: `run()` / `block()` builders, the `Notion` recorder stub for `api`, the `Workspace` scripted opener. | selftest.py:64-131, 530-585 |
| T4 | `tests/test_regressions.py` imports `notion_md` directly (long text chunks, chunked annotations, links, payload limits). | tests/test_regressions.py:19-25, 328-365 |

## 5. Facts: Sticky Notes provider

| # | Claim | Where |
|---|---|---|
| K1 | The Sticky Notes provider is a `LaneProvider`. Declarations: `id "sticky"`, `markdown: false`, `hasTitle: false // subject == first line`, `canCreate: true`, `canDelete: true`, `canReorder: false`, `canCreateSection: false`, `microsoftScopes ["Mail.ReadWrite"]`, its own `microsoftClientId`. No `tools`, no `canImages`. | plugins/org.note-note.sticky/Provider.qml:8-24 |
| K2 | `laneKey: "graph-mail"`. It has its own Microsoft account via `services.microsoft.create`. | Provider.qml:27-36 |
| K3 | Model `notes: [] // [{ id, title, body, modified }]`. `ready` requires a sign-in with the `Mail.ReadWrite` scope. | Provider.qml:38-39 |
| K4 | `previewOf(body)` returns the first non-empty line, with leading `#>-*`/space and any `*_\`` removed. | Provider.qml:52-61 |
| K5 | Rows: `{kind: "note", path, title: "", preview, version: modified, modified, menu: Delete}`. Footer: New Note, Sign out. One section `key "sticky"`, color `#F5D33F`. | Provider.qml:64-87 |
| K6 | `createTargetFor` returns `"new"` when ready. | Provider.qml:89-90 |
| K7 | `search()` matches every listed body in memory. | Provider.qml:159-171 |
| K8 | `load()` answers from the listing with no request. Answer: `{title: "", body, editable: true, version: modified}`. A note cut at its size limit (`truncatedAt`) opens read-only with a reason. | Provider.qml:190-202 |
| K9 | `save()` sends payload `{ title, body }` to `update <id> -`, with key `note:<id>`, replace, flush. On success it mutates `saved.body = body` in place and rebuilds. | Provider.qml:211-242 |
| K10 | `create()` runs `create` with **no payload** (key `create`, append, flush) and prepends the new note. | Provider.qml:244-274 |
| K11 | `remove()` uses the same key `note:<id>` as saves. | Provider.qml:276-301 |
| K12 | Poll: one listing request per poll. | Provider.qml:303-304 |
| K13 | `sticky.py` is configured with `msgraph.configure("graph-mail", [(60, 240)])`. Limits: `MAX_NOTES 500`, `MAX_NOTE_BODY 256 KiB`, `MAX_CACHE 32 MiB`. | plugins/org.note-note.sticky/sticky.py:29-36 |
| K14 | `to_note`: CRLF becomes LF, trailing newlines are stripped, `title: ""`, `body[:256 KiB]`, `truncatedAt` set when cut. | sticky.py:39-53 |
| K15 | The listing sends GET `/me/mailFolders/notes/messages?$select=id,subject,body,lastModifiedDateTime&$orderby=...&$top=100` with header `Prefer: outlook.body-content-type="text"`. Pages are followed only through validated Graph URLs. | sticky.py:56-81 |
| K16 | `cmd_update` reads only `body` from the payload. `subject` = first non-empty stripped line, cut to 255 characters. It sends PATCH `/me/messages/<id>` with `{body: {contentType: "text", content: body}, subject}`. | sticky.py:84-102 |
| K17 | `cmd_create` sends POST `/me/mailFolders/notes/messages` with `{subject: "", body: {contentType: "text", content: ""}, singleValueExtendedProperties: [{id: "String 0x001A", value: "IPM.StickyNote"}]}` and `retry_policy=NEVER`. | sticky.py:105-119 |
| K18 | `cmd_delete` sends DELETE `/me/messages/<id>`; a 404 counts as deleted. | sticky.py:124-132 |
| K19 | The selftest covers line-ending normalisation and no title, truncation, the session-scoped cache, and pagination host validation. | plugins/org.note-note.sticky/selftest.py:101-116 |

## 6. Facts: Shared base and host wiring

| # | Claim | Where |
|---|---|---|
| H1 | `LaneProvider`: `savePause: 1500`; `noteEdited` restarts a Timer that emits `saveRequested(path)`. | services/providers/LaneProvider.qml:30-45 |
| H2 | `session` / `environment` come from `ms` by default; Notion overrides both. Lane: `queueFor(laneKey)`. | LaneProvider.qml:52-66 |
| H3 | `unsentSave(info)` turns cancelled into `{error: "not saved — the request was cancelled"}`; superseded gives `{}`. | LaneProvider.qml:82-89 |
| H4 | `runProcess` runs `python3 script args` with a 600 s timeout. An answer arriving after a session change becomes `{error: "the signed-in account changed"}`. | LaneProvider.qml:108-122 |
| H5 | The host maps the provider-level `markdown` boolean to the editor's `plain`: `plain: p ? !p.markdown : false`. It also wires `hasTitle`, `enabledTools = p.tools` (null when undeclared) and `canImages`. | Workspace.qml:2831-2848 |
| H6 | In plain mode the editor uses `TextEdit.PlainText`. Load shows the body verbatim; save sends `plainText()` (no Markdown conversion). | ui/NoteEditor.qml:122-126, 300-306, 319, 339, 2075 |
| H7 | `EditorApi.writable` is false when `host.plain`, so no tool acts on Sticky notes. `supports(capability)` reads `enabledTools`. | ui/editing/EditorApi.qml:13-14, 63-65 |
| H8 | Host create: `newNote(providerId, target)` calls `p.create(target, cb)`; there is no type argument. After creation the title gets focus when `p.hasTitle`, otherwise the editor does. | Workspace.qml:1887-1936 |
| H9 | Host load: `provider.load(path, cb)` then `editor.setNote(title, body)` then `noteReady(result.editable === false, result.reason)`. Only those fields of the load answer are consumed. | services/notes/NoteSession.qml:252-275 |
| H10 | The sidebar row copies a fixed field set from provider rows (`provider, notebook, kind, path, title, hasTitle, preview, icon, reorder, level, expanded, count, menu, modified`). No type field. | services/notes/sidebar.js:24-31 |
| H11 | Provider manifest entries carry only `{id, path, order}`; capabilities live in `Provider.qml`. | plugins/org.note-note.notion/plugin.json:7-14; plugins/org.note-note.sticky/plugin.json:7-14; docs/plugins.md:20, 28 |
| H12 | Contract text: `markdown`: "bodies are Markdown (rendered); false = plain text". `tools`: "omitted = all (when `markdown`) … a construct the backend flattens must not be offered, and a save holding one must fail rather than lose it". | docs/providers.md:47-54 |
| H13 | Mirror for plugin authors: "`markdown` \| bool \| bodies are Markdown; false = plain text". | skills/note-note-plugin/references/providers.md:236-242 |

## 7. Facts: Notion API (external, developers.notion.com)

| # | Claim | Source |
|---|---|---|
| X1 | "If the new page is a child of another page, `title` is the only valid property in `properties`." | https://developers.notion.com/reference/post-page |
| X2 | Page object: "If `parent.type` is `"page_id"` or `"workspace"`, then the only valid key is `title`"; data-source pages have schema-defined properties. There is no custom or integration metadata field. Icon types: emoji, native icon, custom emoji, file. | https://developers.notion.com/reference/page |
| X3 | Update page: "This endpoint can be used to update any page `icon` or `cover`". Properties can be updated only for data-source pages, apart from the title. `erase_content` exists; `is_locked` affects the Notion UI only. | https://developers.notion.com/reference/patch-page |
| X4 | Block `to_do` fields: `rich_text`, `checked`, `color`, `children`. `to_do`, paragraph, list items, toggle, callout and others support children. A block has no custom or app metadata field. `child_page` blocks are created through Create a page with a page parent. | https://developers.notion.com/reference/block |
| X5 | Update a block: for `to_do`, `rich_text`, `checked`, `color` and `in_trash` can be updated; "If a field is omitted (ex: omitting `checked` …), the value will not be changed"; children cannot be updated there. | https://developers.notion.com/reference/update-a-block |
| X6 | Append block children: 100 children per request, two nesting levels per request; `position` (start/end/after_block); `after` is deprecated. | https://developers.notion.com/reference/patch-block-children |
| X7 | The latest documented Notion-Version is `2026-03-11`. Markdown content endpoints exist: GET/PATCH `/v1/pages/:id/markdown`, a `markdown` parameter on create, `update_content` (search/replace) and `replace_content`. To-do items are `- [ ]` / `- [x]`, and unsupported blocks appear as `<unknown …/>`. | https://developers.notion.com/guides/data-apis/working-with-markdown-content ; https://developers.notion.com/reference/post-page |
| X8 | Search returns pages or data sources ("full or partial" objects) whose titles include the query. The latest filter values are `"page"` / `"data_source"`. | https://developers.notion.com/reference/post-search |

## 8. Facts: Microsoft Graph (external)

| # | Claim | Source |
|---|---|---|
| G1 | Extended properties can be stored on `message` (and `note`) resources. A custom named property uses the id `"String {guid} Name {name}"`. Open extensions are the recommended route for custom data. "You can't use the REST API to get all the extended properties of a specific instance in one call"; they are read with `$expand` or `$filter`. | https://learn.microsoft.com/en-us/graph/api/resources/extended-properties-overview?view=graph-rest-1.0 |
| G2 | Repo engine note: Sticky Notes are items in the `notes` mail folder, the subject is a copy of the first body line, and a note counts as a sticky note only with `String 0x001A` = `IPM.StickyNote`. | docs/engine-notes.md:483-487 |

---

## Answers to the four questions

**Q1. Notion mapping, writes and declarations**
- Blocks map to Markdown as in M1-M13: `to_do` becomes `- [ ]` / `- [x]`, with `checked` written back; headings 1-3; paragraphs joined by hard breaks; children nested only under list items and to-dos.
- Saves replace every top-level block: append first, delete after (S12, S13).
- "Unwritable" means the property-level round trip fails (M6). It is checked at load (S10) and again before every save (S12).
- Declarations: N2-N4 (markdown true, hasTitle true, tools without table and textColor, no images).

**Q2. A durable timeline marker on a Notion page**
- No invisible slot exists (X1-X4): page-parented pages hold only `title`, and blocks and pages have no app metadata.
- Visible options:
  - The page icon (X3; updatable, and returned with the page object).
  - A marker block. A callout is unwritable today (probe F); a heading or paragraph is plain editable text (probe E).
  - A database property, which exists only for database pages, needs a schema the user owns, and goes against the non-goal "no databases" (business-requirements.md:57-58).
  - A local map kept by Note Note, which is not durable across machines.
- In Notion's UI, `to_do` blocks show as a checklist, which is a sensible rendering, but nothing enforces "all above checked".
- The body shapes that round-trip are A/B: title, then a newline, then the description inside one `to_do`.
- Two common Notion edits break the shape:
  - A paragraph nested under a to-do opens read-only (probe C).
  - Any non-to-do block turns the page into ordinary Markdown.

**Q3. Sticky Notes**
- Format: plain text and no title (the subject mirrors the first line) (K1, K14-K16). It declares `markdown: false`, `hasTitle: false` and no tools.
- A save is a PATCH of a text body plus subject (K16).
- A timeline could only be invented text syntax, shown raw in Microsoft's apps, or a custom extended property (G1) whose survival through Microsoft's clients is unverified. The repo's decision forbids inventing behaviour the backend cannot keep (decisions.md:557-561).

**Q4. Recommendation for the first release.** See "Recommendations" below.

---

## Integration points

| Where | What changes | Why |
|---|---|---|
| plugins/org.note-note.notion/Provider.qml:17 | Replace or complement `markdown: true` with the new per-provider declaration of supported content types (first release: Markdown only, unless the user chooses Notion timeline support). | The content type becomes per note; providers declare which types they can store. |
| plugins/org.note-note.sticky/Provider.qml:14 | Replace or complement `markdown: false` with a declaration of plain text only. | Sticky can store only plain text. |
| Workspace.qml:2837-2840 | `plain: !p.markdown` must read the open note's type, not the provider-wide flag. | The editor mode is chosen per note. |
| Notion Provider.qml:161-200 / notion.py:304-318 | `load()` / `cmd_page` would report the note's type (derived from the chosen marker) and cache it in `bodies`. | The host must know which editor to open. |
| Notion Provider.qml:75-95 / notion.py:253-277 | Rows and `cmd_list` would carry a type, if the list must show it or choose before load. The icon is in the search page object (X8: full or partial) and is not read today. | Type in the list without an extra request. |
| Notion Provider.qml:241-279 / notion.py:378-401 | `create()` sends a hard-coded `{title: "", body: ""}`. A typed create needs the type (and initial body) in the payload, and `cmd_create` would set the marker (e.g. `icon`) in the same POST. | Creating a timeline note. |
| Workspace.qml:1887-1912 | `newNote(providerId, target)` and `p.create(target, cb)` carry no type; the signature needs one, or a second action. | A "New timeline" flow. |
| Notion Provider.qml:202-239 / notion.py:321-375 | A timeline save would go through the same replace path if its body is serialised as a Markdown task list (shapes A/B, unchanged writer). `cmd_update` re-reads the page (`GET /pages`), so the marker can be re-checked there before writing, like `unwritable`. | Saving and checking events. |
| notion_md.py:440-467 | A timeline description with more than one paragraph is refused today; the form must forbid blank lines or the writer must change. | Description editing. |
| Notion Provider.qml:73, 85-89 | Note menu (Delete only) and footer (New Note, Refresh, Settings) are where a typed "New …" action or a "Convert" item would be added. | UI entry points live in provider rows and footers. |
| plugins/org.note-note.sticky/Provider.qml:190-202, 244-274; sticky.py:84-119 | Load reports plain text; create takes no payload. If Sticky stays plain text only, it needs only the new declaration (and an explicit type in the load answer if the contract requires one). | Contract conformance. |
| services/notes/sidebar.js:24-31 | Copies a fixed set of row fields; a per-note type for list display would be added here. | Rows drop unknown fields. |
| docs/providers.md:47-54, 260-357; skills/note-note-plugin/references/providers.md:236-242; examples/hello/Provider.qml:14 | The contract rows for `markdown` / `tools` / load / create, the mirror, and the example provider. | Documented contract. |
| plugins/org.note-note.notion/selftest.py; tests/test_regressions.py | New cases for the timeline shape (A/B round trip, refusal of paragraph children, multi-paragraph description, marker check). | Each shipped bug has a pinned test (docs/testing.md:428-471). |

## Constraints

| Rule | Source |
|---|---|
| A note that cannot be written back safely opens read-only with a visible reason; never lossy writes. The decision is made by the round trip, not by a type list. | docs/business-requirements.md:29-31; docs/decisions.md:660-697 |
| Be honest about limits in the UI. | docs/business-requirements.md:42-44 |
| Sticky Notes: plain text, no title, no reordering — "would be inventing behaviour the backend cannot keep". | docs/decisions.md:557-561; docs/business-requirements.md:73-74 |
| Not a Notion replacement: no databases or templates. | docs/business-requirements.md:57-58 |
| Providers change their model only after the backend answers; the host keeps the draft. | docs/providers.md:301-306; docs/decisions.md:946-951; Notion Provider.qml:202-207; Sticky Provider.qml:204-210 |
| Every save and load callback is answered exactly once; an unsent save answers `{error}`. | docs/providers.md:271-300; LaneProvider.qml:82-89 |
| `tools`: never offer what the backend flattens; a save holding it must fail. | docs/providers.md:54 |
| The Notion writer refuses Markdown it has no block for (`Unkept`) before any request; the unwritable re-check runs before any write. | docs/decisions.md:685-692; notion.py:321-341 |
| Notion update order: insert new blocks before deleting old ones (pinned by a test). | notion.py:352-375; plugins/org.note-note.notion/selftest.py:163-201 |
| Creates are never re-run on an uncertain answer (Notion `transient_5xx=False`, Graph `RetryPolicy.NEVER`). | notion.py:389-394; sticky.py:110-111; docs/providers.md:575-602 |
| Every remote request goes through the provider's lane and rate key (`notion` 3/s; `graph-mail` 240/min). | docs/technical-requirements.md:162-166, 182-183; docs/providers.md:604-616 |
| Bodies and the Notion secret travel over stdin only. | docs/security.md:53-57 |
| Bound everything read: Notion 1000 pages / 300 blocks; Sticky 500 notes / 256 KiB. | docs/technical-requirements.md:170-188; docs/providers.md:493-507 |
| No provider is named in the host; capabilities flow through the contract. | docs/decisions.md:450-474 |
| Notion has no `search()` (titles only). | Notion Provider.qml:97-101; docs/providers.md:401-404 |
| Notion and Sticky are flat lists; no `notebookTabs`. | docs/decisions.md:903-910 |
| Notion integration session isolation. | docs/security.md:225-229; docs/engine-notes.md:735-740 |
| Code style: braces on every if/else/for/while, body on its own lines; no hacks. | CLAUDE.md |

## Reusable

| What | Where |
|---|---|
| `to_do` mapping, hard breaks in items | notion_md.py:201-205, 259-262, 440-467 |
| Round-trip editability check (`unwritable`, `essence`) and `Unkept` refusal | notion_md.py:133-198, 308-329 |
| Request-size validation and batching | notion_md.py:332-386 |
| Insert-then-delete page replace; title PATCH only when changed | notion.py:321-375 |
| `api()` transport with the `transient_5xx` gate | notion.py:115-180 |
| `title_of`, `parent_of` | notion.py:187-197 |
| Load cache keyed by `edited`; save and remove share one lane key | Notion Provider.qml:161-239, 281-306 |
| LaneProvider: debounce, `unsentSave`, `runScript`, session guard, `busy`/`writeBusy` | services/providers/LaneProvider.qml:30-122 |
| Writing an extended property on a sticky message (precedent) | sticky.py:105-111 |
| Session-scoped cache (`load_for_session` / `save_for_session`); `graph()` with headers and retry policy | services/microsoft/msgraph.py:423, 453, 462; sticky.py:58-101 |
| Test fakes: `run`/`block` builders, `Notion` api recorder, `Workspace` opener; Sticky `message()` builder | plugins/org.note-note.notion/selftest.py:64-131, 530-585; plugins/org.note-note.sticky/selftest.py:16-37 |
| Editor plain mode for text-only notes | ui/NoteEditor.qml:122-126, 300-306, 2075; ui/editing/EditorApi.qml:13 |

## Risks

1. **Notion has no invisible per-page metadata.** Every durable marker is either user-visible and user-editable (icon, marker block) or not durable (a local map). A user who changes or removes the icon in Notion silently turns the type back into Markdown.
2. **Icon collisions.** An emoji used as a type marker may already be used by the user for other pages, which would then be misread as timelines.
3. **No ordering invariant in Notion's UI.** Notion lets users check any to-do independently, so a page can load with item 3 checked and item 2 unchecked.
4. **Nesting a paragraph under a to-do in Notion makes the page read-only** in Note Note (probe C). Any non-to-do block makes it not a pure timeline.
5. **Multi-paragraph descriptions are refused** by the Notion writer (`Unkept` "a list item of more than one paragraph").
6. **Every check toggle rewrites the whole page.** Each save of N top-level blocks costs roughly N DELETEs + 2×ceil(N/100) + 1-2 other requests at 3 requests/s (about 11 s for 30 events). Block ids change on every save. A partial failure leaves the events duplicated ("the note twice over").
7. **Size limits.** `MAX_BLOCKS` 300 (nested blocks count) makes large timelines read-only; description children would double the block count.
8. **Creating a page under the open page makes that parent read-only** (`child_page` block → "a child page block"; probe). This applies to any new note, timelines included.
9. **The Notion API version is pinned to `2022-06-28`.** Markdown endpoints, native icons and `position` need a version bump, which changes parents to `data_source_id` and the search filter to `data_source`; `parent_of` and `cmd_list` would need review.
10. **Sticky text formats would show raw.** Any textual timeline syntax shows as raw text in Microsoft's apps and can be broken there. The subject would become the first line of that syntax.
11. **Sticky extended properties may not survive.** Whether a custom extended property or open extension outlives edits in Microsoft's Sticky Notes clients is unverified.
12. **Sticky saves replace the body as text** (`contentType: "text"`), the existing behaviour. Any formatting another client stored in the HTML body is replaced on save. This is inferred, not measured.

## Open questions

1. Where should a Notion page's content type live: the page icon, a marker block, a local map kept by Note Note, or (database pages only) a property? This is a product choice for the user.
2. On load, should a Notion timeline whose checks are non-monotonic be normalised (which costs a write) or shown as it is?
3. How should a Notion page typed as a timeline be treated when it also holds nested children or non-to-do blocks: read-only, or opened as Markdown?
4. Does the `/search` page object reliably include `icon` under `Notion-Version 2022-06-28`? The docs say results are "full or partial" objects.
5. Should timeline checks use targeted `PATCH /blocks/{id}` (`checked` only, per X5)? That needs block ids in the load answer (an editing baseline `view`), which is a new save path for Notion.
6. Do Microsoft's Sticky Notes clients (Windows app, OneNote mobile, Outlook) preserve a custom named extended property or open extension on a note message when the user edits it?
7. Should timeline event descriptions allow several paragraphs? The Notion writer refuses that today.
8. Does the host need the type in listing rows (an icon in the list, picking the editor before load) or only in `load()`? For Notion this decides whether the listing must classify pages.
9. Is the type of an existing note changeable after creation (convert a Markdown page into a timeline)? For Notion that means adding or removing the marker.

## Recommendations

**Notion: DEFER the timeline type.**
- In the first release Notion declares Markdown only, which is its behaviour today.
- Reasons:
  - No invisible durable marker exists (title-only properties, no app metadata).
  - Any visible marker is a product decision the user has not made.
  - Notion's UI does not keep the "all above checked" rule.
  - Common Notion edits (a nested paragraph) make the page read-only.
  - Every check costs a whole-page rewrite at 3 requests/s.
- Path to support later:
  - Body as one `to_do` per event, with "title\ndescription" in its rich text (probes A/B round-trip with the unchanged writer).
  - Descriptions limited to a single paragraph.
  - The marker chosen explicitly (icon recommended over a marker block, since a callout is unwritable today), and re-checked in `cmd_update` the way `unwritable` is.
  - Optionally, targeted `checked` updates.

**Sticky Notes: UNSUPPORTED.** Declare plain text only.
- Reasons:
  - The backend is plain text with no title, and the editor runs in plain mode with no tools.
  - A timeline would be invented syntax shown raw in Microsoft's apps, which the documented decision rules out ("inventing behaviour the backend cannot keep").
  - Marker persistence through Microsoft's clients is unverified.

**Cross-provider: keep the timeline body valid Markdown.** If the timeline body is serialised as a Markdown task list (`- [x] **Title**  \n  Description`), a provider that cannot persist the type (Notion today) still shows and saves it losslessly as an ordinary checklist.

**Map today's booleans to the new declaration** without breaking external providers: Notion's `markdown: true` becomes Markdown, Sticky's `markdown: false` becomes plain text, and `examples/hello` and external providers keep working.

## Sources

- [Create a page](https://developers.notion.com/reference/post-page)
- [Page object](https://developers.notion.com/reference/page)
- [Update page](https://developers.notion.com/reference/patch-page)
- [Block object](https://developers.notion.com/reference/block)
- [Update a block](https://developers.notion.com/reference/update-a-block)
- [Append block children](https://developers.notion.com/reference/patch-block-children)
- [Search](https://developers.notion.com/reference/post-search)
- [Working with markdown content](https://developers.notion.com/guides/data-apis/working-with-markdown-content)
- [Outlook extended properties overview](https://learn.microsoft.com/en-us/graph/api/resources/extended-properties-overview?view=graph-rest-1.0)
