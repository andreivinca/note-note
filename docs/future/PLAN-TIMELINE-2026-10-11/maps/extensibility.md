# Extensibility map — the plugin system as the contribution point for note types

Repository `/home/andrei/Projects/note-note`, HEAD `e2cdc4e` (master). Every citation is `file:line` at HEAD.
Nothing in the repository was changed.

## Summary

Every package is one folder with a `plugin.json`. Built-in packages live in `plugins/`, user packages in
`$XDG_CONFIG_HOME/notenote/plugins/`. One Python helper (`services/extensions/manifest.py`) discovers them all.
`PluginCatalog.qml` runs that helper once, with no QML executed, after settings load. It publishes one descriptor
array per kind: `commands`, `keybindings`, `themes`, `providers`, `tools`.

- **Validation is strict.** `schemaVersion` and `apiVersion` must be exactly 1. Any key under `contributes` that is
  not a known kind rejects the whole package. Package IDs are reverse-DNS, and `org.note-note.*` is reserved for
  built-ins.
- **Resources are bounded.** They are relative regular files read through no-follow directory descriptors, with
  byte and count caps.
- **Trust is a settings switch.** Data-only packages (themes) load by default. Any package with commands, tools or
  providers is "executable". User packages of that kind start disabled until `plugins.<id>.enabled` is set to true.
  Built-ins are enabled by default and can be disabled, except the protected `org.note-note.appearance`. Every
  package change needs a restart. There is no hot unload.
- **QML runs as trusted code, with no sandbox.**
  - Providers are created with `Qt.createComponent` by `Workspace.addProvider`. Each gets `host` and `services`.
  - Tools are created eagerly, once per editor, by `ToolRegistry`, with `PreferSynchronous`. Each gets an `editor`
    (`EditorApi`).
  - Commands are created lazily, once per invocation, by `CommandRegistry`, with `Asynchronous`. Each gets a
    `context` API object.
- **The public `NoteNote.Extensions 1.0` module** (`Command`, `Tool`) is an import root that each host registers.
  - The standalone host always registers it.
  - In Omarchy it exists only when the optional native module is built. So built-in packages that must always work
    (the calendar tools, the providers) use repository-relative imports instead.
- **The extension API has only an exact-match version number.** `apiVersion` 1 in the manifest and `apiVersion: 1`
  on each QML object. A new kind was added before (tools, the "fifth kind", commit `2c5920f`) without bumping it.
  That commit is the template for a sixth kind. It touched `manifest.py` and its selftest, `PluginCatalog.qml`, a
  contract QML plus a public wrapper and a `qmldir` line, a registry, one wiring line each in `Workspace.qml` and
  `NoteEditor.qml`, the docs, the plugin-author skill and its `check.py`, an example package and tests.
- **Built-in contributions are mostly packages:** calendar (tools), appearance (themes and a command), workspace
  (data-only commands), and the four providers. The app's core formatting tools are the exception: they live in
  `ui/tools/` outside any package and cannot be disabled. A built-in timeline type could ship as
  `plugins/org.note-note.timeline/`, which dogfoods the contribution point the way calendar does for tools. Then a
  user can disable it.
- **Absent contributions are left dormant, never rewritten:** layouts keep naming missing tools, bindings stay
  dormant, a missing theme falls back to System without changing settings. Together with "open read-only rather
  than risk a bad write", these precedents set the rule for notes whose type package is disabled or removed.
- **Note content is hostile input.** A type's codec must bound what it parses and refuse (read-only) rather than
  truncate.
- **No per-note content type exists anywhere today.** The editor's only switch is `plain = !provider.markdown`
  (`Workspace.qml:2837-2840`), and tools, word count and keyboard context all assume the TextEdit document.

## 1. How a package contributes today

### Manifest and validation (`services/extensions/manifest.py`)

| Claim | Where |
|---|---|
| Kinds are a closed list: `KINDS = ("commands", "themes", "providers", "tools", "keybindings")` | `services/extensions/manifest.py:30` |
| `schemaVersion` and `apiVersion` must both be the integer 1 exactly; otherwise "unsupported plugin schemaVersion/apiVersion" | `services/extensions/manifest.py:133-137` |
| Package ID regex `[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+`; local ID `[a-z][a-z0-9-]*`; action ID (tools) `[a-z][a-zA-Z0-9]{0,63}`; version `major.minor.patch` | `services/extensions/manifest.py:24-27` |
| Non-built-ins may not use `org.note-note.*` or `user.themes` ("reserved package namespace") | `services/extensions/manifest.py:139-140`, `:28-29` |
| `contributes` must be a non-empty dict whose keys are a subset of `KINDS`; an unknown kind rejects the whole package ("unsupported or missing contributions") | `services/extensions/manifest.py:142-144`; test `services/extensions/selftest.py:162` (`widgets=[]` rejected) |
| Unknown fields inside a contribution entry and unknown top-level manifest keys are ignored (builders read only named keys) | `services/extensions/manifest.py:62-95`, `:133-152` |
| Every contribution descriptor carries `id` (`<package-id>/<local-id>`), `localId`, `packageId`, `packageName`, `root`, `builtin`, plus `path` and a `file://` `url` when it names a file | `services/extensions/manifest.py:52-59` |
| Commands: `handler` XOR `workspaceAction`; `title`, `category`, `keywords` (≤32×64), `requires` (≤16×64) | `services/extensions/manifest.py:62-72` |
| Themes: only `path` (JSON, data) | `services/extensions/manifest.py:75-76` |
| Providers keep an unqualified id ("the identity its notes, settings and state are filed under") and an `order` 0..9999, default 1000 | `services/extensions/manifest.py:79-87`, `:31-34` |
| Tools keep an unqualified action ID, which must equal the QML `toolId` | `services/extensions/manifest.py:90-95` |
| Adding a kind means editing `BUILDERS` and, for a special ID grammar, `IDENTIFIERS` | `services/extensions/manifest.py:98-101` |
| At most 128 entries per kind; entries must be objects; duplicate local IDs within a kind are rejected | `services/extensions/manifest.py:104-122` |
| Keybindings may only name a command of the same package; they are qualified `<pkg>/<cmd>` | `services/extensions/manifest.py:125-130` |
| `executable = bool(commands or providers or tools)`; a new code-bearing kind must be added here | `services/extensions/manifest.py:151` |

### Discovery, limits and diagnostics

| Claim | Where |
|---|---|
| Built-in root is scanned before the user root, so user packages cannot use up the app's share of a limit; each immediate subdirectory's `plugin.json` is read with a 64 KiB cap and an 8 MiB total input cap | `services/extensions/manifest.py:183-200`, `:18-23` |
| At most 128 entries per scanned directory ("directory exceeds the entry limit") | `services/extensions/manifest.py:162-180` |
| Enable policy: `PROTECTED` (appearance) is always on; otherwise `settings[id].enabled`, defaulting to `builtin or not executable` | `services/extensions/manifest.py:203-206` |
| Duplicate package IDs reject every claimant; a disabled package produces a `level: "note"` diagnostic, not an error | `services/extensions/manifest.py:209-223` |
| A package's contributions are admitted all or none, against a 4,096-contribution total cap | `services/extensions/manifest.py:226-233` |
| Loose themes (`configDir/themes/*.json`) and legacy providers (old directories, symlinked roots allowed) are adapters beside packages | `services/extensions/manifest.py:236-265` |
| Provider ID conflicts are settled at discovery: a built-in keeps its ID; among others nobody wins; tabs sorted by `order` | `services/extensions/manifest.py:268-283` |
| The helper answers one JSON request on stdin; a `resource` operation reads one package-relative file (optionally as strict JSON) | `services/extensions/manifest.py:286-306` |
| `PluginCatalog` runs `python3 manifest.py` with a 15 s timeout and 8 MiB output cap, passing `builtinRoot` (app `plugins/`), `userRoot` (`configDir/plugins`), `themesRoot`, `legacyRoot` and `settings` | `services/extensions/PluginCatalog.qml:35-53` |
| One array property per kind (`commands`, `keybindings`, `themes`, `providers`, `tools`, `diagnostics`), assigned from the result | `services/extensions/PluginCatalog.qml:7-12`, `:40-46` |
| `problems` filters out `note`-level diagnostics; `problemSummary` is the one-line status text | `services/extensions/PluginCatalog.qml:13-25` |
| `readResource(descriptor, path, json, cb)`: a bounded package-relative read (10 s, 2 MiB) | `services/extensions/PluginCatalog.qml:55-58` |
| The catalog is loaded once per process, from `SettingsStore.onLoaded`; `initialize()` calls `settingsStore.load()` once | `Workspace.qml:2496-2510`, `:2365-2377`; `services/settings/SettingsStore.qml:43-51` |
| On `loaded`: problems go to the status line, then providers and the committed theme | `Workspace.qml:2474-2483` |
| Providers wait for the catalog, the config and the state (`maybeLoadProviders`) | `Workspace.qml:839-845` |

### Resource-safety helpers

| Claim | Where |
|---|---|
| `label()`: non-empty string, length cap, no NUL | `lib/packagefiles.py:18-21` |
| Resource paths must be relative, with no `/` prefix, `\`, `:` or `..` | `lib/packagefiles.py:24-29` |
| Each component is opened with `O_NOFOLLOW` through directory fds; the leaf must be a regular file | `lib/packagefiles.py:32-52` |
| Reads take cap+1 bytes (256 KiB), with a 5 s deadline and a changed-while-reading check | `lib/packagefiles.py:14-15`, `:61-70` |
| Strict JSON: duplicate keys rejected, non-finite numbers rejected, nesting limited to 32 | `lib/jsondata.py:9-38` |
| Helper scripts answer `{error}` instead of a traceback | `lib/jsondata.py:48-65` |

### Settings and enabling

| Claim | Where |
|---|---|
| `plugins` and `providers` are registries of `{enabled: bool}` objects; a wrong type is a settings problem | `services/settings/settings.js:37-66` |
| `plugins.<id>.enabled` is a restart-time package switch | `docs/plugins.md:60-69` |
| `providers.<id>.enabled` is the live provider activation, applied through drain, commit and retire in `ProviderLifecycle` | `services/providers/ProviderLifecycle.qml:64-100`; `Workspace.qml:847-850` |

### How QML is loaded (no sandbox)

| Claim | Where |
|---|---|
| **Providers:** `Qt.createComponent(url)` then `createObject(root, {host, services})`. A `Component.Error` is logged; an instance whose `id` differs from the manifest ID, or that is already loaded, is destroyed | `Workspace.qml:684-713` |
| The `services` object injected into providers holds `platform`, `style`, `colors`, `processes`, `microsoft` and `requests` | `Workspace.qml:124-146` |
| **Tools:** one instance per editor, `Qt.createComponent(url, Component.PreferSynchronous)` then `createObject(registry, {editor})`. Validated: `apiVersion === 1`, `toolId`, `label`, `options`, an `execute` function, and the manifest ID equal to `toolId` | `ui/editing/ToolRegistry.qml:111-136` |
| **Commands:** created lazily per invocation with `Component.Asynchronous`. Validated: `apiVersion === 1` and an `execute` function. Creation and synchronous errors are caught; handler and component are destroyed when the command finishes | `services/commands/CommandRegistry.qml:185-222`, `:80-98` |
| **Themes:** never QML. JSON is validated by `services/themes/theme.py` through `ThemeCatalog` | `services/themes/ThemeCatalog.qml:29-43` |
| Docs: "Enabling QML trusts it with the host process's privileges … not a code sandbox. There is no store, signing system, dependency resolver, or automatic updater." | `docs/plugins.md:72-75` |
| Docs: "QML's own loader is trusted executable code, outside these data-read rules." | `docs/plugins.md:105` |
| Code: "Extensions are trusted code; this is a boundary for maintainability, not a sandbox." | `services/commands/CommandApi.qml:3-6` |
| Docs: "infinite loops and process crashes cannot be isolated by this API" | `docs/commands.md:22-25` |
| The plugin runs unsandboxed inside the user's shell process | `docs/security.md:3-5` |
| The Omarchy shell shares one QML engine; the runtime only adds an import path | `cpp/extensionruntime.h:7-8`; `cpp/extensionruntime.cpp:6-14` |

### The public module and versioning

| Claim | Where |
|---|---|
| `NoteNote.Extensions` qmldir: `Command 1.0 Command.qml`, `Tool 1.0 Tool.qml` | `extensions/NoteNote/Extensions/qmldir:1-3` |
| The public `Tool` is a thin re-export of the app's own contract (`import "../../../ui/editing"`) | `extensions/NoteNote/Extensions/Tool.qml:1-7` |
| The public `Command` is a `QtObject` with `readonly property int apiVersion: 1` and a default `execute` that answers an error | `extensions/NoteNote/Extensions/Command.qml:1-10` |
| Omarchy host: `extensionsReady` is true only if the native module (`cpp/build/NoteNote/Native`) loads and `install()` adds `extensions/` to the import path | `hosts/omarchy/Backend.qml:15-19`; `hosts/omarchy/NativeExtensions.qml:1-3` |
| Standalone host: `extensionsReady: true`; `engine.addImportPath(dataDir + "/extensions")` | `hosts/standalone/Backend.qml:10`; `hosts/standalone/application.cpp:87` |
| Handler commands are refused while `extensionsAvailable` is false ("Build the native module …") | `services/commands/CommandRegistry.qml:55-58`; `Workspace.qml:2582` |
| Tools have no such gate: an external tool that fails to import is skipped with a diagnostic | `ui/editing/ToolRegistry.qml:113-118` |
| Decision: external tools import `NoteNote.Extensions`; "the calendar, like the built-in providers, uses relative imports, so it keeps working in Omarchy without the native helper" | `docs/decisions.md:1002-1005` |
| Commands and custom themes need the native helper in Omarchy | `docs/decisions.md:987-988`; `docs/themes.md:30-35` |
| The built-in theme command imports the public module | `plugins/org.note-note.appearance/commands/SelectTheme.qml:1` |
| Precedent: the tools kind was added without an `apiVersion` bump. The diff shows `KINDS` gaining `"tools"`, plus a builder, `IDENTIFIERS` and `executable` | commit `2c5920f`; `git show 2c5920f -- services/extensions/manifest.py` |
| Commands' `requires` fails closed on unknown names: "a command written for a later version stays unavailable" | `services/commands/CommandRegistry.qml:42-53`; `docs/commands.md:99-103` |
| The legacy provider adapter is scheduled for removal in 2.0 | `docs/plugins.md:122-124` |

## 2. Registries a note-type registry could mirror

### `ToolRegistry` (eager, per editor)

| Claim | Where |
|---|---|
| Inputs: a required `editor` and `keybindings`; `directory` is the app's own `ui/tools`; `contributions` are the catalog's descriptors, or null while the catalog is unread | `ui/editing/ToolRegistry.qml:8-16` |
| `ready`, `upToDate`, `errors` and `tools` are exposed through an internal `registryState` | `ui/editing/ToolRegistry.qml:17-22`, `:56-63` |
| Loads only when the `FolderListModel` has listed the current directory **and** contributions are non-null, through a 0 ms Timer | `ui/editing/ToolRegistry.qml:54`, `:65-93` |
| `sources()` lists the app directory first, then packages | `ui/editing/ToolRegistry.qml:99-109` |
| `claims()` and `definitionError()`: "The application's tools keep their IDs against a package's; among equals nobody wins." Bad shortcuts are refused too | `ui/editing/ToolRegistry.qml:138-170` |
| `loadTools()` discovers once per set of sources ("do not destroy tool instances underneath pending conversions"), destroys rejected tools, warns `Editing tool skipped: …`, then destroys the previous set | `ui/editing/ToolRegistry.qml:172-224` |
| Execution re-reads the context and checks `canExecute` (`upToDate`, writable, visible, capability) | `ui/editing/ToolRegistry.qml:264-280` |
| Panels close on note change, on losing writability and on capability change | `ui/editing/ToolRegistry.qml:302-317` |
| Wiring: `NoteEditor` creates `EditorApi` and `ToolRegistry` and aliases `toolContributions` | `ui/NoteEditor.qml:1799-1820` |
| Wiring: `Workspace` passes `pluginCatalog.ready ? pluginCatalog.tools : null` | `Workspace.qml:2850` |
| Contract: a `QtObject` with `apiVersion: 1`, a required `editor`, `toolId`, `label`, `icon`, `capability`, `available`, `checked`, shortcut defaults, `options`, `isMenu`, `panel` (a Component), `panelOpen`, `panelContext`; `openPanel()`, `cancelPanel()`, `submitPanel(apply)`, `execute()` | `ui/editing/Tool.qml:1-68` |

### `CommandRegistry` (lazy, per invocation)

| Claim | Where |
|---|---|
| Inputs: `descriptors`, `api`, `workspaceActions`, `keybindings`, `picker`, `contextState` | `services/commands/CommandRegistry.qml:6-16` |
| `list()` reads metadata only: "Opening the palette reads metadata; it does not instantiate all handlers." | `services/commands/CommandRegistry.qml:66-74`; `docs/commands.md:3-6` |
| One active invocation; arguments are passed as bounded JSON (65,536 chars), "so a handler gets data and nothing live" | `services/commands/CommandRegistry.qml:140-147`, `:149-173` |
| `CommandApi.contextFor()` builds the per-invocation `workspace`, `ui`, `themes`, `settings`, `resources` and `cancellation`; callbacks are `guarded` | `services/commands/CommandApi.qml:17-41` |
| Package resources are read through `catalog.readResource` | `services/commands/CommandApi.qml:132-145` |
| `WorkspaceActions` holds a fixed handler table (`newNote`, `newNotebook`, `openSettings`, `toggleList`, `deleteNote`); `invoke(action)` takes no parameters | `services/commands/WorkspaceActions.qml:18-34`, `:91-98` |

### `PluginCatalog` and `ThemeCatalog` (data kinds)

| Claim | Where |
|---|---|
| `ThemeCatalog` sends descriptors plus a validation table from QML (`Resolve.validationTable()`) to a Python validator, and publishes `entries` by ID | `services/themes/ThemeCatalog.qml:17-43` |
| Picker metadata comes from the validated data, not from code | `services/themes/ThemeCatalog.qml:55-68` |

### Keybindings

| Claim | Where |
|---|---|
| Target kinds are `app/…`, `tool/<toolId>` (context `editor`) and commands (context `notes` unless narrowed) | `services/shortcuts/resolve.js:66-93` |
| Plugin and tool defaults rank below app defaults and user overrides | `services/shortcuts/resolve.js:179-209`; `docs/commands.md:166-171` |
| `KeybindingRegistry` compiles from defaults, commands, contributions, tools and overrides | `services/shortcuts/KeybindingRegistry.qml:6-13` |

### Other contributed-component precedents

| Claim | Where |
|---|---|
| A provider's `viewRequested(title, component, props)` is rendered by `NoteEditor`'s `customLoader` in the note's place (properties copied on load, focus via `Qt.callLater`) | `Workspace.qml:735-737`; `ui/NoteEditor.qml:168-188`, `:1918-1931` |
| Tool `panel` Components are rendered by app-owned Loaders in the toolbar | `ui/editing/ToolBar.qml:208-219`, `:253-298` |
| The status bar is app-owned; runtime additions come from "an app-owned Component" | `docs/status-bar.md:61-65` |
| The skill: status-bar controls "are not a plugin kind" | `skills/note-note-plugin/SKILL.md:32-33` |

## 3. Built-in contributions are packages

| Claim | Where |
|---|---|
| `org.note-note.calendar` is a tools-only package: `insertMonth`, `currentMonth`, `nextMonth`, `customMonth` | `plugins/org.note-note.calendar/plugin.json:1-27` |
| Its QML imports the app by relative path (`"../../ui/editing"`, `"../../design"`, `"../../ui"`) and uses a `.pragma library` JS helper | `plugins/org.note-note.calendar/InsertMonth.qml:1-8`; `plugins/org.note-note.calendar/InsertCustomMonth.qml:1-6`; `plugins/org.note-note.calendar/Calendar.js:1-2` |
| Docs: "Built-in packages … may import its source tree by relative path: the calendar tools use `ToolForm`, `ChromeTextField` and `ChromeDropdown`"; external packages build panels "from Qt Quick's own controls" | `docs/editing-tools.md:316-320` |
| `org.note-note.appearance` contributes themes plus a command, and is the one protected package | `plugins/org.note-note.appearance/plugin.json:1-44`; `services/extensions/manifest.py:28`, `:203-205` |
| `org.note-note.workspace` contributes five commands, each with a `workspaceAction` and no handler | `plugins/org.note-note.workspace/plugin.json:1-62`; `docs/commands.md:49-56` |
| The four providers are packages with an `order` (local 10, sticky 20, onenote 30, notion 40) | `plugins/org.note-note.local/plugin.json:8-14`; `plugins/org.note-note.sticky/plugin.json:8-14`; `plugins/org.note-note.onenote/plugin.json:8-14`; `plugins/org.note-note.notion/plugin.json:8-14` |
| The app's core tools (bold, heading, …) are **not** a package: `ui/tools/*.qml`, discovered by `FolderListModel` | `ui/editing/ToolRegistry.qml:10-11`; `docs/editing-tools.md:3-7` |
| Disabling the calendar: "removes the four tools on the next start; layouts keep naming them, without empty buttons, for when the package is enabled again" | `docs/editing-tools.md:233-236` |
| Decision: tools moved into `org.note-note.calendar` "without a settings migration"; the editor's registry, not discovery, settles tool ID ownership | `docs/decisions.md:991-1005` |
| A removed package leaves no registrations on restart; "a missing selected theme falls back to System without changing saved settings"; no hot unload | `docs/plugins.md:129-134` |
| The theme fallback in code: "unavailable; using System for this session" | `services/themes/ThemeService.qml:82-102` |
| Commands: "Bindings for absent/disabled plugins remain dormant, consuming no keys" | `docs/commands.md:161-164` |
| Install and packaging take `plugins/` and `extensions/` wholesale (QML, JS, PY, JSON, qmldir, SVG; `*selftest*` excluded; tracked files only), so a new built-in package needs no list change | `CMakeLists.txt:56-64`; `packaging/package.py:14-15`, `:26-37` |

## 4. Security and robustness rules for third-party QML and JS

| Claim | Where |
|---|---|
| Threat model: note content from any backend is hostile; the user, shell, OS and vendored mistune are trusted | `docs/security.md:327-338` |
| Rule 1: bound every input at read time, collections included (notes, blocks, …) | `docs/security.md:16-39` |
| Rule 7: anything that decodes untrusted data gets limits and a timeout | `docs/security.md:231-237` |
| Extension data: `manifest.py` validates without running QML; resource reads refuse symlinks and special files; "enabled executable QML remains trusted process code" | `docs/security.md:340-349` |
| Resource rules and limits: regular files only, no absolute paths, schemes, traversal or symlinks; caps of 128 entries, 64 KiB per manifest, 256 KiB per resource, 128 per kind, 4,096 total, 8 MiB catalog input, 32 JSON levels | `docs/plugins.md:99-105` |
| Mutable plugin data lives under `stateDir/plugins/<id>` or `cacheDir/plugins/<id>`; "notes and recovery drafts must never live in the package or a disposable cache" | `docs/plugins.md:110-113` |
| Skill code rules: portable code imports only `QtQuick`, `QtQuick.Controls`, `QtQml` and `NoteNote.Extensions 1.0`; no imports from the app tree; bound everything; secrets and bodies go over stdin; braces style | `skills/note-note-plugin/SKILL.md:149-163` |
| Tools receive `editor` and "must not reach through its implementation references to the host or TextEdit"; shared primitives belong in `EditorApi`, an action's content, rules and UI in its file | `docs/editing-tools.md:376-380`; `ui/editing/EditorApi.qml:6-11` |
| The command context excludes the workspace, provider instances and account objects; interfaces are added "when a real command needs them" | `docs/commands.md:45-47` |
| Loading at runtime: check `Component.Error` and log `errorString()`, or a broken external fails silently | `docs/engine-notes.md:51-53` |
| Design rule: no backend-specific branches in the host — "Every branch of the form `if (provider.id === "…")` is a design failure" | `docs/technical-requirements.md:85-91` |
| The provider contract is public: "change it additively, never silently" | `docs/technical-requirements.md:99-101` |
| Project rules: never lose, duplicate or corrupt notes; open read-only rather than risk a bad write; every input bounded and untrusted | `docs/README.md:38-45` |
| Decision: a note that cannot be written back faithfully opens read-only with a visible reason; decided by the round trip | `docs/decisions.md:660-697` |

## Where today's code assumes one TextEdit document and a per-provider format

| Claim | Where |
|---|---|
| The only content-type switch is `plain = !provider.markdown`, set on `NoteEditor` | `Workspace.qml:2837-2840` |
| `markdown` is a per-provider bool | `docs/providers.md:47` |
| Sticky Notes: `markdown: false` | `plugins/org.note-note.sticky/Provider.qml:14` |
| Local, OneNote, Notion and hello: `markdown: true` | `plugins/org.note-note.local/Provider.qml:20`; `plugins/org.note-note.onenote/Provider.qml:19`; `plugins/org.note-note.notion/Provider.qml:17`; `examples/hello/Provider.qml:14` |
| `EditorApi.writable` requires `!host.plain`, and the toolbar shows only while writable | `ui/editing/EditorApi.qml:13`; `ui/NoteEditor.qml:155`, `:1826-1833` |
| Shortcut context is `editor` only while the TextEdit has focus (`bodyFocused: area.activeFocus`) | `Workspace.qml:2168-2176`; `ui/NoteEditor.qml:72` |
| The view bar's word count comes from the TextEdit | `ui/NoteEditor.qml:1794-1797`; `Workspace.qml:2920`; `ui/ViewBar.qml:125-134` |
| Sidebar note rows draw no per-row icon (only action and tree rows do), though the row shape has `icon` | `ui/NoteList.qml:463-477`; `docs/providers.md:89` |
| Provider capability lists can already name capabilities that packages define ("any other capability a package's tool names") | `docs/providers.md:54`; `ui/editing/EditorApi.qml:63-65` |
| No `contentType` or `noteType` concept exists in the app (searched across QML, JS, PY and MD) | — |
| Local previews and search run in the provider's own Python (`notefile.preview`, `search.py` over `notefile.split(text)[1]`) | `plugins/org.note-note.local/notefile.py:79-86`; `plugins/org.note-note.local/search.py:31-54`; `plugins/org.note-note.local/list.py:148-153` |
| Local front matter keeps unknown lines verbatim (`extra`) | `plugins/org.note-note.local/notefile.py:10-15`, `:48-76` |
| Reusable form pieces: `ToolForm` (header, fields, hint and one Insert button) requires `required property Tool action` | `ui/editing/ToolForm.qml:11-20` |
| `ChromeTextField` and `ChromeDropdown` exist | `ui/ChromeTextField.qml:1-30` |
| `PromptDialog` is single-field | `design/controls/PromptDialog.qml:1-37` |
| There is no multi-line text area control in `design/controls/` | — |

## Integration points (for a sixth kind, note types)

| Where | What changes | Why |
|---|---|---|
| `services/extensions/manifest.py:30`, `:90-101`, `:151` | Add the kind to `KINDS` and `BUILDERS` (and to `IDENTIFIERS` if its ID grammar differs), and to `executable` | Unknown kinds reject the package; a type with QML is code the user must enable |
| `services/extensions/manifest.py:28`, `:203-206` | If the core types (plain, Markdown) become packages, `PROTECTED` must become a set | The fallback types must not be disableable, like the System theme |
| `services/extensions/manifest.py:268-283` vs `ui/editing/ToolRegistry.qml:138-170` | Decide where type ID conflicts are settled: discovery (providers) or registry (tools) | Only the registry sees app-core items that live outside packages |
| `services/extensions/PluginCatalog.qml:7-12`, `:40-46` | Add the property and the assignment for the new kind | The catalog publishes one array per kind |
| `extensions/NoteNote/Extensions/qmldir:1-3` | Add a public wrapper file and a qmldir line (like `Tool.qml`) | External packages import only the public module |
| `ui/editing/Tool.qml` (pattern) | Add a new contract QML: `apiVersion: 1`, a type ID, metadata, an editor Component, codec functions | Mirrors the existing per-object versioned contracts |
| `ui/editing/ToolRegistry.qml` (pattern) | Add a new registry: null contributions until the catalog is ready, `PreferSynchronous` creation, validation, built-in precedence, diagnostics, load once | Same robustness rules |
| `Workspace.qml:2474-2483`, `:839-845`, `:2850` | Pass `pluginCatalog.ready ? pluginCatalog.<kind> : null`; gate note opening or provider loading on type readiness | A typed note must not open before its type is known |
| `Workspace.qml:2824-2850`; `ui/NoteEditor.qml:28`, `:34`, `:1799-1820`, `:1918-1931` | Replace the provider-level `plain`/`enabledTools` with a per-note type; host the type editor Component in an app-owned Loader | Today the editor is the TextEdit only |
| `ui/editing/EditorApi.qml:13`; `ui/NoteEditor.qml:155` | Toolbar and tools must stand down for non-TextEdit types | Tools act on the TextEdit document |
| `Workspace.qml:2168-2176`; `ui/NoteEditor.qml:72` | The shortcut context for a focused type editor | Today only TextEdit focus counts as `editor` |
| `Workspace.qml:2920`; `ui/NoteEditor.qml:1794-1797` | Word count or another summary for non-text types | It is computed from the TextEdit |
| `ui/NoteList.qml:463-477` | Note rows could show the type icon | Note rows ignore `icon` today |
| `services/commands/WorkspaceActions.qml:18-34`, `:91-98`; `services/shortcuts/defaults.js:21` | Creating a note of a type has no parameterized action | `newNote` takes no type |
| `services/extensions/selftest.py:37-55`, `:162`, `:182-198` | New kind tests; update the built-in lists if a timeline package adds tools | Exact lists are asserted |
| `tests/extensions.qml:374-376`; `tests/extensions_selftest.py:26-33`; `tests/EditorKeys.qml:48-61`, `:1460-1495` | Counts, wiring and registry validation patterns | Catalog counts are asserted |
| `skills/note-note-plugin/SKILL.md:8-18`, `:69-91`; `skills/note-note-plugin/scripts/check.py:76-94` | Kinds table, validator summary, a new reference file, `check.py` output | Must change in the same commit (`docs/plugins.md:46-53`) |
| `docs/plugins.md:9-42`, `:55-75`; `README.md:38-58`; `docs/decisions.md:980-1005` | Document the kind, trust and a decision record | Docs and code in the same commit (`docs/release-process.md:36-37`) |
| `docs/technical-requirements.md:14`; `docs/providers.md:47`, `:54`, `:257-300` | The editor-format statement, `markdown` flag, capability list, and `load`/`save`/`create` shapes | All are per-provider and Markdown-only today |
| `examples/plugins/` | An example note-type package, as greeting is for tools | Authors copy examples |

## Constraints

| Rule | Source |
|---|---|
| Unknown `contributes` kinds reject the whole package; `apiVersion` must be 1 | `services/extensions/manifest.py:136`, `:142-144` |
| Executable packages from users start disabled; built-ins are enabled; only appearance is protected | `services/extensions/manifest.py:203-206`; `docs/plugins.md:55-69` |
| Package enable or disable needs a restart; no hot unload; do not remove resources under accepted writes | `docs/plugins.md:66-69`, `:129-134` |
| Built-ins keep their IDs against user packages; among others nobody wins | `services/extensions/manifest.py:268-283`; `ui/editing/ToolRegistry.qml:154-165`; `docs/plugins.md:79-87` |
| Built-in packages that must always work use relative imports, not `NoteNote.Extensions` (Omarchy without the native helper) | `docs/decisions.md:1002-1005` |
| No sandbox; enabled QML has full process privileges (the Omarchy shell's) | `docs/plugins.md:72-75`; `docs/security.md:3-5` |
| Bound every input; decoders get limits; note content is hostile | `docs/security.md:16-39`, `:231-237`, `:327-338` |
| Open read-only rather than write lossily; never lose a note | `docs/README.md:38-45`; `docs/decisions.md:660-697`; `docs/business-requirements.md:29-31` |
| Absent contributions stay dormant and their references are preserved; fall back without changing saved settings | `docs/editing-tools.md:233-236`; `docs/commands.md:161-164`; `docs/plugins.md:129-133` |
| No `if (id === "…")` branches in the host | `docs/technical-requirements.md:85-91` |
| Contract changes are additive and documented | `docs/technical-requirements.md:99-101`; `docs/release-process.md:36-37` |
| The skill references must change with the contracts, in the same commit | `docs/plugins.md:46-53` |
| Extensions get a narrow API object, never host internals | `docs/editing-tools.md:376-380`; `docs/commands.md:45-47` |
| Plugin mutable data lives in `stateDir`/`cacheDir`, never notes in caches | `docs/plugins.md:110-113` |
| Local files stay plain Markdown readable by any tool | `docs/business-requirements.md:32-34` |
| Non-goal on record: "No backlinks, graph view, tags, databases, templates or plugins-inside-the-plugin" | `docs/business-requirements.md:57-58` |
| Code style: braces on every control statement, with the body on its own lines | `CLAUDE.md`; `skills/note-note-plugin/SKILL.md:162-163` |

## Reusable pieces

| What | Where |
|---|---|
| The discovery, validation, enable and limit pipeline, plus the descriptor shape from `owned()` | `services/extensions/manifest.py` |
| One array property per kind; `readResource` for bounded package reads | `services/extensions/PluginCatalog.qml` |
| Bounded, no-follow package file access; strict JSON | `lib/packagefiles.py`; `lib/jsondata.py` |
| The registry pattern: catalog gating, validation, precedence, diagnostics, load once | `ui/editing/ToolRegistry.qml` |
| A versioned QML contract (`apiVersion: 1`) with metadata and a Component property | `ui/editing/Tool.qml` |
| Lazy, metadata-first listing and guarded API callbacks | `services/commands/CommandRegistry.qml`; `services/commands/CommandApi.qml` |
| The public module re-export pattern | `extensions/NoteNote/Extensions/Tool.qml`; `extensions/NoteNote/Extensions/qmldir` |
| An app-owned Loader for a contributed Component | `ui/NoteEditor.qml:1918-1931`; `ui/editing/ToolBar.qml:208-298` |
| The built-in package template with relative imports | `plugins/org.note-note.calendar/` |
| Example packages | `examples/plugins/greeting`; `examples/plugins/colors`; `examples/hello` |
| Fallback without rewriting settings | `services/themes/ThemeService.qml:82-102` |
| Form pieces (`ToolForm` needs generalizing) | `ui/editing/ToolForm.qml`; `ui/ChromeTextField.qml`; `ui/ChromeDropdown.qml` |
| Author tooling | `skills/note-note-plugin/scripts/check.py` |
| Test harness patterns | `services/extensions/selftest.py`; `tests/extensions_selftest.py`; `tests/EditorKeys.qml:1460-1495` |
| The template of files a new kind touches | commit `2c5920f` |

## Risks

1. **A broken or hostile type editor can take down the whole shell.** It runs in-process, in the Omarchy shell's
   shared engine, so an infinite loop or crash brings everything down.
2. **A built-in type package that imports `NoteNote.Extensions` stops working in Omarchy without the native helper.**
   Notes of that type would become unusable. Use relative imports.
3. **Built-in packages can be disabled.** Disabling the timeline package leaves timeline notes with an unloaded type.
   A non-type-aware editor must not save them, or the structure is lost.
4. **Unqualified type IDs persisted in notes can be taken over later.** A future built-in of the same ID wins, by the
   precedence rule. The user's existing notes would then be parsed, and possibly rewritten, by a different codec.
5. **Older app versions reject the whole package** when it declares an unknown kind, including its other kinds.
   There is no minimum-app-version field.
6. **Load ordering.** The catalog, then providers, then notes load asynchronously. A typed note could open before its
   type registry is ready unless gated.
7. **The codec parses hostile input.** Unbounded event counts or sizes break the bounding rules. Truncating would be
   lossy.
8. **Provider-side previews and search run in each provider's Python** and cannot call a QML or JS extractor from a
   type package. There is no precedent for cross-package Python imports.
9. **Toolbar, shortcuts, word count and the `plain` gates all assume the TextEdit document.** A type editor beside
   it needs explicit stand-down logic.
10. **`ToolForm` is hard-typed to `Tool`.** Reusing it for "Add new event" needs a generalization.
11. **Tests assert exact counts and lists.** They break if the timeline package also adds tools or commands.
12. **The skill and docs can drift.** They have drifted before.

## Open questions

1. Manifest key and descriptor fields: `noteTypes` vs `contentTypes`? Which fields live in the manifest (title, icon)
   and which in QML (editor, codec)?
2. Type ID: qualified `<package-id>/<local-id>`, like themes and commands, which are persisted in `config.json`? Or
   unqualified, like providers and tools? How does each provider persist it?
3. Are plain text and Markdown app-core types (a `ui/` folder like `ui/tools`) or a protected built-in package?
4. Is there one type registry per workspace (stateless codecs) or per editor (like tools)? Where is the editor
   component instantiated?
5. How do previews and search work for typed notes when the provider's Python computes them?
6. Must the "databases, templates, plugins-inside-the-plugin" non-goal be amended?
7. A note whose type is not loaded: read-only raw body, or editable as Markdown or plain with the type marker kept?
8. What API object does a type editor get (model, `edited()`, `readOnly`, style and colors, status)? Providers get
   `services.style`/`services.colors`; tools get `editor`.
9. Can type packages contribute tools or commands scoped to their type, and is the provider `tools` capability list
   the gate?
10. How is "New note of type X" invoked? `WorkspaceActions` and `create(target, cb)` carry no type.

## Recommendations

1. **Add note types as the catalog's sixth kind, following the tools precedent (commit `2c5920f`).**
   - Extend `KINDS`, `BUILDERS` and `executable` in `manifest.py`.
   - Add a property in `PluginCatalog`.
   - Add an app-owned contract QML with `apiVersion: 1`, re-exported from `NoteNote.Extensions` through a qmldir line.
   - Add a registry modelled on `ToolRegistry`: null until the catalog is ready, `PreferSynchronous` creation, ID
     equal to the manifest's, built-ins win, diagnostics in an `errors` list and the log, load once.
   - Keep `apiVersion` 1, as the tools kind did.
2. **Put display metadata (title, icon glyph) in the manifest.** Pickers and the list can then name types without
   instantiating code, as commands do. Keep the editor Component and the codec in the type's QML.
3. **Ship the timeline as `plugins/org.note-note.timeline/` with relative imports**, as the calendar does, so it
   works in Omarchy without the native helper. Keep plain text and Markdown always available (app-core, or a
   protected package), as the fallback, like System for themes.
4. **A note whose type is not loaded opens read-only with a visible reason, showing its raw body.** It is never
   re-serialized by another type, and its type marker is preserved. This follows the theme, toolbar and binding
   precedents and "read-only rather than lossy".
5. **Prefer qualified type IDs for package-contributed types.** Built-ins then cannot later capture a user type's
   notes. Decide whether the core types get short reserved names.
6. **Make the codec bounded and fail-closed.** Cap the number of events and the size of each title and description,
   and treat an unparseable body as read-only with a reason.
7. **Update everything in the same commit:** `docs/plugins.md`, the skill (`SKILL.md`, a new reference, `check.py`),
   `README.md` "Writing plugins", a decision record, an example package, and tests (`manifest` selftest, extensions
   harness, a registry validation test).
