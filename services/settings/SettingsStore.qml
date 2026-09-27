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
  property string revision: ""
  property bool ready: false
  property bool unwritten: false
  property bool busy: false
  property bool stale: false
  property string error: ""
  readonly property string script: Platform.localPath(Qt.resolvedUrl("config_io.py"))
  signal loaded()
  ProcessRunner { id: runner }

  function merge(value) {
    return Settings.merge(value, store.providerIds, store.providerDefaults)
  }

  function request(payload, callback) {
    return runner.run({ command: ["python3", store.script], timeoutMs: 15000, maxOutputBytes: 8 * 1024 * 1024,
                        payload: JSON.stringify(Object.assign({ path: store.path }, payload)) }, callback)
  }

  function load() {
    store.request({ operation: "read" }, function(result) {
      store.revision = result.revision || ""
      store.config = store.merge(result.config || {})
      store.unwritten = result.unwritten === true
      store.error = result.error || ""
      store.ready = true
      store.loaded()
    })
  }

  function check(callback) {
    store.request({ operation: "read" }, function(result) {
      if (result.revision !== store.revision) {
        store.stale = true
        callback({ error: "Settings changed elsewhere. Restart to load them before saving.", kind: "stale" })
        return
      }
      callback(result)
    })
  }

  function write(payload, expectedRevision, callback) {
    if (store.busy || !store.ready || !store.revision || store.stale) {
      callback({ error: store.stale ? "Settings changed elsewhere. Restart before saving." : "Settings are not ready for another save." })
      return
    }
    store.busy = true
    store.request(Object.assign({}, payload, { revision: expectedRevision }), function(result) {
      store.busy = false
      if (result.kind === "stale") {
        store.stale = true
      }
      if (!result.error) {
        store.revision = result.revision
        store.unwritten = false
        store.error = ""
      }
      callback(result)
    })
  }

  function replace(text, expectedRevision, callback) {
    store.write({ operation: "replace", text: text }, expectedRevision, callback)
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

  function setTheme(id, expectedRevision, callback) {
    store.write({ operation: "theme", theme: id }, expectedRevision, function(result) {
      if (!result.error) {
        store.config = store.merge(result.config)
      }
      callback(result)
    })
  }
}
