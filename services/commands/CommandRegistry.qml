import QtQuick
import "../processes"

Item {
  id: registry
  property var descriptors: []
  property var catalog: null
  property var themeCatalog: null
  property var themes: null
  property var settings: null
  property var workspaceActions: null
  property var keybindings: null
  property var picker: null
  property var contextState: ({})
  property var active: null
  property int sequence: 0
  readonly property bool busy: active !== null
  signal notified(string message)
  signal listingChanged()
  onDescriptorsChanged: listingChanged()
  onContextStateChanged: listingChanged()
  Connections {
    target: registry.keybindings
    function onCompiledChanged() { registry.listingChanged() }
  }
  ProcessRunner { id: processes }

  function unavailable(descriptor) {
    if (!registry.contextState.extensionsAvailable) {
      return "Build the native module (sh cpp/build.sh) and restart to enable commands."
    }
    var reasons = { hasDocument: "Open a note first.", editorWritable: "This note is read-only.",
      settingsClean: "Save or discard your Settings edits first." }
    var requirements = descriptor.requires || []
    for (var i = 0; i < requirements.length; i++) {
      if (!registry.contextState[requirements[i]]) {
        return reasons[requirements[i]]
      }
    }
    if (descriptor.workspaceAction) {
      return registry.workspaceActions ? registry.workspaceActions.unavailable(descriptor.workspaceAction)
        : "Workspace actions are unavailable in this host."
    }
    return ""
  }

  function list() {
    return registry.descriptors.map(function(descriptor) {
      var reason = registry.unavailable(descriptor)
      return { id: descriptor.id, label: descriptor.title,
        detail: reason || descriptor.packageName, keywords: (descriptor.keywords || []).concat(descriptor.category || []),
        shortcut: registry.keybindings ? registry.keybindings.label(descriptor.id) : "",
        enabled: !reason, reason: reason }
    })
  }

  function valid(invocation) {
    return registry.active === invocation && !invocation.finished
  }

  function finish(invocation, result) {
    if (!registry.valid(invocation)) {
      return
    }
    invocation.finished = true
    var cleanup = invocation.cleanup.concat(invocation.cancelRequested ? invocation.cancellations : [])
    cleanup.forEach(function(callback) {
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
    registry.active = null
    if (result && result.error) {
      registry.picker.showCommands(registry.list(), result.error)
    } else {
      registry.picker.close()
    }
  }

  function cancel() {
    var invocation = registry.active
    if (!invocation) {
      return true
    }
    invocation.cancelRequested = true
    if (invocation.committing) {
      return false
    }
    registry.finish(invocation, { cancelled: true })
    return true
  }

  function contextFor(invocation) {
    function guarded(callback) {
      return function(result) {
        if (registry.valid(invocation)) {
          try {
            callback(result)
          } catch (error) {
            registry.finish(invocation, { error: error.message })
          }
        }
      }
    }
    function read(path, json, callback) {
      var task = registry.catalog.readResource(invocation.descriptor, path, json, guarded(callback))
      invocation.tasks.push(task)
    }
    return {
      workspace: {
        invoke: function(action) {
          if (!registry.valid(invocation) || invocation.cancelRequested || invocation.committing || invocation.handedOff) {
            return { error: "This command cannot start another workspace action." }
          }
          var reason = registry.workspaceActions ? registry.workspaceActions.unavailable(action)
            : "Workspace actions are unavailable in this host."
          if (reason) {
            return { error: reason }
          }
          invocation.handedOff = true
          // Restore the old focus before an action opens a page, input or
          // confirmation. Closing after it would steal the new view's focus.
          registry.picker.close()
          return registry.workspaceActions.invoke(action)
        }
      },
      ui: {
        pick: function(options, callbacks) {
          if (callbacks.cancel) {
            invocation.cancellations.push(function() {
              if (invocation.cancelRequested) {
                callbacks.cancel()
              }
            })
          }
          return registry.picker.pick(options, {
            preview: guarded(callbacks.preview || function() {}),
            accept: guarded(callbacks.accept), cancel: guarded(callbacks.cancel || function() {})
          })
        },
        notify: function(message) {
          if (registry.valid(invocation)) {
            registry.notified(String(message).slice(0, 1024))
          }
        }
      },
      themes: {
        list: function(callback) {
          invocation.tasks.push(registry.themeCatalog.refresh(guarded(function(result) {
            callback(result.error ? result : { items: registry.themeCatalog.list(), diagnostics: registry.themeCatalog.diagnostics })
          })))
        },
        current: function() { return registry.themes.committedThemeId },
        supported: registry.contextState.nativeDisplay,
        beginPreview: function() {
          var session = registry.themes.beginPreview()
          invocation.cleanup.push(session.cancel)
          return session
        },
        diagnostics: function() { return registry.themes.diagnostics }
      },
      settings: {
        revision: registry.settings.revision,
        check: function(callback) { registry.settings.check(guarded(callback)) },
        setTheme: function(id, revision, callback) {
          if (invocation.committing || !registry.valid(invocation)) {
            return
          }
          if (!registry.contextState.settingsClean) {
            callback({ error: "Save or discard Settings edits and wait for pending settings operations first." })
            return
          }
          invocation.committing = true
          registry.settings.setTheme(id, revision, function(result) {
            invocation.committing = false
            guarded(callback)(result)
            if (invocation.cancelRequested && registry.valid(invocation)) {
              registry.finish(invocation, { cancelled: true })
            }
          })
        }
      },
      resources: {
        readText: function(path, callback) { read(path, false, callback) },
        readJson: function(path, callback) { read(path, true, callback) }
      },
      cancellation: {
        isActive: function() { return registry.valid(invocation) && !invocation.cancelRequested },
        onCancel: function(callback) { invocation.cancellations.push(callback) }
      }
    }
  }

  function execute(id, parameters, focusOwner) {
    if (!registry.cancel()) {
      return
    }
    if (!registry.picker.opened) {
      registry.picker.rememberFocus(focusOwner || null)
    }
    var encodedArguments
    try {
      encodedArguments = JSON.stringify(parameters || {})
      if (encodedArguments.length > 65536) {
        throw new Error("Command arguments exceed the size limit.")
      }
    } catch (error) {
      registry.picker.showCommands(registry.list(), error.message)
      return
    }
    var descriptor = registry.descriptors.find(function(item) { return item.id === id })
    if (!descriptor) {
      registry.picker.showCommands(registry.list(), "This command is no longer available.")
      return
    }
    var reason = registry.unavailable(descriptor)
    if (reason) {
      registry.picker.showCommands(registry.list(), reason)
      return
    }
    var invocation = { id: ++registry.sequence, descriptor: descriptor, handler: null, component: null,
      cancellations: [], cleanup: [], tasks: [], finished: false, committing: false, cancelRequested: false, handedOff: false }
    registry.active = invocation
    registry.picker.setBusy(true, "Loading command…")
    var component = Qt.createComponent(descriptor.url, Component.Asynchronous)
    invocation.component = component
    function loaded() {
      if (!registry.valid(invocation) || component.status === Component.Loading) {
        return
      }
      if (component.status !== Component.Ready) {
        registry.finish(invocation, { error: component.errorString() })
        return
      }
      try {
        var handler = component.createObject(registry)
        invocation.handler = handler
        if (!handler || handler.apiVersion !== 1 || typeof handler.execute !== "function") {
          throw new Error("Invalid command handler: " + descriptor.id)
        }
        handler.execute(registry.contextFor(invocation), JSON.parse(encodedArguments), function(result) {
          registry.finish(invocation, result || { ok: true })
        })
      } catch (error) {
        registry.finish(invocation, { error: error.message })
      }
    }
    if (component.status === Component.Loading) {
      component.statusChanged.connect(loaded)
    } else {
      loaded()
    }
  }
}
