import "../../services/platform"
import QtQuick
import "../../services/processes"
import "../../services/providers"

// Microsoft Sticky Notes: items in the Outlook mailbox's Notes folder, read
// and written online through Graph (sticky.py). Needs services.microsoft.
LaneProvider {
  id: root

  readonly property string id: "sticky"
  readonly property string name: "Sticky Notes"
  readonly property url logo: Qt.resolvedUrl("logo.svg")
  readonly property bool markdown: false
  readonly property bool hasTitle: false      // subject == first line
  readonly property bool canCreate: true
  readonly property bool canDelete: true
  readonly property bool canReorder: false
  readonly property bool canCreateSection: false
  readonly property var microsoftScopes: ["Mail.ReadWrite"]
  // This provider's own app registration: an Entra public client for
  // personal and work accounts, registered by the author, that every user
  // of Sticky Notes here signs in through. OneNote has one of its own.
  readonly property string microsoftClientId: "867770a1-477d-4864-9e09-8e3019ca336c"

  readonly property string dir: Platform.localPath(Qt.resolvedUrl(".")).replace(/\/$/, "")
  script: dir + "/sticky.py"
  // Mail's limits are far above OneNote's, so this lane exists mostly to
  // keep sticky notes moving *while* OneNote is parked: separate keys,
  // separate cooldowns (providers/PROVIDERS.md).
  laneKey: "graph-mail"
  Component.onCompleted: {
    if (services && services.microsoft) {
      root.ms = services.microsoft.create(root.id, root.microsoftScopes, root.microsoftClientId)
    }
  }

  property var notes: []        // [{ id, title, body, modified }]
  readonly property bool ready: ms && ms.signedIn && ms.hasScope("Mail.ReadWrite")

  function idOf(path) { return path.substring(root.id.length + 1) }
  function pathOf(id) { return root.id + ":" + id }
  function noteAt(path) {
    var id = idOf(path)
    for (var i = 0; i < root.notes.length; i++) {
      if (root.notes[i].id === id) {
        return root.notes[i]
      }
    }
    return null
  }
  function previewOf(body) {
    var lines = body.split("\n")
    for (var i = 0; i < lines.length; i++) {
      var l = lines[i].replace(/^[#>\-\*\s]+/, "").replace(/[*_`]/g, "").trim()
      if (l) {
        return l
      }
    }
    return ""
  }

  function rebuild() {
    var rows = []
    var footerActions = []
    if (!ms || !ms.configured) {
      rows.push({ kind: "action", path: "unavailable", title: "Not available in this build", icon: "󰒓" })
    } else if (!ms.signedIn) {
      rows.push({ kind: "action", path: "login", title: ms.loggingIn ? "Cancel signing in…" : "Sign in to Microsoft…", icon: ms.loggingIn ? "󰅖" : "󰊻" })
    } else if (!ms.hasScope("Mail.ReadWrite")) {
      rows.push({ kind: "action", path: "relogin", title: ms.loggingIn ? "Cancel signing in…" : "Sign in again to enable Sticky Notes…", icon: ms.loggingIn ? "󰅖" : "󰊻" })
    } else {
      for (var i = 0; i < root.notes.length; i++) {
        rows.push({ kind: "note", path: pathOf(root.notes[i].id), title: "", preview: previewOf(root.notes[i].body), fixed: true, version: root.notes[i].modified || "", modified: root.notes[i].modified || "" })
      }
      footerActions.push({ path: "newNote", title: "New Note", icon: "󰐕", shortcut: "newNote" })
      footerActions.push({ path: "logout", title: "Sign out" + (ms.account ? " (" + ms.account + ")" : ""), icon: "󰍃" })
    }
    // The sticky-note yellow, which is recognisable where Microsoft's
    // corporate purple is not. "Sticky Notes" because a tab is narrow.
    root.sections = [{ key: "sticky", name: "Sticky Notes", color: "#F5D33F", rows: rows, footerActions: footerActions }]
    root.updated()
  }

  function crumb(path) { return "Microsoft Sticky Notes" }
  function createTargetFor(path) { return root.ready ? "new" : "" }

  function action(id) {
    if (!ms) {
      return
    }
    if (id === "newNote" && root.ready) {
      root.host.newNote(root.id, "new")
    } else if (id === "login") {
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
      root.noticeRequested("Sign out of Sticky Notes?",
        "You'll need to sign in again" + (ms.account ? " as " + ms.account : "") + " to keep using Sticky Notes.", "",
        [{ label: "Sign out", action: function() { root.noticeCleared(); ms.logout() } },
         { label: "Cancel", action: function() { root.noticeCleared() } }])
    } else if (id === "unavailable") {
      root.noticeRequested("Microsoft sign-in is not configured in this build",
        "This copy of Note Note has no app registration for Sticky Notes built in (microsoftClientId in providers/sticky/Provider.qml), so nobody can sign in yet.", "", [])
    }
  }

  function refresh() {
    if (!root.ready) {
      root.notes = []
      rebuild()
      return
    }
    cachedProc.start()       // a local file: instant, and never queued
    root.listNotes()
  }

  // One listing request, deduped: open() and the account's own updated()
  // both ask, and one request answers both.
  function listNotes() {
    if (!root.rq || !root.ready) {
      return
    }
    root.rq.enqueue({ key: "list", mode: "dedupe", priority: 1, owner: root, label: "listing" },
      function(ctx) { root.runScript(["list"], "", ctx) },
      function(r) {
        if (!r) {
          return
        }
        if (r.error) {
          root.statusRequested("Sticky Notes: " + r.error)
          if (/not signed in|expired/.test(r.error) && root.ms) {
            root.ms.refresh()
          }
        } else if (Array.isArray(r.notes)) {
          root.notes = r.notes
        }
        root.rebuild()
      })
  }

  // Content search, answered from memory: the listing already carries every
  // note's whole body (a sticky note is small), so nothing is fetched. The
  // host matches the first line itself (the row's preview); this adds the
  // lines below it.
  function search(query, cb) {
    var q = query.toLowerCase(), paths = []
    for (var i = 0; i < root.notes.length; i++) {
      if ((root.notes[i].body || "").toLowerCase().indexOf(q) >= 0) {
        paths.push(pathOf(root.notes[i].id))
      }
    }
    cb({ paths: paths })
  }

  Connections {
    target: root.ms
    function onSignedOut() {
      root.notes = []
      root.clearCache()
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

  function load(path, cb) {
    var n = noteAt(path)
    if (!n) {
      cb({ error: "unknown note" })
      return
    }
    if (n.truncatedAt) {
      cb({ title: "", body: n.body, editable: false, version: n.modified || "",
           reason: "Only the first " + Math.round(n.truncatedAt / 1024) + " KB of this note could be read, so it opened read-only" })
      return
    }
    cb({ title: "", body: n.body, editable: true, version: n.modified || "" })
  }

  // The model follows the backend, never runs ahead of it: a note's text
  // changes here when Graph has taken it, and a note leaves here when Graph
  // has removed it. The host keeps the draft of a save in flight and shows
  // it if the note is reopened meanwhile (services/notes/NoteSession.qml),
  // so nothing is lost by waiting — while a model that moved first served a
  // failed save's text as the stored note, and showed a failed delete as
  // done.
  function save(path, title, body, cb) {
    if (!root.rq) {
      if (cb) {
        cb({ error: "not ready" })
      }
      return
    }
    var id = idOf(path), payload = JSON.stringify({ title: title, body: body })
    // A note's save and delete share one key, so they can never overlap; a
    // newer save replaces a queued older one, and flush keeps it draining
    // after the window closes.
    root.rq.enqueue({ key: "note:" + id, mode: "replace", priority: 0, owner: root, flush: true, label: "save" },
      function(ctx) { root.runScript(["update", id, "-"], payload, ctx) },
      function(r, info) {
        if (!r) {
          if (cb) {
            cb(root.unsentSave(info))
          }
          return
        }
        if (!r.error) {
          var saved = noteAt(path)
          if (saved) {
            saved.body = body
          }
          rebuild()
        }
        if (cb) {
          cb(r.error ? { error: r.error } : {})
        }
      })
  }

  function create(target, cb) {
    if (!root.ready || !root.rq) {
      if (cb) {
        cb({ error: "not ready" })
      }
      return
    }
    root.statusRequested("Creating a sticky note…")
    root.rq.enqueue({ key: "create", mode: "append", priority: 0, owner: root, flush: true, label: "new note" },
      function(ctx) { root.runScript(["create"], "", ctx) },
      function(r) {
        root.statusRequested("")
        if (!r) {
          if (cb) {
            cb({ error: "the window closed before the note was made" })
          }
          return
        }
        if (r.error) {
          if (cb) {
            cb({ error: r.error })
          }
          return
        }
        root.notes = [r.note].concat(root.notes)
        root.rebuild()
        if (cb) {
          cb({ path: root.pathOf(r.note.id) })
        }
      })
  }

  function remove(path, cb) {
    if (!root.rq) {
      if (cb) {
        cb({ error: "not ready" })
      }
      return
    }
    var id = idOf(path)
    root.rq.enqueue({ key: "note:" + id, mode: "replace", priority: 0, owner: root, flush: true, label: "delete" },
      function(ctx) { root.runScript(["delete", id], "", ctx) },
      function(r) {
        if (!r) {
          if (cb) {
            cb({ error: "not deleted — the request was cancelled" })
          }
          return
        }
        if (!r.error) {
          root.notes = root.notes.filter(function(n) { return n.id !== id })
          rebuild()
        }
        if (cb) {
          cb(r.error ? { error: r.error } : {})
        }
      })
  }

  // One listing request per poll; nothing else is needed to spot changes.
  function poll() { root.listNotes() }

  ProcessTask {
    id: cachedProc
    environment: root.ms ? root.ms.env : ({})
    command: ["python3", root.script, "list", "--cached"]
    raw: true
    onFinished: function(result) {
      var res = root.parse(result.text || "")
      if (!res.error && Array.isArray(res.notes)) {
        root.notes = res.notes
      }
      root.rebuild()
    }
  }
}
