# Quality-gates map: tests, docs, decisions, packaging, review backlog

Repository: `/home/andrei/Projects/note-note`, HEAD `e2cdc4e` (master). The only change in the working tree is the untracked `CODE-REVIEW-2026-10-11.md`. Every citation below is `file:line` at HEAD.

## Summary

- There are two test entry points, and each is registered by hand:
  - **Aggregate runner**: `python3 tests/selftest.py` (`--host` adds the Omarchy host check). Its `SUITES` list is at `tests/selftest.py:15-43`.
  - **CTest**: `cmake -S . -B build && cmake --build build && ctest --test-dir build`. Its `add_test` entries are at `CMakeLists.txt:71-131`.
  - The two lists do not match. CTest leaves out most Python suites: the local, Notion, Sticky and OneNote provider selftests, merge, search, the converter round trip, `cpp/selftest.py`, `tests/test_regressions.py` and others.
- Transition suite names live in three places that must agree:
  - `tests/transition_selftest.py:18`
  - `CMakeLists.txt:99`
  - `tests/EditorKeys.qml:3051-3059`
  - Review finding F17 covers this.
- The shared QML scenarios live in `tests/transitions.qml`. The core suite holds the controllers, providers, sessions and pure-JS checks in `pureCases`. `tests/EditorKeys.qml` holds the real-key editor scenarios, grouped into suites.
- `tests/transition_selftest.py` runs each suite in an isolated temporary home, either under Quickshell (`qs`) or the native harness (`--standalone`).
- Results are framed `<<<RESULT>>>…<<<END>>>`. A log line holding `TypeError:`, `ReferenceError:`, `Binding loop`, `Unable to assign`, `Error:` or `ERROR` fails the suite (`tests/transition_selftest.py:217-222`).
- Python provider tests are standalone scripts with a `check()` helper. They drive `operations.py` as the child process the provider runs. Example: `plugins/org.note-note.local/selftest.py:78-82` and `:423-429`.
- There are three ways to test pure JS:
  - add checks to `pureCases()` in `tests/transitions.qml:785-965`;
  - write an offscreen `qml6` runner like `services/requests/selftest.py` + `selftest.qml`;
  - write a `run(verify)` library module like `tests/ShortcutChecks.js`.
- No file has to be listed anywhere to be built or packaged, with a few exceptions:
  - CMake installs the runtime trees by pattern (`CMakeLists.txt:56-64`), except that `hosts/standalone` QML is listed by name (`:65-66`).
  - `packaging/package.py` builds the plugin archive from tracked files under fixed roots (`:14-15`, `:26-37`).
  - Both packagers leave out any file whose name contains `selftest`.
  - `design/qmldir` and `services/platform/qmldir` list their types by name. `ui/` has no qmldir. Every `*.qml` in `ui/tools/` is loaded as an editing tool (`ui/editing/ToolRegistry.qml:72`).
- The provider contract today is per provider:
  - `markdown: bool` means "bodies are Markdown (rendered); false = plain text" (`docs/providers.md:47`).
  - `Workspace.qml:2837-2840` turns that flag into `editor.plain`.
  - The documented decisions tie notes to Markdown on disk. Sticky Notes is plain text by product decision. The local format owns only `title` in front matter (`plugins/org.note-note.local/notefile.py:10-12`).
- Several documented rules must be respected or explicitly amended. The most important:
  - the non-goal "Not an Obsidian/Notion replacement… no … templates, databases" (`docs/business-requirements.md:57-58`);
  - "Local notes are plain Markdown … readable and editable by any other tool" (`:32-34`);
  - "change it additively, never silently" (`docs/technical-requirements.md:99-101`).
- Release steps:
  - bump `manifest.json:5` and add a lead `<release>` in `packaging/desktop/io.github.andreivinca.note-note.metainfo.xml:36-60`; `packaging/package.py:70-77` enforces the match;
  - `omarchy plugin validate .` must pass;
  - docs go in the same commit as the behaviour (`docs/release-process.md:25-37`).
- The untracked code review lists 21 findings (1 high, 4 medium, 16 low). All are still open: HEAD is the reviewed commit and nothing else has changed. These sit on the feature's paths:
  - F1: `NoteSession.replacePath` aliases;
  - F2 and F21: `runRowAction` save, wait and lock;
  - F10: the in-place rename;
  - F11: no tests for row actions;
  - F14: the `stored` snapshot;
  - F15: read-only pushed by hand;
  - F16: duplicated note-slot `Loader`;
  - F17: suite lists;
  - F20: the local `unkept` re-render;
  - plus the low-severity contract and menu duplication findings F8, F12 and F13.
- A new parser has to follow the security rules:
  - bound bytes and collections at read time (`docs/security.md:16-39`);
  - treat note content as hostile (`:329-331`);
  - read local files only through `lib/readfile.py`;
  - for JSON, use `lib/jsondata.py` (no duplicate keys, finite numbers only, depth ≤ 32);
  - open read-only with a reason rather than write lossily.
- **Baseline I ran at HEAD.** Python bytecode writing was off, and the tree was unchanged afterwards.

  | Check | Result |
  |---|---|
  | `tests/test_regressions.py` | 42 tests OK |
  | `plugins/org.note-note.local/selftest.py` | all green |
  | `services/markdown/qthtml/selftest.py` | 141/141 cases |
  | `transition_selftest.py --standalone --suite core`, harness `build/release/note-note-harness` | 289/289 |
  | same, `--suite keys` | 54/54 |
  | documented `qmllint` command | no output, exit 0 |
  | `uvx ruff check --no-cache .` | "All checks passed!" |

---

## 1. Tests: how to add, register and run

### 1.1 Runners and registration

| What | Where | Notes |
|---|---|---|
| Aggregate runner | `tests/selftest.py:15-43` (SUITES), `:46-68` (main) | Each entry runs as `[sys.executable, *suite.split()]` (`:50`) with `QT_QPA_PLATFORMTHEME=generic` (`:48`) and a 240 s timeout (`:58`). It adds `--shell` for `tests/extensions_selftest.py` and `tests/tabstrip_selftest.py` (`:51-52`), and `--host` only for the core transition suite (`:55-56`). |
| Transition suites inside the aggregate | `tests/selftest.py:11`, `:41` | Imports `SUITES` from `transition_selftest` and adds `tests/transition_selftest.py --suite <name>` for each. |
| CTest | `CMakeLists.txt:13` (`include(CTest)`), `:71-131` | Registered tests: document-theme, settings, extensions, theme, native-runtime, standalone, `native-transitions-{core,tools,lists,blocks,toolbar,diacritics,tables,keys}` (`:99-104`, TIMEOUT 240, `NOTE_NOTE_HARNESS` env), native-extensions, native-tabstrip, native-ordering, native-signout, onenote-page-order, onenote-blank-lines, onenote-audio, and audio-playback (only if Qt Multimedia is found, `:119-124`). |
| Not in CTest | compare `tests/selftest.py:16-39` with `CMakeLists.txt:71-131` | local, notion, sticky and onenote `selftest.py`; `onenote/merge_selftest.py`; `search_selftest.py`; `page_inventory_selftest.py`; `order_selftest.py`; `services/microsoft/selftest.py`; `lib/ratelimit_selftest.py`; `services/requests/selftest.py`; `services/markdown/qthtml/selftest.py`; `cpp/selftest.py`; `tests/test_regressions.py`; `tests/statusbar_selftest.py`; `lib/notemerge/selftest.py`. |
| In neither runner | `tests/flatpak_selftest.py`, `tests/audio_selftest.py` (CTest only, conditional) | |
| Transition suite names | `tests/transition_selftest.py:18`: `("core", "tools", "lists", "blocks", "toolbar", "diacritics", "tables", "keys")`. `CMakeLists.txt:99` repeats the list by hand. `tests/EditorKeys.qml:3051-3059` maps names to case lists. | A new suite needs all three edits (F17). |
| Native harness | `tests/harness_main.cpp:10-31` (built by `CMakeLists.txt:92-93`, never installed) | Runs `--data-dir <root> --qml <file>` over the application library. The default path is `build/note-note-harness`; override with `NOTE_NOTE_HARNESS` (`tests/transition_selftest.py:190`). |
| Documented commands | `docs/testing.md:3-18`, `:177-185`, `docs/standalone.md:228-233` | `python3 tests/transition_selftest.py [--standalone] [--suite X] [--host] [--notes]` |
| Deadlines | `tests/transition_selftest.py:19-24` (QML 150 s, process 180 s); `docs/testing.md:191-195` | |
| Dependencies | `docs/testing.md:69-73` | Python, `qml6`, `qs`, `inotifywait`, the Omarchy shell components, and the built native inspector (`sh cpp/build.sh`). |

### 1.2 A pure-JS unit test

- **Option A, the core transition suite.** Import the `.pragma library` module at the top of `tests/transitions.qml` with the `"app/…"` prefix (examples at `:15-22`). Add `check(name, ok, detail)` calls (`:250-252`) inside `pureCases()` (`:785-965`). `pureCases()` runs from `Component.onCompleted` (`:2029`).
  - `pureCases` is not called in the `--notes` branch (`:2010-2022`).
  - The runner rewrites `"app/` imports to `file:` URLs, and for `--standalone` turns `ShellRoot` into `Tests.TestRoot` (`tests/transition_selftest.py:110-116`).
  - Run with `python3 tests/transition_selftest.py --suite core [--standalone]`. CTest runs it as `native-transitions-core`.
- **Option B, a standalone offscreen qml6 runner.** Copy the pattern of `services/requests/selftest.py:28-75` with `selftest.qml`:
  - `check()` at `selftest.qml:16-18`;
  - `console.error("<<<RESULT>>>"…"<<<END>>>")` then `Qt.exit(0)` at `:395-398`;
  - the runner fails on any stderr line holding `qrc:` or `.qml:` (`selftest.py:56-57`).
  - Register it in `tests/selftest.py` SUITES, and in `CMakeLists.txt` with `add_test` if CTest should run it.
  - Name the files `*selftest*` so CMake install (`CMakeLists.txt:61`) and `package.py` (`:35`) leave them out.
- **Option C, a library test module.** `tests/ShortcutChecks.js` is `.pragma library` with `run(verify)` (`:1-30`), called from `tests/extensions.qml:11` and `:201`. `tests/extensions_selftest.py:38-42` rewrites its `.import` paths.

### 1.3 A QML transition test

- **Core suite** (`tests/transitions.qml`):
  - Write a function `xxxCases()` and call it from `Component.onCompleted` (`:2004-2048`). Session and OneNote cases also run in the `NOTE_NOTE_TEST_NOTES_ONLY` branch (`:2010-2022`).
  - Asynchronous work must keep the run open. Either increment and decrement `test.processes` (example `:1005-1008`), or add a `…Finished` flag to the completion timer condition (`:2055`).
  - Reusable test doubles:
    - the fake editor `document` (`:375-400`) shows the exact editor interface `NoteSession` needs: `setNote(t, b, shown)`, `snapshotDocument()`, `restoreDocument()`, `requestMarkdown(cb)`, `viewState`/`restoreViewState`, `showConflict`/`clearConflict`, `clearNotice`, `readOnly`, `documentBase`;
    - the fake provider queues `loads`/`saves`/`deletions` so a test controls callback order (`:401-414`);
    - a `Notes.NoteSession` wired to them (`:424-430`).
  - The real local provider runs on `NOTE_NOTE_TEST_DIR` (`:281`), with fixtures written by the runner (`tests/transition_selftest.py:152-154`).
  - The whole workspace is created only under `--host` or `--standalone` (`:932-962`).
- **Editor suites** (`tests/EditorKeys.qml`):
  - Each scenario is `{ name, run }` inside a suite list. The suites map is at `:3048-3059`.
  - A scenario runs synchronously, waits with `keys.wait`/`keys.tryVerify` (QtTest `TestCase` at `:98`), and fails by throwing through `require(ok, message)` (`:362-366`).
  - One scenario runs per event-loop turn (`:3381-3398`), and `resetEditor()` runs after each (`:3336-3346`). It resets `toolbarLayout`, `enabledTools`, `plain`, `hasNote`, `readOnly` and notices; any new editor state must be added there.
  - Save tests through the real editor use a stand-in provider with a session: `quietProvider`/`quietSession`/`quietSave` (`:300-331`). Example: `unchangedNoteUnsent` (`:336-360`).
- **Focused QML harness suites:**
  - `tests/ordering_selftest.py:28-54` with `tests/ordering.qml` (QtTest `TestCase`, done marker `<<<ORDERING_DONE>>>`; fails on `TypeError:`, `ReferenceError:`, `Binding loop`, `Unable to assign` or `FAIL!`). Registered in CTest as `native-ordering` (`CMakeLists.txt:109-110`, `:129-130`) and in `tests/selftest.py:38`.
  - The same shape is used by tabstrip, statusbar and signout.

### 1.4 A Python selftest for a provider

- Pattern in `plugins/org.note-note.local/selftest.py`:
  - module docstring explaining the property under test (`:1-41`);
  - `check()` appends to `FAILURES` (`:78-82`);
  - `operation(root, **payload)` runs `operations.py` as the provider's child process (`:423-429`);
  - each `test_xxx(directory, verbose)` returns a failure count and is listed in `main()` (`:557-582`).
  - Template for "opens read-only with a reason": `test_unkept_opens_read_only` (`:524-554`).
  - It is already in `tests/selftest.py:18`. It is not in CTest.
- Unit-style regressions, in `tests/test_regressions.py`:
  - `Files.operation()` (`:84`);
  - the front-matter preservation test (`:86-95`);
  - "the note format has one reading", a `notefile.split`/`serialize` round trip (`:97-110`);
  - structural source scans: only `ui/AudioPlayback.qml` imports QtMultimedia (`:540-549`); constants agree across `ui/Dialect.js`, `qthtml.dialect` and `cpp/dialect.h` (`:551-570`).
- Converter round trip: `services/markdown/qthtml/selftest.py`. Add a case to `CASES` (`:32`) for every formatting bug. Notes the editor cannot write back go in `UNKEPT` (`:233-260`). Documented at `docs/testing.md:353-380`.
- House rules: "Add a case for every provider-script bug" (`docs/testing.md:488`); "Add a case to `CASES` for every formatting bug" (`:369`); "Add a case for every queueing bug" (`:409`).

### 1.5 Fixed values in tests that a feature can break

- `services/extensions/selftest.py:37-55` pins the built-in catalog:
  - provider ids `["local","sticky","onenote","notion"]`;
  - workspace commands `new-note`, `new-notebook`, `open-settings`, `toggle-sidebar`, `delete-note`;
  - calendar tools.
  - A new built-in command, tool or package means updating this test.
- `tests/standalone_selftest.py:183-184` pins the first-run config to each provider's declared defaults. A new provider setting means updating it.
- `tests/standalone_selftest.py:190` installs `examples/hello` as a legacy provider. `tests/standalone_launch.qml:38-40` requires it to load. An old-style provider (`markdown: true`, four-argument `load` result) must keep working.
- Log-noise gates:
  - `tests/standalone_selftest.py:154-155` also fails on `QML ` and `Error:`;
  - `tests/transition_selftest.py:217-222`;
  - `tests/extensions_selftest.py:69-70`.

### 1.6 Lint and the UI checklist

- `qmllint -I /usr/share/omarchy/shell …` (the documented file set), `python3 -m py_compile`, and `uvx ruff check .` (`docs/testing.md:91-99`). Ruff rules: `pyproject.toml:19-44` (E4, E7, E9, F).
- UI-change checklist (`docs/testing.md:763-775`): lint clean, the converter selftest green, the relevant provider suites, restart with a clean log, screenshot, exercise through `shell call` and check the saved file.
- IPC surface for manual checks: `debugState` (`Workspace.qml:1576-1606`), documented at `docs/testing.md:111-127`.
- With real accounts: throwaway notes only; never print, screenshot or commit note contents (`docs/testing.md:582-588`).

---

## 2. Decisions and non-goals the feature must respect or amend (quoted)

| Rule | Source |
|---|---|
| "**Not an Obsidian/Notion replacement.** No backlinks, graph view, tags, databases, templates or plugins-inside-the-plugin." | `docs/business-requirements.md:57-58` |
| "**Not a rich-text word processor.** Fonts, colours, text size and hand-drawn ink are outside what Markdown can carry, so they are not offered." | `docs/business-requirements.md:59-60` |
| Goal 2: "a note that cannot be written back safely opens read-only with a visible reason." | `docs/business-requirements.md:29-31` |
| Goal 3: "Local notes are plain Markdown in `~/Notes`, readable and editable by any other tool, with no database and no lock-in." | `docs/business-requirements.md:32-34` |
| Goal 4: "One list for every source… same sidebar, same editor, same shortcuts." | `docs/business-requirements.md:35-36` |
| Goal 6: a provider is a folder with a `Provider.qml`. Goal 7: "Honest about limits". | `docs/business-requirements.md:40-44` |
| "Local notes are one Markdown file per note, in folders \| any editor can read them; folders map to notebooks with no metadata of our own" | `docs/business-requirements.md:70` |
| "The title lives in a small front-matter block, not the filename" | `docs/business-requirements.md:71` |
| "Sticky Notes has no title field" / "Sticky Notes are plain text; OneNote and Notion are Markdown" (content type decided per provider) | `docs/business-requirements.md:73-74` |
| Success criterion: "A new provider can be written against PROVIDERS.md without reading the host's code." | `docs/business-requirements.md:85-86` |
| "The app owns only `title`. Any other line inside the fences … is not the app's to understand" | `plugins/org.note-note.local/notefile.py:10-12` |
| "Editor format: the document is **rich text** (HTML); notes and the provider contract are **Markdown**, converted at both ends by `services/markdown/qthtml/`" | `docs/technical-requirements.md:14` |
| "Language: QML + JavaScript (ES5-era engine…)" | `docs/technical-requirements.md:8` |
| "The host must not know any backend, path format… Every branch of the form `if (provider.id === "…")` is a design failure" | `docs/technical-requirements.md:85-91` |
| Contract: "It is the API other people write against: change it additively, never silently." | `docs/technical-requirements.md:99-101` |
| "A note is addressed by `"<providerId>:<opaque>"`. Only the provider parses the part after the colon." | `docs/technical-requirements.md:105-106` |
| Limits table: local note 2 MiB, provider payload 8 MiB, Sticky 256 KiB per body, Notion 300 blocks per page, … | `docs/technical-requirements.md:170-188` |
| Rich text, not Markdown, in the editor: "Notes on disk and the provider contract are unchanged"; the loop must reach a fixpoint, and that is a test | `docs/decisions.md:131-154` |
| Vendored mistune: "standard library only, nothing installed"; the renderers stay ours | `docs/decisions.md:156-163` |
| "The host owns the note and the text — it is the editor's document, and only the host can turn it into Markdown — and the provider owns the timing" | `docs/decisions.md:470-473` |
| A note is unsaved until a provider says otherwise; a failed save puts the note back to unsaved | `docs/decisions.md:489-521` |
| Converter answers are framed: "an answer that does not parse is the failure, always"; "a note is loading until its document is on screen" | `docs/decisions.md:523-555` |
| "Sticky Notes: plain text, no title, no reordering … exposing a title field … would be inventing behaviour the backend cannot keep." | `docs/decisions.md:557-561` |
| "Read-only rather than lossy writes … What decides it is the round trip, not a list of block types." | `docs/decisions.md:660-721` |
| The parser enables `task_lists`, `strikethrough`, `table`, `mark`, underline; "a style the save would silently drop breaks the first rule of the project the quiet way" | `docs/decisions.md:723-731` |
| "A rich paste brings only what the notebook can keep" (`tools`, `canImages`, `ui/PasteFit.js`) | `docs/decisions.md:779-809` |
| "A tool is offered only where it can act" | `docs/decisions.md:852-869` |
| "A separator line is never an item" (list/todo restyling) | `docs/decisions.md:871-883` |
| Setup belongs to the provider: `viewRequested(title, component, props)` is rendered in the note pane; a host-rendered declarative schema was rejected ("would grow into a form framework") | `docs/decisions.md:120-129` |
| "a row carries only what the list shows or drags on" | `docs/decisions.md:444-448` |
| Settings: "a setting that changes nothing would be a lie in a self-documenting config file"; providers declare `settings` and defaults are recorded off a fresh instance | `docs/decisions.md:903-935` |
| `NoteSession` owns load generations, drafts and completion; "All local mutations use one queue"; "The editor's read-only flag is derived, never put back" | `docs/decisions.md:938-972` |
| Nested tables: "neither the editor nor providers receive unchecked HTML" | `docs/decisions.md:6-11` |
| A different rich-text editor was rejected: "inside Quickshell there is none — QML offers this engine or a QtWebEngine-sized dependency" | `docs/decisions.md:581-587` |
| "A tool's edit is one transaction" (one undo step) | `docs/decisions.md:748-765` |
| "A save already accepted finishes, even after the window closes" | `docs/decisions.md:360-369` |
| The three rules: notes are the product (when in doubt, read-only); every input is bounded and untrusted; a provider owns its backend | `docs/README.md:38-45` |
| Code style: no hacks or workarounds; braces always; body on its own lines; one statement per line | `CLAUDE.md`, `AGENTS.md:1-6` |
| Python: floor 3.9, nothing newer than 3.8 syntax, `dependencies = []` | `pyproject.toml:10-17` |
| JS engine: no regex lookbehind | `docs/engine-notes.md:17-19` |
| Models: a plain JS array, replaced wholesale | `docs/engine-notes.md:42-49`, `docs/technical-requirements.md:167-168` |

---

## 3. When the provider contract changes; release steps

### Files that change with the provider contract

Precedent: commit `ed99df7`, the row-menu contract change, touched:

- `docs/providers.md` (properties `:41-60`, rows `:89-94`, menus `:96-139`, functions `:257-367`, signals `:429-467`, limits `:493-507`);
- `skills/note-note-plugin/references/providers.md` (minimal provider `:40-55+`, properties `:229-247`, rows `:249-310`, functions `:312-320`);
- `examples/hello/Provider.qml` (`:14-15` flags, `:90-105` `load`/`save`/`create`);
- all four built-in `plugins/org.note-note.*/Provider.qml` files;
- `README.md` (Notebooks `:185-241`, Providers `:269-289`);
- the metainfo release notes.

Also in scope:

- `docs/technical-requirements.md` editor format `:14` and data model `:105-117`. The row shape there is already stale.
- `docs/business-requirements.md:66-78` product decisions.
- `docs/decisions.md`, for a new decision entry.
- `docs/testing.md`.
- `docs/README.md:7-23`, if a new doc is added.

### The checker

- `skills/note-note-plugin/scripts/check.py` only runs `services/extensions/manifest.py` over `plugin.json` packages (`:1-7`, `:17`, `:61-73`).
- The validator reads only `id`, `path` and `order` for a provider (`manifest.py:79-87`), and requires `apiVersion == 1` (`:136-137`).
- So the checker changes only if `plugin.json` gains fields. That would also mean changing `services/extensions/selftest.py`, `docs/plugins.md:9-41` and `SKILL.md:50-91`.
- Nothing checks that `docs/providers.md` and the skill reference agree. They are synced by hand, and F13 is a drift that already happened.

### Additive precedent

The legacy `canReorder` flag kept working while per-row `reorder` descriptors took precedence over it (`docs/providers.md:170-175`).

### Release steps

1. Commit only when the author asks (`docs/release-process.md:25`).
2. Bump `version` in `manifest.json:5`. The documented semver rule (`docs/release-process.md:26-27`): breaking layout or contract change → major, feature → minor, fix → patch.
3. Add a lead `<release version=… date=…>` with user-facing notes to `packaging/desktop/io.github.andreivinca.note-note.metainfo.xml:36-60`. "Nothing else carries the version" (`docs/release-process.md:28-29`).
4. Run `omarchy plugin validate .` (`docs/release-process.md:30`).
5. Commit and push, then `gh release create vX.Y.Z` with notes written for users (`docs/release-process.md:31-34`).
6. Keep the README, `docs/providers.md` and `docs/` in the same commit as the behaviour they describe (`docs/release-process.md:36-37`).
7. Read the pre-release security checklist (`docs/security.md:10`, `:286-325`).

Archives:

- `cmake -S . -B build/release -G Ninja -DCMAKE_BUILD_TYPE=Release …`, then `ctest`, then `python3 packaging/package.py` (`docs/standalone.md:110-135`).
- `package.py` checks:
  - the metainfo leads with the manifest version (`:70-73`);
  - the binary `--version` matches (`:74-77`);
  - the installed, stripped layout passes `tests/standalone_selftest.py` (`:104-108`);
  - the plugin passes `omarchy plugin validate` (`:128`).
- CMake reads the version from `manifest.json` (`CMakeLists.txt:2-7`).

---

## 4. Open review findings on the feature's paths

Source: `CODE-REVIEW-2026-10-11.md`. Status COMPLETE (`:7`); 21 findings (`:11`). All are open at HEAD. I re-checked every cited line against HEAD.

| ID | Severity | What | Where | Why it matters to this feature |
|---|---|---|---|---|
| F1 | high | Folder renames reuse `replacePath`'s permanent one-way aliases. Renaming A→B→A makes `resolvedPath` point at a dead path, so autosave stops silently, the busy state sticks, and the folder's other notes cannot be opened. | `CODE-REVIEW…:52-57`; `services/notes/NoteSession.qml:63`, `:68-70`, `:75-114` (alias at `:76`; the re-keyed maps listed at `:77`); `Workspace.qml:767-775` | The feature will add per-note state to the session, such as the content type of the open note. A new path-keyed map must also be re-keyed in `replacePath` (`:77`). A timeline in a renamed local section hits the same bug. The proposed fix: delete `pathAliases[next]` and collapse alias chains. |
| F2 | medium | `runRowAction` calls `flushSave()`, which only starts a save, then calls `rowAction` at once. The documentation and comments say the save is written first. | `CODE-REVIEW…:59-64`; `Workspace.qml:2105-2132`; `plugins/org.note-note.local/Provider.qml:621-623`; `docs/providers.md:115-120` | Any new row-menu item (for example a typed "New …" on a section) goes through this path. |
| F21 | low | `runRowAction` locks the session on trust. A provider that answers `cb()` throws before `unlock()`. | `CODE-REVIEW…:175-179`; `Workspace.qml:2116-2131` | Same path as F2. Fix together: `result = result \|\| {}` and an unconditional unlock. |
| F10 | medium | The in-place rename field loses what was typed whenever the rows rebuild, for example when an autosave lands. | `CODE-REVIEW…:112-117`; `ui/NoteList.qml:366-374`, `:495-529` | Every timeline check-off is a save that rebuilds rows, so this triggers more often. |
| F11 | medium | No tests cover `renameSection`, `removeSection`, `rowAction`, `runRowAction`, `RowMenu`, `PromptDialog` or the notewalk caps. | `CODE-REVIEW…:119-123`. `replacePath` is exercised only through OneNote creation (`tests/transitions.qml:1661-1662`). | The feature's tests go into the same suites. These are the missing patterns. |
| F14 | low | `NoteSession.stored` keeps a snapshot of every note ever opened. | `CODE-REVIEW…:135-139`; `NoteSession.qml:37-43`, `:251`, `:294`, `:364-367`, `:485`, `:526` | The no-op-save comparison uses the editor's own form (`snapshotDocument`). A timeline view needs a comparable snapshot, and the proposed fix (one `{path, document}`) simplifies that. |
| F15 | low | The read-only flag is a binding but is still pushed by hand from six places. | `CODE-REVIEW…:141-145`; `NoteSession.qml:28-29`, `:119-121` (calls at `:127`, `:132`, `:142`, `:174`, `:319`, `:329`) | A second view that must honour read-only needs a single derived source of truth. |
| F16 | low | The conflict-review `Loader` copies the provider-view `Loader`. | `CODE-REVIEW…:147-150`; `ui/NoteEditor.qml:1918-1931`, `:1934-1948` | A timeline view hosted in the note slot would make a third copy. Suggested fix: a `PropsLoader`. |
| F17 | low | Suite names live in two lists; `tests/selftest.py` splits argv strings. | `CODE-REVIEW…:152-156`; `CMakeLists.txt:99`; `tests/transition_selftest.py:18`; `tests/selftest.py:50`, `:55` | A new timeline suite would otherwise run under `tests/selftest.py` but silently not under CTest. |
| F20 | low | Every local note is rendered twice on open; `unkept` comes from a second render in `operations.py`. | `CODE-REVIEW…:169-173`; `plugins/org.note-note.local/operations.py:19-24`, `:111-120` | The local read path is where a per-note type is read. A non-Markdown body would be judged by Markdown `unkept` rules unless the check knows the type. |
| F8 | low | The delete menu item is pasted into five providers. | `CODE-REVIEW…:100-104`; local `Provider.qml:120`, onenote `:227`, notion `:73`, sticky `:64`, `examples/hello/Provider.qml:54` | Per-note menu items for a new type would multiply the copies. |
| F12 | low | `runFooterAction` spells the tab key by hand. | `CODE-REVIEW…:125-128`; `Workspace.qml:1679`; `services/notes/sidebar.js:4-9` | Typed creation buttons in the footer use this path. |
| F13 | low | The skill reference's row shape lacks `count`. | `CODE-REVIEW…:130-133`; `skills/note-note-plugin/references/providers.md:267` vs `docs/providers.md:89` | The same file is edited for the content-type contract; fix the drift in the same pass. |
| F5 | low | `removeFolder` returns `removed` by mutating the answer object. | `CODE-REVIEW…:81-85`; local `Provider.qml:517-536`, `:706-723` | Local provider row actions. |
| F3 / F4 / F6 | medium / low / low | Silent depth cap; off-by-one truncation sentinel; quadratic `rebuild()`. | `CODE-REVIEW…:66-91`; `lib/notewalk.py:14-41`; `plugins/org.note-note.local/list.py:218-219`, `:254-255`; local `Provider.qml:200-262` | The local listing and rebuild; touched if the list gains a per-note type. |
| F18 | low | Comments narrate history ("used to", "now"). | `CODE-REVIEW…:158-162`; `ui/PasteFit.js:6-11`; `tests/EditorKeys.qml:3378-3380`; `services/markdown/qthtml/selftest.py:227` | Style rule: state the present rule. |
| F7, F9, F19 | low | OneNote section cache "unknown means gone"; the section-name rule written twice; `notion.py`'s two ways of removing its cache. | `CODE-REVIEW…:93-98`, `:106-110`, `:164-167` | Not on the feature's paths. |

Other observations from the review, confirmed:

- `git worktree list` shows `.claude/worktrees/agent-a4f19c270115b62cd`, which pollutes repo-wide grep, and a prunable `/tmp/note-note-omarchy-1.0.21`.
- `git describe --tags HEAD` gives `v1.0.39-5-ge2cdc4e`. There is no local `v1.0.40` tag.

---

## 5. Security and bounds rules for a new parser (for example a timeline body parser)

- **Rule 1** (`docs/security.md:16-39`): bound every input at the moment it is read; read cap+1 bytes once; count bytes, not characters (`provider_io.read_payload`); "Bound collections too, not only bytes: number of notes, sections, pages, blocks, images". For a timeline that means a maximum number of events and maximum title and description lengths.
- **Rule 9** (`docs/security.md:245-261`): open local files through `lib/readfile.py` (`O_NOFOLLOW|O_NONBLOCK`, `fstat` regular file, cap, deadline).
- **Rule 2** (`docs/security.md:41-51`): write through `fileio.write_atomic`.
- **Rule 3** (`docs/security.md:53-64`): note bodies go to scripts over stdin, never through `/tmp`.
- **JSON bodies**: `lib/jsondata.py` gives strict bounded JSON. It rejects duplicate keys (`:9-15`), non-finite numbers (`:18-29`) and nesting deeper than 32 (`:22-38`); it reads through `read_document` (`:41-45`); `answer()` caps stdin and frames errors (`:48-65`). Mentioned at `docs/security.md:340-349`.
- **Threat model**: "Assumed hostile: note content from any backend… and anything on disk that another process with the same uid can replace" (`docs/security.md:329-331`).
- **No unchecked HTML**: "neither the editor nor providers receive unchecked HTML" (`docs/decisions.md:10-11`).
- **Failure is never an empty note**: a parse failure must open read-only with a reason and must not become an editable empty or partial note that autosave writes back (`docs/decisions.md:523-555`, `:660-667`; `docs/providers.md:495-507`: "It must never become an editable partial note").
- **Who bounds**: "Everything a provider reads is the provider's responsibility to bound … The host never reads provider data from disk or network itself" (`docs/providers.md:495-499`).
- **JS side**: no regex lookbehind (`docs/engine-notes.md:17-19`). Maps keyed by user text must be prototype-free (`Object.create(null)`, commit `0fa55bc`), and are tested with names like `constructor`, `toString` and `__proto__` (`docs/testing.md:54-60`; `tests/ordering_selftest.py:12-25`).
- **Python side**: standard library only, Python 3.9 floor (`pyproject.toml:10-17`). Any subprocess gets `timeout=`, resource limits and argv arguments (`docs/security.md:310-311`, rule 8 at `:239-243`).
- **Limits are documented** in `docs/technical-requirements.md:170-188` and enforced at read time.
- **Pre-release checklist**: `docs/security.md:286-325`.

---

## 6. Packaging: do new files have to be listed?

| Mechanism | Rule | Source |
|---|---|---|
| CMake install (standalone and Flatpak) | Installs `assets design ui plugins extensions services lib` by pattern (`*.qml *.js *.py *.json qmldir *.svg *.ttf *.otf *.md LICENSE* COPYING*`), excluding `__pycache__`, `graphify-out` and `*selftest*`. `Workspace.qml`, `LICENSE` and `NOTICE.md` are installed explicitly. | `CMakeLists.txt:50`, `:56-64` |
| CMake install of `hosts/standalone` | Only `Main.qml`, `Backend.qml` and `TextInspector.qml`, listed by name. | `CMakeLists.txt:65-66` |
| Native C++ sources | Listed by name in `NOTE_NOTE_NATIVE_SOURCES`. | `cpp/sources.cmake:4-9` |
| Omarchy plugin archive | Tracked files only, under `assets cpp design extensions lib plugins services ui`, plus `manifest.json`, `Workspace.qml`, `LICENSE`, `NOTICE.md` and `hosts/omarchy/`. Skips dotfiles and names containing `selftest`. | `packaging/package.py:14-15`, `:26-37`, `:110-114` |
| Flatpak | Builds the working tree through CMake with `-DBUILD_TESTING=OFF`. No file list. | `packaging/flatpak/io.github.andreivinca.note-note.json:46-56` |
| QML module registration | `design/qmldir:1-5` and `services/platform/qmldir:1-2` list their types (a new type at those roots needs an entry). `ui/`, `services/notes/` and `plugins/*` have no qmldir; plain directory imports pick new files up. | the qmldir files |
| Tool discovery | `ui/editing/ToolRegistry.qml:65-75` loads every `*.qml` in the tool directory as a tool. A non-tool QML file must not go in `ui/tools/`. | `ToolRegistry.qml:72` |
| Not packaged | `docs/`, `skills/`, `examples/`, `tests/` and `README.md` are in neither archive. | `package.py:14-15`, `CMakeLists.txt:56` |

---

## Integration points (quality gates)

1. `tests/transitions.qml:785-965` (`pureCases`), `:1-23` (imports), `:2004-2048` (case order). Add checks for the content-type and timeline JS modules and new session cases. The core suite is where controllers and sessions are tested.
2. `tests/EditorKeys.qml:3048-3059` and `:3336-3346`. Add timeline scenarios (or a suite) and reset any new editor or content-type state in `resetEditor`. Real-key click and save checks live here.
3. `tests/transition_selftest.py:18` with `CMakeLists.txt:99`, if a new suite is added. Both lists must name it (F17).
4. `tests/selftest.py:15-43` and `CMakeLists.txt:71-131`. Register every new Python or qml6 suite; neither runner discovers suites.
5. `plugins/org.note-note.local/selftest.py:557-582`. Add tests that a note's type survives `operations.py` read, save and create and the listing; that is the provider-script test home.
6. `tests/test_regressions.py:86-110`. Extend the `notefile` split/serialize round trip if the front matter gains a key. `notefile` currently owns only `title`.
7. `services/markdown/qthtml/selftest.py:32`, `:233-260`. Add CASES or UNKEPT entries if the timeline is stored as Markdown constructs; the round trip must close.
8. `services/extensions/selftest.py:37-55`. Update it if built-in commands, tools or packages are added; it pins the catalog.
9. `tests/standalone_selftest.py:183-184`, `:190`; `tests/standalone_launch.qml:38-40`. Update for any new declared provider settings; the legacy `examples/hello` must still load. These pin defaults and backward compatibility.
10. The provider contract docs: `docs/providers.md:41-60`, `:257-357`; `skills/note-note-plugin/references/providers.md:229-247`, `:312-320`; `examples/hello/Provider.qml:14-15`, `:90-105`. Document the content-type contract additively and keep the mirror in sync. The contract is public (`docs/technical-requirements.md:99-101`).
11. Product docs: `README.md:185-241`; `docs/technical-requirements.md:14`, `:105-117`, `:170-188`; `docs/business-requirements.md:57-58`, `:66-78`; `docs/decisions.md` (new entry); `docs/testing.md`. Update user docs, the format, limits and product decisions, and amend the non-goals explicitly; docs must ship in the same commit.
12. `manifest.json:5` and the metainfo (`:36-60`). Version bump and user-facing release notes; `package.py:70-77` enforces them.
13. `Workspace.qml:2837-2840`. The per-provider `markdown` → `editor.plain` binding is the content-type seam today; tests set `editor.plain` directly (`EditorKeys.qml:3342`).
14. `services/notes/NoteSession.qml:77`. Any new per-path map must be re-keyed in `replacePath` (and F1 fixed), or a note whose path changes loses its state.
15. `Workspace.qml:1576-1606`. Exposing the open note's type in `debugState` lets IPC and tests check it (`docs/testing.md:116-117`).
16. `CMakeLists.txt:65-66`, `design/qmldir`, `cpp/sources.cmake`. Touch these only if new files land in `hosts/standalone`, the `design/` root or native C++; those are the only by-name registries.

## Constraints

- Code style: braces on every `if`/`else`/`for`/`while`; body on its own lines; one statement per line; no hacks or workarounds; do the proper fix (`CLAUDE.md`, `AGENTS.md:1-6`).
- After modifying code, run `graphify update .` (`/home/andrei/CLAUDE.md`).
- Contract changes are additive and never silent (`docs/technical-requirements.md:99-101`). `apiVersion` stays 1 (`services/extensions/manifest.py:136-137`).
- Non-goal: no templates or databases; "Not an Obsidian/Notion replacement" (`docs/business-requirements.md:57-58`). Amend explicitly if timeline notes are added.
- Local notes stay plain Markdown, readable by any tool (`docs/business-requirements.md:32-34`, `:70`).
- The title lives in front matter; the app owns only `title` (`docs/business-requirements.md:71`; `notefile.py:10-12`).
- The read-only-with-reason rule beats lossy writes (`docs/business-requirements.md:29-31`; `docs/decisions.md:660-721`).
- The host must not branch on provider id (`docs/technical-requirements.md:85-91`).
- Every input is bounded at read time, collections included (`docs/security.md:16-39`).
- The read-only flag is derived, never put back (`docs/decisions.md:963-972`).
- Every bug gets a regression case in the matching suite (`docs/testing.md:369`, `:409`, `:488`).
- Tests use temporary fixtures and no real accounts or notes (`docs/testing.md:3-4`, `:582-588`).
- No QML warnings or errors in suite output; the noise gates fail the run (`tests/transition_selftest.py:217-222`; `tests/standalone_selftest.py:154-155`).
- Runtime-tree test files must contain `selftest` in their names to stay out of packages (`CMakeLists.txt:61`; `packaging/package.py:35`).
- Docs, README and `providers.md` go in the same commit as the behaviour (`docs/release-process.md:36-37`).
- Bump the version in `manifest.json` and the metainfo together (`docs/release-process.md:26-29`; `packaging/package.py:70-77`).
- Commit only when the author asks (`docs/release-process.md:25`).
- Python: floor 3.9, standard library only, no dependencies (`pyproject.toml:10-17`).
- JS: ES5-era engine, no regex lookbehind (`docs/technical-requirements.md:8`; `docs/engine-notes.md:17-19`).
- Sidebar model rows carry only what the list shows (`docs/decisions.md:444-448`).
- A provider declares its settings; no setting that changes nothing (`docs/decisions.md:903-935`).

## Reusable pieces

- The `check()`, fake editor `document`, fake provider and NoteSession wiring in `tests/transitions.qml:250-252`, `:375-430`.
- `quietProvider`/`quietSession`/`quietSave`/`require()` and the suites map in `tests/EditorKeys.qml:300-366`, `:3048-3059`.
- The offscreen qml6 runner with RESULT framing: `services/requests/selftest.py:28-75`; `services/requests/selftest.qml:16-18`, `:395-398`.
- The focused native-harness suite pattern: `tests/ordering_selftest.py:28-54` with `tests/ordering.qml`.
- The `run(verify)` library test module: `tests/ShortcutChecks.js:1-30`.
- The provider selftest helpers `check()`/`operation()` and the read-only template: `plugins/org.note-note.local/selftest.py:78-82`, `:423-429`, `:524-554`.
- The note-format round trip and front-matter preservation tests: `tests/test_regressions.py:84-110`.
- The CASES and UNKEPT tables: `services/markdown/qthtml/selftest.py:32`, `:233-260`.
- Strict bounded JSON: `lib/jsondata.py:9-65`.
- Bounded reads and atomic writes: `lib/readfile.py` (`read_document`), `lib/fileio.py` (`write_atomic`), `lib/provider_io.py` (`read_payload`, `load_json`) — `docs/security.md:16-51`.
- `notefile.split`/`serialize` keep the extra front-matter lines: `plugins/org.note-note.local/notefile.py:48-76`.
- The additive contract precedent (legacy `canReorder` with per-row `reorder`): `docs/providers.md:170-175`.
- Host JS imported by providers (`services/notes/ordering.js`): `plugins/org.note-note.local/Provider.qml:5`.
- The provider-view `Loader` in the note slot plus `viewRequested`: `ui/NoteEditor.qml:1918-1931`; `docs/providers.md:435-443`.
- The prototype-free map fixtures: `tests/ordering_selftest.py:12-25`; `docs/testing.md:54-60`.
- The plugin checker and validator: `skills/note-note-plugin/scripts/check.py:61-73`; `services/extensions/manifest.py:79-87`.

## Risks

- **Two unsynced runners.** A suite registered in only one of `tests/selftest.py` and CTest silently skips in the other (F17, plus most Python suites are missing from CTest).
- **Noise gates.** Any `Binding loop`, `TypeError:`, `Error:` or `QML ` line from new QML fails the transition and standalone suites, including warnings in production code.
- **Fixed catalog values.** `services/extensions/selftest.py:37-55` and `tests/standalone_selftest.py:183-184` will fail if a feature adds built-in commands, tools, packages or provider settings without updating them.
- **Legacy compatibility.** `examples/hello` is installed as a legacy provider by `tests/standalone_selftest.py:190`. A host change that requires a per-note type from every provider would break it and external providers.
- **Content type is per provider today.** `editor.plain` derives from `provider.markdown` (`Workspace.qml:2837-2840`). Per-note switching changes editor mode within a session, and `resetEditor` (`EditorKeys.qml:3336-3346`) and the fakes (`transitions.qml:375-414`) must cover the new state.
- **Local `unkept` check.** The local read runs the Markdown renderer's `unkept` on every body (`operations.py:111-120`). A non-Markdown body would be judged as Markdown (F20).
- **Path aliases (F1).** New per-path session maps must be re-keyed in `replacePath` (`NoteSession.qml:77`), or a renamed section's timeline loses its state.
- **Upstream Qt table bug.** Rendering a timeline as RichText tables inside the TextEdit would hit it (`docs/known-bugs.md:11-99`); the documented policy is to wait for Qt, not work around it (`:95-99`).
- **Tool directory.** Any `*.qml` placed in `ui/tools/` is loaded as a tool (`ToolRegistry.qml:72`).
- **Doc drift that will be touched:**
  - the row shape in `docs/technical-requirements.md:107-109` lacks `menu`/`count`/`reorder`/`modified`;
  - the skill reference lacks `count` (F13);
  - `docs/security.md:319-320` refers to a README "Limits" section that does not exist;
  - `docs/business-requirements.md:63-64` says "No image upload" while images are pasted and uploaded (`docs/decisions.md:217-259`);
  - code comments say `PROVIDERS.md` for `docs/providers.md`.
- **Release-process drift:**
  - semver says feature → minor (`docs/release-process.md:26-27`), but recent features shipped as patch bumps (1.0.39 → 1.0.40);
  - the release-history table (`:76-94`) lists 2.x versions while `manifest.json:5` is 1.0.40;
  - authorship says "no co-author trailers" (`:9-11`) while recent commits (`5887a8f`, `7162589`, `20e0b24`, `9f37b41`, `0fa55bc`) carry Co-Authored-By.
- **Repository hygiene:** the stale `.claude/worktrees` checkout pollutes grep results; there is no local `v1.0.40` tag.
- **Existing style deviations** (one-line function bodies such as `plugins/org.note-note.local/Provider.qml:37`, `examples/hello/Provider.qml:90`, `tests/transitions.qml:398`) must not be copied into new code.

## Open questions

1. Does the per-note content type live in the local note's front matter? That would amend `notefile.py:10-12` ("The app owns only `title`"), the README format at `README.md:193-200`, and `tests/test_regressions.py:97-110`. Or does it live elsewhere?
2. How should `docs/business-requirements.md` be amended so a timeline note type is not read as the "templates/databases" non-goal (`:57-58`)? Which providers can store a timeline? Sticky Notes is plain text with a 256 KiB body cap; Notion allows 300 blocks per page.
3. Should timeline editor checks get their own EditorKeys suite (three lists to edit, F17) or join an existing suite such as `keys`?
4. Which version bump applies? The documented semver rule says minor for a feature and major for a breaking contract change; practice has been patch bumps.
5. Should commits carry Co-Authored-By trailers? `docs/release-process.md:9-11` says no; recent practice says yes.
6. Where should timeline limits (maximum events, title and description lengths) be documented, given `docs/security.md:319-320` points at a README "Limits" section that does not exist? `docs/technical-requirements.md:170-188` and `docs/providers.md:493-507` are the existing limit tables.
7. Are CTest and `tests/selftest.py` both mandatory gates for this feature? `docs/testing.md` documents both, and they cover different sets.
8. The computed task calls the review "in-progress", but the file says "Status: COMPLETE" (`CODE-REVIEW…:7`). Are more findings expected?

## Recommendations

These are recommendations, not facts.

- Fix F1, then F2 with F21, then F17, before or alongside the feature. They sit on the session, row-menu and test-registration paths the feature extends. Fold F13 into the contract-doc update, and consider F14, F15 and F16 if the timeline adds a second document view.
- Add tests at every level:
  - pure-JS parser checks (`pureCases` or an offscreen qml6 selftest);
  - session cases with the fake provider and editor (content type carried by `load`, kept across `replacePath`, no-op saves);
  - real-key EditorKeys scenarios (checking event k checks all above it, the add-event form, undo, read-only);
  - local provider selftest cases (type persisted and preserved, unknown types open read-only with a reason);
  - converter CASES if the format is Markdown.
- Register each new suite in both `tests/selftest.py` and CTest.
- Keep the contract change additive (the `canReorder` → `reorder` precedent). Update `docs/providers.md`, the skill reference, `examples/hello`, the README, `docs/technical-requirements.md`, `docs/decisions.md` and `docs/testing.md` in the same commit. Then bump `manifest.json` and the metainfo together.
