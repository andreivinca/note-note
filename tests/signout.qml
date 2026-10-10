import QtQuick
import QtTest
import "app/hosts/standalone" as Native
import "app/services/platform"
import "app/services/microsoft" as Microsoft
import "app/plugins/org.note-note.notion" as Notion

// A sign-out is one only once the script confirms it: a Microsoft account
// and the Notion provider, each against a stand-in script whose answers the
// test chooses (tests/signout_selftest.py).
Item {
  id: test

  Native.Backend {
    Component.onCompleted: install()
  }

  // The stand-in answers for msgraph.py by the account's owner.
  Microsoft.Account {
    id: account
    clientId: "test"
    script: Platform.env("NOTE_NOTE_TEST_SIGNOUT_DIR") + "/msgraph_stub.py"
  }
  SignalSpy {
    id: accountUpdated
    target: account
    signalName: "updated"
  }
  SignalSpy {
    id: signedOut
    target: account
    signalName: "signedOut"
  }
  SignalSpy {
    id: signOutFailed
    target: account
    signalName: "signOutFailed"
  }

  Notion.Provider {
    id: notion
  }
  SignalSpy {
    id: notionNotice
    target: notion
    signalName: "noticeRequested"
  }
  SignalSpy {
    id: notionStatus
    target: notion
    signalName: "statusRequested"
  }
  SignalSpy {
    id: notionUpdated
    target: notion
    signalName: "updated"
  }

  TestCase {
    id: checks
    name: "SignOut"
    when: false

    function check(condition, message) {
      if (!condition) {
        throw new Error(message)
      }
    }

    function answered(spy, action) {
      var before = spy.count
      action()
      tryVerify(function() {
        return spy.count > before
      }, 5000)
    }

    function signIn(owner) {
      account.owner = owner
      answered(accountUpdated, function() {
        account.refresh()
      })
      check(account.signedIn, owner + ": the stand-in reports a sign-in")
    }

    function signOut() {
      answered(accountUpdated, function() {
        account.logout()
      })
    }

    function checkAccount() {
      signIn("undeletable")
      signOut()
      check(account.signedIn && signedOut.count === 0 && signOutFailed.count === 1,
            "a token that could not be removed keeps the account signed in")
      check(signOutFailed.signalArguments[0][0].indexOf("could not be removed") >= 0,
            "and the failure says why: " + signOutFailed.signalArguments[0][0])

      signIn("crashing")
      signOut()
      check(account.signedIn && signedOut.count === 0 && signOutFailed.count === 2,
            "a sign-out that crashed keeps the account signed in")

      signIn("silent")
      signOut()
      check(account.signedIn && signedOut.count === 0 && signOutFailed.count === 3,
            "a sign-out answered without ok keeps the account signed in")

      signIn("undeletable")
      answered(accountUpdated, function() {
        account.relogin()
      })
      check(account.signedIn && !account.reloginPending && !account.loggingIn,
            "signing in again does not begin after a sign-out that failed")

      signIn("removable")
      signOut()
      check(!account.signedIn && signedOut.count === 1 && signOutFailed.count === 4,
            "a confirmed sign-out signs the account out")
    }

    function checkNotion() {
      var stubs = Platform.env("NOTE_NOTE_TEST_SIGNOUT_DIR")
      notion.script = stubs + "/notion_undeletable.py"
      answered(notionUpdated, function() {
        notion.refresh()
      })
      check(notion.configured, "the stand-in reports Notion set up")
      notion.bodies = ({ p: { title: "Kept", body: "kept" } })
      answered(notionNotice, function() {
        notion.removeIntegration()
      })
      check(notionNotice.signalArguments[0][1].indexOf("could not be removed") >= 0,
            "a secret that could not be removed is said: " + notionNotice.signalArguments[0][1])
      check(notion.configured && notion.bodies.p !== undefined,
            "and the provider stays set up with what it had")

      notion.script = stubs + "/notion_cache_stays.py"
      answered(notionUpdated, function() {
        notion.removeIntegration()
      })
      check(!notion.configured && notion.bodies.p === undefined && notionNotice.count === 1,
            "a sign-out whose cache stayed is still a sign-out")
      check(notionStatus.count === 1 && notionStatus.signalArguments[0][0].indexOf("cached page list") >= 0,
            "and the cache that stayed is said on the status line")
    }

    function run() {
      checkAccount()
      checkNotion()
      console.log("<<<SIGNOUT_DONE>>>")
      Qt.exit(0)
    }
  }

  Timer {
    interval: 100
    running: true
    onTriggered: {
      try {
        checks.run()
      } catch (error) {
        console.error("FAIL!", error.message)
        Qt.exit(1)
      }
    }
  }
}
