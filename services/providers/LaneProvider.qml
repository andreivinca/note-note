import QtQuick
import "../processes"

// What every built-in provider that talks to a backend script through a
// request lane shares (providers/PROVIDERS.md): the host's hooks and the
// contract's signals, the save schedule, the lane and the sign-in its
// requests are made with, and one process per script run. A provider
// extends this with its identity, its model, its rows and its calls.
Item {
  id: lane

  property var host: null
  property var services: null
  property var sections: []
  // The keys of this provider's config entry that are its settings, each a
  // property whose initial value is the default (PROVIDERS.md).
  property var settings: []

  signal updated()
  signal statusRequested(string text)
  signal noticeRequested(string title, string text, string code, var actions)
  signal noticeCleared()
  signal viewRequested(string title, var component, var props)
  signal viewCleared()
  signal persistRequested()

  // A save is a request against the backend, paced and counted against a
  // budget, so the typing is let settle first: long enough that a sentence
  // is one request rather than one per word (noteEdited / saveRequested,
  // PROVIDERS.md).
  signal saveRequested(string path)
  property int savePause: 1500
  function noteEdited(path) {
    saveSchedule.path = path
    saveSchedule.restart()
  }
  Timer {
    id: saveSchedule
    property string path: ""
    interval: lane.savePause
    onTriggered: lane.saveRequested(saveSchedule.path)
  }

  // The script that answers, and the lane its requests go through — keyed
  // to the backend's own budget, so one backend's throttle never reaches
  // another (services/requests/, PROVIDERS.md). A provider with a
  // Microsoft sign-in sets `ms` to its own account: own registration, own
  // token file, own scope.
  property string script: ""
  property string laneKey: ""
  property var rq: null
  property var ms: null
  Component.onCompleted: {
    if (services && services.requests && lane.laneKey) {
      lane.rq = services.requests.queueFor(lane.laneKey, lane)
    }
  }
  // A provider is destroyed and rebuilt when its settings change, and on
  // sign-out. What it had not started yet goes with it; what is already
  // running finishes, since its process is running either way.
  Component.onDestruction: {
    if (services && services.requests) {
      services.requests.cancelOwner(lane)
    }
  }

  // The contract's state hooks, for a provider that keeps none.
  function restoreState(obj) {}
  function saveState() { return {} }
  function toggleTree(id) {}
  function setOrder(sectionKey, paths) {}

  // A save the lane never sent. Superseded means a newer save of the same
  // note carries this one's intent and answers for it: `{}`. Cancelled — the
  // lane emptied on sign-out, or this provider going — means nobody will, and
  // that is a failure the host must hear: an accepted save finishes or fails
  // out loud (business-requirements.md), never silently.
  function unsentSave(info) {
    return (info && info.cancelled) ? { error: "not saved — the request was cancelled" } : {}
  }

  function parse(text) {
    try {
      return JSON.parse(text)
    } catch (e) {
      return { error: "unexpected reply" }
    }
  }

  // One process per job, made when the job runs and destroyed when it
  // answers, so the callback travels with the process instead of living in a
  // single `saveCb`-shaped slot that the next save would overwrite. (That
  // slot is where a second save used to drop the first one's answer.)
  ProcessRunner { id: scriptRunner }
  readonly property bool busy: scriptRunner.active > 0
  // One provider to a lane, so the lane's accepted writes are this one's.
  readonly property bool writeBusy: lane.rq ? lane.rq.writeDepth > 0 : false

  function runScript(args, payload, ctx) {
    lane.runProcess(scriptRunner, args, payload || undefined, function(result) { ctx.done(result) })
  }

  // An answer is for the account the request was made under: one that
  // arrives after a sign-out or a switch is refused, not applied.
  function runProcess(runner, args, payload, callback) {
    var session = lane.ms ? lane.ms.cacheSession : ""
    return runner.run({ command: ["python3", lane.script].concat(args),
                       environment: lane.ms ? lane.ms.env : ({}),
                       payload: payload,
                       timeoutMs: 600000 }, function(result) {
      callback(session === (lane.ms ? lane.ms.cacheSession : "") ? result : { error: "the signed-in account changed" })
    })
  }

  // The backend's cache of the account that just left, dropped with it.
  function clearCache() {
    clearProc.start()
  }
  ProcessTask { id: clearProc; environment: lane.ms ? lane.ms.env : ({}); command: ["python3", lane.script, "clear-cache"] }
}
