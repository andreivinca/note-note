import QtQuick

// Owns document identity, load generations, drafts and save completion.
// UI, provider lookup and status presentation are injected, so transitions
// can be exercised with delayed providers without a desktop or account.
Item {
  id: session
  property var editor: null
  property var providerFor: null
  property var versionFor: null
  property var report: null

  property string currentPath: ""
  property bool loadingNote: false
  property bool loadFailed: false
  property bool dirty: false
  // Held by an operation that must not see the note change (lock).
  property bool locked: false
  // Whether the provider lets the displayed document be written: what its
  // load said (noteReady). One of the conditions `writable` weighs.
  property bool documentEditable: false
  // The merge conflict under review for the open note, or null. The review
  // is the session's own: it stands in the editor until the user answers it
  // or the note goes, whatever notices come and go over it meanwhile.
  property var conflict: null
  // The editor may change the document: one is shown, loaded, the
  // provider's to write, held by no operation and under no review.
  readonly property bool writable: session.currentPath !== "" && !session.loadingNote && !session.loadFailed
    && !session.locked && session.conflict === null && session.documentEditable
  property string loadingPath: ""
  property var loadHandle: null
  property string loadedVersion: ""
  // Opaque provider baseline belonging to the document actually displayed.
  property var editingView: null
  property int noteLoadSeq: 0
  property var saveEpoch: ({})
  property var savesPending: ({})
  // Replaced wholesale, never mutated (setDraft), like savesPending:
  // unsavedTitles follows them.
  property var drafts: ({})
  // The titles the list shows over its providers' while they are unsaved:
  // path -> title. The open note's is the editor's while it holds edits no
  // save has taken yet; any other's is the one its draft carries — a save
  // still in flight, or one that failed and is kept. A note leaves once its
  // save lands, and its provider's row says the same by then.
  readonly property var unsavedTitles: {
    var titles = {}
    for (var path in session.drafts) {
      titles[path] = session.drafts[path].document.title
    }
    if (session.dirty) {
      titles[session.currentPath] = session.editor.title
    }
    return titles
  }
  property var pathAliases: ({})
  property var pendingDeletions: ({})
  readonly property bool busy: Object.keys(session.savesPending).length > 0 || Object.keys(session.pendingDeletions).length > 0
  readonly property string notDisplayable: "This note could not be displayed — it has not been changed"

  function resolvedPath(path) {
    return session.pathAliases[path] || path
  }

  // Creating a remote note replaces its provisional identity, without
  // loading the document again or changing the caret and undo history.
  // Callbacks accepted under the old identity still settle the same draft.
  function replacePath(previous, next, view) {
    session.pathAliases[previous] = next
    if (previous in session.saveEpoch) {
      session.saveEpoch[next] = session.saveEpoch[previous]
      delete session.saveEpoch[previous]
    }
    var drafts = Object.assign({}, session.drafts)
    if (previous in drafts) {
      drafts[next] = drafts[previous]
      delete drafts[previous]
    }
    session.drafts = drafts
    var pending = Object.assign({}, session.savesPending)
    if (previous in pending) {
      pending[next] = pending[previous]
      delete pending[previous]
    }
    session.savesPending = pending
    var deletions = Object.assign({}, session.pendingDeletions)
    if (previous in deletions) {
      deletions[next] = deletions[previous]
      delete deletions[previous]
      deletions[next].view = deletions[next].view || view || null
    }
    session.pendingDeletions = deletions
    var draft = session.drafts[next]
    if (draft && !draft.view) {
      draft.view = view || null
    }
    if (session.loadingPath === previous) {
      session.loadingPath = next
    }
    if (session.currentPath === previous) {
      session.currentPath = next
      session.editingView = session.editingView || view || null
    }
  }

  // The editor's read-only flag, from the session's state alone. Every
  // change to what `writable` weighs ends here; nothing restores a flag
  // saved from before, which a transition finishing meanwhile made stale.
  function updateReadOnly() {
    editor.readOnly = !session.writable
  }

  // Holds the open note still while an operation that must not see it
  // change finishes — a delete, a settings change draining its writes.
  function lock() {
    session.locked = true
    session.updateReadOnly()
  }

  function unlock() {
    session.locked = false
    session.updateReadOnly()
  }

  function showConflict(path, conflict) {
    path = session.resolvedPath(path)
    if (path !== session.currentPath || session.saveInFlight(path)) {
      return
    }
    var provider = session.providerFor(path)
    session.conflict = conflict
    session.updateReadOnly()
    editor.showConflict({
      conflict: conflict,
      remoteName: provider ? provider.name : "Elsewhere",
      retry: function() {
        if (path !== session.currentPath) {
          return
        }
        session.closeConflict()
        session.flushSave()
      },
      continueEditing: function() {
        if (path !== session.currentPath) {
          return
        }
        session.closeConflict()
      },
      resolve: function(choices) {
        if (path !== session.currentPath) {
          return
        }
        session.closeConflict()
        session.flushSave({ id: conflict.id, choices: choices })
      }
    })
  }

  // The review goes — answered, or its note put away — and the note is
  // editable again unless something else holds it.
  function closeConflict() {
    session.conflict = null
    editor.clearConflict()
    session.updateReadOnly()
  }

  function cancelLoad() {
    var handle = session.loadHandle
    session.loadHandle = null
    if (handle) {
      handle.cancel()
    }
  }

  function selectPath(path) {
    path = session.resolvedPath(path)
    if (session.locked || path === session.currentPath || (path && !session.providerFor(path))) {
      return
    }
    session.flushSave()
    session.currentPath = path
    session.load(false)
  }

  // Puts the note away for the caller that holds the lock — a settings
  // commit retiring the provider whose note is open. selectPath refuses
  // while locked, and it flushes; this does neither: the caller already
  // saved, and holds the lock for exactly that reason.
  function putAway() {
    session.currentPath = ""
    session.load(false)
  }

  function reloadCurrent() {
    if (!session.locked && !session.dirty && !session.saveInFlight(session.currentPath)) {
      session.load(true)
    }
  }

  function load(reload) {
    var path = session.currentPath
    var generation = ++session.noteLoadSeq
    session.cancelLoad()
    session.loadingNote = true
    session.loadFailed = false
    session.loadingPath = path
    session.dirty = false
    session.editingView = null
    // A note opens at its top (NoteEditor.showBody); a reload in place
    // keeps the caret and the scroll where the reader had them.
    var view = reload ? editor.viewState() : null
    editor.clearNotice()
    session.closeConflict()
    editor.documentBase = ""
    if (!reload) {
      editor.setNote("", "")
    }
    if (!path) {
      session.loadingNote = false
      session.loadedVersion = ""
      return
    }
    // An accepted save can outlive selection. Returning to that note shows
    // its captured document, including a draft whose conversion/save failed.
    var draft = session.drafts[path]
    if (draft) {
      editor.restoreDocument(draft.document)
      session.editingView = draft.view || null
      session.noteReady(false, "")
      session.dirty = !!draft.error
      if (draft.conflict) {
        session.showConflict(path, draft.conflict)
      }
      return
    }
    var provider = session.providerFor(path)
    if (!provider) {
      session.noteUnavailable("The notebook is not available")
      return
    }
    var handle = provider.load(path, function(result) {
      if (!session.ownsLoad(path, generation)) {
        return
      }
      session.loadHandle = null
      if (result.error) {
        session.noteUnavailable(provider.name + ": " + result.error)
        return
      }
      session.loadedVersion = result.version || session.versionFor(session.resolvedPath(path))
      editor.documentBase = result.base || ""
      editor.setNote(result.title || "", result.body || "", function(shown) {
        if (!session.ownsLoad(path, generation)) {
          return
        }
        if (!shown) {
          session.noteUnavailable(session.notDisplayable)
          return
        }
        if (view) {
          editor.restoreViewState(view)
        }
        session.editingView = result.view || (session.resolvedPath(path) !== path ? session.editingView : null)
        session.noteReady(result.editable === false, result.reason || "")
        if (result.recovered) {
          session.dirty = true
          session.setDraft(path, { document: editor.snapshotDocument(),
              view: session.editingView, epoch: session.saveEpoch[path] || 0,
              error: "Recovered unsaved changes", conflict: result.conflict })
          session.report("Recovered unsaved changes")
          if (result.conflict) {
            session.showConflict(path, result.conflict)
          } else if (result.retry) {
            // Once this load has settled: the save it asks for reads the
            // session's state, which this very callback is still writing.
            Qt.callLater(function() {
              if (session.ownsLoad(path, generation) && !session.saveInFlight(path)) {
                session.flushSave()
              }
            })
          }
        } else if (reload) {
          session.report(provider.name + ": reloaded, changed elsewhere")
        }
      })
    })
    // A synchronous provider may have finished before returning its handle.
    if (session.ownsLoad(path, generation) && session.loadingNote) {
      session.loadHandle = handle || null
    }
  }

  function ownsLoad(path, generation) {
    return session.currentPath === session.resolvedPath(path) && session.noteLoadSeq === generation
  }

  // `reason` is the provider's own words for why the note is read-only, said
  // once on the status line; the view bar keeps showing "Read-only" after it.
  function noteReady(readOnly, reason) {
    session.documentEditable = !readOnly
    session.loadFailed = false
    session.loadingNote = false
    session.loadingPath = ""
    session.dirty = false
    session.updateReadOnly()
    if (readOnly && reason) {
      session.report(reason)
    }
  }

  function noteUnavailable(message) {
    session.loadFailed = true
    session.loadingNote = false
    session.loadingPath = ""
    session.updateReadOnly()
    session.report(message)
  }

  function onEdited() {
    if (!session.writable) {
      return
    }
    session.dirty = true
    var provider = session.providerFor(session.currentPath)
    if (provider && typeof provider.noteEdited === "function") {
      provider.noteEdited(session.currentPath)
    } else {
      schedule.path = session.currentPath
      schedule.restart()
    }
  }

  Timer {
    id: schedule
    property string path: ""
    interval: 1500
    onTriggered: {
      if (path === session.currentPath) {
        session.flushSave()
      }
    }
  }

  function saveInFlight(path) {
    return (session.savesPending[session.resolvedPath(path)] || 0) > 0
  }

  // `draft` is { document, view, epoch, error, conflict }; null drops it.
  function setDraft(path, draft) {
    var drafts = Object.assign({}, session.drafts)
    if (draft) {
      drafts[path] = draft
    } else {
      delete drafts[path]
    }
    session.drafts = drafts
  }

  function countSave(path, delta) {
    path = session.resolvedPath(path)
    var count = (session.savesPending[path] || 0) + delta
    var pending = Object.assign({}, session.savesPending)
    if (count > 0) {
      pending[path] = count
    } else {
      delete pending[path]
    }
    session.savesPending = pending
  }

  // Used only after the user confirms deleting this note.
  function cancelPendingSave(path) {
    path = session.resolvedPath(path)
    if (path) {
      session.saveEpoch[path] = (session.saveEpoch[path] || 0) + 1
      session.setDraft(path, null)
    }
  }

  // The session reports every delete it does not complete, whether refused
  // here or failed by the provider, so its callers act on success only.
  function remove(path, callback) {
    path = session.resolvedPath(path)
    if (session.pendingDeletions[path]) {
      session.refuseRemoval("The note is already being deleted", callback)
      return
    }
    if (session.locked) {
      session.refuseRemoval("A note operation is still finishing", callback)
      return
    }
    var provider = session.providerFor(path)
    if (!provider) {
      session.refuseRemoval("The notebook is not available", callback)
      return
    }
    var current = path === session.currentPath
    var recovery = current ? editor.snapshotDocument() : (session.drafts[path] || {}).document
    var recoveryView = current ? session.editingView : (session.drafts[path] || {}).view
    var unsaved = current ? session.dirty || session.saveInFlight(path) : !!session.drafts[path]
    session.cancelPendingSave(path)
    var deletions = Object.assign({}, session.pendingDeletions)
    deletions[path] = { document: recovery, view: recoveryView, unsaved: unsaved,
                        epoch: session.saveEpoch[path] }
    session.pendingDeletions = deletions
    session.lock()
    provider.remove(path, function(result) {
      path = session.resolvedPath(path)
      if (!result.pending) {
        session.finishDeletion(path, result)
      }
      if (current) {
        session.dirty = !!result.error && unsaved
      }
      session.unlock()
      callback(result)
    })
  }

  function refuseRemoval(message, callback) {
    session.report(message)
    callback({ error: message })
  }

  // An optimistic delete releases the editor immediately, but keeps its
  // recovery document until the provider confirms the remote outcome.
  function finishDeletion(path, result) {
    path = session.resolvedPath(path)
    var recovery = session.pendingDeletions[path]
    if (!recovery) {
      return
    }
    if (result.error) {
      if (recovery.document && recovery.unsaved && !session.drafts[path]) {
        session.setDraft(path, { document: recovery.document, view: recovery.view,
            error: result.error, epoch: recovery.epoch })
        if (path === session.currentPath) {
          session.dirty = true
        }
      }
      var provider = session.providerFor(path)
      session.report((provider ? provider.name + ": " : "") + result.error)
    }
    var deletions = Object.assign({}, session.pendingDeletions)
    delete deletions[path]
    session.pendingDeletions = deletions
  }

  function flushSave(resolution) {
    var path = session.currentPath
    if (!session.dirty || !session.writable) {
      return
    }
    var provider = session.providerFor(path)
    if (!provider) {
      return
    }
    var epoch = (session.saveEpoch[path] || 0) + 1
    session.saveEpoch[path] = epoch
    var draft = { document: editor.snapshotDocument(), view: session.editingView, epoch: epoch, error: "" }
    session.setDraft(path, draft)
    session.dirty = false
    session.loadedVersion = ""
    session.countSave(path, 1)
    editor.requestMarkdown(function(body, ok) {
      path = session.resolvedPath(path)
      if (session.saveEpoch[path] !== epoch) {
        session.countSave(path, -1)
        return
      }
      if (!ok) {
        session.finishSave(path, draft, { error: "the note could not be read for saving" })
        return
      }
      provider.save(path, draft.document.title, body, function(result) {
        session.finishSave(path, draft, result || {})
      }, { view: draft.view, resolution: resolution })
    })
  }

  function finishSave(path, draft, result) {
    path = session.resolvedPath(path)
    var showConflict = false
    if (session.drafts[path] === draft) {
      if (result.error) {
        // A conflict computed for an older edit cannot decide newer text.
        var newerEdits = path === session.currentPath && session.dirty
        draft.conflict = newerEdits ? null : result.conflict
        showConflict = !!draft.conflict && path === session.currentPath
        draft.error = result.error
        if (path === session.currentPath) {
          session.dirty = true
        }
      } else {
        session.setDraft(path, null)
        if (path === session.currentPath && !session.dirty && result.version) {
          session.loadedVersion = result.version
        }
      }
    }
    if (result.error || result.warning) {
      session.report(result.error || result.warning)
    }
    // Release last: observers checking whether retirement is safe see the
    // final draft/error state, never a gap before a failed draft is restored.
    session.countSave(path, -1)
    if (showConflict) {
      session.showConflict(path, result.conflict)
    }
  }

  function reconcile(exists, version) {
    if (session.locked || session.loadingNote || session.dirty || session.saveInFlight(session.currentPath)) {
      return
    }
    if (session.currentPath && !exists) {
      session.selectPath("")
    } else if (session.currentPath && version && session.loadedVersion && version !== session.loadedVersion) {
      session.reloadCurrent()
    } else if (version && !session.loadedVersion) {
      session.loadedVersion = version
    }
  }

  function failureFor(providerIds) {
    for (var path in session.drafts) {
      if (providerIds.indexOf(path.substring(0, path.indexOf(":"))) >= 0 && session.drafts[path].error) {
        return "A note has unsaved changes: " + session.drafts[path].error
      }
    }
    return ""
  }
}
