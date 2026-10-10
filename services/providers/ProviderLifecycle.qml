import QtQuick
import "plan.js" as Plan
import "../settings/settings.js" as Settings

// Settings changes have three phases: validate, drain, commit. Providers stay
// alive until their accepted writes settle; a failed save keeps the old setup.
Item {
  id: lifecycle
  property var host: null
  property var session: null
  property var settings: null
  property bool busy: false
  property var pending: null
  property bool committing: false
  // The moment the change may commit: every accepted write has settled and
  // no provider being replaced is still at work — retirement waits for all
  // of a provider's activity, where a close waits for its writes only. The
  // commit follows its inputs' changes (the host's settled state and the
  // replaced providers' `busy`, connected in apply), and runs once the
  // notification has completed: committing starts the config write and
  // retires providers, which are inputs of that very state, and a reaction
  // that writes its own inputs mid-update is a binding loop.
  readonly property bool drained: lifecycle.pending !== null && (!lifecycle.pending.drain || (host.writesSettled
    && !lifecycle.pending.changes.some(function(change) {
      var provider = change.replace ? host.providerById(change.id) : null
      return !!provider && provider.busy === true
    })))
  function commitWhenDrained() {
    Qt.callLater(lifecycle.tryCommit)
  }
  Connections {
    target: lifecycle.host
    function onWritesSettledChanged() {
      lifecycle.commitWhenDrained()
    }
  }

  function apply(text, callback, expectedRevision) {
    if (lifecycle.busy || settings.busy) {
      callback({ error: "A note or settings operation is still finishing" })
      return
    }
    var parsed
    try {
      parsed = JSON.parse(text)
    } catch (error) {
      callback({ error: "Invalid JSON: " + error.message })
      return
    }
    var validationError = Settings.validate(parsed)
    if (validationError) {
      callback({ error: validationError })
      return
    }
    settings.prepare(text, function(result) {
      if (result.error) {
        callback(result)
        return
      }
      lifecycle.applyPrepared(result.config, text, callback, expectedRevision)
    })
  }

  function applyPrepared(parsed, text, callback, expectedRevision) {
    var merged = settings.merge(parsed)
    var changes = Plan.plan(host.config, merged, Object.keys(host.providerUrls), function(id) {
      var provider = host.providerById(id)
      return provider && Array.isArray(provider.liveSettings) ? provider.liveSettings : []
    })
    for (var i = 0; i < changes.length; i++) {
      if (changes[i].replace && changes[i].enabled) {
        var component = Qt.createComponent(host.providerUrls[changes[i].id])
        if (component.status !== Component.Ready) {
          callback({ error: "The provider could not be loaded: " + component.errorString() })
          return
        }
      }
    }
    var drain = changes.length > 0
    if (drain && (session.locked || session.loadingNote)) {
      callback({ error: "A note operation is still finishing" })
      return
    }
    lifecycle.busy = true
    if (drain) {
      session.flushSave()
      session.lock()
    }
    var watched = []
    for (var j = 0; j < changes.length; j++) {
      var provider = host.providerById(changes[j].id)
      if (provider && changes[j].replace) {
        if (typeof provider.watch === "function") {
          provider.watch(false)
        }
        if (provider.busyChanged) {
          provider.busyChanged.connect(lifecycle.commitWhenDrained)
          watched.push(provider)
        }
      }
    }
    // Last, with the flush under way: the commit follows the drain, which
    // may be settled already.
    lifecycle.pending = { text: text, merged: merged, changes: changes,
                          callback: callback, watched: watched, drain: drain,
                          revision: expectedRevision }
    lifecycle.tryCommit()
  }

  function tryCommit() {
    if (!lifecycle.drained || lifecycle.committing) {
      return
    }
    lifecycle.committing = true
    var error = lifecycle.pending.drain ? session.failureFor(Object.keys(host.providerUrls)) : ""
    if (error) {
      lifecycle.finish({ error: error })
      return
    }
    settings.replace(lifecycle.pending.text, lifecycle.pending.revision, function(result) {
      if (result.error) {
        lifecycle.finish(result)
        return
      }
      lifecycle.commit()
    })
  }

  function commit() {
    var pending = lifecycle.pending
    host.config = pending.merged
    if (!pending.drain) {
      lifecycle.finish({ ok: true })
      return
    }
    host.providerState = host.providerSnapshot()
    for (var i = 0; i < pending.changes.length; i++) {
      var change = pending.changes[i]
      var provider = host.providerById(change.id)
      if (change.replace) {
        if (provider) {
          // The note has already been saved and all accepted work drained.
          if (host.providerOf(session.currentPath) === provider) {
            session.putAway()
          }
          host.retireProvider(provider)
        }
        if (change.enabled) {
          provider = host.addProvider(change.id)
          if (provider) {
            provider.refresh()
          }
        }
      } else if (provider && change.presentation) {
        host.applyProviderSettings(provider)
        provider.rebuild()
      }
    }
    host.reorderProviders()
    host.rebuildRows()
    host.saveState()
    lifecycle.finish({ ok: true })
  }

  function finish(result) {
    var pending = lifecycle.pending
    lifecycle.pending = null
    lifecycle.committing = false
    for (var w = 0; w < pending.watched.length; w++) {
      pending.watched[w].busyChanged.disconnect(lifecycle.commitWhenDrained)
    }
    if (pending.drain) {
      session.unlock()
    }
    lifecycle.busy = false
    if (host.opened) {
      for (var i = 0; i < host.providers.length; i++) {
        var provider = host.providers[i]
        if (typeof provider.watch === "function") {
          provider.watch(true)
        }
      }
    }
    pending.callback(result)
  }
}
