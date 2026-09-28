import QtQuick

// Looks commands up, says whether one can run, and owns an invocation from
// its first moment to its last. What a command may ask of the application
// is the CommandApi's to say.
Item {
  id: registry
  property var descriptors: []
  property var api: null
  property var workspaceActions: null
  property var keybindings: null
  property var picker: null
  property var contextState: ({})
  // What the palette says when it opens with nothing else to report.
  property string notice: ""
  property var active: null
  readonly property bool busy: active !== null
  // What a command may require of the moment, and what to say when the
  // moment does not offer it. A manifest names these; nothing else lists them.
  readonly property var requirements: ({
    hasDocument: "Open a note first.",
    editorWritable: "This note is read-only.",
    settingsClean: "Save or discard your Settings edits first."
  })
  signal notified(string message)
  signal listingChanged()
  onDescriptorsChanged: listingChanged()
  onContextStateChanged: listingChanged()
  Connections {
    target: registry.keybindings
    function onCompiledChanged() {
      registry.listingChanged()
    }
  }
  Connections {
    target: registry.workspaceActions
    function onAvailabilityChanged() {
      registry.listingChanged()
    }
  }

  // The first requirement the moment does not meet, in words, or nothing. A
  // name this version does not know is not met: it fails closed.
  function unmet(names) {
    var missing = names.find(function(name) {
      return !registry.contextState[name]
    })
    if (!missing) {
      return ""
    }
    return registry.requirements[missing]
      || "This command needs \"" + missing + "\", which this version does not provide."
  }

  function unavailable(descriptor) {
    if (descriptor.url && !registry.contextState.extensionsAvailable) {
      return "Build the native module (sh cpp/build.sh) and restart to enable commands."
    }
    var reason = registry.unmet(descriptor.requires || [])
    if (reason || !descriptor.workspaceAction) {
      return reason
    }
    return registry.workspaceActions.unavailable(descriptor.workspaceAction)
  }

  function list() {
    return registry.descriptors.map(function(descriptor) {
      var reason = registry.unavailable(descriptor)
      return { id: descriptor.id, label: descriptor.title, detail: descriptor.packageName,
        keywords: (descriptor.keywords || []).concat(descriptor.category || []),
        shortcut: registry.keybindings ? registry.keybindings.label(descriptor.id) : "",
        enabled: !reason, reason: reason }
    })
  }

  function valid(invocation) {
    return registry.active === invocation && !invocation.finished
  }

  function release(invocation) {
    var endings = invocation.cleanup.concat(invocation.cancelRequested ? invocation.cancellations : [])
    endings.forEach(function(callback) {
      try {
        callback()
      } catch (error) {
        console.warn("note-note command cleanup:", invocation.descriptor.id, error.message)
      }
    })
    invocation.tasks.forEach(function(task) {
      task.cancel()
    })
    if (invocation.handler) {
      invocation.handler.destroy()
    }
    if (invocation.component) {
      invocation.component.destroy()
    }
  }

  function finish(invocation, result) {
    if (!registry.valid(invocation)) {
      return
    }
    invocation.finished = true
    registry.release(invocation)
    registry.active = null
    if (result && result.error) {
      registry.picker.showCommands(registry.list(), result.error)
    } else {
      registry.picker.close()
    }
  }

  // Nothing when the active command was cancelled or none was running;
  // otherwise what it is in the middle of, in the words of whoever asked it
  // to wait. It ends by itself once that is over.
  function cancel() {
    var invocation = registry.active
    if (!invocation) {
      return ""
    }
    invocation.cancelRequested = true
    if (invocation.hold) {
      return invocation.hold
    }
    registry.finish(invocation, { cancelled: true })
    return ""
  }

  function honourCancel(invocation) {
    if (invocation.cancelRequested && !invocation.hold) {
      registry.finish(invocation, { cancelled: true })
    }
  }

  function refuse(message) {
    registry.picker.showCommands(registry.list(), message)
  }

  // Arguments travel as bounded JSON, so a handler gets data and nothing live.
  function encoded(parameters) {
    var text = JSON.stringify(parameters || {})
    if (text.length > 65536) {
      throw new Error("Command arguments exceed the size limit.")
    }
    return text
  }

  function execute(id, parameters, focusOwner) {
    if (registry.cancel()) {
      return
    }
    if (!registry.picker.opened) {
      registry.picker.rememberFocus(focusOwner || null)
    }
    var descriptor = registry.descriptors.find(function(item) {
      return item.id === id
    })
    var reason = descriptor ? registry.unavailable(descriptor) : "This command is no longer available."
    if (reason) {
      registry.refuse(reason)
      return
    }
    if (descriptor.workspaceAction) {
      registry.runWorkspaceAction(descriptor)
      return
    }
    try {
      registry.runHandler(descriptor, registry.encoded(parameters))
    } catch (error) {
      registry.refuse(error.message)
    }
  }

  function runWorkspaceAction(descriptor) {
    // Restore the old focus before the action opens a page, an input or a
    // confirmation. Closing after it would take the new view's focus.
    registry.picker.close()
    var result = registry.workspaceActions.invoke(descriptor.workspaceAction)
    if (result.error) {
      registry.refuse(result.error)
    }
  }

  function runHandler(descriptor, encodedArguments) {
    var invocation = { descriptor: descriptor, handler: null, component: null, cancellations: [], cleanup: [],
      tasks: [], finished: false, hold: "", cancelRequested: false, handedOff: false }
    registry.active = invocation
    registry.picker.setBusy(true, "Loading command…")
    var component = Qt.createComponent(descriptor.url, Component.Asynchronous)
    invocation.component = component
    function loaded() {
      if (registry.valid(invocation) && component.status !== Component.Loading) {
        registry.start(invocation, encodedArguments)
      }
    }
    if (component.status === Component.Loading) {
      component.statusChanged.connect(loaded)
    } else {
      loaded()
    }
  }

  function start(invocation, encodedArguments) {
    var component = invocation.component
    if (component.status !== Component.Ready) {
      registry.finish(invocation, { error: component.errorString() })
      return
    }
    try {
      var handler = component.createObject(registry)
      invocation.handler = handler
      if (!handler || handler.apiVersion !== 1 || typeof handler.execute !== "function") {
        throw new Error("Invalid command handler: " + invocation.descriptor.id)
      }
      handler.execute(registry.api.contextFor(invocation), JSON.parse(encodedArguments), function(result) {
        registry.finish(invocation, result || { ok: true })
      })
    } catch (error) {
      registry.finish(invocation, { error: error.message })
    }
  }
}
