import QtQuick

// The workspace's own actions and when each can run: the one executor behind
// the palette, the shortcuts and a command's context. Plugins never receive
// the workspace itself.
QtObject {
  id: actions
  required property var host
  property bool blocked: false
  // Everything availability depends on, so whoever lists the actions can
  // follow it instead of asking again on a guess.
  readonly property var state: ({ blocked: blocked, opened: host.opened, closing: host.closing,
    pageOpen: host.pageOpen, providersLoaded: host.providersLoaded, footerActions: host.footerActions,
    currentPath: host.currentPath })
  signal availabilityChanged()
  onStateChanged: availabilityChanged()

  readonly property var handlers: ({
    newNote: function() {
      host.newNote()
    },
    newNotebook: function() {
      host.startNewNotebook()
    },
    openSettings: function() {
      host.openPage("settings")
    },
    toggleList: function() {
      host.toggleList()
    },
    deleteNote: function() {
      host.requestDelete(host.currentPath)
    }
  })

  function hasFooter(shortcut) {
    return state.footerActions.some(function(action) {
      return action.shortcut === shortcut
    })
  }

  function canCreateNote() {
    if (hasFooter("newNote") || hasFooter("newNotebook")) {
      return true
    }
    var destination = host.newNoteDestination()
    return !!(destination.provider && destination.provider.canCreate && destination.target)
  }

  function canDeleteNote() {
    var provider = host.providerOf(state.currentPath)
    return !!(state.currentPath && provider && provider.canDelete)
  }

  // Why the notes are not there to act on, or nothing.
  function notesUnavailable() {
    if (state.pageOpen) {
      return "Return to your notes first."
    }
    return state.providersLoaded ? "" : "Wait for the notebooks to load."
  }

  function unavailable(action) {
    if (!Object.prototype.hasOwnProperty.call(handlers, action)) {
      return "Unknown workspace action: " + action
    }
    if (state.blocked || !state.opened || state.closing) {
      return "Wait for the current operation to finish."
    }
    if (action === "openSettings") {
      return ""
    }
    var reason = actions.notesUnavailable()
    if (reason) {
      return reason
    }
    if (action === "newNotebook" && !hasFooter("newNotebook")) {
      return "This notebook source cannot create notebooks here."
    }
    if (action === "newNote" && !canCreateNote()) {
      return "Open a notebook that supports new notes."
    }
    if (action === "deleteNote" && !canDeleteNote()) {
      return "Open a note that can be deleted."
    }
    return ""
  }

  // Success means the existing UI flow accepted the action. Its provider
  // operation or confirmation continues under the workspace's ownership.
  function invoke(action) {
    var reason = actions.unavailable(action)
    if (reason) {
      return { error: reason }
    }
    handlers[action]()
    return { ok: true }
  }
}
