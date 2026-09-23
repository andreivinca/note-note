pragma Singleton
import QtQuick

// The launcher installs its backend before initializing the workspace. The
// backend says what is its own — where its host keeps state and caches,
// which text inspector it ships, how it reads the system clipboard — and
// nothing here asks which host it is.
QtObject {
  property var backend: null
  readonly property url textInspectorUrl: backend ? backend.textInspectorUrl : ""
  // The host's directory names under the XDG bases: its state and cache
  // directory, its configuration directory (where external providers
  // live), and its Microsoft account configuration file.
  readonly property string storageName: backend ? backend.storageName : "notenote"
  readonly property string configName: backend ? backend.configName : "notenote"
  readonly property string accountConfig: backend ? backend.accountConfig : "notenote/accounts.json"

  function env(name) {
    return backend ? backend.env(name) : ""
  }
  function directory(variable, fallback) {
    var value = env(variable)
    return value.charAt(0) === "/" ? value : env("HOME") + fallback
  }
  readonly property string configDir: directory("XDG_CONFIG_HOME", "/.config") + "/notenote"
  readonly property string stateDir: directory("XDG_STATE_HOME", "/.local/state") + "/" + storageName
  readonly property string cacheDir: directory("XDG_CACHE_HOME", "/.cache") + "/" + storageName
  readonly property string providersDir: directory("XDG_CONFIG_HOME", "/.config") + "/" + configName + "/providers"
  readonly property string pasteDir: cacheDir + "/note-note-paste"
  readonly property var environment: ({
    NOTE_NOTE_STATE_DIR: stateDir,
    NOTE_NOTE_CACHE_DIR: cacheDir,
    NOTE_NOTE_PASTE_DIR: pasteDir,
    NOTE_NOTE_ACCOUNT_CONFIG: directory("XDG_CONFIG_HOME", "/.config") + "/" + accountConfig
  })
  function createProcess(parent) {
    if (!backend) {
      throw new Error("The application platform has not been initialized")
    }
    return backend.processComponent.createObject(parent)
  }
  function openUrl(url) {
    return Qt.openUrlExternally(url)
  }
  function copyText(text) {
    backend.copyText(text)
  }
  function localPath(url) {
    return decodeURIComponent(url.toString().replace(/^file:\/\//, ""))
  }
  function fileUrl(path) {
    return "file://" + path.split("/").map(encodeURIComponent).join("/")
  }
}
