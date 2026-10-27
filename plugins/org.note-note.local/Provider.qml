import "../../services/platform"
import QtQuick
import "../../services/processes"
import "../../services/requests"
import "../../services/notes/ordering.js" as Ordering

// Local notebooks: folders under ~/Notes (or $NOTE_NOTE_DIR) holding Markdown
// files with a tiny title front-matter, and the folders inside them their
// sections, to any depth. Notes directly in the root show up as a "Notes"
// notebook. Each folder keeps its order in .order; the notebook order lives
// in .notebooks. A binder tab per notebook, or one "Notes" tab of fold-out
// trees — the host's notebookTabs setting decides (true here by default).
Item {
  id: root

  readonly property string id: "local"
  // The header titles whichever provider's tab is open; the local notebooks
  // are the app's own, so they go by the app's name.
  readonly property string name: "Note Note"
  readonly property bool markdown: true
  readonly property bool hasTitle: true
  // A pasted picture is copied into `.assets/` beside the note on save
  // (images.py) and the note keeps a relative link, resolved through the
  // `base` this provider returns from load().
  readonly property bool canImages: true
  readonly property bool canCreate: true
  readonly property bool canDelete: true
  readonly property bool canReorder: false
  readonly property bool canCreateSection: true
  readonly property var microsoftScopes: []

  // A write here is a file on this disk rather than a request, so the note
  // can follow the typing closely: the pause is only long enough that a word
  // being typed is one write and not five (noteEdited / saveRequested,
  // PROVIDERS.md).
  signal saveRequested(string path)
  function noteEdited(path) { saveSchedule.path = path; saveSchedule.restart() }
  Timer {
    id: saveSchedule
    property string path: ""
    interval: 500
    onTriggered: root.saveRequested(saveSchedule.path)
  }

  property var host: null
  property var services: null

  // This provider's settings (PROVIDERS.md): the host records their initial
  // values as the defaults its config file shows, and assigns whatever the
  // entry in config.providers.local holds right after creating this provider.
  readonly property var settings: ["notebookTabs", "notesDir"]
  // The tab shape is a presentation the instance changes in place; the
  // directory is what it reads, and a new one means a new instance.
  readonly property var liveSettings: ["notebookTabs"]
  // notebookTabs: one binder tab per notebook folder — this provider's
  // historic shape — or, false, a single "Notes" tab holding the folders as
  // fold-out trees, the same shape the remote providers use.
  property bool notebookTabs: true
  property string notesDir: Platform.env("NOTE_NOTE_DIR") || (Platform.env("HOME") + "/Notes")
  // notesDir as everything below reads it: "~" expands here, not in the
  // host — the path is this provider's to interpret, and it reaches
  // processes as a literal argv entry, never through a shell, so nothing
  // else would expand it. An emptied setting falls back to the default.
  readonly property string notesRoot: {
    var p = root.notesDir || Platform.env("NOTE_NOTE_DIR") || (Platform.env("HOME") + "/Notes")
    return p.charAt(0) === "~" ? Platform.env("HOME") + p.substring(1) : p
  }
  readonly property string dir: Platform.localPath(Qt.resolvedUrl(".")).replace(/\/$/, "")
  // Both readers refuse symlinks and special files and race a deadline
  // (docs/security.md, rule 9): a path under ~/Notes is user-writable and
  // cannot be trusted to be a plain file.
  readonly property string listScript: dir + "/list.py"
  readonly property string searchScript: dir + "/search.py"
  // This provider's limits: a note bigger than this is listed but not loaded
  // (it is almost certainly not a note), and the listing itself is capped.
  readonly property int maxNoteBytes: 2 * 1024 * 1024
  readonly property int maxListBytes: 4 * 1024 * 1024

  signal updated()
  signal statusRequested(string text)
  signal noticeRequested(string title, string text, string code, var actions)
  signal noticeCleared()
  signal viewRequested(string title, var component, var props)
  signal viewCleared()
  signal persistRequested()
  // A note's path is its file's, so renaming its notebook moves it.
  signal notePathChanged(string previous, string next, var view)

  // notebooks: [{ key, name, dir }]; sectionFolders: [{ key, name }], every
  // folder inside a notebook, keyed by its path from the root ("Work/Plans"),
  // depth first; notes: [{ path, key, file, title, preview }], `key` the
  // notebook's or section's they are in.
  property var notebooks: []
  property var sectionFolders: []
  property var notes: []
  property var sections: []
  // Available before the first notebook exists as well as on every tab.
  readonly property var footerActions: [
    { path: "newNotebook", title: "New notebook", icon: "󱘒",
      prompt: "Notebook name", shortcut: "newNotebook" }
  ]

  // A notebook's footer: in its own tab, New section makes a section in it;
  // in the one tab of trees, each notebook row's menu does (folderMenu). The
  // root's loose notes have no sections, their subfolders being notebooks.
  function notebookActions(key) {
    var actions = [{ path: "newNote", title: "New Note", icon: "󰐕", shortcut: "newNote" }]
    if (key) {
      actions.push({ path: "newSection", title: "New section", icon: "󰉗", prompt: "Section name" })
    }
    return actions.concat(root.footerActions)
  }

  // Right-click menus (PROVIDERS.md, `menu`): a note's is the app's own
  // delete. A notebook's, in the folded shape, and a section's make a
  // section inside it, or rename or delete its folder (rowAction) — only
  // once the listing read it to its end, so the count the delete asks about
  // is all of them. The loose notes in the root are no folder of their own
  // and have none.
  readonly property var noteMenu: [{ id: "delete", title: "Delete", icon: "󰆴", command: "deleteNote" }]
  function folderMenu(folder, count, kind) {
    if (!folder.key || !root.orderWritable(folder.key)) {
      return []
    }
    return [{ id: "newSection", title: "New section", icon: "󰉗", prompt: "Section name" },
            { id: "rename", title: "Rename", icon: "󰑕", rename: true },
            { id: "delete", title: "Delete", icon: "󰆴",
              confirm: "Delete the " + kind + " “" + folder.name + "” and its " + count + (count === 1 ? " note?" : " notes?") }]
  }

  function dirOf(key) { return key ? root.notesRoot + "/" + key : root.notesRoot }
  function baseName(p) { return p.substring(p.lastIndexOf("/") + 1) }
  function fileOf(path) { return path.substring(root.id.length + 1) }
  function pathOf(file) { return root.id + ":" + file }
  function noteAt(path) {
    for (var i = 0; i < root.notes.length; i++) {
      if (root.notes[i].path === path) {
        return root.notes[i]
      }
    }
    return null
  }
  // A notebook's name, or a section's path through its notebook.
  function nameOf(key) {
    for (var i = 0; i < root.notebooks.length; i++) {
      if (root.notebooks[i].key === key) {
        return root.notebooks[i].name
      }
    }
    return key ? key.split("/").join(" › ") : "Notes"
  }

  // ── folders ─────────────────────────────────────────────────────────
  // A notebook or a section is its folder, named by its path from the root;
  // the root's own key is "" and holds the loose notes.
  function parentOf(key) { return key.substring(0, Math.max(0, key.lastIndexOf("/"))) }
  // `key` is folder `top` or a section somewhere inside it.
  function within(key, top) { return key === top || (top !== "" && key.indexOf(top + "/") === 0) }
  function notesUnder(key) { return root.notes.filter(function(note) { return root.within(note.key, key) }) }
  function childSections(key) {
    return root.sectionFolders.filter(function(folder) { return root.parentOf(folder.key) === key })
  }
  function folderAt(key) {
    var all = root.notebooks.concat(root.sectionFolders)
    for (var i = 0; i < all.length; i++) {
      if (all[i].key && all[i].key === key) {
        return all[i]
      }
    }
    return null
  }
  // Depth first, each level by name: the listing's own order (notewalk.py).
  function byFolderPath(a, b) {
    var left = a.key.split("/"), right = b.key.split("/")
    for (var i = 0; i < Math.min(left.length, right.length); i++) {
      if (left[i] !== right[i]) {
        return left[i] < right[i] ? -1 : 1
      }
    }
    return left.length - right.length
  }

  // The file format — the front matter, the title, the preview — is
  // notefile.py's alone; the listing, the search and the operations all
  // read it there, and nothing here parses a note.

  // ── the tree ────────────────────────────────────────────────────────
  // Notebooks the user folded shut (single-tab shape only), by key — kept in
  // the host's state file. The folded set rather than the open one, so the
  // first flip of the setting shows every notebook open instead of every
  // notebook gone. Sections are the other way round: shut until opened, as
  // OneNote's are, and `opened` keeps the ones that are.
  property var folded: []
  property var opened: []

  // Everything under a folder's own row: its sections first, each followed
  // by what it holds when open, then its notes — and, inside a tree, a New
  // note row for them. A folder's notes are their own reorder group, so a
  // drag never moves a note into another folder.
  function folderRows(key, level) {
    var rows = []
    root.childSections(key).forEach(function(section) {
      var open = root.opened.indexOf(section.key) >= 0
      var count = root.notesUnder(section.key).length
      rows.push({ kind: "tree", path: "dir:" + section.key, title: section.name, level: level,
                  expanded: open, count: count, menu: root.folderMenu(section, count, "section") })
      if (open) {
        rows = rows.concat(root.folderRows(section.key, level + 1))
      }
    })
    root.notes.forEach(function(n) {
      if (n.key === key) {
        rows.push({ kind: "note", path: n.path, title: n.title, preview: n.preview, level: level, menu: root.noteMenu,
                    reorder: root.orderWritable(key) ? { scope: key, id: n.path } : null,
                    version: n.version || "", modified: Math.floor(Number(n.version || 0) / 1000000) })
      }
    })
    if (level > 0) {
      rows.push({ kind: "new", path: "section:" + key, level: level })
    }
    return rows
  }

  // Folded trees hide note rows, so a tab's count and its searchable list
  // are given whole (`count` and `notes` in PROVIDERS.md).
  function searchable(notes) {
    return notes.map(function(n) {
      return { path: n.path, title: n.title, preview: n.preview, modified: Math.floor(Number(n.version || 0) / 1000000) }
    })
  }

  // Two shapes, one setting (notebookTabs): a binder tab per notebook
  // folder, or one "Notes" tab holding the notebooks as fold-out trees.
  function rebuild() {
    if (root.notebookTabs) {
      var out = []
      for (var b = 0; b < root.notebooks.length; b++) {
        var nb = root.notebooks[b], held = root.notesUnder(nb.key)
        // No colour: a notebook takes its own from its name, so Work and
        // Personal never look alike.
        out.push({ key: nb.key, name: nb.name, count: held.length, notes: root.searchable(held),
                   rows: root.folderRows(nb.key, 0), footerActions: root.notebookActions(nb.key) })
      }
      root.sections = out
    } else {
      var rows = []
      for (var t = 0; t < root.notebooks.length; t++) {
        var book = root.notebooks[t], open = root.folded.indexOf(book.key) < 0
        var count = root.notesUnder(book.key).length
        rows.push({ kind: "tree", path: "book:" + book.key, title: book.name, level: 0,
                    expanded: open, count: count, menu: root.folderMenu(book, count, "notebook") })
        if (open) {
          rows = rows.concat(root.folderRows(book.key, 1))
        }
      }
      root.sections = [{ key: "notes", name: "Notes", count: root.notes.length, notes: root.searchable(root.notes),
                         rows: rows,
                         footerActions: root.notebooks.length ? root.notebookActions("") : root.footerActions }]
    }
    root.updated()
  }

  function crumb(path) { var n = noteAt(path); return n ? nameOf(n.key) : root.name }
  function storageLabel(path) { return baseName(fileOf(path)) }
  function createTargetFor(path) { var n = noteAt(path); return n ? "section:" + n.key : (root.notebooks.length ? "section:" + root.notebooks[root.notebooks.length - 1].key : "") }
  function restoreState(obj) {
    if (obj && Array.isArray(obj.folded)) {
      root.folded = obj.folded
    }
    if (obj && Array.isArray(obj.opened)) {
      root.opened = obj.opened
    }
  }
  function saveState() { return { folded: root.folded, opened: root.opened } }
  function action(id, value, sectionKey) {
    if (id === "newNote") {
      var target = root.notebookTabs ? "section:" + sectionKey : createTargetFor(root.host.currentPath)
      root.host.newNote(root.id, target)
    } else if (id === "newNotebook") {
      root.host.newNotebook(value, root.id)
    } else if (id === "newSection") {
      root.createFolder(sectionKey, value, function(result) {
        if (result.error) {
          root.statusRequested(root.name + ": " + result.error)
        }
      })
    }
  }
  function toggleTree(id) {
    if (id.indexOf("book:") === 0) {
      root.folded = root.toggled(root.folded, id.substring(5))
    } else if (id.indexOf("dir:") === 0) {
      root.opened = root.toggled(root.opened, id.substring(4))
    } else {
      return
    }
    rebuild()
    root.persistRequested()
  }
  function toggled(keys, key) {
    return keys.indexOf(key) >= 0 ? keys.filter(function(other) { return other !== key }) : keys.concat([key])
  }
  // Opens the way to folder `key`: its notebook, and every section down to
  // it and including it.
  function openTo(key) {
    var parts = key.split("/"), opened = root.opened.slice()
    for (var i = 2; i <= parts.length; i++) {
      var section = parts.slice(0, i).join("/")
      if (opened.indexOf(section) < 0) {
        opened.push(section)
      }
    }
    root.opened = opened
    root.folded = root.folded.filter(function(folded) { return folded !== parts[0] })
  }
  // A note inside a folded notebook or a shut section has no row; open the
  // way to it so the host can scroll to the row — asked for when a search
  // ends on such a note.
  function revealPath(path) {
    var n = noteAt(path)
    if (!n) {
      return
    }
    var before = JSON.stringify([root.folded, root.opened])
    root.openTo(n.key)
    if (JSON.stringify([root.folded, root.opened]) !== before) {
      rebuild()
      root.persistRequested()
    }
  }

  property bool listing: false
  property bool relistDue: false
  function refresh() {
    root.relistDue = true
    if (root.listing || mutations.depth > 0) {
      return
    }
    root.relistDue = false
    root.listing = true
    var revision = root.mutationRevision
    runner.run({ command: ["python3", root.listScript, root.notesRoot, String(root.maxListBytes)], raw: true }, function(result) {
      root.listing = false
      if (result.error) {
        root.statusRequested(root.name + ": " + result.error)
      } else if (revision === root.mutationRevision) {
        root.loadList(result.text)
      } else {
        root.relistDue = true
      }
      if (root.relistDue) {
        Qt.callLater(root.refresh)
      }
    })
  }

  // A superseded search settles its old caller before starting the new one.
  property var searchHandle: null
  function search(query, callback) {
    if (root.searchHandle) {
      root.searchHandle.cancel()
    }
    root.searchHandle = runner.run({ command: ["python3", root.searchScript, root.notesRoot, query, String(root.maxNoteBytes)], raw: true }, function(result) {
      callback({ paths: (result.text || "").split("\n").filter(function(line) { return !!line }).map(root.pathOf) })
    })
  }

  // Saved order first, then anything unlisted in the given (birth-time) order.
  function applyOrder(entries, keyOf, savedNames) {
    var rank = Object.create(null)
    for (var i = 0; i < savedNames.length; i++) {
      if (savedNames[i]) {
        rank[savedNames[i]] = i
      }
    }
    return entries.map(function(e, i) { return { e: e, i: i } })
      .sort(function(a, b) {
        var ra = rank[keyOf(a.e)], rb = rank[keyOf(b.e)], ha = ra !== undefined, hb = rb !== undefined
        if (ha && hb) {
          return ra - rb
        }
        if (ha) {
          return -1
        }
        if (hb) {
          return 1
        }
        return a.i - b.i
      }).map(function(x) { return x.e })
  }

  // The last listing reached its end, so the model says what is there and
  // an order written from it names every note. A listing cut short by its
  // budget or deadline leaves this false: what it listed is shown when the
  // sidebar had nothing, an existing model is kept, and no order is written
  // until a whole listing lands — an order written from a partial list
  // would drop every note the list did not reach. A notebook the lister
  // could not read is unknown, not empty, and its order is kept too.
  property bool listingComplete: true
  // Keyed by notebook name, like the maps loadList and applyOrder build, so
  // none of them has a prototype: the names are the user's, and a notebook
  // called `constructor`, `toString` or `__proto__` must not find a property
  // every object already has.
  property var unreadableNotebooks: Object.create(null)

  function orderWritable(key) {
    return root.listingComplete && !root.unreadableNotebooks[key]
  }

  function refuseOrderWrite() {
    root.statusRequested(root.name + ": the notes could not all be listed, so the order was not saved")
  }

  // A listing field as list.py wrote it: `\t`, `\n` and `\\` stand for the
  // tab, the newline and the backslash the stream's own delimiters keep out.
  function unescaped(field) {
    return field.replace(/\\(.)/g, function(match, letter) {
      if (letter === "t") {
        return "\t"
      }
      if (letter === "n") {
        return "\n"
      }
      return letter
    })
  }

  // Parses the listing script's output.
  function loadList(raw) {
    var lines = raw.split("\n"), dirs = [], orders = Object.create(null), bookOrder = [], entries = []
    var end = null, unreadable = Object.create(null)
    for (var i = 0; i < lines.length; i++) {
      var p = lines[i].split("\t").map(root.unescaped)
      if (p[0] === "D") {
        dirs.push(p[1] || "")
      } else if (p[0] === "O") {
        (orders[p[1] || ""] = orders[p[1] || ""] || []).push(p[2])
      } else if (p[0] === "B") {
        bookOrder.push(p[1])
      } else if (p[0] === "X") {
        unreadable[p[1] || ""] = p[2] || "the notebook could not be read"
      } else if (p[0] === "E") {
        end = { complete: p[1] === "complete", reason: p[2] || "" }
      } else if (p[0] === "N") {
        entries.push({ key: p[1] || "", file: p[2], path: pathOf(p[2]), title: p[3] || "", preview: p[4] || "", size: Number(p[5] || 0), version: p[6] || "" })
      }
    }
    if (!end) {
      // A stream without its last line is a listing that died, not a list.
      root.statusRequested(root.name + ": the listing ended before it was complete")
      return
    }
    root.listingComplete = end.complete
    root.unreadableNotebooks = unreadable
    for (var unread in unreadable) {
      root.statusRequested(root.name + ": " + (unread || "Notes") + " — " + unreadable[unread])
    }
    if (!end.complete) {
      root.statusRequested(root.name + ": " + end.reason + " — showing what was listed")
      if (root.notes.length > 0 || root.notebooks.length > 0) {
        // The rows kept are drawn again without what only a whole listing
        // offers — a folder's delete, a drag — until one lands.
        rebuild()
        return
      }
    }
    // A folder right under the root is a notebook; one deeper, a section.
    var books = dirs.filter(function(k) {
      return k.indexOf("/") < 0 && (k !== "" || entries.some(function(e) { return e.key === "" }))
    }).map(function(k) { return { key: k, name: k || "Notes", dir: dirOf(k) } })
    books = applyOrder(books, function(b) { return b.key }, bookOrder)
    root.notebooks = books.filter(function(b) { return b.key === "" }).concat(books.filter(function(b) { return b.key !== "" }))
    root.sectionFolders = dirs.filter(function(k) { return k.indexOf("/") >= 0 }).map(function(k) {
      return { key: k, name: k.substring(k.lastIndexOf("/") + 1) }
    })
    var ordered = []
    root.notebooks.concat(root.sectionFolders).forEach(function(folder) {
      ordered = ordered.concat(applyOrder(entries.filter(function(e) { return e.key === folder.key }),
                                          function(e) { return baseName(e.file) }, orders[folder.key] || []))
    })
    root.notes = ordered
    rebuild()
  }

  // Reads retain errors and the byte limit from the same descriptor as the text.
  ProcessRunner { id: runner }
  RequestQueue {
    id: mutations
    domain: "local"
    concurrency: 1
    onUpdated: {
      if (mutations.depth === 0 && root.relistDue) {
        Qt.callLater(root.refresh)
      }
    }
  }
  readonly property bool busy: mutations.depth > 0 || runner.active > 0
  readonly property bool writeBusy: mutations.depth > 0
  property int mutationRevision: 0
  property var deleting: ({})

  function load(path, cb) {
    var file = root.fileOf(path)
    var request = JSON.stringify({ action: "read", root: root.notesRoot, file: file })
    return runner.run({ command: ["python3", root.dir + "/operations.py"], payload: request }, function(result) {
      if (result.error) {
        cb(result)
        return
      }
      // Read-only, with operations.py's reason, when the note holds what
      // the editor would not write back as it is.
      cb({ title: result.title, body: result.body, editable: result.editable !== false,
           reason: result.reason || "", version: result.version,
           base: file.substring(0, file.lastIndexOf("/")) })
    })
  }

  // Staging, writing, creating and deleting share one ordering policy.
  // Callers and models see success only after the filesystem has committed:
  // `commit(answer)` runs first, on success only, and returns what `cb` is
  // told beside the answer — the path a note was created at, the notes a
  // delete took — or nothing.
  function mutate(key, payload, commit, cb) {
    return mutations.enqueue({ key: key, mode: "append", owner: root, flush: true }, function(ctx) {
      root.mutationRevision++
      var request = typeof payload === "function" ? payload() : payload
      request.root = root.notesRoot
      runner.run({ command: ["python3", root.dir + "/operations.py"],
                   payload: JSON.stringify(request), timeoutMs: 60000 }, ctx.done)
    }, function(result, info) {
      root.mutationRevision++
      var answer = result || { error: info.cancelled ? "operation cancelled" : "operation was not completed" }
      if (!answer.error) {
        answer = Object.assign({}, answer, commit(answer))
      }
      if (cb) {
        cb(answer)
      } else if (answer.error) {
        root.statusRequested(root.name + ": " + answer.error)
      }
    })
  }

  function save(path, title, body, cb) {
    if (root.deleting[path]) {
      cb({ error: "the note is being deleted" })
      return
    }
    mutate(path, { action: "save", file: fileOf(path), title: title, body: body }, function(result) {
      root.notes = root.notes.map(function(note) {
        if (note.path !== path) {
          return note
        }
        return { key: note.key, file: note.file, path: path, title: title.trim(),
                 preview: result.preview, size: result.bytes, version: result.version }
      })
      rebuild()
    }, cb)
  }

  function create(target, cb) {
    var key = target.indexOf("section:") === 0 ? target.substring(8) : ""
    mutate("create:" + key, { action: "create", key: key }, function(result) {
      root.openTo(key)
      root.persistRequested()
      var entry = { key: key, file: result.file, path: pathOf(result.file),
                    title: "", preview: "", size: result.bytes, version: result.version }
      var arr = root.notes.slice(), at = arr.length
      for (var i = arr.length - 1; i >= 0; i--) {
        if (arr[i].key === key) {
          at = i + 1
          break
        }
      }
      arr.splice(at, 0, entry)
      root.notes = arr
      rebuild()
      persistOrder(key)
      return { path: entry.path }
    }, cb)
  }

  function remove(path, cb) {
    var note = noteAt(path)
    if (!note) {
      cb({ error: "unknown note" })
      return
    }
    root.deleting[path] = true
    mutate(path, { action: "remove", file: note.file }, function(result) {
      root.notes = root.notes.filter(function(n) { return n.path !== path })
      rebuild()
      persistOrder(note.key)
    }, function(result) {
      delete root.deleting[path]
      if (cb) {
        cb(result)
      }
    })
  }

  // The folder a notebook called `name` lives in, or "" for a name that
  // cannot be one: a separator would make it a path, a leading dot a hidden
  // folder the listing skips.
  function notebookKey(name) {
    var key = name.replace(/[/\\]/g, "-").trim()
    return key && key[0] !== "." ? key : ""
  }

  function createSection(name, cb) {
    var key = root.notebookKey(name)
    if (!key) {
      cb({ error: "invalid name" })
      return
    }
    mutate("section:" + key, { action: "section", key: key }, function(result) {
      if (!root.notebooks.some(function(book) { return book.key === key })) {
        root.notebooks = root.notebooks.concat([{ key: key, name: key, dir: root.dirOf(key) }])
        persistNotebookOrder()
      }
      rebuild()
      return { key: root.notebookTabs ? key : "notes", target: "section:" + key }
    }, cb)
  }

  // A notebook's or a section's menu (folderMenu). The host has written the
  // open note and holds it still until this answers; earlier writes run
  // first, the queue being one at a time.
  function rowAction(path, id, value, cb) {
    var key = path.indexOf("book:") === 0 ? path.substring(5) : (path.indexOf("dir:") === 0 ? path.substring(4) : "")
    if (!root.folderAt(key)) {
      cb({ error: "unknown notebook or section" })
    } else if (id === "newSection") {
      root.createFolder(key, value, cb)
    } else if (id === "rename") {
      root.renameFolder(key, value, cb)
    } else if (id === "delete") {
      root.removeFolder(key, cb)
    } else {
      cb({ error: "unknown action" })
    }
  }

  // A section inside notebook or section `parent`, shown open in an open
  // place: there is nothing in it to hide yet.
  function createFolder(parent, name, cb) {
    var leaf = root.notebookKey(name), key = parent + "/" + leaf
    if (!leaf) {
      cb({ error: "invalid name" })
      return
    }
    if (root.folderAt(key)) {
      cb({ error: "a section with that name already exists" })
      return
    }
    mutate("section:" + key, { action: "section", key: key }, function(result) {
      root.sectionFolders = root.sectionFolders.concat([{ key: key, name: leaf }]).sort(root.byFolderPath)
      root.openTo(key)
      rebuild()
      root.persistRequested()
    }, cb)
  }

  // Everything inside moves with the folder, each note reported at its new
  // path; a folder keeps its parent, so only its own name changes.
  function renameFolder(key, name, cb) {
    var leaf = root.notebookKey(name), parent = root.parentOf(key)
    var target = parent ? parent + "/" + leaf : leaf
    if (!leaf) {
      cb({ error: "invalid name" })
      return
    }
    if (root.folderAt(target)) {
      cb({ error: "a notebook or section with that name already exists" })
      return
    }
    mutate("section:" + key, { action: "renameSection", key: key, name: leaf }, function(result) {
      var moved = []
      var rekey = function(other) {
        return root.within(other, key) ? target + other.substring(key.length) : other
      }
      root.notes = root.notes.map(function(note) {
        if (!root.within(note.key, key)) {
          return note
        }
        var file = root.dirOf(target) + note.file.substring(root.dirOf(key).length)
        moved.push({ previous: note.path, next: root.pathOf(file) })
        return Object.assign({}, note, { key: rekey(note.key), file: file, path: root.pathOf(file) })
      })
      root.notebooks = root.notebooks.map(function(book) {
        return book.key === key ? { key: target, name: leaf, dir: root.dirOf(target) } : book
      })
      root.sectionFolders = root.sectionFolders.map(function(folder) {
        return root.within(folder.key, key) ? { key: rekey(folder.key), name: folder.key === key ? leaf : folder.name } : folder
      }).sort(root.byFolderPath)
      root.folded = root.folded.map(rekey)
      root.opened = root.opened.map(rekey)
      rebuild()
      if (!parent) {
        persistNotebookOrder()
      }
      root.persistRequested()
      moved.forEach(function(move) {
        root.notePathChanged(move.previous, move.next, null)
      })
    }, cb)
  }

  // Its sections go with it. The answer names the notes that went with it
  // (`removed`), taken as the folder goes, so a note made in it while the
  // delete waited its turn is one of them. operations.py keeps a folder
  // holding anything that is not a note.
  function removeFolder(key, cb) {
    mutate("section:" + key, { action: "removeSection", key: key }, function(result) {
      var removed = root.notesUnder(key).map(function(note) {
        return note.path
      })
      var gone = function(other) { return root.within(other, key) }
      root.notes = root.notes.filter(function(note) { return !gone(note.key) })
      root.notebooks = root.notebooks.filter(function(book) { return book.key !== key })
      root.sectionFolders = root.sectionFolders.filter(function(folder) { return !gone(folder.key) })
      root.folded = root.folded.filter(function(folded) { return !gone(folded) })
      root.opened = root.opened.filter(function(opened) { return !gone(opened) })
      rebuild()
      if (!root.parentOf(key)) {
        persistNotebookOrder()
      }
      root.persistRequested()
      return { removed: removed }
    }, cb)
  }

  function reorderNotes(sectionKey, paths) {
    var rank = {}
    paths.forEach(function(path, index) { rank[path] = index })
    var mine = root.notes.filter(function(note) { return note.key === sectionKey })
    mine = mine.map(function(note, index) { return { note: note, index: index } })
      .sort(function(a, b) {
        var left = rank[a.note.path], right = rank[b.note.path]
        return (left === undefined ? paths.length + a.index : left)
             - (right === undefined ? paths.length + b.index : right)
      }).map(function(entry) { return entry.note })
    var next = 0
    return root.notes.map(function(note) { return note.key === sectionKey ? mine[next++] : note })
  }

  function reorder(sectionKey, paths, callback) {
    if (!orderWritable(sectionKey)) {
      callback({ error: "the notes could not all be listed, so the order was not saved" })
      return
    }
    var current = root.notes.filter(function(note) {
      return note.key === sectionKey
    }).map(function(note) {
      return note.path
    })
    if (!Ordering.isPermutation(current, paths)) {
      callback({ error: "the notes changed — try reordering again" })
      return
    }
    var file = dirOf(sectionKey) + "/.order"
    mutate("order:" + file, function() {
      var names = reorderNotes(sectionKey, paths).filter(function(note) { return note.key === sectionKey })
        .map(function(note) { return baseName(note.file) })
      return { action: "order", file: file, text: names.join("\n") + "\n" }
    }, function(result) {
      root.notes = reorderNotes(sectionKey, paths)
      rebuild()
    }, callback)
  }

  // ── watching: inotify while the app is open (event-driven, no polling) ──
  function watch(on) {
    if (on) {
      watchProc.start()
    } else {
      watchProc.cancel()
    }
  }
  function poll() { root.refresh() }
  Timer { id: relistDebounce; interval: 400; onTriggered: root.refresh() }
  ProcessTask {
    id: watchProc
    timeoutMs: 0
    maxOutputBytes: 1024 * 1024
    command: ["inotifywait", "-m", "-r", "-q", "-e", "create,delete,move,close_write", "--format", "%e %w%f", "--", root.notesRoot]
    streaming: true
    onLineReceived: function(line) {
      if (/\/\.(order|notebooks)(\s|$)/.test(line)) {
        return  // our bookkeeping files
      }
      relistDebounce.restart()
    }
  }

  function persistOrder(key) {
    if (!orderWritable(key)) {
      refuseOrderWrite()
      return
    }
    var file = dirOf(key) + "/.order"
    mutate("order:" + file, function() {
      var names = root.notes.filter(function(note) { return note.key === key }).map(function(note) { return baseName(note.file) })
      return { action: "order", file: file, text: names.join("\n") + "\n" }
    }, function(result) {})
  }

  function persistNotebookOrder() {
    if (!root.listingComplete) {
      refuseOrderWrite()
      return
    }
    var file = root.notesRoot + "/.notebooks"
    mutate("order:" + file, function() {
      var keys = root.notebooks.filter(function(book) { return !!book.key }).map(function(book) { return book.key })
      return { action: "order", file: file, text: keys.join("\n") + "\n" }
    }, function(result) {})
  }
}
