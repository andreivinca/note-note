# Map: the local Markdown provider's storage (HEAD e2cdc4e)

Area: `plugins/org.note-note.local/` (Provider.qml, notefile.py, operations.py, list.py, search.py, images.py, getting-started.md, plugin.json, selftest.py), `lib/notewalk.py`, `lib/readfile.py`, `lib/fileio.py`, plus the docs about local notes.
Everything below was read at HEAD. Items marked "verified" were also run against a scratch notes root outside the repo, with `python3 -B` so no bytecode was written.

## Summary

A local note is one UTF-8 `.md` file under the notes root (`~/Notes`, `NOTE_NOTE_DIR` or `providers.local.notesDir`). Its absolute path is its identity (`local:<abs path>`). Folders are notebooks and sections, with order kept in `.order` and `.notebooks` files and pictures in `.assets/`.

The format is owned by one module, `notefile.py`. It handles a `---` fenced front-matter block parsed line by line (not YAML), in which the app owns only the first column-0 `title:` line. Every other front-matter line comes back verbatim as `extra` and is written back after the title line on save. A BOM and CRLF or lone-CR endings are read transparently, and a save always writes LF with no BOM.

Content type is per provider today (`markdown: true`, Provider.qml:20). No note carries a type, and nothing reads or writes a type key. A hand-written `type: timeline` line would already survive every save as an unowned `extra` line (verified). It is invisible to the listing, the load answer and search.

**Listing.** `list.py` reads only the first 4096 bytes of each note. It emits one `N key path title preview size mtime_ns` record per note, and `Provider.qml` parses that into the entry `{key, file, path, title, preview, size, version}`. Rows carry `version` (mtime ns) and `modified` (ms).

**Search.** `search.py` reads each whole note (capped at 2 MiB) and matches the body only. Front-matter text is never searched.

**Load.** `load` runs `operations.py read` every time, so the provider caches no bodies. That call returns `{title, body, editable, reason, version, bytes}`, where `editable` comes from `qthtml.unkept` (raw HTML and some quote/list shapes make it read-only). `Provider.qml` forwards only `{title, body, editable, reason, version, base}`.

**Create.** `create` writes `---\ntitle: \n---\n` into a new `note-<uuid hex>.md`, using an exclusive atomic link.

**Save.** The save re-reads the current file for its `extra` lines, serializes, refuses anything over 2 MiB and commits with `write_atomic` (temp file, fsync, rename). There is no version or compare-and-swap check, so the last writer wins for the body.

**Delete and rename.** Delete unlinks the file and leaves its pictures in `.assets`. There is no per-note rename because the title lives in the front matter. Folder rename and delete exist, and folder delete refuses any folder holding non-`.md` files other than `.order` and `.assets/`.

**Mutations and refresh.** All mutations go through one ordered queue (concurrency 1), and the model changes only after the commit. The listing reruns on open, on inotify events (400 ms debounce) and on the 20 s poll.

**External edits.** An external edit reloads the open note only if it has no unsaved edits and no save in flight. Otherwise the next autosave overwrites the external body change. External front-matter lines survive, because they are re-read at save time.

**Outside editors.** A timeline stored as a GFM task list (`- [ ]` / `- [x]`) in the Markdown body would stay plain Markdown, readable and editable by other tools (checkboxes in GitHub, Obsidian, VS Code). It would be searchable, and the current Markdown editor opens it editable (`unkept` is empty).

**Two traps when adding a type field.** `Provider.qml` rebuilds the note entry with explicit fields on save (Provider.qml:548-549) and rebuilds the load answer the same way (Provider.qml:509-511). Both would silently drop a new `type` field.

## Facts

### 1. On-disk format

| # | Fact | Where |
|---|---|---|
| 1.1 | Only regular, non-symlink files whose name ends in `.md` are notes. The same filter appears in four places: the listing (`if not entry.name.endswith(".md"): continue`), the search, first-run detection and the folder-delete whitelist | list.py:228, list.py:231-235, search.py:43, list.py:177, operations.py:66 |
| 1.2 | A front matter is recognized only when the first line (after an optional BOM) is exactly `---`. It closes at the next line that is exactly `---`. An unclosed block makes the whole file body ("nothing is guessed"). `--- ` with a trailing space, a leading blank line or a YAML `...` terminator are not fences (verified) | notefile.py:29, 48-68 |
| 1.3 | The app owns only `title:`. The match is `line.startswith(TITLE_KEY) and not title`: column 0, case-sensitive, first non-empty one wins. The value is the rest of the line with tabs turned into spaces and stripped. There is no YAML unquoting: `title: "Quoted"` reads as `"Quoted"`, and `Title:` or an indented `  title:` goes to `extra` (verified) | notefile.py:30, 64-65 |
| 1.4 | Every other front-matter line is kept verbatim in `extra`, in order: "Any other line inside the fences … is not the app's to understand, so `split` hands it back verbatim and `serialize` writes it back where it was" | notefile.py:10-15, 66-67 |
| 1.5 | `serialize` builds `front = [FENCE, TITLE_KEY + " " + title] + list(extra) + [FENCE]`, then `"\n".join(front) + "\n" + body`. The title line always goes first, so `tags:` written before `title:` comes back after it (verified). Title line breaks collapse to spaces. No quoting or escaping is applied. An empty title writes `title: ` with a trailing space | notefile.py:71-76 |
| 1.6 | Line endings: LF, CRLF and lone CR are recognized and a leading BOM is dropped. The body is returned exactly as written, CRLF included (verified read answer). A save writes LF with no BOM, and a kept front-matter line keeps its text but takes the format's LF ending | notefile.py:17-25, 33, 38-45, 55-56; README.md:203-204; docs/providers.md:714-716 |
| 1.7 | An editable read must be valid UTF-8, otherwise `{error: "file is not valid UTF-8", kind: "invalid-encoding"}`. The listing and search decode with `errors="replace"` | readfile.py:79-84; list.py:151; search.py:49 |
| 1.8 | A new note is named `note-<uuid4 hex>.md` in the target folder, and the name never changes later. The title lives in the front matter so that "renaming a note must not rename a file the user may have linked elsewhere" | operations.py:105-106; business-requirements.md:71 |
| 1.9 | A note's identity is its absolute file path: `pathOf(file) = "local:" + file`. The list docstring says "the path is the note's identity" | Provider.qml:133-134; list.py:23-26 |
| 1.10 | Layout: notebooks are the non-hidden folders under the root, sections are the folders inside them (depth ≤ 16, ≤ 4096 folders). There is a `.order` per folder, `.notebooks` in the root, and `.assets/` beside notes for pasted images | lib/notewalk.py:1-41; list.py:5-13; Provider.qml:7-12; images.py:1-18 |
| 1.11 | Permissions: a new file is 0600 (mkstemp plus fchmod), an existing file keeps its mode, and folders are created 0700 | fileio.py:27-33; operations.py:85; list.py:183 |
| 1.12 | First run: an unused root gets `Notes/Getting started.md`, copied from getting-started.md, which already contains a task list (`- [x] Open your first notebook`, `- [ ] Write a note`) | list.py:168-190; getting-started.md:1-3, 15-17 |
| 1.13 | No YAML parser exists or may be added: "dependencies = [] … Empty, and enforced". Only the stdlib plus vendored mistune and merge3 are allowed | pyproject.toml:13-17; docs/technical-requirements.md:9 |

### 2. Listing, preview, version, search, caching

| # | Fact | Where |
|---|---|---|
| 2.1 | Stream records: `B key`, `D key`, `O key name`, `N key path title preview size mtime_ns`, `X key reason`, and always a last `E complete` or `E partial reason` | list.py:5-11 |
| 2.2 | The N record is written as `emit("N", key, path, title, preview, str(size), str(mtime))` | list.py:253 |
| 2.3 | Title and preview come from the first HEAD_BYTES = 4096 bytes: `head_of` does `read_capped(path, HEAD_BYTES, deadline)`, then `title, body, _ = notefile.split(text)` (extra is discarded), then `notefile.preview(body)` | list.py:64, 147-153 |
| 2.4 | A front matter longer than 4096 bytes never closes inside the head. It lists with an empty title and the preview `title: Long` (verified with a 5,575-byte front matter) | list.py:147-153 + notefile.py:68 |
| 2.5 | Preview is the first non-empty body line: the first 200 characters, leading `^[#>*\-\s]+` stripped, inline `[*_\`]` removed, tabs turned into spaces. Task items keep the box (`- [ ] Event one` becomes `[ ] Event one`, `- [x] **Kickoff**` becomes `[x] Kickoff`). Ordered `1. [ ] x` is unchanged (verified) | notefile.py:32-35, 79-86 |
| 2.6 | `version` is `st_mtime_ns` as a string, in the same unit everywhere (list, read and write) | list.py:244, 253; readfile.py:80; fileio.py:41 |
| 2.7 | Note order is birth time from statx(2), falling back to mtime, with ties broken by mtime and then name. A saved `.order` comes first | list.py:126-144, 237-244; Provider.qml:368-390, 473-477 |
| 2.8 | Fields escape `\`, tab and newline as `\\`, `\t`, `\n`, and Provider.qml unescapes them | list.py:156-160; Provider.qml:414-426 |
| 2.9 | The listing has a byte budget (maxListBytes 4 MiB, 256 bytes reserved for E) and a 10 s deadline, and a cut listing ends `E partial`. A partial listing keeps the existing model and blocks order writes | list.py:66-67, 199-208, 250-259; Provider.qml:392-408, 448-463 |
| 2.10 | Model entry: `{ key, file, path, title, preview, size, version }`, parsed from N in `loadList` | Provider.qml:89-95, 444-446 |
| 2.11 | Note row: `{ kind: "note", path, title, preview, level, menu, reorder, version, modified: Math.floor(Number(n.version) / 1000000) }`. The search inventory `notes` holds `{path, title, preview, modified}` | Provider.qml:211-216, 226-230 |
| 2.12 | There is no body cache in the provider. The model holds no bodies, and every `load()` runs `operations.py read`. The host keeps its own `session.stored` and drafts | Provider.qml:499-513; services/notes/NoteSession.qml:235-251, 480-484 |
| 2.13 | Relist triggers: `refresh()` on open; inotify `create,delete,move,close_write` recursively, ignoring `.order` and `.notebooks`, debounced 400 ms; `poll()` every 20 s. A relist is deferred while listing or while mutations are queued, and is discarded if a mutation ran during it | Provider.qml:332-355, 764-786, 772; Workspace.qml:319-324, 2398-2410 |
| 2.14 | Search walks the same folders (notewalk), `.md` only, in name order. It reads each whole note capped at maxNoteBytes and matches the body only: `if needle in notefile.split(text)[1].casefold()`. It returns at most 1,000 matches within a 10 s deadline. Front-matter words are never found (verified: `timeline` in front matter, no match) | search.py:1-58; Provider.qml:357-366 |

### 3. Where a type marker would be read or written

| # | Fact | Where |
|---|---|---|
| 3.1 | On list, the only per-note read is `head_of`, which already has `extra` from `notefile.split` and throws it away (`title, body, _ =`). A type from front matter would be read here, but only within 4096 bytes | list.py:147-153 |
| 3.2 | On list, the N record has 7 fields (`FIELDS = {"N": 7}` in the selftest), and Provider.qml reads p[1]..p[6]. A trailing 8th field would be ignored by today's parser | list.py:253; selftest.py:347; Provider.qml:444-446 |
| 3.3 | On load, `operations.py read` does `title, body, _ = notefile.split(document["text"])` (extra discarded) and answers `{ok, title, body, version, bytes, editable, reason}` | operations.py:111-120 |
| 3.4 | On load, Provider.qml constructs a new answer object `{ title, body, editable, reason, version, base }`, so any new field from operations.py is dropped | Provider.qml:507-511 |
| 3.5 | On save, the extra lines come from the current file at save time: `notefile.serialize(payload["title"], body, notefile.split(current["text"])[2])`. An unowned `type:` line is preserved with no code change (verified, with CRLF input becoming LF) | operations.py:131-136 |
| 3.6 | On save, the provider commit builds a fresh entry `{ key, file, path, title: title.trim(), preview: result.preview, size: result.bytes, version: result.version }`, so a `type` on the entry would be lost | Provider.qml:544-550 |
| 3.7 | On create, the request is `{action: "create", key}`, the file text is `notefile.serialize("", "")`, and the new entry is `{ key, file, path, title: "", preview: "", size, version }`. No type is passed or written anywhere | Provider.qml:555-575; operations.py:104-109 |
| 3.8 | On create, the host chain is `newNote(providerId, target)` → `p.create(target, cb)` → `choosePath(r.path)` (which then loads), with no type parameter | Workspace.qml:1887-1937 |
| 3.9 | On rename, `renameFolder` re-keys entries with `Object.assign({}, note, …)`, so it would keep a `type` field | Provider.qml:677-684 |
| 3.10 | A file-extension marker would touch the `.md` filters, the create name and the identity: list.py:177, list.py:228, search.py:43, operations.py:66, operations.py:106. The path is the identity and `.order` stores file names | list.py:23-26; Provider.qml:753-757, 793-797 |
| 3.11 | A sidecar (e.g. a hidden JSON next to the note) would make folder delete refuse with "“…” is not a note, so nothing was deleted", and each write would trigger a relist | operations.py:55-68; Provider.qml:780-785 |
| 3.12 | An in-body HTML comment marker (`<!-- … -->`) makes `unkept` answer `['HTML']`, so the note opens read-only in the Markdown editor (verified) | operations.py:117-120; decisions.md:698-708 |
| 3.13 | Row `kind` already means `note` / `new` / `action` / `tree`, so a content type cannot be called `kind` | docs/providers.md:89-91; Provider.qml:205, 213, 219 |
| 3.14 | The host sidebar copies only named fields from provider rows (`kind, path, title, preview, icon, level, …, modified`), so an unknown `type` would not reach the UI. Note rows draw no icon (icons appear only on action rows) | services/notes/sidebar.js:24-31; ui/NoteList.qml:447-475 |
| 3.15 | The per-provider flag reaches the editor as `plain: p ? !p.markdown : false` | Workspace.qml:2837-2840; Provider.qml:20; docs/providers.md:47 |

### 4. External edits and interoperability

| # | Fact | Where |
|---|---|---|
| 4.1 | An external write is seen by inotify, then a relist runs and rows carry the new version. `reconcileNote` → `session.reconcile(exists, versionOf(currentPath))` reloads only when `!locked && !loadingNote && !dirty && !saveInFlight` and the version differs. A reload keeps the caret and scroll | Provider.qml:774-786; Workspace.qml:1384-1406; NoteSession.qml:204-208, 219-221, 544-555 |
| 4.2 | With unsaved edits or a save in flight the reload is skipped. The next save then writes the editor's body over the external one, because the save sends no version and checks none (`{action: "save", file, title, body}`). Afterwards `finishSave` sets `loadedVersion` to the save's version | Provider.qml:543; operations.py:126-141; NoteSession.qml:528-530 |
| 4.3 | External front-matter lines survive even that overwrite, because the save re-reads them | operations.py:131-136 |
| 4.4 | If the file was deleted externally, a clean open note is put away (`selectPath("")`). A dirty one fails its save with `[Errno 2] No such file or directory`, because a save refuses to recreate a note (verified) | NoteSession.qml:548-549; operations.py:127-129 |
| 4.5 | Watching runs only while the window is visible. On reopen, a refresh catches up | Workspace.qml:319-336; business-requirements.md:78; technical-requirements.md:141-146 |
| 4.6 | `read_document` refuses a file that changed during the read (fstat before and after) | readfile.py:72-78 |
| 4.7 | The Markdown dialect enables `task_lists`, items parse as `task_list_item` with `attrs.checked` (verified AST), and the editor maps `- [ ]` / `- [x]` to `<li class="unchecked">` / `<li class="checked">` | services/markdown/parse.py:73, 100-105; docs/engine-notes.md:124 |
| 4.8 | A tight item `- [x] Kickoff\n  Agree scope` is one paragraph with a softbreak, drawn as "Kickoff Agree scope". A loose item (blank line, indented second paragraph) keeps a separate `<p>`. `unkept` is empty for tight, loose and nested task lists (verified) | services/markdown/qthtml/writer.py:84-94 (verified by running) |
| 4.9 | The business goal "Your files stay yours": "Local notes are plain Markdown in `~/Notes`, readable and editable by any other tool, with no database and no lock-in" | business-requirements.md:32-34, 70-72 |
| 4.10 | Success criterion: "A note edited elsewhere (phone, file manager, another app) shows up while the window is open, without a manual refresh" | business-requirements.md:83-84 |

### 5. Mutations and limits

| # | Fact | Where |
|---|---|---|
| 5.1 | `mutate`: RequestQueue domain `local`, concurrency 1, mode `append` (every job runs, in order), flush true, `operations.py` over stdin with a 60 s timeout. `mutationRevision` is bumped before and after, and the commit runs only on success. "Callers and models see success only after the filesystem has committed" | Provider.qml:483-536; services/requests/scheduler.js:15-16 |
| 5.2 | Create: `inside(root, …/note-<hex>.md)`, then `write_atomic(path, text, exclusive=True)`, which links the temp file so an existing path is refused. Returns `{ok, file, version, bytes}`. The `key` is not validated by `folder()`, only by `inside()` | operations.py:104-109; fileio.py:37-38; operations.py:35-42 |
| 5.3 | Save: `lstat` must be a regular file, then `stage()` copies pasted images to `.assets`, then the current file is read (failure becomes an error), then serialize, then a check `> MAX_NOTE_BYTES` ("note exceeds the 2 MB limit"), then `write_atomic`. Returns `{ok, body, preview, version, bytes}` | operations.py:126-141; images.py:63-102 |
| 5.4 | `write_atomic`: mkstemp beside the target (`.xxxx.tmp`), fchmod, write, flush, fsync, then `os.replace` (or `os.link` when exclusive), then return `st_mtime_ns`. The temp file is always unlinked. The target must be a regular file or absent | fileio.py:13-46 |
| 5.5 | Remove: `lstat` must be regular, then `os.unlink`. `.assets` images stay. The provider marks `deleting[path]`, which refuses saves, and the commit drops the entry and rewrites `.order` | operations.py:121-125; Provider.qml:539-542, 577-594 |
| 5.6 | There is no note rename. A title edit is a save | Provider.qml:538-553; business-requirements.md:71 |
| 5.7 | `renameSection`: `folder()` validation, `lexists(target)` refusal, then `os.rename`. The provider re-keys entries and emits `notePathChanged` for each moved note | operations.py:87-100; Provider.qml:659-702 |
| 5.8 | `removeSection`: `check_removable` accepts only `.md` and `.order` regular files, `.assets` directories and non-hidden subfolders, then `shutil.rmtree` | operations.py:55-78, 101-103; Provider.qml:704-723 |
| 5.9 | `section`: `os.makedirs(folder(root, key), 0o700, exist_ok=True)`. `order`: `write_atomic(path, text)` | operations.py:84-86, 142-143 |
| 5.10 | Path guards: `inside()` keeps paths inside the root, not the root itself, and refuses symlinks. `folder()` refuses empty or hidden parts | operations.py:35-52 |
| 5.11 | Limits: MAX_NOTE_BYTES 2 MiB; maxNoteBytes 2 MiB and maxListBytes 4 MiB; MAX_PAYLOAD 8 MiB on stdin; HEAD_BYTES 4096; ORDER_BYTES 256 KiB; listing DEADLINE 10 s; END_BYTES 256; search DEADLINE 10 s and MAX_MATCHES 1000; MAX_DEPTH 16 and MAX_FOLDERS 4096; readfile DEADLINE 5 s; MAX_IMAGE 40 MiB, MAX_SAME_NAME 100 and image DEADLINE 15 s; PREVIEW_CHARS 200; save debounce 500 ms; relist debounce 400 ms; watcher output 1 MiB; mutation timeout 60 s | operations.py:16; Provider.qml:74-77, 41, 773, 777, 523; fileio.py:10; operations.py:149-151; list.py:64-67; search.py:27-28; notewalk.py:10-11; readfile.py:24; images.py:32-34; notefile.py:32 |
| 5.12 | A note over 2 MiB loads as an error (`kind: "too-large"`) and the host shows it as unavailable: read-only, no content, message reported. The docs say "larger opens read-only" | readfile.py:75-76; operations.py:114-116; NoteSession.qml:257-259, 325-331; tests/transitions.qml:1006-1009; technical-requirements.md:174; decisions.md:662-664 |

### 6. Test structure

| # | Fact | Where |
|---|---|---|
| 6.1 | `plugins/org.note-note.local/selftest.py` is a plain script, not unittest. Each `test_*(directory, verbose)` returns a failure count via `check(name, ok, detail)` into FAILURES. `main()` calls each test by hand inside a TemporaryDirectory and prints "all green" | selftest.py:78-87, 557-586 |
| 6.2 | Helpers run the real scripts as child processes: `operation(root, **payload)` (operations.py over stdin), `stream(root, budget)` (raw list lines), `listed(root)` (N names), `found(root, query)` (search), plus `FIELDS` record arities and `unescaped` | selftest.py:99-112, 338-353, 423-436 |
| 6.3 | The best template for a type round trip is `test_line_endings`. It writes raw bytes, then checks listed (title, preview), search, read (title, body), save, the exact bytes on disk and the re-read | selftest.py:439-493 |
| 6.4 | `test_unkept_opens_read_only` checks `editable` and `reason` from read | selftest.py:524-554 |
| 6.5 | `tests/test_regressions.py` `Files` runs `operations.execute` in-process via `self.operation(action, **payload)`. It has a front-matter-preservation test and the `split(serialize(split(x))) == split(x)` property table | tests/test_regressions.py:17-28, 83-110 |
| 6.6 | `tests/transitions.qml` drives the real provider: `localCases` (load too-large, createSection, create, save ordering, external edit, remove, stale save), with `NOTE_NOTE_TEST_DIR`. Its `loadList` parse cases build 7-field N records with `record()` | tests/transitions.qml:281, 1003-1044, 1457-1498 (1480); tests/transition_selftest.py:162 |
| 6.7 | The aggregate runner includes the local selftest. docs/testing.md lists what each local case pins and the rule "Add a case for every provider-script bug" | tests/selftest.py:15-18; docs/testing.md:418, 430-453, 488-491 |

## Integration points

1. **notefile.py:48-86.** Teach the one format module the type key. Either:
   - read it from the front-matter lines through a helper and keep it an unowned `extra` line, or
   - own it next to `title`, with `split` returning it and `serialize` writing it.

   Also add a type-aware preview if timelines need one. Why: notefile.py:10-15 makes this the only parser; list, search, load and save all go through it.
2. **list.py:147-153 and list.py:253, plus the docstring at list.py:5-11.** `head_of` returns the type, and the N record gets an 8th, trailing field. Why: rows can then carry the type without a load.
3. **Provider.qml:444-446, 211-216, 226-230.** Parse the new N field into the entry, and put `type` (not `kind`) on note rows and in `searchable()` notes. Why: the host and the list need the type before a note is loaded.
4. **Provider.qml:544-550 (save commit).** Carry the entry's type, for example with `Object.assign`. Why: the commit rebuilds the entry from explicit fields and would drop `type`.
5. **operations.py:111-120 and Provider.qml:507-511.** Return the type from `read` and forward it in the load answer. Decide editability for a timeline with the timeline parser rather than, or as well as, `unkept`. Why: the host must pick the editor per note, and Provider.qml rebuilds the answer explicitly.
6. **operations.py:104-109, Provider.qml:555-575 and Workspace.qml:1887-1937.** Creation must accept a type and write it into the new file's front matter. Why: create today writes only `title: `, and `create(target, cb)` has no type.
7. **operations.py:126-141.** If the type is owned rather than extra, the save must keep the current file's type unless it is explicitly changed. Return the type (and a timeline preview) in the save answer. Why: a save must never lose or flip the type.
8. **notefile.py:79-86, used by list.py:153 and operations.py:140.** A timeline preview, such as progress or the next event, would be computed here. Why: one place for the preview, used at listing and at save.
9. **Provider.qml:20 (`markdown: true`) with docs/providers.md:47 and Workspace.qml:2837-2840.** The per-provider flag must coexist with, or give way to, a per-note type that this provider supports. Why: today the editor's `plain` flag comes from the provider, not the note.
10. **services/notes/sidebar.js:24-31 and ui/NoteList.qml:447-475 (host area).** Pass `type` through and show it if the list should. Why: unknown row fields are dropped and note rows draw no icon.
11. **Only if a file extension is chosen: list.py:177, list.py:228, search.py:43, operations.py:66, operations.py:106.** Every `.md` filter and the create name. Why: these five places define what a note is.
12. **Tests: selftest.py:347 (FIELDS N), new tests in main (557-575); tests/test_regressions.py:97-110; tests/transitions.qml:1480 (`record()`) and `localCases` (1003-1044).** Type round trips, an 8-field N record and create with a type. Why: these suites pin the format and the stream.
13. **Docs: README.md:185-204; docs/providers.md:47, 260, 350, 705-716; docs/technical-requirements.md:105-112, 128; docs/business-requirements.md:66-78; skills/note-note-plugin/references/providers.md:236, 319-321; the docstrings at notefile.py:1-25 and list.py:1-50; docs/testing.md:418-453.** Document the new key, record and contract. Why: the contract changes additively and is documented (technical-requirements.md:99-101).
14. **getting-started.md and list.py:188-190 (optional).** A sample timeline note on first run, if wanted. Why: this is the only template the app writes.

## Constraints

- One parser for the format. notefile.py:10-15 says "The lister, the search, the save and the load all read the format through here; a fourth private parser is how a hand-written front matter once opened as body text". Provider.qml:183-185 says "nothing here parses a note". See also docs/providers.md:711-713.
- Front-matter lines the app does not own must survive a save verbatim. Sources: notefile.py:10-13, tests/test_regressions.py:86-95, selftest.py:439-493.
- Files stay plain Markdown that any tool can read and edit: no database, no lock-in, folders map to notebooks with no metadata of our own. Sources: business-requirements.md:32-34, 70.
- The title lives in the front matter, not the filename, and a note's path is its identity. Sources: business-requirements.md:71, list.py:23-26.
- Read-only rather than lossy writes: a note the app cannot write back opens read-only with a reason. Sources: business-requirements.md:29-31, decisions.md:660-714, docs/README.md:40-41.
- Every file read goes through lib/readfile.py (no symlinks, regular files only, capped, deadline). Every write goes through fileio.write_atomic. Payloads travel over stdin. Sources: security.md:16-64, 245-261, 286-305.
- Bound every input when it is read, collections included. Sources: docs/providers.md:493-507, security.md:16-39.
- No runtime dependencies: stdlib plus the vendored libraries, Python ≥ 3.9, so front matter must stay hand-parsed. Sources: pyproject.toml:13-17, technical-requirements.md:9.
- The host must not know backends. No `if (provider.id === …)`. Source: technical-requirements.md:85-91.
- The provider contract changes additively, never silently. Source: technical-requirements.md:99-101.
- The model changes only after the backend or file has committed, and every local mutation uses the one queue. Sources: docs/providers.md:301-306, decisions.md:946-954, Provider.qml:515-516.
- A row carries only what the list shows or drags on. Fields that change often (like `version`) made rows compare different. Source: decisions.md:444-448.
- A save writes LF with no BOM. Source: notefile.py:22-25.
- Add a selftest case for every provider-script bug. Source: docs/testing.md:488-491.
- Code style: braces on every `if`/`else`/`for`/`while` with the body on its own lines; no hacks or workarounds. Source: CLAUDE.md.
- Non-goal: not an Obsidian or Notion replacement (no tags, databases or templates). Source: business-requirements.md:57-58.

## Reusable pieces

- `notefile.split` / `serialize` / `preview`, the single format: notefile.py:48-86
- `readfile.read_document` (complete UTF-8, explicit errors and kinds) and `read_capped` (best-effort prefix): lib/readfile.py:54-86
- `fileio.write_atomic` (atomic, exclusive create, mode keeping): lib/fileio.py:13-46
- `operations.execute`, the action dispatch where new actions such as setting a type would go, and the path guards `inside` / `folder`: operations.py:35-52, 81-144
- The local mutation queue `mutate()` (commit-after-write, revision guard): Provider.qml:515-536
- Stream escaping `escaped` and `unescaped`: list.py:156-160; Provider.qml:414-426
- The shared Markdown parser with task_lists (`task_list_item`, `attrs.checked`) and `walk_text`: services/markdown/parse.py:73, 100-105, 120-135
- Markdown escaping for writing event text: `escape_inline`, `escape_line_start`, `escape_text`: services/markdown/mdtext.py:46, 84-106
- `qthtml.unkept`, the round-trip guard for Markdown notes: services/markdown/qthtml/writer.py:84-94; operations.py:19-32
- Selftest helpers `check`, `operation`, `stream`, `listed`, `found` and `FIELDS`, with `test_line_endings` as the template: selftest.py:78-112, 338-353, 423-493
- In-process `Files.operation` and the notefile property table: tests/test_regressions.py:83-110
- QML `localCases` and `loadList` `record()` fixtures: tests/transitions.qml:1003-1044, 1457-1498

## Risks

1. Provider.qml:548-549 rebuilds the note entry on every save with explicit fields. A `type` field would vanish after the first autosave until the next relist, and the row could flip to the default type.
2. Provider.qml:509-511 rebuilds the load answer, so a type returned by operations.py would never reach the host unless this mapping is changed.
3. The listing parses only 4096 bytes. A front matter longer than that, or a `type:` line beyond it, lists with no title, the preview `title: …` and no type, while a load reads the whole file and sees it. List and load would disagree (verified).
4. A bare `type:` key can collide with metadata other tools write. This is general knowledge, not a code fact: Hugo uses front-matter `type` to pick layouts, and many Obsidian vaults use a `type:` property. Today such notes open as editable Markdown. Treating their values as content types, or refusing them, would regress.
5. There is no YAML parser. Events stored as YAML in front matter would be kept verbatim but would need a hand-written YAML subset. They would also be excluded from search (search.py:50-52) and from the preview.
6. No version check on save (last writer wins). A timeline checked in another editor or synced from a phone while the note has unsaved edits is silently overwritten by the next autosave.
7. Outside edits can produce a non-monotonic state (`[ ]` above `[x]`) that the "check everything above" rule does not allow. Behavior must be defined.
8. Tight task items join title and description with a softbreak, which is ambiguous to parse back. Opening such a note in the generic Markdown editor and saving rewrites it as one line ("Kickoff Agree scope").
9. Any body marker that is raw HTML makes the note read-only in the Markdown editor (unkept answers HTML). That breaks editing in an older app version and in any fallback that opens it as Markdown.
10. The generic preview shows `[ ] First event`, with the brackets kept. A progress-style preview computed from the 4 KiB head would be wrong for long timelines.
11. A file-extension marker changes identity (path), invalidates `.order` names, needs five `.md` filter changes and breaks "readable by any tool" if the extension is not `.md`.
12. A sidecar file blocks folder delete (operations.py:60-68) and causes relists.
13. Titles are written raw with no YAML quoting (notefile.py:75). Tools that parse front matter as strict YAML may misread titles containing `: `, `#` or leading quotes. This gap already exists and is unchanged by adding keys.
14. Docs and behavior differ: docs say a note over 2 MiB "opens read-only", but it loads as an error and is shown unavailable with no content.
15. Context only, not at HEAD: the untracked CODE-REVIEW-2026-10-11.md in the working tree reports that row actions (folder rename and delete) do not wait for the open note's save (its F2). A timeline note in a renamed folder would share that race.

## Open questions

1. Key name and vocabulary. A bare `type:` (collision risk) or a namespaced key? What values: `timeline`, `markdown`, `text`?
2. Does the app own the type key like `title` (parsed into a field, written by `serialize`) or keep it as an unowned `extra` line read through a notefile helper? Can a save or a later action ever change it?
3. Is an absent key the Markdown default? Should the app never write `type: markdown`, so existing notes are never rewritten?
4. Exact timeline body format. Tight or loose task list? How are the event title and description distinguished (first paragraph, bold, softbreak)? What about multi-paragraph descriptions, escaping of `[`, `*`, `#` in titles, and empty titles?
5. What happens with a non-monotonic check state, or non-task-list content, in a timeline note: show as is, normalize on the next check, or open read-only with a reason?
6. Must event text be found by body search? Body storage gives this for free; front-matter storage loses it.
7. What should a timeline row's preview be (first event, next unchecked event, "k of n")? Can it be computed from 4 KiB?
8. Can an existing note be converted to or from a timeline? If so, a set-type operation is needed in operations.py and the provider.
9. Should the local provider offer a plain-text type at all? Today every local note is `.md` Markdown, and Sticky Notes is the plain-text provider.
10. Should local adopt lib/notemerge or a version check so an outside check-off is not overwritten? This is a non-goal for local today.
11. How should an older app version, or an unknown future type, open a typed note: as editable Markdown (risking lossy writes for non-Markdown types) or read-only?

## Recommendations

1. Put the marker in the front matter, the format's own metadata place. It is read in the listing head with no load, preserved by the save path, ignored by search, and shown as a property by outside tools. Do not use a body marker, a file extension or a sidecar.
2. Read and write the type only through notefile.py, with a single helper used by list.py, operations.py read and save, and create. Never parse it in QML.
3. Treat an absent key as Markdown and write the key only for non-default types. Map unknown values to Markdown and keep the line verbatim.
4. Consider a namespaced key to avoid colliding with user metadata. Decide this before release, because the key is permanent on disk.
5. Store events in the Markdown body as a GFM task list (`- [x] Title` with an indented description paragraph). Read them with services/markdown/parse.py (`task_list_item`, `attrs.checked`) and write them with mdtext escaping. This keeps the note readable, editable and searchable outside the app, and keeps the existing editor able to open it.
6. Append the type as a trailing 8th field of the N record, and update `FIELDS` and the transitions `record()` fixtures.
7. Carry `type` through the save commit (Provider.qml:548) and the load answer (Provider.qml:509-511). Prefer `Object.assign` or explicit propagation so later fields are not dropped.
8. Return the type and a type-aware preview from the save answer, so the row stays consistent without waiting for a relist.
9. Add tests:
   - notefile property cases with a type line (tests/test_regressions.py:97-110)
   - a selftest round trip over list, read, save, the exact bytes and the re-read, including CRLF/BOM and a front matter over 4096 bytes
   - create with a type
   - unknown type falls back to Markdown
   - search finds event text
   - QML `loadList` with an 8-field N record
