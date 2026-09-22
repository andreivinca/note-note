import QtQuick

// Two small background jobs at a time; local searches never enter the API lane.
// The provider supplies transport so this lifecycle can be tested on its own.
Item {
  id: root

  property bool ready: false
  property bool inventoryReady: false
  property bool inventoryComplete: false
  property string session: ""
  property var pages: []
  property var preferredSections: []
  property var queue: null
  property var run: null
  // The index's coverage as the script last answered it (search_index.py,
  // summary): totals, one entry per section, its serial and the next delay.
  property var coverage: ({})
  // Two ways the cache can be down: it could not be read or synchronised at
  // all, or one indexing step failed and will be tried again. The text the
  // panel shows follows from them.
  property bool unavailable: false
  property bool stepFailed: false
  readonly property string error: root.unavailable ? "Search cache unavailable"
    : root.stepFailed ? "Search indexing paused; retrying" : ""
  property bool deferred: false
  property real resumeAt: 0
  property bool initialized: false
  property bool syncing: false
  readonly property bool indexing: root.pendingJobs.length > 0
  property int epoch: 0
  property string previousSession: ""
  property var pendingJobs: []
  property bool resync: false

  signal updated()

  onSessionChanged: reset()
  onReadyChanged: {
    if (root.ready) {
      root.refresh()
    } else {
      root.reset()
    }
  }
  onPagesChanged: refresh()
  onInventoryReadyChanged: refresh()
  onInventoryCompleteChanged: updated()
  onQueueChanged: refresh()
  Component.onCompleted: refresh()
  Component.onDestruction: {
    root.epoch++
    root.cancelJobs()
    if (root.queue) {
      root.queue.cancelOwner(root)
    }
  }

  function reset() {
    root.epoch++
    syncTimer.stop()
    indexTimer.stop()
    root.cancelJobs()
    root.syncing = false
    root.initialized = false
    root.coverage = ({})
    root.unavailable = false
    root.stepFailed = false
    root.deferred = false
    root.resumeAt = 0
    if (root.previousSession && root.previousSession !== root.session && root.run) {
      root.run(["clear-search", root.previousSession], undefined, function(result) {})
    }
    root.previousSession = root.session
    root.updated()
    root.refresh()
  }

  function cancelJobs() {
    var jobs = root.pendingJobs || []
    root.pendingJobs = []
    for (var i = 0; i < jobs.length; i++) {
      if (jobs[i].handle) {
        jobs[i].handle.cancel()
      }
      if (jobs[i].process) {
        jobs[i].process.cancel()
      }
    }
  }

  function refresh() {
    if (!root.ready || !root.inventoryReady || !root.session || !root.run) {
      return
    }
    if (root.syncing) {
      root.resync = true
      return
    }
    syncTimer.restart()
  }

  Timer { id: syncTimer; interval: 100; onTriggered: root.synchronize() }
  Timer { id: indexTimer; interval: 100; onTriggered: root.indexNext() }

  function accept(result) {
    if (result && result.status && (!root.coverage.serial || result.status.serial >= root.coverage.serial)) {
      root.coverage = result.status
      root.unavailable = false
      root.stepFailed = false
      root.updated()
    }
  }

  function synchronize() {
    if (!root.ready || !root.inventoryReady || !root.session) {
      return
    }
    var generation = root.epoch
    root.syncing = true
    root.resync = false
    var inventory = root.pages.map(function(page) {
      return { id: page.id, sectionId: page.sectionId, modified: page.modified || "" }
    })
    root.run(["search-sync", "-"], JSON.stringify({ pages: inventory }), function(result) {
      if (generation !== root.epoch) {
        return
      }
      root.syncing = false
      if (!result || result.error) {
        root.unavailable = true
        root.updated()
        root.schedule(60)
        return
      }
      root.initialized = true
      root.accept(result)
      if (root.resync) {
        root.refresh()
      } else {
        root.schedule(root.deferred ? Math.max(0, root.resumeAt - Date.now()) / 1000 : root.coverage.nextDelay)
      }
    })
  }

  function schedule(seconds) {
    if (!root.ready || !root.session || root.pendingJobs.length >= 2) {
      return
    }
    if (root.deferred) {
      seconds = Math.max(seconds || 0, (root.resumeAt - Date.now()) / 1000)
    }
    indexTimer.interval = Math.max(100, Math.min(3600000, Math.ceil((seconds || 0) * 1000)))
    indexTimer.restart()
  }

  function indexNext() {
    if (!root.ready || !root.queue || root.pendingJobs.length >= 2) {
      return
    }
    if (!root.initialized || root.syncing || syncTimer.running || root.unavailable) {
      root.refresh()
      return
    }
    for (var slot = 0; slot < 2; slot++) {
      if (!root.pendingJobs.some(function(job) { return job.slot === slot })) {
        root.startIndex(slot)
      }
    }
  }

  function startIndex(slot) {
    var generation = root.epoch
    var job = { slot: slot, handle: null, process: null }
    root.pendingJobs = root.pendingJobs.concat([job])
    job.handle = root.queue.enqueue({ key: "search-index:" + slot, mode: "dedupe", priority: 1,
                                     runWhenPaused: true, owner: root, label: "search index" },
      function(ctx) {
        job.process = root.run(["search-step", "-"], JSON.stringify({ preferredSections: root.preferredSections }),
                               function(result) { ctx.done(result) })
      },
      function(result) {
        if (generation !== root.epoch) {
          return
        }
        root.pendingJobs = root.pendingJobs.filter(function(pending) { return pending !== job })
        if (!result) {
          return
        }
        if (result.error) {
          root.stepFailed = true
          root.updated()
          root.schedule(60)
          return
        }
        if (result.deferred) {
          root.resumeAt = Math.max(root.resumeAt, Date.now() + result.retryAfter * 1000)
        }
        root.deferred = root.resumeAt > Date.now()
        root.accept(result)
        root.schedule(root.deferred ? (root.resumeAt - Date.now()) / 1000 : root.coverage.nextDelay)
      })
  }

  Connections {
    target: root.queue
    function onPausedChanged() {
      if (!root.queue.paused) {
        root.refresh()
      }
      root.updated()
    }
    function onUpdated() { root.updated() }
  }

  function search(query, callback) {
    if (!root.ready || !root.session) {
      callback({ paths: [] })
      return
    }
    var generation = root.epoch
    root.run(["search", "-"], JSON.stringify({ query: query }), function(result) {
      if (generation !== root.epoch) {
        callback({ paths: [] })
        return
      }
      if (!result || result.error) {
        // Report a failure once. Repeating the same notification would make
        // the host keep querying the unavailable cache in a feedback loop.
        if (!root.unavailable) {
          root.unavailable = true
          root.updated()
        }
        root.schedule(60)
        callback({ paths: [] })
        return
      }
      // Successful reads never emit updated(): the host must not search
      // again in response to its own search callback.
      callback(result)
    })
  }

  function status(sectionIds) {
    if (!root.ready) {
      return ""
    }
    if (root.error) {
      return root.error
    }
    if (!root.initialized) {
      return "Preparing content search…"
    }
    var counts = { total: 0, indexed: 0, pending: 0, failed: 0 }
    for (var i = 0; i < sectionIds.length; i++) {
      var section = (root.coverage.sections || {})[sectionIds[i]]
      if (section) {
        counts.total += section.total
        counts.indexed += section.indexed
        counts.pending += section.pending
        counts.failed += section.failed
      }
    }
    if (!counts.pending) {
      return root.inventoryComplete ? "" : "Known pages searchable · page list incomplete"
    }
    var progress = counts.indexed + " of " + counts.total + " pages searchable"
    if (root.deferred || (root.queue && root.queue.cooling)) {
      return progress + " · indexing paused"
    }
    if (counts.failed && counts.failed === counts.pending) {
      return progress + " · retrying unavailable pages"
    }
    return progress + (counts.indexed === counts.total ? " · refreshing…" : " · indexing…")
  }

  function diagnostics() {
    return { total: root.coverage.total || 0, indexed: root.coverage.indexed || 0,
             pending: root.coverage.pending || 0, failed: root.coverage.failed || 0,
             workers: root.pendingJobs.length, syncing: root.syncing,
             initialized: root.initialized, deferred: root.deferred,
             resumeIn: Math.max(0, Math.ceil((root.resumeAt - Date.now()) / 1000)), error: root.error }
  }
}
