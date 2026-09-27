import QtQuick

// A small host-owned action interface. Plugins never receive the workspace.
QtObject {
  id: actions
  required property var host
  property bool blocked: false
  readonly property var handlers: ({
    newNote: function() { host.newNote() },
    newNotebook: function() { host.startNewNotebook() },
    openSettings: function() { host.openPage("settings") },
    toggleList: function() { host.toggleList() },
    deleteNote: function() { host.requestDelete(host.currentPath) }
  })

  function hasFooter(shortcut) {
    return host.footerActions.some(function(action) {
      return action.shortcut === shortcut
    })
  }

  function unavailable(action) {
    if (!Object.prototype.hasOwnProperty.call(handlers, action)) {
      return "Unknown workspace action: " + action
    }
    if (actions.blocked || !host.opened || host.closing) {
      return "Wait for the current operation to finish."
    }
    if (action === "openSettings") {
      return ""
    }
    if (host.pageOpen) {
      return "Return to your notes first."
    }
    if (!host.providersLoaded) {
      return "Wait for the notebooks to load."
    }
    if (action === "newNotebook") {
      return hasFooter("newNotebook") ? "" : "This notebook source cannot create notebooks here."
    }
    if (action === "newNote") {
      if (hasFooter("newNote") || hasFooter("newNotebook")) {
        return ""
      }
      var destination = host.newNoteDestination()
      return destination.provider && destination.provider.canCreate && destination.target
        ? "" : "Open a notebook that supports new notes."
    }
    if (action === "deleteNote") {
      var provider = host.providerOf(host.currentPath)
      return host.currentPath && provider && provider.canDelete ? "" : "Open a note that can be deleted."
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
