import QtQuick
import "../platform"
import "../processes"
import "settings.js" as Settings

Item {
  id: store
  property string path: Platform.configDir + "/config.json"
  property var providerIds: []
  property var providerDefaults: ({})
  property var config: Settings.defaults([], {})
  // What the file holds that cannot be used, as { path, message }. Those
  // parts run on their defaults; the file itself is left as it is.
  property var problems: []
  readonly property string problemSummary: Settings.summary(problems)
  property string revision: ""
  property bool ready: false
  property bool unwritten: false
  property bool busy: false
  property bool stale: false
  // Why the last read failed, if it did. A file that could not be read at
  // all has no revision, and nothing is written over an unknown file.
  property string readError: ""
  readonly property string script: Platform.localPath(Qt.resolvedUrl("config_io.py"))
  signal loaded()
  ProcessRunner { id: runner }

  function merge(value) {
    return Settings.merge(value, store.providerIds, store.providerDefaults)
  }

  function adopt(parsed) {
    var found = Settings.problems(parsed)
    store.problems = found
    store.config = store.merge(Settings.usable(parsed, found))
  }

  function request(payload, callback) {
    return runner.run({ command: ["python3", store.script], timeoutMs: 15000, maxOutputBytes: 8 * 1024 * 1024,
                        payload: JSON.stringify(Object.assign({ path: store.path }, payload)) }, callback)
  }

  function load() {
    store.request({ operation: "read" }, function(result) {
      store.revision = result.revision || ""
      store.readError = result.error || ""
      store.unwritten = result.unwritten === true
      store.adopt(result.config || {})
      store.ready = true
      store.loaded()
    })
  }

  // Only a different revision means someone else wrote the file. A read that
  // fails says nothing about it, and must not stop later saves.
  function check(callback) {
    store.request({ operation: "read" }, function(result) {
      if (!result.revision) {
        callback({ error: "Settings could not be read: " + result.error, kind: result.kind || "unreadable" })
        return
      }
      if (result.revision !== store.revision) {
        store.stale = true
        callback({ error: "Settings changed elsewhere. Restart to load them before saving.", kind: "stale" })
        return
      }
      callback(result)
    })
  }

  function refusal() {
    if (store.stale) {
      return "Settings changed elsewhere. Restart before saving."
    }
    if (!store.ready) {
      return "Settings are still loading."
    }
    if (!store.revision) {
      return "Settings could not be read (" + store.readError + "). Correct the file and restart."
    }
    if (store.busy) {
      return "A settings operation is still finishing."
    }
    return ""
  }

  function write(payload, callback) {
    var reason = store.refusal()
    if (reason) {
      callback({ error: reason })
      return
    }
    store.busy = true
    store.request(payload, function(result) {
      store.busy = false
      if (result.kind === "stale") {
        store.stale = true
      }
      if (!result.error) {
        store.revision = result.revision
        store.unwritten = false
        store.readError = ""
      }
      callback(result)
    })
  }

  // The first write of a file that did not exist. If another host made it
  // meanwhile, theirs is adopted rather than overwritten.
  function create(text, callback) {
    store.write({ operation: "create", text: text }, function(result) {
      if (!result.error) {
        store.adopt(result.config)
      }
      callback(result)
    })
  }

  // The caller has validated `text` (settings.js) and publishes the config
  // it prepared from it; a saved text has no problems left.
  function replace(text, expectedRevision, callback) {
    store.write({ operation: "replace", text: text, revision: expectedRevision }, function(result) {
      if (!result.error) {
        store.problems = []
      }
      callback(result)
    })
  }

  function prepare(text, callback) {
    if (store.busy) {
      callback({ error: "A settings operation is still finishing." })
      return
    }
    store.busy = true
    store.request({ operation: "validate", text: text }, function(result) {
      store.busy = false
      callback(result)
    })
  }

  function setTheme(id, callback) {
    store.write({ operation: "theme", theme: id, revision: store.revision }, function(result) {
      if (!result.error) {
        store.adopt(result.config)
      }
      callback(result)
    })
  }
}
