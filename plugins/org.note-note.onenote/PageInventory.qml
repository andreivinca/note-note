import QtQuick

// One response per queue job. Discovery never queues the whole account, and
// expanding a section promotes its next response to interactive priority.
Item {
  id: root

  property bool ready: false
  property string session: ""
  property var queue: null
  property var run: null
  property var pendingSections: []
  property var retryAt: ({})
  property var preferredSections: []
  property var jobs: []
  property int epoch: 0
  property int serial: 0
  property real resumeAt: 0
  readonly property bool busy: root.jobs.length > 0

  signal loaded(var result)
  signal failed(string message)

  onSessionChanged: reset()
  onReadyChanged: {
    if (!root.ready) {
      root.reset()
    } else {
      root.schedule()
    }
  }
  onQueueChanged: schedule()
  Component.onDestruction: reset()

  function reset() {
    root.epoch++
    nextStep.stop()
    var jobs = root.jobs
    root.jobs = []
    if (root.queue) {
      root.queue.cancelOwner(root)
    }
    for (var i = 0; i < jobs.length; i++) {
      if (jobs[i].process) {
        jobs[i].process.cancel()
      }
    }
    root.pendingSections = []
    root.retryAt = ({})
    root.resumeAt = 0
    root.serial = 0
  }

  function accept(result) {
    if (!result || (result.pageListSerial || 0) < root.serial) {
      return false
    }
    root.serial = result.pageListSerial || 0
    if (!Array.isArray(result.pendingSections)) {
      return true
    }
    root.pendingSections = result.pendingSections
    root.retryAt = result.sectionRetryAt || ({})
    root.schedule()
    return true
  }

  function schedule() {
    if (!root.ready || !root.queue || !root.run || !root.pendingSections.length || root.jobs.length) {
      return
    }
    var now = Date.now()
    var wake = Infinity
    for (var i = 0; i < root.pendingSections.length; i++) {
      var sid = root.pendingSections[i]
      wake = Math.min(wake, Math.max(root.resumeAt, (root.retryAt[sid] || 0) * 1000))
    }
    nextStep.interval = Math.max(100, Math.min(3600000, wake - now))
    nextStep.restart()
  }

  function status(sid) {
    if ((root.retryAt[sid] || 0) * 1000 > Date.now()) {
      return "Could not load pages — retry"
    }
    if (root.resumeAt > Date.now() || (root.queue && root.queue.cooling)) {
      return "Page loading paused — retry"
    }
    return "Loading pages…"
  }

  Timer {
    id: nextStep
    onTriggered: {
      if (root.resumeAt > Date.now()) {
        root.schedule()
        return
      }
      var candidates = root.preferredSections.concat(root.pendingSections)
      for (var i = 0; i < candidates.length; i++) {
        var sid = candidates[i]
        if (root.pendingSections.indexOf(sid) >= 0 && (root.retryAt[sid] || 0) * 1000 <= Date.now()) {
          root.request(sid, false, false)
          return
        }
      }
      root.schedule()
    }
  }

  function request(sid, interactive, refresh) {
    if (!root.ready || !root.queue || !root.run || (!refresh && root.pendingSections.indexOf(sid) < 0)) {
      return
    }
    var existing = root.jobs.filter(function(job) { return job.sectionId === sid })[0]
    if (existing) {
      if (interactive) {
        existing.interactive = true
        if (existing.handle) {
          existing.handle.promote()
        }
      }
      return
    }
    var generation = root.epoch
    var job = { sectionId: sid, interactive: interactive, refresh: refresh, handle: null, process: null }
    root.jobs = root.jobs.concat([job])
    job.handle = root.queue.enqueue({ key: "pages:" + sid, mode: "dedupe", priority: interactive ? 0 : 1,
                                     runWhenPaused: !interactive, owner: root, label: "section pages" },
      function(ctx) {
        job.process = root.run(["list-step", "-"], JSON.stringify({ sectionId: sid,
                               interactive: job.interactive, refresh: job.refresh }),
                               function(result) { ctx.done(result) })
        // A queue retry resumes the saved cursor instead of restarting it.
        job.refresh = false
      },
      function(result) {
        if (generation !== root.epoch) {
          return
        }
        root.jobs = root.jobs.filter(function(pending) { return pending !== job })
        if (!result) {
          root.schedule()
          return
        }
        if (result.error) {
          var retries = Object.assign({}, root.retryAt)
          retries[sid] = Date.now() / 1000 + 60
          root.retryAt = retries
          root.failed(result.error)
          root.schedule()
          return
        }
        if (result.deferred) {
          root.resumeAt = Math.max(root.resumeAt, Date.now() + result.retryAfter * 1000)
        }
        if (root.accept(result)) {
          root.loaded(result)
        }
        if (result.listingError) {
          root.failed(result.listingError)
        }
        if (job.interactive && !result.deferred && !result.listingError && root.pendingSections.indexOf(sid) >= 0) {
          root.request(sid, true, false)
        } else {
          root.schedule()
        }
      })
  }
}
