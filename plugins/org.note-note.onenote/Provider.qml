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
                                "h1", "h2", "h3", "p", "ul", "ol", "listStyles", "todo", "indent", "outdent",
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
  property var creatingSections: ({}) // stand-in id -> section listed before OneNote has made it
  property var deletingSections: ({}) // section id -> true while its delete runs, the section hidden
  property var pageOrderWrites: ({}) // section id -> the newest order asked for it, until its write answers
  property var heldPageOrders: ({})  // section id -> an order waiting for its pages being made or deleted
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
  // A page's ID in its section's order: the path it was first listed under.
  // A page made here keeps its draft's, so an order asked for while OneNote
  // was making it, and shown over the rows until it is saved, still names
  // it once the page has an ID of its own (idOf resolves either).
  function orderId(id) {
    for (var draft in root.pageAliases) {
      if (root.pageAliases[draft] === id) {
        return root.pathOf(draft)
      }
    }
    return root.pathOf(id)
  }
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
  // A listing's sections with those still being created, which a listing
  // made before OneNote had them does not hold.
  function listedSections(sections) {
    var listed = sections.slice()
    for (var id in root.creatingSections) {
      listed.push(root.creatingSections[id])
    }
    return listed
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

  // What a section's page order arranges: its parent pages, each carrying
  // its subpages, as the list shows them. A page being deleted has left
  // it, and a draft OneNote could not make is no page of the section; one
  // still being made is, at the end, where OneNote puts a new page.
  function orderedPage(page) {
    var pending = root.pendingPages[page.id]
    return page.level === 0 && !root.pendingDeletes[page.id] && !(pending && pending.error)
  }
  function parentPageIds(sectionId) {
    return root.sectionPages(sectionId).filter(function(page) {
      return root.orderedPage(page)
    }).map(function(page) {
      return page.id
    })
  }

  function bookPages(bookId, pages) {
    return pages.filter(function(page) {
      var section = root.sectionAt(page.sectionId)
      return section && section.notebookId === bookId
    })
  }

  // A section is a .one file in its owner's OneDrive, which its page order,
  // rename and delete write: a personal notebook this account owns, or one
  // shared with it for editing. web_session.py's writable_notebook()
  // enforces the same rule.
  function sectionFileWritable(bookId) {
    var book = root.onNotebooks.find(function(candidate) {
      return candidate.id === bookId
    })
    var role = book ? (book.userRole || "").toLowerCase() : ""
    return (role === "owner" || role === "contributor")
      && /^0-[0-9a-f]{16}!(?:[0-9]+|s[0-9a-f]{32})$/i.test(book.id)
  }

  // Page ordering is the notebook's to allow, and nothing the section is
  // doing turns it off: not a listing of its pages again, not an order still
  // saving, not a page being made or deleted. An order asked for meanwhile
  // is queued (reorder). The section needs all its pages listed (a first
  // listing under way, or one cut at the limit, has only some), its
  // hierarchy, which a list from before pages carried their level lacks
  // until the section is opened and listed again, and two parent pages.
  function pageOrderingAvailable(section) {
    if (!root.ready || !root.ms.hasScope("Files.ReadWrite") || !root.sectionFileWritable(section.notebookId)
        || pageInventory.partialSections.indexOf(section.id) >= 0) {
      return false
    }
    return root.parentPageIds(section.id).length > 1 && root.sectionPages(section.id).every(function(page) {
      return typeof page.level === "number" && page.level >= 0 && page.level <= 2
        && Math.floor(page.level) === page.level
    })
  }
  // A page's right-click menu (PROVIDERS.md, `menu`) where the notebook can
  // be written: the app's own delete.
  readonly property var noteMenu: [{ id: "delete", title: "Delete", icon: "󰆴", command: "deleteNote" }]

  // One notebook's sections with their pages and New Note rows when open,
  // starting at `level`: 0 when the notebook is a tab
  // of its own, 1 when it sits under its own tree row.
  function bookRows(bookId, level) {
    var rows = []
    for (var k = 0; k < root.onSections.length; k++) {
      var sec = root.onSections[k]
      if (sec.notebookId !== bookId || root.deletingSections[sec.id]) {
        continue
      }
      var secOpen = root.expanded.indexOf(sec.id) >= 0
      var pages = root.sectionPages(sec.id).filter(function(page) {
        return !root.pendingDeletes[page.id]
      })
      rows.push({ kind: "tree", path: sec.id, title: sec.name, level: level,
                  expanded: secOpen, count: pages.length, menu: root.sectionMenu(sec) })
      if (!secOpen) {
        continue
      }
      var orderable = root.pageOrderingAvailable(sec)
      var pageMenu = root.bookWritable(bookId) ? root.noteMenu : []
      for (var p = 0; p < pages.length; p++) {
        var pg = pages[p]
        rows.push({ kind: "note", path: pathOf(pg.id), title: pg.title, preview: "", menu: pageMenu,
                    level: level + 1 + (pg.level || 0),
                    reorder: orderable && root.orderedPage(pg)
                      ? { scope: "pages:" + sec.id, id: root.orderId(pg.id), descendants: true } : null,
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
  // A notebook's tab has its New section button; the one tab holding every
  // notebook has New section on each notebook row's menu instead.
  function accountActions(bookId) {
    var actions = []
    if (bookId && root.bookWritable(bookId)) {
      actions.push({ path: "newSection", title: "New section", icon: "󰉗", prompt: "Section name" })
    }
    actions.push({ path: "logout", title: "Sign out" + (ms.account ? " (" + ms.account + ")" : ""), icon: "󰍃" })
    return actions
  }

  readonly property var notebookMenu: [{ id: "newSection", title: "New section", icon: "󰉗", prompt: "Section name" }]

  // `notes` on a section is its searchable whole, fold state ignored: rows
  // only carry the pages of expanded sections, and a search (and the hit
  // count on the tab) must see the closed ones too.
  function rebuild() {
    var account = accountRows(), books = account ? [] : bookList()
    var visiblePages = root.pages.filter(function(page) {
      return !root.pendingDeletes[page.id] && !root.deletingSections[page.sectionId]
    })
    if (root.notebookTabs && books.length > 0) {
      // A tab per notebook. No colour: each takes a pastel from its own
      // name, which is what tells Work from Personal apart (the logo keeps
      // them OneNote's); the account footer appears on every tab, since any of
      // them is equally the account's.
      root.sections = books.map(function(b) {
        var pgs = root.bookPages(b.id, visiblePages)
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
        rows.push({ kind: "tree", path: books[b].id, title: books[b].name, level: 0,
                    expanded: open, count: root.bookPages(books[b].id, visiblePages).length,
                    menu: root.bookWritable(books[b].id) ? root.notebookMenu : [] })
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
    if (obj.expanded instanceof Array) {
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
    // A section still being created has no pages to fetch yet.
    if (i < 0 && root.sectionAt(id) && !root.creatingSections[id]) {
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

  // `sectionKey` is the tab a footer action belongs to: a notebook's ID,
  // where the footer offers New section.
  function action(id, value, sectionKey) {
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
    } else if (id === "newSection") {
      root.createSection(sectionKey, value, function(result) {
        if (result.error) {
          root.statusRequested("OneNote: " + result.error)
        }
      })
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
  // From a notebook tab's footer button or a notebook row's menu, both
  // after the host asked for the name (`prompt`). Listed at once under a
  // stand-in id while OneNote makes it, it takes no page, rename or delete
  // until then (create, sectionMenu). `done` hears { error } for a section
  // that cannot be asked for, or {} once it is listed; OneNote refusing it
  // takes it off the list and says why.
  function createSection(notebook, name, done) {
    var n = name.trim()
    if (!n) {
      done({ error: "a section needs a name" })
      return
    }
    if (!root.rq) {
      done({ error: "OneNote is not signed in" })
      return
    }
    var draft = { id: "draft-section-" + Date.now() + "-" + (++root.nextDraft), notebookId: notebook,
                  name: n, notebook: root.notebookName(notebook) }
    root.creatingSections = root.withEntry(root.creatingSections, draft.id, draft)
    root.onSections = root.onSections.concat([draft])
    var exp = root.expanded.slice()
    if (exp.indexOf(notebook) < 0) {
      exp.push(notebook)
    }
    exp.push(draft.id)
    root.expanded = exp
    root.rebuild()
    done({})
    root.rq.enqueue({ key: "section:" + notebook, mode: "append", priority: 0, owner: root,
                      flush: true, label: "new section" },
      function(ctx) { root.runScript(["create-section", notebook, "-"], JSON.stringify({ name: n }), ctx) },
      function(r, info) {
        root.creatingSections = root.withoutEntry(root.creatingSections, draft.id)
        if (!r || r.error) {
          root.onSections = root.onSections.filter(function(other) { return other.id !== draft.id })
          root.expanded = root.expanded.filter(function(id) { return id !== draft.id })
          root.rebuild()
          root.statusRequested(root.name + ": " + root.sectionFailure(r, info, "section creation"))
          return
        }
        var sct = r.section
        root.supersedeOrderPass()
        pageInventory.serial = Math.max(pageInventory.serial, r.pageListSerial || 0)
        if (!sct.notebook) {
          sct.notebook = root.notebookName(sct.notebookId)
        }
        // A listing may have brought the section already: that row goes, and
        // the section takes the stand-in's place.
        root.onSections = root.onSections.filter(function(other) {
          return other.id !== sct.id
        }).map(function(other) {
          return other.id === draft.id ? sct : other
        })
        root.expanded = root.expanded.map(function(id) {
          return id === draft.id ? sct.id : id
        })
        root.rebuild()
        root.persistRequested()
        root.statusRequested("Section created")
      })
  }

  // ── section refresh, rename and delete ──────────────────────────────
  // Refresh lists a section's pages again at once, whatever its timestamp
  // says: besides the open page's, a section is listed again only when the
  // periodic listing finds its timestamp moved (poll). Every section
  // OneNote has made offers it, disabled while a page order this app wrote
  // there may not reach Graph yet (PageInventory.orderSettling): a listing
  // then could bring the old order back.
  // A section of a personal notebook is a .one file in its owner's OneDrive,
  // named after it: renaming or deleting the file renames the section in
  // every OneNote app, or sends it to the recycle bin (onenote.py,
  // rename-section and delete-section). Those two are offered where that
  // file can be written (sectionFileWritable); the rows that carry this
  // menu are listed only for an account that may write files (accountRows).
  function sectionMenu(sec) {
    if (root.creatingSections[sec.id]) {
      return []
    }
    var menu = [{ id: "refresh", title: "Refresh", icon: "󰑐", enabled: !pageInventory.orderSettling(sec.id) }]
    if (root.sectionFileWritable(sec.notebookId)) {
      menu.push({ id: "rename", title: "Rename", icon: "󰑕", rename: true },
                { id: "delete", title: "Delete", icon: "󰆴",
                  confirm: "Delete the section “" + sec.name + "” and everything in it? It goes to your OneDrive recycle bin." })
    }
    return menu
  }

  // A page of the section may still be saving, so a section's request waits
  // for the writes accepted before it.
  property var afterWrites: []
  onWriteBusyChanged: {
    if (!root.writeBusy) {
      var waiting = root.afterWrites
      root.afterWrites = []
      waiting.forEach(function(run) {
        run()
      })
    }
  }

  function rowAction(path, id, value, cb) {
    if (id === "newSection") {
      root.createSection(path, value, cb)
      return
    }
    var sec = root.sectionAt(path)
    if (sec && id === "refresh") {
      // Nothing the user wrote moves or goes with a listing, so the open
      // note need not wait for it: the pages show as they arrive.
      pageInventory.request(sec.id, true, true)
      cb({})
      return
    }
    var run = null
    if (sec && id === "rename") {
      // Shown at once as typed. renameSection then shows the name onenote.py
      // stored, cut to OneNote's length, or puts the old one back if
      // OneNote refuses the new one.
      root.setSectionName(sec.id, value.trim())
      run = function() { root.renameSection(sec, value, cb) }
    } else if (sec && id === "delete") {
      // Off the list at once, the host told which notes went with it; the
      // request follows (deleteSection), and a section OneNote keeps comes
      // back.
      var paths = root.sectionPages(sec.id).map(function(page) {
        return root.pathOf(page.id)
      })
      root.deletingSections = root.withEntry(root.deletingSections, sec.id, true)
      root.rebuild()
      cb({ pending: true, removed: paths })
      run = function() { root.deleteSection(sec, paths) }
    }
    if (!run) {
      cb({ error: "unknown section action" })
    } else if (root.writeBusy) {
      root.afterWrites = root.afterWrites.concat([run])
    } else {
      run()
    }
  }

  // A section job's answer as rowAction's callback wants it.
  function sectionFailure(r, info, verb) {
    if (r) {
      return r.error
    }
    return info.cancelled ? "the " + verb + " was cancelled" : "the " + verb + " was not completed"
  }

  function setSectionName(id, name) {
    root.onSections = root.onSections.map(function(other) {
      return other.id === id ? Object.assign({}, other, { name: name }) : other
    })
    root.rebuild()
  }

  // `sec` is the section as it was before rowAction showed the new name.
  function renameSection(sec, name, cb) {
    if (!root.rq) {
      root.setSectionName(sec.id, sec.name)
      cb({ error: "OneNote is not signed in" })
      return
    }
    root.rq.enqueue({ key: "section:" + sec.id, mode: "append", priority: 0, owner: root,
                      flush: true, label: "rename section" },
      function(ctx) { root.runScript(["rename-section", sec.id, "-"], JSON.stringify({ name: name }), ctx) },
      function(r, info) {
        if (r && r.gone) {
          cb({ error: r.error, removed: root.dropSection(sec, r) })
          return
        }
        if (!r || r.error) {
          root.setSectionName(sec.id, sec.name)
          cb({ error: root.sectionFailure(r, info, "rename") })
          return
        }
        root.supersedeOrderPass()
        pageInventory.serial = Math.max(pageInventory.serial, r.pageListSerial || 0)
        root.setSectionName(sec.id, r.name)
        root.statusRequested("Section renamed")
        cb({})
      })
  }

  // The request for a section rowAction has taken off the list already,
  // with its pages, `paths`: OneNote deleting it drops it for good, and
  // failing to brings it back. Either way the host hears each page's
  // outcome (noteDeletionFinished), which keeps or gives back its unsaved
  // text.
  function deleteSection(sec, paths) {
    if (!root.rq) {
      root.finishSectionDeletion(sec, paths, { error: "OneNote is not signed in" })
      return
    }
    root.rq.enqueue({ key: "section:" + sec.id, mode: "append", priority: 0, owner: root,
                      flush: true, label: "delete section" },
      function(ctx) { root.runScript(["delete-section", sec.id], "", ctx) },
      function(r, info) {
        if (!r || r.error) {
          root.finishSectionDeletion(sec, paths, { error: root.sectionFailure(r, info, "delete") })
          return
        }
        root.dropSection(sec, r)
        root.statusRequested("Section deleted")
        root.finishSectionDeletion(sec, paths, {})
      })
  }

  function finishSectionDeletion(sec, paths, result) {
    root.deletingSections = root.withoutEntry(root.deletingSections, sec.id)
    root.rebuild()
    // With no pages, no page's outcome says it failed.
    if (result.error && paths.length === 0) {
      root.statusRequested(root.name + ": " + result.error)
    }
    paths.forEach(function(path) {
      root.noteDeletionFinished(path, result)
    })
  }

  // Takes a section that is gone off the model, as onenote.py's answer
  // (forget_section) took it off the cache. Returns its pages' paths: the
  // listed ones, and any the cache knew that were not listed yet.
  function dropSection(sec, r) {
    root.supersedeOrderPass()
    pageInventory.serial = Math.max(pageInventory.serial, r.pageListSerial || 0)
    var gone = root.pages.filter(function(page) {
      return page.sectionId === sec.id
    }).map(function(page) {
      return page.id
    })
    var cached = r.pages || []
    cached.forEach(function(id) {
      if (gone.indexOf(id) < 0) {
        gone.push(id)
      }
    })
    gone.forEach(function(id) {
      delete root.bodies[id]
    })
    // Its drafts OneNote could not make go with it: the host was told they
    // went, and no listing would show their section again.
    var drafts = {}
    for (var draftId in root.pendingPages) {
      if (root.pendingPages[draftId].page.sectionId !== sec.id) {
        drafts[draftId] = root.pendingPages[draftId]
      }
    }
    root.pendingPages = drafts
    root.pages = root.pages.filter(function(page) { return page.sectionId !== sec.id })
    root.onSections = root.onSections.filter(function(other) { return other.id !== sec.id })
    root.expanded = root.expanded.filter(function(id) { return id !== sec.id })
    root.inventoryRevision++
    root.rebuild()
    root.persistRequested()
    return gone.map(root.pathOf)
  }

  // ── running the script ──────────────────────────────────────────────
  // The search cache's runs, outside the lane (SearchCache.qml).
  ProcessRunner { id: searchRunner }
  function runLocal(args, payload, callback) {
    return root.runProcess(searchRunner, args, payload, callback)
  }

  // A drop is taken however soon it follows the last, whatever the section
  // is doing (pageOrderingAvailable). Its order waits only while OneNote has
  // still to answer for a page being made or deleted in the section: the
  // order names a made page by the ID its creation gives it, and a page
  // being deleted may be in OneNote until then. The writes it waits on keep
  // the app open meanwhile (writeBusy). A section's order writes run one at
  // a time, and a newer order replaces one still waiting, held or queued,
  // since it holds all of it. A write is checked against the order known
  // when it starts: the one the write before it left, or the pages listed
  // before a listing still under way, which OneNote checks in turn. Only the
  // newest order's failure re-reads the section: an older write's leaves it
  // to the newer one, whose own check finds what OneNote holds.
  function reorder(scope, paths, callback) {
    var sectionId = scope.indexOf("pages:") === 0 ? scope.substring(6) : ""
    var section = root.sectionAt(sectionId)
    if (!section || !root.rq || !root.pageOrderingAvailable(section)) {
      callback({ error: "This section's pages cannot be reordered until they are all listed" })
      return
    }
    var wanted = paths.map(function(path) {
      return root.idOf(path)
    })
    if (!Ordering.isPermutation(root.parentPageIds(sectionId), wanted)) {
      callback({ error: "The pages changed — try reordering again" })
      return
    }
    var replaced = root.heldPageOrders[sectionId]
    root.pageOrderWrites = root.withEntry(root.pageOrderWrites, sectionId, paths)
    root.heldPageOrders = root.withEntry(root.heldPageOrders, sectionId, { paths: paths, callback: callback })
    if (replaced) {
      // The newer order holds all of this one and answers for it.
      replaced.callback({})
    }
    root.sendHeldOrder(sectionId)
  }

  // Whether OneNote has still to answer for a page being made or deleted in
  // the section.
  function pagesInFlight(sectionId) {
    return root.sectionPages(sectionId).some(function(page) {
      var pending = root.pendingPages[page.id]
      return (pending && !pending.error) || !!root.pendingDeletes[page.id]
    })
  }

  // Asked again whenever a page of the section has been made or deleted.
  function sendHeldOrder(sectionId) {
    var held = root.heldPageOrders[sectionId]
    if (!held || root.pagesInFlight(sectionId)) {
      return
    }
    root.heldPageOrders = root.withoutEntry(root.heldPageOrders, sectionId)
    root.writePageOrder(sectionId, held.paths, held.callback)
  }

  function writePageOrder(sectionId, paths, callback) {
    root.rq.enqueue({ key: "page-order:" + sectionId, mode: "replace", priority: 0,
                      owner: root, flush: true, label: "page order" },
      function(ctx) {
        var expected = root.parentPageIds(sectionId)
        var wanted = paths.map(function(path) {
          return root.idOf(path)
        })
        if (!Ordering.isPermutation(expected, wanted)) {
          ctx.done({ error: "The pages changed — try reordering again" })
          return
        }
        root.runScript(["reorder-pages", "-"], JSON.stringify({ sectionId: sectionId,
                       expected: expected, order: wanted }), ctx)
      },
      function(result, info) {
        if (!result && info.superseded) {
          // The newer order holds all of this one and answers for it.
          callback({})
          return
        }
        var newest = root.pageOrderWrites[sectionId] === paths
        if (newest) {
          root.pageOrderWrites = root.withoutEntry(root.pageOrderWrites, sectionId)
        }
        var answer = result || { error: "The order was not saved — the request was cancelled" }
        if (!answer.error) {
          root.applyInventory(answer)
        } else if (newest) {
          // The response might have been lost after a successful revision.
          // Refresh canonical Graph order rather than retrying the write.
          pageInventory.request(sectionId, true, true)
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
          if (r.listingWarnings instanceof Array && r.listingWarnings.length) {
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
    if (result.notebooks instanceof Array) {
      root.onNotebooks = result.notebooks
    }
    if (result.sections instanceof Array) {
      root.onSections = root.listedSections(result.sections)
    }
    if (result.pages instanceof Array) {
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
    preferredSections: root.expanded.filter(function(id) { return !!root.sectionAt(id) && !root.creatingSections[id] })
    onLoaded: function(result) {
      root.applyInventory(result)
      root.rebuild()
    }
    onFailed: function(message) {
      root.listingError = message
      root.statusRequested("OneNote: " + message)
      root.rebuild()
    }
    onSettled: root.rebuild()
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
      if (result.sections instanceof Array) {
        root.onSections = root.listedSections(result.sections)
      }
      if (result.sectionOrderWarnings instanceof Array && result.sectionOrderWarnings.length) {
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
    pages: root.pages.filter(function(page) {
      return !root.pendingPages[page.id] && !root.pendingDeletes[page.id] && !root.deletingSections[page.sectionId]
    })
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
      root.trackedSections = ({})
      root.changedSections = ({})
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
    if (root.creatingSections[section]) {
      if (cb) {
        cb({ error: "This section is still being created — try again in a moment." })
      }
      return
    }
    var id = "draft-" + Date.now() + "-" + (++root.nextDraft)
    // A top-level page at the end of its section, which is where OneNote
    // puts a new one, so the section's order takes it in at once.
    var pending = { page: { id: id, sectionId: section, title: "", modified: "", level: 0 },
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
      } else {
        // The draft stays, out of its section's order (orderedPage).
        root.rebuild()
        if (pending.operations.length === 0) {
          // Waiting saves and deletes report the failure themselves; with
          // none, the status line is the only place left to say it.
          root.statusRequested(pending.error)
        }
      }
      root.finishPendingOperations(pending, { error: pending.error }, removed)
      root.sendHeldOrder(pending.page.sectionId)
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
    root.sendHeldOrder(page.sectionId)
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
    // A page the listing had not reached was in no section's order.
    if (deletion.page) {
      root.sendHeldOrder(deletion.page.sectionId)
    }
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

  // Polling, on a diet. Every third tick (so once a minute) this asks
  // OneDrive which section files changed (onenote.py, changes): one request
  // for every notebook the account owns, and none of OneNote's budget. Only
  // while the open page's section changed does it ask for the page and list
  // the section: two requests while the page is unchanged and the section
  // holds at most a hundred pages. A page that did change also costs its
  // list levels and the images not cached yet (onenote.py, read_page). A
  // section OneDrive does not track, in a notebook shared with the account,
  // is asked for every minute. It used to re-list *every* expanded section —
  // up to eleven requests a minute, which is 660 an hour against a budget of
  // 400, so polling alone could exhaust the account. Other sections come
  // back with the periodic listing (which now fetches only what changed) or
  // their menu's Refresh (sectionMenu).
  property int pollTick: 0
  property var trackedSections: ({})  // section id -> true: OneDrive reports its changes
  property var changedSections: ({})  // section id -> when OneDrive last reported its file changed (ms)
  // Graph shows a change up to about a minute and a half after OneDrive
  // reports it (docs/onenote-changes.md), so a section is checked for this
  // long after its last change.
  readonly property int changeSettleMs: 150000
  function poll(currentPath) {
    if (!root.ready || !root.rq) {
      return
    }
    root.pollTick++
    // Everything the poll no longer looks at comes back here instead: every
    // fifth minute the account listing is asked for. Unchanged section
    // timestamps skip page requests; OneDrive metadata supplies section
    // order. Under --max-age (listPages) a complete cached listing under ten
    // minutes old answers with no request of either kind, and a listing is
    // stamped a few seconds after the tick that asked for it, so a steady
    // run lists the account again at every third ask: about every fifteen
    // minutes.
    if (root.pollTick % 15 === 0) {
      root.listPages(false)
    }
    if (root.pollTick % 3 !== 0) {
      return
    }
    var mine = currentPath && currentPath.indexOf(root.id + ":") === 0
    if (!mine || root.pendingPages[root.idOf(currentPath)] || root.pendingDeletes[root.idOf(currentPath)]) {
      return
    }
    root.rq.enqueue({ key: "changes", mode: "dedupe", priority: 1, owner: root, label: "changes" },
      function(ctx) { root.runScript(["changes"], "", ctx) },
      function(r) {
        if (!r) {
          return
        }
        root.noteChanges(r)
        var page = root.pageAt(currentPath)
        if (!page || root.sectionChanging(page.sectionId)) {
          root.checkPage(currentPath, page)
        }
      })
  }

  // An error, a pause or an answer without its two lists leaves every
  // section untracked until the next answer: each is polled as before.
  function noteChanges(r) {
    if (r.error || r.deferred || !(r.tracked instanceof Array) || !(r.changed instanceof Array)) {
      root.trackedSections = ({})
      return
    }
    var tracked = {}
    for (var i = 0; i < r.tracked.length; i++) {
      tracked[r.tracked[i]] = true
    }
    var changed = Object.assign({}, root.changedSections)
    var now = Date.now()
    for (var j = 0; j < r.changed.length; j++) {
      changed[r.changed[j]] = now
    }
    root.trackedSections = tracked
    root.changedSections = changed
  }

  function sectionChanging(sectionId) {
    return !root.trackedSections[sectionId] || Date.now() - (root.changedSections[sectionId] || 0) < root.changeSettleMs
  }

  function checkPage(path, page) {
    root.rq.enqueue({ key: "check:" + path, mode: "dedupe", priority: 1, owner: root, label: "check" },
      function(ctx) { root.runScript(["page", root.idOf(path), "--check"], "", ctx) },
      function(r) {
        if (r && !r.error && !r.deferred) {
          root.applyCheck(path, r)
        }
      })
    if (page && page.sectionId) {
      pageInventory.request(page.sectionId, false, true)
    }
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
