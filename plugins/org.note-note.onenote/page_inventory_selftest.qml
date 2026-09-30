import QtQuick
import "../../services/requests"

Item {
  id: test
  property var results: []
  property var requests: []
  property var replies: ({})
  property int phase: 0
  property int serial: 0
  property bool noteOpened: false
  property int loaded: 0

  function check(name, ok) {
    test.results.push({ name: name, ok: !!ok })
  }

  function inventory(excluded, serial) {
    var pending = []
    for (var i = 0; i < 400; i++) {
      if ("s" + i !== excluded) {
        pending.push("s" + i)
      }
    }
    return { pendingSections: pending, sectionRetryAt: {}, pageListSerial: serial }
  }

  function backend(args, payload, callback) {
    var request = JSON.parse(payload)
    test.requests.push(request)
    test.replies[request.sectionId] = callback
    return { cancel: function() { callback({ error: "cancelled" }) } }
  }

  RequestQueue { id: lane; concurrency: 3 }
  PageInventory {
    id: cache
    ready: true
    session: "a"
    queue: lane
    run: test.backend
    onLoaded: test.loaded++
  }

  Component.onCompleted: {
    lane.queue.cooldownUntil = Date.now() + 60000
    lane.bump()
    cache.accept(test.inventory("", 1))
  }

  Timer {
    interval: 10
    repeat: true
    running: true
    onTriggered: {
      if (test.phase === 0 && lane.depth === 1) {
        test.check("hundreds of sections queue just one background step", cache.jobs.length === 1 && test.requests.length === 0)
        cache.request("s399", true, false)
        lane.queue.cooldownUntil = 0
        lane.bump()
        lane.pump()
        test.check("the opened section starts ahead of background discovery",
                   test.requests.length === 2 && test.requests[0].sectionId === "s399" && test.requests[0].interactive)
        lane.enqueue({ key: "open-note", priority: 0, owner: test }, function(ctx) {
          test.noteOpened = true
          ctx.done({ ok: true })
        }, function(result) {})
        test.phase = 1
      } else if (test.phase === 1 && test.noteOpened) {
        test.check("opening a note has a slot during discovery", cache.jobs.length === 2)
        test.replies.s399(test.inventory("s399", 3))
        test.replies.s0(test.inventory("", 2))
        test.check("a late background snapshot cannot undo a completed section",
                   cache.pendingSections.indexOf("s399") < 0 && cache.serial === 3 && test.loaded === 1)
        test.phase = 2
      } else if (test.phase === 2 && test.requests.length === 3) {
        var sid = test.requests[2].sectionId
        var response = test.inventory("s399", 4)
        response.deferred = true
        response.retryAfter = 30
        test.replies[sid](response)
        test.check("background budget exhaustion does not park the note lane", !lane.cooling && cache.resumeAt > Date.now())
        cache.request("s398", true, false)
        test.phase = 3
      } else if (test.phase === 3 && test.requests.length === 4) {
        test.check("opening another section bypasses the background-only wait",
                   test.requests[3].sectionId === "s398" && test.requests[3].interactive)
        var late = test.replies.s398
        cache.session = "b"
        late(test.inventory("", 999))
        test.check("sign-in changes cancel jobs and reject old snapshots", cache.jobs.length === 0 && cache.pendingSections.length === 0 && cache.serial === 0)
        lane.queue.cooldownUntil = Date.now() + 60000
        cache.accept(test.inventory("", 1))
        test.phase = 4
      } else if (test.phase === 4 && cache.jobs.length === 1) {
        var job = cache.jobs[0]
        cache.request(job.sectionId, true, false)
        test.check("expanding an already queued section promotes the existing job",
                   lane.queue.jobs.length === 1 && lane.queue.jobs[0].priority === 0 && job.interactive)
        cache.ready = false
        test.check("disabling discovery drops queued work", lane.depth === 0 && cache.jobs.length === 0)
        console.error("<<<RESULT>>>" + JSON.stringify(test.results) + "<<<END>>>")
        Qt.quit()
        test.phase = 5
      }
    }
  }

  Timer {
    interval: 8000
    running: true
    onTriggered: {
      test.check("discovery completes without stalling in phase " + test.phase, false)
      console.error("<<<RESULT>>>" + JSON.stringify(test.results) + "<<<END>>>")
      Qt.quit()
    }
  }
}
