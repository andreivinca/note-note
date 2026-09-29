# Providers

A provider is a QML `Item` that supplies one or more sidebar tabs
("sections") and the notes in them: it lists them, loads one, saves it,
creates and deletes them, and runs its own setup screen. The app owns the
window, the list and the editor; the provider owns its backend — its
credentials, caches, limits and quirks. The host never sees a provider's
settings or secrets.

**The user's notes are the product.** A provider must never lose, duplicate
or corrupt them. When unsure whether a write is safe, open the note
read-only with a reason instead.

## Manifest entry

```json
"providers": [{ "id": "nextcloud", "path": "Provider.qml", "order": 500 }]
```

- `id` is a local ID and **must equal the QML `id` property** of the provider.
  It prefixes every note path and names the provider's config entry, so never
  change it once people use it. `local`, `sticky`, `onenote` and `notion` are
  taken; two external packages claiming one ID are both refused.
- `order` (0–9999, default 1000) places its tabs among the others; lower is
  earlier. The built-ins use 10–40.
- A provider package is executable: it loads only once the user enables the
  package. After that, `providers.<id>.enabled` in `config.json` turns the
  provider itself off and on (on by default).

Package layout:

```
~/.config/notenote/plugins/io.github.someone.nextcloud/
├── plugin.json
├── Provider.qml
├── logo.svg           optional tab mark
└── backend.py         optional script(s) the provider runs
```

## Minimal provider

Notes kept in the provider's own state, with a setup screen. Copy it, then
replace the model with the real backend.

```qml
import QtQuick
import QtQuick.Controls

Item {
  id: root

  readonly property string id: "hello"
  readonly property string name: "Hello"
  // readonly property url logo: Qt.resolvedUrl("logo.svg")
  readonly property bool markdown: true
  readonly property bool hasTitle: true
  readonly property bool canCreate: true
  readonly property bool canDelete: true
  readonly property bool canReorder: false
  readonly property bool canCreateSection: false
  readonly property var microsoftScopes: []
  readonly property string microsoftClientId: ""

  property var host: null
  property var services: null
  readonly property var style: services ? services.style : null
  readonly property var colors: services ? services.colors : null

  signal updated()
  signal statusRequested(string text)
  signal noticeRequested(string title, string text, string code, var actions)
  signal noticeCleared()
  signal viewRequested(string title, var component, var props)
  signal viewCleared()
  signal persistRequested()

  property string owner: ""
  property var notes: []          // [{ id, title, body }]
  property int nextId: 1
  readonly property bool configured: owner.length > 0
  property var sections: []

  function restoreState(obj) {
    if (obj) {
      root.owner = obj.owner || ""
      root.notes = obj.notes || []
      root.nextId = obj.nextId || 1
    }
  }
  function saveState() {
    return { owner: root.owner, notes: root.notes, nextId: root.nextId }
  }

  function rebuild() {
    var rows = []
    var footerActions = []
    if (!root.configured) {
      rows.push({ kind: "action", path: "setup", title: "Set up…", icon: "󰒓" })
    } else {
      for (var i = 0; i < root.notes.length; i++) {
        var note = root.notes[i]
        rows.push({ kind: "note", path: root.id + ":" + note.id, title: note.title, preview: note.body.split("\n")[0] })
      }
      footerActions.push({ path: "newNote", title: "New Note", icon: "󰐕", shortcut: "newNote" })
      footerActions.push({ path: "settings", title: "Settings…", icon: "󰒓" })
    }
    root.sections = [{ key: "hello", name: "Hello", rows: rows, footerActions: footerActions }]
    root.updated()
  }
  function refresh() {
    rebuild()
  }

  function noteAt(path) {
    var id = Number(path.substring(root.id.length + 1))
    return root.notes.find(function(note) {
      return note.id === id
    }) || null
  }
  function crumb(path) {
    return "Hello"
  }
  function createTargetFor(path) {
    return root.configured ? "new" : ""
  }
  function toggleTree(id) {
  }
  function setOrder(sectionKey, paths) {
  }

  function load(path, cb) {
    var note = noteAt(path)
    cb(note ? { title: note.title, body: note.body, editable: true } : { error: "This note no longer exists." })
  }
  function save(path, title, body, cb) {
    var note = noteAt(path)
    if (!note) {
      cb({ error: "This note no longer exists." })
      return
    }
    note.title = title
    note.body = body
    rebuild()
    root.persistRequested()
    cb({})
  }
  function create(target, cb) {
    var note = { id: root.nextId++, title: "", body: "" }
    root.notes = root.notes.concat([note])
    rebuild()
    root.persistRequested()
    cb({ path: root.id + ":" + note.id })
  }
  function remove(path, cb) {
    var note = noteAt(path)
    root.notes = root.notes.filter(function(candidate) {
      return candidate !== note
    })
    rebuild()
    root.persistRequested()
    cb({})
  }

  function action(id, value, sectionKey) {
    if (id === "newNote" && root.configured) {
      root.host.newNote(root.id, "new")
    } else if (id === "setup" || id === "settings") {
      root.viewRequested(root.configured ? "Hello — settings" : "Set up Hello", setupView, { current: root.owner })
    }
  }

  Component {
    id: setupView
    FocusScope {
      property string current: ""
      width: parent ? parent.width : root.style.space(600)
      height: column.implicitHeight

      Column {
        id: column
        spacing: root.style.spacing.md
        leftPadding: root.style.spacing.md
        topPadding: root.style.spacing.md

        TextField {
          id: nameField
          width: root.style.space(320)
          text: current
          placeholderText: "Your name"
          color: root.colors.menu.text
          selectionColor: root.colors.accent
          font.family: root.style.font.menuFamily
          focus: true
          Keys.onReturnPressed: saveButton.clicked()
        }
        Row {
          spacing: root.style.spacing.sm
          Button {
            id: saveButton
            text: "Save"
            palette.buttonText: root.colors.menu.text
            palette.highlight: root.colors.accent
            onClicked: {
              var value = nameField.text.trim()
              if (!value) {
                root.statusRequested("Hello: a name is required")
                return
              }
              root.owner = value
              root.persistRequested()
              root.viewCleared()
              root.rebuild()
            }
          }
          Button {
            text: "Cancel"
            palette.buttonText: root.colors.menu.text
            palette.highlight: root.colors.accent
            onClicked: root.viewCleared()
          }
        }
      }
    }
  }
}
```

## Properties the host reads

| Property | Type | Meaning |
|---|---|---|
| `id` | string | the manifest ID; every note path starts with `id + ":"` |
| `name` | string | display name; heads its tabs and starts its status messages |
| `logo` | url | optional mark for its tabs, `Qt.resolvedUrl("logo.svg")`; must read on light and dark themes |
| `markdown` | bool | bodies are Markdown; false = plain text |
| `hasTitle` | bool | notes have a separate editable title |
| `canCreate` / `canDelete` | bool | `create()` / `remove()` work |
| `canReorder` | bool | rows can be dragged within a section; `setOrder()` persists it |
| `canCreateSection` | bool | `createSection()` works; the provider offers the action in `footerActions` |
| `canImages` | bool | pasted pictures can be stored (default false). The editor writes `![](file:///…)` into the body and `save()` must carry it to the backend, keeping any `{width=N}` marker |
| `tools` | list | formatting capabilities the backend can store: any of `bold italic underline strikeout highlight textColor code h1 h2 h3 p ul ol todo indent outdent quote codeblock rule link table` (`table` also covers the calendar tools), or another capability a package's tool names. Omitted = all (when `markdown`); `[]` = no toolbar. Never offer a construct the backend would flatten |
| `microsoftScopes`, `microsoftClientId` | list, string | only for a Microsoft Graph backend (see below); otherwise `[]` and `""` |
| `sections` | list | the tabs, below |
| `footerActions` | list | optional buttons shown before any tab exists (such as creating the first notebook) |
| `settings`, `liveSettings` | list | settings from the app's config, below |
| `busy`, `writeBusy` | bool | optional: work in progress outside the host's queue; `writeBusy` for accepted writes, which the app waits for before closing |

## Sections and rows

```js
root.sections = [{
  key: "work",                      // the provider's own key for the tab
  name: "Work",                     // tab label
  color: "#a9dcc0",                 // optional
  count: 12,                        // optional, overrides the note count
  rows: [ /* rows, below */ ],
  notes: [ /* optional: every note, for search, when rows hide some (folded trees) */ ],
  footerActions: [
    { path: "add", title: "New Note", icon: "󰐕", shortcut: "newNote" },
    { path: "notebook", title: "New notebook", icon: "󰉗", inputPlaceholder: "Notebook name", shortcut: "newNotebook" }
  ]
}]
root.updated()
```

A row is `{ kind, path, title, preview, icon, level, expanded, version, modified }`:

- `kind: "note"` — `path` is the note's `<id>:<anything>` path.
- `kind: "new"` — `path` is a create target handed to `create()`.
- `kind: "action"` — `path` is an action ID handed to `action()`.
- `kind: "tree"` — a foldable group; `path` is the tree ID for `toggleTree()`.
- `version` — an opaque change marker (mtime, etag). When a listing shows a
  newer version of the open, unedited note, the host reloads it.
- `modified` — ISO 8601 with a timezone, or epoch milliseconds, for the dates shown.

Footer actions are buttons pinned under the list: a click calls
`action(path, value, sectionKey)`; with `inputPlaceholder` the row first
collects a line of text, passed as `value`. `shortcut` ties Ctrl+N
(`newNote`) or Ctrl+Shift+N (`newNotebook`) to the button. Creation handlers
call `host.newNote(id, target)` or `host.newNotebook(value, id)` to use the
app's own create-and-open flow.

## Functions

Required:

| Function | Contract |
|---|---|
| `refresh()` | (re)load the listing; set `sections` and emit `updated()` |
| `load(path, cb)` | `cb({ title, body, editable, reason?, version?, base? })` or `cb({ error })` |
| `save(path, title, body, cb, options)` | `cb({})`, `cb({ warning })` or `cb({ error })` |
| `create(target, cb)` | `cb({ path })` or `cb({ error })` |
| `remove(path, cb)` | `cb({})` or `cb({ error })` |
| `action(id, value, sectionKey)` | a row or footer button was clicked |
| `crumb(path)` | the line of context shown above the note |
| `createTargetFor(path)` | where Ctrl+N creates while `path` is open, or `""` |
| `toggleTree(id)`, `setOrder(sectionKey, paths)` | fold a tree; persist a drag order (empty bodies when unsupported) |
| `restoreState(obj)`, `saveState()` | the provider's small persistent state, kept by the host; emit `persistRequested()` when it changes |

Optional: `createSection(name, cb)` → `cb({ key, target?, error? })`;
`search(query, cb)` → `cb({ paths })` of notes whose **body** matches (titles
are matched by the host); `revealPath(path)` to unfold a note's row;
`storageLabel(path)`; `defaultNote(sectionKey)`; `noteOpened(path)`;
`noteEdited(path)` with signal `saveRequested(path)` to choose the save
schedule (without them the host saves 1.5 s after typing stops);
`watch(on)` when the window shows/hides; `poll(currentPath)` every 20 s while
visible, for a cheap change check; `searchStatus(sectionKey)` and signal
`searchChanged()` for content-search coverage.

The callback contracts are what keep notes safe:

- **Answer every `load`, `save`, `create`, `remove` and `search` exactly once**,
  errors included. A save never answered looks unsaved forever.
- A `load` may return a handle with `cancel()`; a cancelled load is still answered.
- A save superseded by a newer save of the same note answers `{}`. A save that
  was never sent (sign-out, provider turned off) answers `{ error }`.
- Change the provider's own model only **after** the backend confirms a
  write. The host keeps the draft meanwhile.
- A note too large or too complex to write back safely loads with
  `editable: false` and a `reason` in the user's words — never as an editable
  partial note.

## Signals

`updated()` — sections changed. `statusRequested(text)` — a transient
message. `noticeRequested(title, text, code, actions)` / `noticeCleared()` —
a full-pane message with buttons `[{ label, icon, action }]`.
`viewRequested(title, component, props)` / `viewCleared()` — show the
provider's own QML component in the note pane (setup and settings screens;
put `focus: true` on the field that should take the keyboard).
`persistRequested()` — save `saveState()`. `saveRequested(path)` — write the
open note now. `noteChanged(path)` — the open note changed on the backend.

## Settings from the app's config

The app keeps one entry per provider in `config.json` under
`providers.<id>`. Declare the keys the provider reads, as properties whose
initial values are the defaults:

```qml
property var settings: ["serverUrl", "notebookTabs"]
property var liveSettings: ["notebookTabs"]
property string serverUrl: ""
property bool notebookTabs: true
```

The host writes missing defaults into the entry, then assigns the entry's
values after creating the provider. A change to a setting recreates the
provider, except for `liveSettings`, which are assigned in place followed by
`rebuild()`. `notebookTabs` is the conventional name for "one tab per
notebook vs. one tab with a tree". Keep secrets out of `config.json`: store
them under the provider's state directory (below).

## Services

The host injects `services`:

| Service | Use |
|---|---|
| `services.platform` | `stateDir`, `cacheDir`, `configDir`; `localPath(url)`, `fileUrl(path)`, `openUrl(url)`, `copyText(text)`, `env(name)`; `environment` |
| `services.style`, `services.colors` | sizes and colors for the provider's own views: `style.spacing.sm/md/lg`, `style.font.body`, `style.font.menuFamily`, `style.space(n)`, `colors.menu.text`, `colors.accent`, `colors.token("<theme token>")` |
| `services.processes.create(owner)` | a process runner owned by `owner` |
| `services.requests` | request lanes that pace and order backend calls |
| `services.microsoft` | Microsoft Graph sign-in, for OneNote/Outlook-style backends |

Provider data belongs in
`services.platform.stateDir + "/plugins/<package-id>"`, disposable data in
`cacheDir + "/plugins/<package-id>"`. Never write into the package folder.

### Running a script

Backends are usually reached through a small script shipped in the package:
one JSON request on stdin, one JSON object on stdout.

```qml
property var runner: null
Component.onCompleted: {
  root.runner = services.processes.create(root)
}

function call(operation, request, cb) {
  var script = services.platform.localPath(Qt.resolvedUrl("backend.py"))
  return root.runner.run({
    command: ["python3", script, operation],
    payload: JSON.stringify(request),
    timeoutMs: 30000,
    maxOutputBytes: 4 * 1024 * 1024
  }, cb)
}
```

`run()` answers exactly once — the parsed object, or `{ error }` on failure,
timeout, oversized or invalid output — and returns a `{ cancel() }` handle.
`raw: true` answers `{ text }` instead of parsing. Pass note bodies and
secrets in `payload` (stdin), never as arguments. The runner gives the script
`NOTE_NOTE_STATE_DIR` and `NOTE_NOTE_CACHE_DIR` in its environment.

### Request lanes

Anything that talks to a network service goes through a lane, which orders
jobs, coalesces redundant ones and backs off when the service throttles:

```qml
property var rq: null
Component.onCompleted: {
  root.runner = services.processes.create(root)
  root.rq = services.requests.queueFor("nextcloud", root)
}
Component.onDestruction: {
  services.requests.cancelOwner(root)
}

function save(path, title, body, cb) {
  rq.enqueue({ key: path, mode: "replace", priority: 0, owner: root, flush: true, label: "save" },
    function(ctx) {
      call("save", { path: path, title: title, body: body }, function(result) {
        ctx.done(result)
      })
    },
    function(result, info) {
      if (info.superseded) {
        cb({})
      } else if (!result) {
        cb({ error: "The save was not sent." })
      } else {
        cb(result.error ? { error: result.error } : {})
      }
    })
}
```

- `key`: jobs sharing a key run in order. `mode`: `append` (default),
  `replace` (a newer job supersedes a queued one — saves), `dedupe` (join a
  queued one — listings). `priority`: `0` interactive, `1` background.
  `flush: true` marks a write, which keeps running while the window is hidden.
- `ctx.done(result)` once per job. A result with `kind: "throttled"`
  (and optional `retryAfter` seconds) parks the whole lane and retries;
  `kind: "transient"` retries this job a few times; anything else is delivered.
- `settled(result, info)` runs once for every enqueue; `result` is `null`
  when the job never ran (`info.superseded` or `info.cancelled`).
- Pick a lane key of your own; never reuse `graph-onenote`, `graph-mail` or `notion`.

### Microsoft Graph

A provider on a Microsoft backend brings its own Entra app registration
(`microsoftClientId`, a public client allowing personal and work accounts)
and the scopes it needs (`microsoftScopes`), and creates its own account with
`services.microsoft.create(root.id, root.microsoftScopes, root.microsoftClientId)`.
The account has `signedIn`, `login()`, `logout()`, `env` (pass it to the
scripts' environment) and the signals `updated()`, `signedOut()`,
`statusFailed(error)`; the host shows the device-code sign-in. Clear caches
and queued work on `signedOut()`.

## Scripts: bounds and safety

Provider code runs unsandboxed with the user's privileges and parses what
arrives from disk and network. Every rule below prevents a real class of bug:

- **Bound every read when it happens**: read `cap + 1` bytes once and refuse
  anything over the cap. A size check before a separate open is not a bound.
  Bound counts too — notes, sections, pages, images.
- **Open local files without following links**, check the type on the
  descriptor, and read against a deadline:

  ```python
  import os
  import stat
  import time


  def read_capped(path, cap, seconds=5):
      fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
      try:
          if not stat.S_ISREG(os.fstat(fd).st_mode):
              raise ValueError("not a regular file")
          deadline = time.monotonic() + seconds
          chunks = []
          size = 0
          while size <= cap:
              if time.monotonic() > deadline:
                  raise TimeoutError("read timed out")
              chunk = os.read(fd, min(65536, cap + 1 - size))
              if not chunk:
                  break
              chunks.append(chunk)
              size += len(chunk)
          if size > cap:
              raise ValueError("file exceeds the size limit")
          return b"".join(chunks)
      finally:
          os.close(fd)
  ```

- **Write atomically and privately**: a fresh temp file from
  `tempfile.mkstemp(dir=<target dir>)`, written, `fsync`ed, then `os.replace()`
  onto the target. Never `open(path + ".tmp", "w")`. Directories `0700`,
  files `0600`.
- **HTTP**: `response.read(cap + 1)` against a wall-clock deadline across the
  whole transfer, not just a socket timeout; don't follow redirects that
  would carry a token.
- **Processes**: argv lists only — no `shell=True`, no string interpolation
  into a shell script; `--` before paths. Anything that decodes untrusted data
  (images) gets memory and time limits.
- **Secrets and note bodies** travel over stdin, never through argv, `/tmp`
  or a shared directory.
- **Caches** are pruned by count and total size, and scoped to the signed-in
  account.
- **Errors**: print `{"error": "message"}` rather than a traceback; a script
  that dies mid-write must not leave a half-written note.

## Portability

Import only `QtQuick` and `QtQuick.Controls` for the setup views, and use the
injected services for paths, processes and colors; then the provider works in
both the Omarchy shell and the standalone app. Importing `Quickshell` or
`qs.*` makes it Omarchy-only. Don't hardcode `~/.cache/omarchy` or other host
paths — read them from `services.platform`.

## Before handing it over

- The manifest `id` equals the QML `id`, and `scripts/check.py --enable <package>`
  reports no error.
- Every callback path answers exactly once, errors included.
- A failed or partial read never becomes an editable note; a failed save
  never looks saved.
- Reads are capped; writes are atomic; secrets go over stdin.
- The user knows the package runs with their privileges and must be enabled
  in `config.json` (`"plugins": {"<package-id>": {"enabled": true}}`), then
  the app restarted.
