import "../processes"
import "../platform"
import QtQuick

// A Microsoft sign-in for one provider: its own app registration, its own
// token file and its own scopes, so nothing about one provider's account
// touches another's. The code and the device-code flow are what they share.
Item {
  id: root

  readonly property string scriptDir: Platform.localPath(Qt.resolvedUrl(".")).replace(/\/$/, "")
  // The script every process here runs; a test points it at a stub.
  property string script: scriptDir + "/msgraph.py"

  // Who this sign-in belongs to (a provider id); names the token file, and
  // the entry in the platform's account config where a user may put a
  // registration of their own for this provider alone.
  property string owner: "default"
  readonly property string tokenPath: Platform.stateDir + "/note-note-ms-" + owner + ".json"
  // The provider's own app registration — the application (client) id of an
  // Entra public client that allows personal and work accounts. Every user
  // of the provider signs in through it; empty, and nobody can.
  property string clientId: ""
  // Space-separated Graph scopes to request at sign-in.
  property string scopes: "offline_access User.Read"
  // Optional features request incremental consent without signing notes out.
  property string optionalScopes: ""
  property string loginScopes: root.scopes
  // Environment for any process that uses msgraph.py on this account's behalf.
  readonly property var env: ({ NOTE_NOTE_MS_ACCOUNT: root.owner, NOTE_NOTE_MS_CLIENT_ID: root.clientId,
                                NOTE_NOTE_MS_SCOPES: root.scopes, NOTE_NOTE_MS_TOKEN: root.tokenPath,
                                NOTE_NOTE_MS_CACHE_SESSION: root.cacheSession,
                                NOTE_NOTE_MS_OPTIONAL_SCOPES: root.optionalScopes })

  property bool configured: false
  property bool signedIn: false
  property string account: ""
  property string cacheSession: ""
  property string grantedScope: ""
  property bool loggingIn: false

  signal updated()
  // The sign-in is gone: a status answer said so, or the user signed out. A
  // provider throws the account's caches away on this, and only on this —
  // `updated()` fires for every answer, and a probe that could not answer
  // at all leaves the state as it was rather than reading as signed out.
  signal signedOut()
  signal statusFailed(string error)
  signal codeReceived(string code, string uri)
  signal loginSucceeded()
  signal loginFailed(string error)

  function hasScope(s) { return (" " + root.grantedScope + " ").indexOf(" " + s + " ") >= 0 }

  function refresh() { statusProc.running = true }

  function login() { startLogin(root.scopes) }
  function loginOptional() { startLogin(root.scopes + " " + root.optionalScopes) }

  function startLogin(requestedScopes) {
    if (root.loggingIn) {
      return
    }
    root.loginScopes = requestedScopes
    root.loggingIn = true
    root.updated()
    loginProc.running = true
  }

  // Abandon an in-progress sign-in — the device code was lost (switching to
  // the browser to enter it can hide and reopen this app, which clears the
  // notice that showed it) or the user simply changed their mind.
  function cancelLogin() {
    if (!root.loggingIn) {
      return
    }
    root.reloginPending = false
    loginProc.running = false
  }

  // Sign out, then sign in again — for a token that predates a provider's scope.
  property bool reloginPending: false
  function relogin() { root.reloginPending = true; logout() }

  function logout() { logoutProc.running = true }

  ProcessTask {
    id: statusProc
    command: ["python3", root.script, "status"]
    environment: root.env
    raw: true
    onFinished: function(result) {
      var st = null
      try {
        st = JSON.parse(result.text || "")
      } catch (e) {
        st = null
      }
      if (!st || st.error) {
        // No answer, or the script's own error: the sign-in is whatever it
        // was, and the reason is said instead of a sign-out being invented.
        root.statusFailed(st && st.error ? st.error : (result.error || "the sign-in status could not be read"))
        root.updated()
        return
      }
      var wasSignedIn = root.signedIn
      root.configured = st.configured === true
      root.signedIn = st.signedIn === true
      root.account = st.account || ""
      root.cacheSession = st.cacheSession || ""
      root.grantedScope = st.scope || ""
      if (wasSignedIn && !root.signedIn) {
        root.signedOut()
      }
      root.updated()
    }
  }

  ProcessTask {
    id: loginProc
    timeoutMs: 600000
    command: ["python3", root.script, "login"]
    environment: Object.assign({}, root.env, { NOTE_NOTE_MS_SCOPES: root.loginScopes })
    streaming: true
    onLineReceived: function(line) {
      var msg
      try { msg = JSON.parse(line) } catch (e) { return }
      if (msg.userCode) {
        root.codeReceived(msg.userCode, msg.verificationUri)
      } else if (msg.ok) {
        root.loginSucceeded()
        root.refresh()
      } else if (msg.error) {
        root.loginFailed(msg.error)
      }
    }
    onFinished: { root.loggingIn = false; root.updated() }
  }

  ProcessTask {
    id: logoutProc
    command: ["python3", root.script, "logout"]
    environment: root.env
    onFinished: {
      var wasSignedIn = root.signedIn
      root.signedIn = false
      root.account = ""
      root.grantedScope = ""
      root.cacheSession = ""
      if (wasSignedIn) {
        root.signedOut()
      }
      root.updated()
      if (root.reloginPending) {
        root.reloginPending = false
        root.login()
      }
    }
  }
}
