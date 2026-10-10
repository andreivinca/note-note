import "../../services/platform"
import QtQuick
import "../../services/processes"
import "../../services/providers"
import "../../services/notes/ordering.js" as Ordering
import "../../design"
import "../../design/controls"

// OneNote: notebooks → sections → pages. A binder tab per notebook by
// default, or one tab holding the whole tree when notebookTabs is false.
// Pages are fetched on demand as
// Markdown (onenote.py + onenote_md.py) and written back as OneNote HTML.
LaneProvider {
  id: root

  readonly property string id: "onenote"
  readonly property string name: "OneNote"
  readonly property url logo: Qt.resolvedUrl("logo.svg")
  readonly property bool markdown: true
  readonly property bool hasTitle: true
  readonly property bool canCreate: true
  readonly property bool canDelete: true
  readonly property bool canReorder: false
  readonly property bool canCreateSection: false
  // Pages carry their images through an edit, and a pasted one is uploaded
  // with the save (onenote.py).
  readonly property bool canImages: true
  // Files.ReadWrite reads the notebooks' section order and writes page
  // order and blank-line removals into their section files.
  readonly property var microsoftScopes: ["Notes.ReadWrite", "Files.ReadWrite"]
  // What the page can hold (PROVIDERS.md). Not a quote, a code block, inline
  // code or a rule: onenote_md.py writes each as a look its reader has no
  // reading for, so they would come back as plain text — and a save holding
  // one is refused (onenote.py, keeps_formatting) rather than flattened.
  readonly property var tools: ["bold", "italic", "underline", "strikeout", "highlight", "textColor",
                                "h1", "h2", "h3", "p", "ul", "ol", "todo", "indent", "outdent",
                                "table", "link", "currentMonth", "nextMonth", "customMonth"]
  // This provider's own app registration: an Entra public client for
  // personal and work accounts, registered by the author, that every user
  // of OneNote here signs in through. Sticky Notes has one of its own.
  readonly property string microsoftClientId: "1ed713b0-195a-4360-88b4-993f3aeaa262"

  // This provider's one setting (PROVIDERS.md), assigned by the host from
  // config.providers.onenote.notebookTabs: each notebook a binder tab of its
  // own by default; the whole tree in one OneNote tab when false.
  settings: ["notebookTabs"]
  liveSettings: ["notebookTabs"]
  property bool notebookTabs: true
  readonly property string dir: Platform.localPath(Qt.resolvedUrl(".")).replace(/\/$/, "")
  script: dir + "/onenote.py"
  // Keyed to OneNote's own Graph budget: everything below goes through the
  // lane, in order, and it parks whole when OneNote says it has had enough
  // (services/requests/, docs/providers.md). Sticky Notes has a lane
  // of its own, so a OneNote throttle never reaches it.
  laneKey: "graph-onenote"
  Component.onCompleted: {
    if (services && services.microsoft) {
      root.ms = services.microsoft.create(root.id, root.microsoftScopes, root.microsoftClientId)
      // A sign-in from before the app asked for Files.ReadWrite still
      // renews, so its notes stay readable; accountRows() asks for a new
      // sign-in.
      root.ms.optionalScopes = "Files.Read Files.ReadWrite"
    }
  }

  // Graph does not reliably bump a page's lastModifiedDateTime, so the open
  // page is re-read on poll and reported when its text differs.
  signal noteChanged(string path)
  signal notePathChanged(string previous, string next, var view)
  signal noteDeletionFinished(string path, var result)
  signal searchChanged()

  property var onSections: []    // [{ id, name, notebook, notebookId }]
  property var onNotebooks: []
  // Canonical page order includes pending deletions; visible rows hide them
  // until the remote result settles, so rollback retains their positions.
  property var pages: []         // [{ id, sectionId, title, modified }]
  property var bodies: ({})      // id -> cached content and Python view token
  property var loadVersions: ({})
  property var saveVersions: ({})
  // Provisional pages and pending deletes outlive an account change: each
  // settles through the lane, and a failed creation keeps the user's text
  // until they delete it. These three maps are replaced, never mutated.
  property var pendingPages: ({})  // draft id -> page, deferred operations and create result
  property var pageAliases: ({})   // draft id -> Graph id, for callbacks captured before creation
  property var pendingDeletes: ({}) // page id -> hidden row and its original order
  property var pageOrderWrites: ({})
  property var pageOrderRecovery: ({})
  property int nextDraft: 0
  property var expanded: []      // notebook/section ids the user opened
  property bool searchInventoryReady: false
  property bool searchInventoryComplete: false
  readonly property bool ready: ms && ms.signedIn && ms.hasScope("Notes.ReadWrite")

  function withEntry(map, key, value) {
    var next = Object.assign({}, map)
    next[key] = value
    return next
  }
  function withoutEntry(map, key) {
    var next = Object.assign({}, map)
    delete next[key]
    return next
  }

  function idOf(path) {
    var id = path.substring(root.id.length + 1)
    return root.pageAliases[id] || id
  }
  function pathOf(id) { return root.id + ":" + id }
  function pageAt(path) {
    var id = idOf(path)
    for (var i = 0; i < root.pages.length; i++) {
      if (root.pages[i].id === id) {
        return root.pages[i]
      }
    }
    return null
  }
  function sectionAt(id) {
    for (var i = 0; i < root.onSections.length; i++) {
      if (root.onSections[i].id === id) {
        return root.onSections[i]
      }
    }
    return null
  }
  function sectionName(id) {
    var s = sectionAt(id)
    return s ? "OneNote › " + (s.notebook ? s.notebook + " › " : "") + s.name : "OneNote"
  }

  // The account rows every shape starts from: null when the tree can show,
  // the one action row that says why it cannot otherwise.
  function accountRows() {
    if (!ms || !ms.configured) {
      return [{ kind: "action", path: "unavailable", title: "Not available in this build", icon: "󰒓" }]
    }
    if (!ms.signedIn) {
      return [{ kind: "action", path: "login", title: ms.loggingIn ? "Cancel signing in…" : "Sign in to Microsoft…", icon: ms.loggingIn ? "󰅖" : "󰊻" }]
    }
    if (!ms.hasScope("Notes.ReadWrite")) {
      return [{ kind: "action", path: "relogin", title: ms.loggingIn ? "Cancel signing in…" : "Sign in again to enable OneNote…", icon: ms.loggingIn ? "󰅖" : "󰊻" }]
    }
    // The same account signing in again keeps its caches and drafts, so
    // this is a sign-in without the sign-out "relogin" does first.
    if (!ms.hasScope("Files.ReadWrite")) {
      return [{ kind: "action", path: "login", title: ms.loggingIn ? "Cancel signing in…" : "Sign in again to update OneNote permissions…", icon: ms.loggingIn ? "󰅖" : "󰊻" }]
    }
    return null
  }
  function bookList() {
    var books = [], seen = {}
    for (var b = 0; b < root.onNotebooks.length; b++) {
      var book = root.onNotebooks[b]
      seen[book.id] = true
      books.push(book)
    }
    for (var i = 0; i < root.onSections.length; i++) {
      var s = root.onSections[i]
      if (!seen[s.notebookId]) {
        seen[s.notebookId] = true
        books.push({ id: s.notebookId, name: s.notebook || "Notebook" })
      }
    }
    books.sort(function(a, b) { return a.name.localeCompare(b.name) })
    return books
  }
  function bookWritable(bookId) {
    for (var i = 0; i < root.onNotebooks.length; i++) {
      var book = root.onNotebooks[i]
      if (book.id === bookId) {
        var role = (book.userRole || "").toLowerCase()
        return role !== "reader" && role !== "none"
      }
    }
    return true
  }
  function noteReadOnly(path) {
    var page = root.pageAt(path)
    var section = page ? root.sectionAt(page.sectionId) : null
    return !!section && !root.bookWritable(section.notebookId)
  }

  function sectionPages(sectionId) {
    return root.pages.filter(function(page) {
      return page.sectionId === sectionId
    })
  }

  // Page order is written into the section's file in its owner's OneDrive:
  // a personal notebook this account owns, or one shared with it for
  // editing. web_session.py's writable_notebook() enforces the same rule.
  function pageOrderingNotebook(bookId) {
    var book = root.onNotebooks.find(function(candidate) {
      return candidate.id === bookId
    })
    var role = book ? (book.userRole || "").toLowerCase() : ""
    return (role === "owner" || role === "contributor")
      && /^0-[0-9a-f]{16}!(?:[0-9]+|s[0-9a-f]{32})$/i.test(book.id)
  }

  function pageOrderingAvailable(section) {
    if (!root.ready || !root.ms.hasScope("Files.ReadWrite") || !root.pageOrderingNotebook(section.notebookId)
        || pageInventory.pendingSections.indexOf(section.id) >= 0 || root.pageOrderRecovery[section.id]) {
      return false
    }
    var pages = root.sectionPages(section.id)
    var parents = pages.filter(function(page) {
      return page.level === 0
    })
    return parents.length > 1 && pages.every(function(page) {
      return typeof page.level === "number" && page.level >= 0 && page.level <= 2
        && Math.floor(page.level) === page.level && !!page.clientId
        && !root.pendingPages[page.id] && !root.pendingDeletes[page.id]
    })
  }
  // One notebook's sections with their pages and New Note rows when open,
  // starting at `level`: 0 when the notebook is a tab
  // of its own, 1 when it sits under its own tree row.
  function bookRows(bookId, level) {
    var rows = []
    for (var k = 0; k < root.onSections.length; k++) {
      var sec = root.onSections[k]
      if (sec.notebookId !== bookId) {
        continue
      }
      var secOpen = root.expanded.indexOf(sec.id) >= 0
      rows.push({ kind: "tree", path: sec.id, title: sec.name, level: level, expanded: secOpen })
      if (!secOpen) {
        continue
      }
      var orderable = root.pageOrderingAvailable(sec)
      for (var p = 0; p < root.pages.length; p++) {
        var pg = root.pages[p]
        if (pg.sectionId !== sec.id || root.pendingDeletes[pg.id]) {
          continue
        }
        rows.push({ kind: "note", path: pathOf(pg.id), title: pg.title, preview: "",
                    level: level + 1 + (pg.level || 0),
                    reorder: orderable && pg.level === 0
                      ? { scope: "pages:" + sec.id, id: pathOf(pg.id), descendants: true } : null,
                    version: pg.modified || "", modified: pg.modified || "" })
      }
      if (pageInventory.pendingSections.indexOf(sec.id) >= 0) {
        rows.push({ kind: "action", path: "loadsection:" + sec.id, title: pageInventory.status(sec.id), icon: "󰑐", level: level + 1 })
      }
      if (root.bookWritable(bookId)) {
        rows.push({ kind: "new", path: "section:" + sec.id, level: level + 1 })
      }
    }
    return rows
  }
  function noteList(pgs) { return pgs.map(function(p) { return { path: pathOf(p.id), title: p.title, preview: "", modified: p.modified || "" } }) }
  function accountActions(bookId) {
    var actions = []
    var books = bookList().filter(function(book) {
      return (!bookId || book.id === bookId) && root.bookWritable(book.id)
    })
    books.forEach(function(book) {
      actions.push({ path: "newsection:" + book.id,
                     title: books.length === 1 ? "New section" : "New section in " + book.name,
                     icon: "󰉗" })
    })
    actions.push({ path: "logout", title: "Sign out" + (ms.account ? " (" + ms.account + ")" : ""), icon: "󰍃" })
    return actions
  }

  // `notes` on a section is its searchable whole, fold state ignored: rows
  // only carry the pages of expanded sections, and a search (and the hit
  // count on the tab) must see the closed ones too.
  function rebuild() {
    var account = accountRows(), books = account ? [] : bookList()
    var visiblePages = root.pages.filter(function(page) { return !root.pendingDeletes[page.id] })
    if (root.notebookTabs && books.length > 0) {
      // A tab per notebook. No colour: each takes a pastel from its own
      // name, which is what tells Work from Personal apart (the logo keeps
      // them OneNote's); the account footer appears on every tab, since any of
      // them is equally the account's.
      root.sections = books.map(function(b) {
        var pgs = visiblePages.filter(function(p) { var sec = root.sectionAt(p.sectionId); return sec && sec.notebookId === b.id })
        return { key: b.id, name: b.name, count: pgs.length, notes: noteList(pgs),
                 rows: bookRows(b.id, 0), footerActions: accountActions(b.id) }
      })
      root.updated()
      return
    }
    // One OneNote tab: the sign-in states, or the notebooks as trees. The
    // empty listing lands here too, whatever the setting says — no notebooks
    // means nothing to spread, and the tab must exist to say so.
    var rows = []
    if (account) {
      rows = account
    } else {
      for (var b = 0; b < books.length; b++) {
        var open = root.expanded.indexOf(books[b].id) >= 0
        rows.push({ kind: "tree", path: books[b].id, title: books[b].name, level: 0, expanded: open })
        if (open) {
          rows = rows.concat(bookRows(books[b].id, 1))
        }
      }
      if (books.length === 0) {
        rows.push(root.listing
          ? { kind: "action", path: "refresh", title: "Loading notebooks…", icon: "󰑐" }
          : { kind: "action", path: "refresh", title: root.listingError ? "Could not load notebooks — retry" : "No notebooks found — refresh", icon: "󰑐" })
      }
    }
    root.sections = [{ key: "onenote", name: "OneNote", color: "#7719AA", count: visiblePages.length,
                       notes: noteList(visiblePages), rows: rows, footerActions: account ? [] : accountActions() }]
    root.updated()
  }

  function crumb(path) { var pg = pageAt(path); return pg ? sectionName(pg.sectionId) : "OneNote" }
  function createTargetFor(path) {
    var pg = pageAt(path)
    return pg && !root.noteReadOnly(path) ? "section:" + pg.sectionId : ""
  }
  function restoreState(obj) {
    if (!obj) {
      return
    }
    if (Array.isArray(obj.expanded)) {
      root.expanded = obj.expanded
    }
    if (typeof obj.lastNotebook === "string") {
      root.lastNotebook = obj.lastNotebook
    }
    if (obj.lastPages && typeof obj.lastPages === "object") {
      root.lastPages = obj.lastPages
    }
  }
  function saveState() { return { expanded: root.expanded, lastNotebook: root.lastNotebook, lastPages: root.lastPages } }

  // ── what a tab opens with ───────────────────────────────────────────
  // The host keeps this for every provider, keyed by tab, and that is the
  // right answer for anything whose tabs are fixed. OneNote's are not: the
  // notebookTabs setting turns one tab holding every notebook into a tab
  // each and back again, so a memory keyed by tab is thrown away by a setting
  // that changed nothing about which notebook the user was reading. Kept per
  // notebook here instead, which is the unit the user actually means either
  // way, and answered into whichever shape the tabs are wearing.
  property string lastNotebook: ""   // the notebook last read in
  property var lastPages: ({})       // notebook id -> the page last open in it

  function noteOpened(path) {
    var pg = pageAt(path)
    if (!pg) {
      return
    }
    var sec = sectionAt(pg.sectionId)
    if (!sec) {
      return
    }
    var book = sec.notebookId
    if (root.lastNotebook === book && root.lastPages[book] === path) {
      return
    }
    root.lastNotebook = book
    var next = {}
    for (var k in root.lastPages) {
      next[k] = root.lastPages[k]
    }
    next[book] = path
    root.lastPages = next
    root.persistRequested()
  }

  // A notebook tab's key is the notebook's own id; the single tree tab's key
  // is "onenote", and the notebook it means is the last one read in — which
  // is what makes that tab open where it was left, notebook and page both,
  // rather than merely on a page.
  function defaultNote(key) {
    return root.lastPages[root.notebookTabs ? key : root.lastNotebook] || ""
  }

  function toggleTree(id) {
    var i = root.expanded.indexOf(id), next = root.expanded.slice()
    if (i >= 0) {
      next.splice(i, 1)
    } else {
      next.push(id)
    }
    root.expanded = next
    if (i < 0 && root.sectionAt(id)) {
      pageInventory.request(id, true, false)
    }
    rebuild()
    root.persistRequested()
  }

  // A page in a folded section has no row. Revealing one opens its section
  // and its notebook, so the row exists when the host scrolls to it — asked
  // for when a search ends on a page the tree was hiding.
  function revealPath(path) {
    var pg = pageAt(path)
    if (!pg) {
      return
    }
    var sec = sectionAt(pg.sectionId), next = root.expanded.slice()
    if (sec && next.indexOf(sec.notebookId) < 0) {
      next.push(sec.notebookId)
    }
    if (next.indexOf(pg.sectionId) < 0) {
      next.push(pg.sectionId)
    }
    if (next.length === root.expanded.length) {
      return
    }
    root.expanded = next
    rebuild()
    root.persistRequested()
  }

  function action(id) {
    if (!ms) {
      return
    }
    if (id === "login") {
      if (ms.loggingIn) {
        ms.cancelLogin()
        root.noticeCleared()
      } else {
        ms.login()
      }
    }
    else if (id === "relogin") {
      if (ms.loggingIn) {
        ms.cancelLogin()
        root.noticeCleared()
      } else {
        ms.relogin()
      }
    }
    else if (id === "logout") {
      root.noticeRequested("Sign out of OneNote?",
        "You'll need to sign in again" + (ms.account ? " as " + ms.account : "") + " to keep using OneNote.", "",
        [{ label: "Sign out", action: function() { root.noticeCleared(); ms.logout() } },
         { label: "Cancel", action: function() { root.noticeCleared() } }])
    } else if (id === "refresh") {
      root.listPages(true)
    } else if (id.indexOf("loadsection:") === 0) {
      pageInventory.request(id.substring(12), true, false)
    } else if (id.indexOf("newsection:") === 0) {
      root.newSectionNotebook = id.substring(11)
      root.newSectionError = ""
      root.viewRequested("New section in " + notebookName(root.newSectionNotebook), sectionView, {})
    } else if (id === "unavailable") {
      root.noticeRequested("Microsoft sign-in is not configured in this build",
        "This copy of Note Note has no app registration for OneNote built in (microsoftClientId in plugins/org.note-note.onenote/Provider.qml), so nobody can sign in yet.", "", [])
    }
  }

  function notebookName(id) {
    for (var i = 0; i < root.onSections.length; i++) {
      if (root.onSections[i].notebookId === id) {
        return root.onSections[i].notebook || "OneNote"
      }
    }
    return "OneNote"
  }

  // ── new section ─────────────────────────────────────────────────────
  property string newSectionNotebook: ""
  property string newSectionError: ""
  property bool newSectionBusy: false
  function createSection(name) {
    var n = name.trim()
    if (!n) {
      root.newSectionError = "A section needs a name."
      return
    }
    if (root.newSectionBusy || !root.rq) {
      return
    }
    var notebook = root.newSectionNotebook
    root.newSectionBusy = true
    root.newSectionError = ""
    root.rq.enqueue({ key: "section:" + notebook, mode: "append", priority: 0, owner: root,
                      flush: true, label: "new section" },
      function(ctx) { root.runScript(["create-section", notebook, "-"], JSON.stringify({ name: n }), ctx) },
      function(r, info) {
        root.newSectionBusy = false
        if (!r) {
          root.newSectionError = info.cancelled ? "The window closed before the section was made." : ""
          return
        }
        if (r.error) {
          root.newSectionError = r.error
          return
        }
        var sct = r.section
        root.supersedeOrderPass()
        pageInventory.serial = Math.max(pageInventory.serial, r.pageListSerial || 0)
        if (!sct.notebook) {
          sct.notebook = root.notebookName(sct.notebookId)
        }
        root.onSections = root.onSections.concat([sct])
        var exp = root.expanded.slice()
        if (exp.indexOf(sct.notebookId) < 0) {
          exp.push(sct.notebookId)
        }
        if (exp.indexOf(sct.id) < 0) {
          exp.push(sct.id)
        }
        root.expanded = exp
        root.viewCleared()
        root.rebuild()
        root.persistRequested()
        root.statusRequested("Section created")
      })
  }

  Component {
    id: sectionView
    FocusScope {
      width: parent ? parent.width : Style.space(600)
      height: column.implicitHeight
      Column {
        id: column
        spacing: Style.spacing.md
        leftPadding: Style.spacing.md
        topPadding: Style.spacing.md

        Text {
          textFormat: Text.PlainText
          width: Style.space(520)
          wrapMode: Text.Wrap
          text: "The section is created in OneNote and appears in the tree; pages you add go into it."
          color: Color.menu.text
          font.family: Style.font.menuFamily
          font.pixelSize: Style.font.body
        }
        TextField {
          id: nameField
          width: Style.space(320)
          placeholderText: "Section name"
          foreground: Color.menu.text
          accent: Color.accent
          font.family: Style.font.menuFamily
          focus: true
          Keys.onReturnPressed: root.createSection(text)
        }
        Text {
          textFormat: Text.PlainText
          visible: root.newSectionError.length > 0
          text: root.newSectionError
          color: Color.urgent
          font.family: Style.font.menuFamily
          font.pixelSize: Style.font.bodySmall
        }
        Row {
          spacing: Style.spacing.sm
          Button {
            text: root.newSectionBusy ? "Creating…" : "Create"
            bordered: true
            enabled: !root.newSectionBusy
            foreground: Color.menu.text
            accent: Color.accent
            onClicked: root.createSection(nameField.text)
          }
          Button {
            text: "Cancel"
            bordered: true
            foreground: Color.menu.text
            accent: Color.accent
            onClicked: root.viewCleared()
          }
        }
      }
    }
  }

  // ── running the script ──────────────────────────────────────────────
  // The search cache's runs, outside the lane (SearchCache.qml).
  ProcessRunner { id: searchRunner }
  function runLocal(args, payload, callback) {
    return root.runProcess(searchRunner, args, payload, callback)
  }

  function reorder(scope, paths, callback) {
    var sectionId = scope.indexOf("pages:") === 0 ? scope.substring(6) : ""
    var section = root.sectionAt(sectionId)
    if (!section || !root.rq || !root.pageOrderingAvailable(section) || root.pageOrderWrites[sectionId]) {
      callback({ error: "The complete section and page ordering permission must be available before reordering" })
      return
    }
    var expected = root.sectionPages(sectionId).filter(function(page) {
      return page.level === 0
    }).map(function(page) {
      return page.id
    })
    var wanted = paths.map(function(path) {
      return root.idOf(path)
    })
    if (!Ordering.isPermutation(expected, wanted)) {
      callback({ error: "The pages changed — try reordering again" })
      return
    }
    root.pageOrderWrites = root.withEntry(root.pageOrderWrites, sectionId, true)
    return root.rq.enqueue({ key: "page-order:" + sectionId, mode: "append", priority: 0,
                             owner: root, flush: true, label: "page order" },
      function(ctx) {
        root.runScript(["reorder-pages", "-"], JSON.stringify({ sectionId: sectionId,
                       expected: expected, order: wanted }), ctx)
      },
      function(result) {
        root.pageOrderWrites = root.withoutEntry(root.pageOrderWrites, sectionId)
        var answer = result || { error: "The order was not saved — the request was cancelled" }
        if (answer.error) {
          // The response might have been lost after a successful revision.
          // Refresh canonical Graph order rather than retrying the write.
          root.pageOrderRecovery = root.withEntry(root.pageOrderRecovery, sectionId, true)
          pageInventory.request(sectionId, true, true)
        } else {
          root.applyInventory(answer)
        }
        root.rebuild()
        callback(answer)
      })
  }

  function refresh() {
    if (!root.ready) {
      root.onNotebooks = []
      root.onSections = []
      root.pages = []
      rebuild()
      return
    }
    // The cached read is a local file and no request at all, so it does not
    // belong in the lane — it must answer instantly even while OneNote is
    // parked, which is what keeps the sidebar populated during a throttle.
    root.readCached()
    root.listPages(false)
  }

  // Discover the tree first. PageInventory fetches one page-list response
  // per job, keeping opening and saving notes ahead of startup work.
  function listPages(force) {
    if (!root.rq || !root.ready) {
      return
    }
    var generation = ++root.listGeneration
    root.listPending = true
    root.listingError = ""
    discoveryRetry.stop()
    root.rq.enqueue({ key: "list", mode: force ? "replace" : "dedupe", priority: 1,
                      runWhenPaused: true, owner: root, label: "listing" },
      function(ctx) { root.runScript(["list", "--incremental"].concat(force ? ["--force"] : ["--max-age", "600"]), "", ctx) },
      function(r) {
        if (generation !== root.listGeneration) {
          return
        }
        root.listPending = false
        if (!r) {
          root.rebuild()
          return
        }
        if (r.error) {
          root.listingError = r.error
          root.statusRequested("OneNote: " + r.error)
          // An interrupted listing checkpoints real sections and pages.
          root.readCached()
        } else {
          root.applyInventory(r)
          root.listed(r)
          if (r.deferred) {
            discoveryRetry.interval = Math.max(100, Math.ceil(r.retryAfter * 1000))
            discoveryRetry.restart()
          }
          if (Array.isArray(r.listingWarnings) && r.listingWarnings.length) {
            root.statusRequested("OneNote: " + r.listingWarnings.join("; "))
          }
        }
        root.rebuild()
      })
    root.rebuild()
  }

  Timer { id: discoveryRetry; onTriggered: root.listPages(false) }

  function applyInventory(result) {
    if (!pageInventory.accept(result)) {
      return
    }
    root.inventoryRevision++
    if (Array.isArray(result.pages) && Array.isArray(result.pendingSections)) {
      var recovering = Object.assign({}, root.pageOrderRecovery)
      Object.keys(recovering).forEach(function(sectionId) {
        if (result.pendingSections.indexOf(sectionId) < 0) {
          delete recovering[sectionId]
        }
      })
      root.pageOrderRecovery = recovering
    }
    if (Array.isArray(result.notebooks)) {
      root.onNotebooks = result.notebooks
    }
    if (Array.isArray(result.sections)) {
      root.onSections = result.sections
    }
    if (Array.isArray(result.pages)) {
      var pages = result.pages
      for (var id in root.pendingPages) {
        pages = root.appendPage(pages, root.pendingPages[id].page)
      }
      for (var deletedId in root.pendingDeletes) {
        pages = root.restorePage(pages, root.pendingDeletes[deletedId])
      }
      root.pages = pages
      root.searchInventoryReady = result.inventoryReady !== false
      root.searchInventoryComplete = result.inventoryComplete === true
    }
  }

  ProcessRunner { id: inventoryRunner }
  PageInventory {
    id: pageInventory
    ready: root.ready && !(root.host && root.host.closing)
    session: root.ms ? root.ms.cacheSession : ""
    queue: root.rq
    run: function(args, payload, callback) {
      return root.runProcess(inventoryRunner, args, payload, callback)
    }
    preferredSections: root.expanded.filter(function(id) { return !!root.sectionAt(id) })
    onLoaded: function(result) {
      root.applyInventory(result)
      root.rebuild()
    }
    onFailed: function(message) {
      root.listingError = message
      root.statusRequested("OneNote: " + message)
      root.rebuild()
    }
  }

  property int inventoryRevision: 0
  property int listGeneration: 0
  property bool listPending: false
  property string listingError: ""
  onRqChanged: {
    if (root.ready && root.rq) {
      root.listPages(false)
    }
  }

  // Every listing answer passes through here: it is the newest word on the
  // sections, and it says whether the section-order pass is due.
  property int listingSerial: 0
  function listed(answer) {
    root.supersedeOrderPass()
    if (answer.sectionOrderPending === true) {
      root.establishOrder()
    }
  }

  // The custom section order is established after the listing, beside the
  // lane (docs/onenote-section-order.md): the OneDrive metadata it reads
  // can take a while, and neither the pages nor a note wait for it. A
  // newer listing, or a sign-out, supersedes a pass under way — its answer
  // would be for sections that are no longer the newest word — and a
  // listing that is due one asks for its own.
  ProcessRunner { id: orderRunner }
  property var orderPass: null
  function supersedeOrderPass() {
    root.listingSerial++
    if (root.orderPass) {
      root.orderPass.cancel()
      root.orderPass = null
    }
  }
  function establishOrder() {
    var serial = root.listingSerial
    root.orderPass = root.runProcess(orderRunner, ["section-order"], "", function(result) {
      if (serial !== root.listingSerial) {
        return
      }
      root.orderPass = null
      if (result.error) {
        root.statusRequested("OneNote section order: " + result.error)
        return
      }
      if (Array.isArray(result.sections)) {
        root.onSections = result.sections
      }
      if (Array.isArray(result.sectionOrderWarnings) && result.sectionOrderWarnings.length) {
        root.statusRequested("OneNote section order: " + result.sectionOrderWarnings.join("; "))
      }
      root.rebuild()
    })
  }

  SearchCache {
    id: searchCache
    ready: root.ready && !(root.host && root.host.closing)
    inventoryReady: root.searchInventoryReady
    inventoryComplete: root.searchInventoryComplete
    session: root.ms ? root.ms.cacheSession : ""
    pages: root.pages.filter(function(page) { return !root.pendingPages[page.id] && !root.pendingDeletes[page.id] })
    queue: root.rq
    run: root.runLocal
    preferredSections: {
      if (!root.searchInventoryReady) {
        return []
      }
      var page = root.host ? root.pageAt(root.host.currentPath) : null
      var section = page ? root.sectionAt(page.sectionId) : null
      return root.searchSections(section ? section.notebookId : "")
    }
    onUpdated: root.searchChanged()
  }

  function searchSections(notebookId) {
    if (!root.searchInventoryReady) {
      return []
    }
    return root.onSections.filter(function(section) {
      return !notebookId || section.notebookId === notebookId
    }).map(function(section) { return section.id })
  }

  function search(query, callback) { searchCache.search(query, callback) }
  function searchDiagnostics() { return searchCache.diagnostics() }

  function searchStatus(sectionKey) {
    // A single OneNote tab contains every notebook; notebook tabs use their
    // notebook identity as the provider's section key.
    return searchCache.status(root.searchSections(root.notebookTabs ? sectionKey : ""))
  }

  Connections {
    target: root.ms
    function onCacheSessionChanged() {
      discoveryRetry.stop()
      root.inventoryRevision++
      root.listGeneration++
      root.listPending = false
      root.listingError = ""
      root.searchInventoryReady = false
      root.searchInventoryComplete = false
      root.onSections = []
      root.onNotebooks = []
      root.clearListedPages()
      root.loadVersions = ({})
      root.saveVersions = ({})
    }
    function onSignedOut() {
      root.supersedeOrderPass()
      root.onSections = []
      root.onNotebooks = []
      root.clearListedPages()
      root.loadVersions = ({})
      root.clearCache()
      // Nothing queued belongs to the account that just left. The rate
      // cooldown is deliberately *not* cleared: Microsoft throttles per
      // app+user, so signing back in does not lift it, and pretending
      // otherwise would just spend the first request learning that again.
      if (services && services.requests) {
        services.requests.cancelOwner(root)
      }
    }
    function onStatusFailed(error) {
      root.statusRequested(root.name + ": could not check the sign-in — " + error)
    }
    function onUpdated() {
      root.refresh()
    }
  }

  // What the account listed goes with the account. A provisional page stays,
  // with its text: the host may hold unsaved edits for its path, and only
  // this row lets the user reach them. It reappears in its section when that
  // is listed again; a queued creation cancelled by a sign-out fails it.
  function clearListedPages() {
    var bodies = {}
    for (var id in root.pendingPages) {
      bodies[id] = root.bodies[id]
    }
    root.pages = root.pages.filter(function(page) {
      return !!root.pendingPages[page.id]
    })
    root.bodies = bodies
  }

  // ── pages ───────────────────────────────────────────────────────────
  // Every call below hands the lane a key, a mode and a callback, and the
  // lane decides when it runs. The keys are what say which requests may not
  // overlap: a page's save, delete and load are three different intents about
  // one page, and only the first two must be ordered against each other.
  function cacheBody(path, result) {
    var id = root.idOf(path)
    var page = root.pageAt(path)
    var cached = Object.assign({}, result, { version: page ? page.modified || "" : "" })
    if (root.noteReadOnly(path)) {
      cached.editable = false
      cached.reason = "This notebook is shared with you as read-only."
    }
    root.bodies[id] = cached
    return cached
  }

  function load(path, cb) {
    var id = idOf(path), cached = root.bodies[id], pg = pageAt(path)
    if (root.pendingDeletes[id]) {
      cb({ error: "The note is being deleted." })
      return
    }
    if (root.pendingPages[id]) {
      cb(cached)
      return
    }
    if (cached && cached.view && (!pg || cached.version === (pg.modified || ""))) {
      cb(root.cacheBody(path, cached))
      return
    }
    if (!root.rq) {
      cb({ error: "not ready" })
      return
    }
    var version = (root.loadVersions[id] || 0) + 1
    root.loadVersions[id] = version
    var saveVersion = root.saveVersions[id] || 0
    return root.rq.enqueue({ key: "load:" + path, mode: "dedupe", priority: 0, owner: root, label: "page" },
      function(ctx) { root.runScript(["page", id], "", ctx) },
      function(result) {
        if (!result || result.error) {
          cb(result || { error: "not loaded — the window closed" })
          return
        }
        searchCache.refresh()
        if (root.loadVersions[id] === version && (root.saveVersions[id] || 0) === saveVersion) {
          result = root.cacheBody(path, result)
        }
        cb(result)
      })
  }

  // A recording is fetched when someone plays it, never with its page: the
  // answer is { url } with the private cached file, or { error }.
  function recording(source, title, cb) {
    if (!root.rq) {
      cb({ error: "not ready" })
      return
    }
    root.rq.enqueue({ key: "recording:" + source, mode: "dedupe", priority: 0, owner: root, label: "recording" },
      function(ctx) { root.runScript(["recording", source, title], "", ctx) },
      function(result) {
        cb(result || { error: "the recording was not downloaded — the window closed" })
      })
  }

  // A save the lane never sent. Superseded means a newer save of the same
  // note carries this one's intent and answers for it: `{}`. Cancelled — the
  // lane emptied on sign-out, or this provider going — means nobody will, and
  // that is a failure the host must hear: an accepted save finishes or fails
  // out loud (business-requirements.md), never silently.
  function save(path, title, body, cb, options) {
    var id = idOf(path)
    if (root.pendingDeletes[id]) {
      cb({ error: "The note is being deleted." })
      return
    }
    if (root.noteReadOnly(path)) {
      cb({ error: "This notebook is shared with you as read-only." })
      return
    }
    if (!root.rq) {
      cb({ error: "not ready" })
      return
    }
    var pending = root.pendingPages[id]
    if (pending) {
      if (pending.operations.some(function(operation) { return operation.remove })) {
        cb({ error: "The note is being deleted." })
        return
      }
      pending.page = Object.assign({}, pending.page, { title: title })
      root.bodies[id] = { title: title, body: body, editable: true }
      root.pages = root.pages.map(function(page) { return page.id === id ? pending.page : page })
      root.rebuild()
      if (pending.error) {
        cb({ error: pending.error })
      } else {
        // Keep one current document during a slow create or a cooldown,
        // just as the lane replaces queued saves of an existing page.
        root.finishPendingOperations(pending, {})
        pending.operations.push({ title: title, body: body, callback: cb, options: options })
      }
      return
    }
    // The session captures this token with the displayed document. Provider
    // cache changes and discarded load callbacks cannot change a save's base.
    var payload = JSON.stringify({ title: title, body: body, view: options ? options.view : "",
                                   resolution: options ? options.resolution : undefined })
    var version = (root.saveVersions[id] || 0) + 1
    root.saveVersions[id] = version
    root.bodies[id] = { title: title, body: body, editable: true, version: "" }
    root.rq.enqueue({ key: "page:" + id, mode: "replace", priority: 0, owner: root, flush: true, label: "save" },
      function(ctx) { root.runScript(["update", id, "-"], payload, ctx) },
      function(result, info) {
        if (!result) {
          cb(root.unsentSave(info))
          return
        }
        if (result.error) {
          cb(result)
          return
        }
        searchCache.refresh()
        var latest = root.saveVersions[id] === version
        if (latest) {
          var page = root.pageAt(path)
          root.bodies[id] = Object.assign({}, result, { editable: true,
              version: page ? page.modified || "" : "" })
          root.pages = root.pages.map(function(row) {
            return row.id === id ? Object.assign({}, row, { title: result.title }) : row
          })
          root.rebuild()
        }
        cb(result)
        // The host reloads only after all saves finish and while the editor
        // has no newer edits. A later save keeps using its original view.
        if (latest && result.merged) {
          root.noteChanged(path)
        }
      })
  }

  function appendPage(pages, page) {
    var next = pages.filter(function(row) { return row.id !== page.id })
    var last = next.length - 1
    for (var i = 0; i < next.length; i++) {
      if (next[i].sectionId === page.sectionId) {
        last = i
      }
    }
    next.splice(last + 1, 0, page)
    return next
  }

  function create(target, cb) {
    if (!root.ready || !root.rq || target.indexOf("section:") !== 0) {
      if (cb) {
        cb({ error: "not ready" })
      }
      return
    }
    var section = target.substring(8)
    if (!root.sectionAt(section) || !root.bookWritable(root.sectionAt(section).notebookId)) {
      if (cb) {
        cb({ error: "This section is not available for new pages." })
      }
      return
    }
    var id = "draft-" + Date.now() + "-" + (++root.nextDraft)
    var pending = { page: { id: id, sectionId: section, title: "", modified: "" },
                    operations: [], error: "", handle: null }
    root.pendingPages = root.withEntry(root.pendingPages, id, pending)
    root.bodies[id] = { title: "", body: "", editable: true }
    root.inventoryRevision++
    root.pages = root.appendPage(root.pages, pending.page)
    root.revealPath(root.pathOf(id))
    root.rebuild()
    // Every Ctrl+N gets its own draft immediately. Remote creates in one
    // section stay ordered, so their final positions match the draft rows.
    pending.handle = root.rq.enqueue({ key: "create:" + target, mode: "append", priority: 0, owner: root, flush: true, label: "new page" },
      function(ctx) { root.runScript(["create", section, "-"], JSON.stringify({ title: "", body: "" }), ctx) },
      function(r) {
        root.finishCreation(id, pending, r || { error: "the page creation was cancelled", cancelled: true })
      })
    if (cb) {
      cb({ path: root.pathOf(id) })
    }
  }

  function finishPendingOperations(pending, result, removed) {
    var operations = pending.operations
    pending.operations = []
    for (var i = 0; i < operations.length; i++) {
      if (operations[i].callback) {
        operations[i].callback(operations[i].remove && removed ? {} : result)
      }
    }
  }

  function discardPendingPage(id) {
    root.pendingPages = root.withoutEntry(root.pendingPages, id)
    delete root.bodies[id]
    root.pages = root.pages.filter(function(page) { return page.id !== id })
    root.rebuild()
  }

  function finishCreation(id, pending, result) {
    if (result.error) {
      // Never re-sent: Graph may have made the page and lost the answer.
      pending.error = "The OneNote page could not be created: " + result.error +
                      " — copy its text elsewhere, then delete this draft"
      var removed = result.cancelled === true && pending.operations.some(function(operation) { return operation.remove })
      if (removed) {
        root.discardPendingPage(id)
      } else if (pending.operations.length === 0) {
        // Waiting saves and deletes report the failure themselves; with
        // none, the status line is the only place left to say it.
        root.statusRequested(pending.error)
      }
      root.finishPendingOperations(pending, { error: pending.error }, removed)
      return
    }
    var page = result.page
    var path = root.pathOf(page.id)
    var cached = root.bodies[id]
    var note = result.note
    root.pageAliases = root.withEntry(root.pageAliases, id, page.id)
    root.inventoryRevision++
    pageInventory.serial = Math.max(pageInventory.serial, result.pageListSerial || 0)
    root.pendingPages = root.withoutEntry(root.pendingPages, id)
    delete root.bodies[id]
    root.bodies[page.id] = Object.assign({}, cached, { view: note.view, version: page.modified || "" })
    // A listing can discover the real page before its create response arrives.
    // Replace the draft in place and remove that duplicate, retaining typed text.
    root.pages = root.pages.filter(function(row) { return row.id !== page.id }).map(function(row) {
      return row.id === id ? Object.assign({}, page, { title: cached.title }) : row
    })
    var deletion = root.pendingDeletes[id]
    if (deletion) {
      deletion.page = Object.assign({}, page, { title: cached.title })
      root.pendingDeletes = root.withEntry(root.withoutEntry(root.pendingDeletes, id), page.id, deletion)
    }
    var remembered = {}
    for (var book in root.lastPages) {
      remembered[book] = root.lastPages[book] === root.pathOf(id) ? path : root.lastPages[book]
    }
    root.lastPages = remembered
    root.notePathChanged(root.pathOf(id), path, note.view)
    var operations = pending.operations
    pending.operations = []
    for (var i = 0; i < operations.length; i++) {
      var operation = operations[i]
      if (operation.remove) {
        root.sendDelete(page.id, operation.deletion)
      } else {
        root.save(path, operation.title, operation.body, operation.callback,
                  Object.assign({}, operation.options || {}, { view: note.view }))
      }
    }
    root.rebuild()
    root.persistRequested()
  }

  function remove(path, cb) {
    var id = idOf(path)
    if (!root.rq || root.pendingDeletes[id]) {
      if (cb) {
        cb({ error: root.pendingDeletes[id] ? "The note is already being deleted." : "not ready" })
      }
      return
    }
    var pending = root.pendingPages[id]
    if (pending && pending.error) {
      root.discardPendingPage(id)
      if (cb) {
        cb({})
      }
      return
    }
    // A page the listing has not reached yet is deleted all the same: it
    // has no row to hide, and no position to restore it to.
    var page = root.pageAt(path)
    var order = page ? root.pages.filter(function(row) {
      return row.sectionId === page.sectionId
    }).map(function(row) { return row.id }) : []
    var deletion = { page: page, order: order }
    root.pendingDeletes = root.withEntry(root.pendingDeletes, id, deletion)
    root.inventoryRevision++
    root.rebuild()
    if (cb) {
      cb({ pending: true })
    }
    if (pending) {
      root.finishPendingOperations(pending, {})
      pending.operations.push({ remove: true, deletion: deletion, callback: function(result) {
        root.finishDeletion(root.idOf(path), deletion, result)
      } })
      pending.handle.cancel()
    } else {
      root.sendDelete(id, deletion)
    }
  }

  function restorePage(pages, deletion) {
    var page = deletion.page
    if (!page || pages.some(function(row) { return row.id === page.id })) {
      return pages
    }
    var next = pages.slice()
    var ids = next.map(function(row) { return row.id })
    var order = deletion.order.map(function(id) { return root.pageAliases[id] || id })
    var position = order.indexOf(page.id)
    for (var i = position + 1; i < order.length; i++) {
      var after = ids.indexOf(order[i])
      if (after >= 0) {
        next.splice(after, 0, page)
        return next
      }
    }
    for (var j = position - 1; j >= 0; j--) {
      var before = ids.indexOf(order[j])
      if (before >= 0) {
        next.splice(before + 1, 0, page)
        return next
      }
    }
    return root.appendPage(next, page)
  }

  // The host reports the outcome: it holds the note's unsaved text, and
  // says the failure along with restoring it.
  function finishDeletion(id, deletion, result) {
    if (root.pendingDeletes[id] !== deletion) {
      return
    }
    root.pendingDeletes = root.withoutEntry(root.pendingDeletes, id)
    root.inventoryRevision++
    if (result.error) {
      root.pages = root.restorePage(root.pages, deletion)
    } else {
      root.pages = root.pages.filter(function(page) { return page.id !== id })
      pageInventory.serial = Math.max(pageInventory.serial, result.pageListSerial || 0)
      delete root.bodies[id]
    }
    root.noteDeletionFinished(root.pathOf(id), result)
    root.rebuild()
  }

  function sendDelete(id, deletion) {
    // The page's own key, and replace: a delete supersedes a save of the same
    // page that has not gone yet (there is nothing left to save it into), and
    // queues behind one that has — per-key order means no resurrection, and
    // no lost answer either way.
    root.rq.enqueue({ key: "page:" + id, mode: "replace", priority: 0, owner: root, flush: true, label: "delete" },
      function(ctx) { root.runScript(["delete", id], "", ctx) },
      function(r) {
        root.finishDeletion(id, deletion, r || { error: "the delete was cancelled" })
      })
  }

  // Polling, on a diet. Every third tick (so once a minute) this costs at
  // most two requests: the open page, and the pages of the section it is in.
  // It used to re-list *every* expanded section — up to eleven requests a
  // minute, which is 660 an hour against a budget of 400, so polling alone
  // could exhaust the account. Other sections come back with the periodic
  // listing (which now fetches only what changed) or a manual refresh.
  property int pollTick: 0
  function poll(currentPath) {
    if (!root.ready || !root.rq) {
      return
    }
    root.pollTick++
    // Everything the poll no longer looks at comes back here instead: every
    // fifth minute the account is re-listed. Unchanged section timestamps
    // skip page requests; OneDrive metadata supplies section order. Under
    // --max-age the complete cached listing avoids both kinds of request.
    if (root.pollTick % 15 === 0) {
      root.listPages(false)
    }
    if (root.pollTick % 3 !== 0) {
      return
    }
    var mine = currentPath && currentPath.indexOf(root.id + ":") === 0
    if (mine && (root.pendingPages[root.idOf(currentPath)] || root.pendingDeletes[root.idOf(currentPath)])) {
      return
    }
    if (mine) {
      root.rq.enqueue({ key: "check:" + currentPath, mode: "dedupe", priority: 1, owner: root, label: "check" },
        function(ctx) { root.runScript(["page", root.idOf(currentPath), "--check"], "", ctx) },
        function(r) {
          if (r && !r.error && !r.deferred) {
            root.applyCheck(currentPath, r)
          }
        })
    }
    var page = mine ? root.pageAt(currentPath) : null
    if (!page || !page.sectionId) {
      return
    }
    pageInventory.request(page.sectionId, false, true)
  }

  // Graph does not reliably bump a page's lastModifiedDateTime, so the open
  // page is compared by its text instead.
  function applyCheck(path, r) {
    searchCache.refresh()
    var id = root.idOf(path), old = root.bodies[id]
    if (old && old.body === r.body && old.title === r.title && old.editable === r.editable) {
      return
    }
    // A poll never changes the active editor's baseline. A subsequent load
    // asks Python for a new view, or restores the persisted recovery draft.
    delete root.bodies[id]
    root.noteChanged(path)
  }

  // The cache, read straight off disk so the sidebar fills instantly — and
  // still fills while the account is parked, which is the point of reading it
  // outside the lane.
  readonly property bool listing: cachedProc.running || root.listPending || pageInventory.busy
  onListingChanged: root.rebuild()
  function readCached() {
    if (cachedProc.running) {
      return
    }
    cachedProc.session = root.ms ? root.ms.cacheSession : ""
    cachedProc.revision = root.inventoryRevision
    cachedProc.start()
  }
  ProcessTask {
    id: cachedProc
    property string session: ""
    property int revision: 0
    environment: root.ms ? root.ms.env : ({})
    command: ["python3", root.script, "list", "--cached"]
    raw: true
    onFinished: function(result) {
      if (cachedProc.session !== (root.ms ? root.ms.cacheSession : "") || cachedProc.revision !== root.inventoryRevision) {
        return
      }
      var res = root.parse(result.text || "")
      if (!res.error) {
        root.applyInventory(res)
        root.listed(res)
      }
      root.rebuild()
    }
  }
}
