import QtQuick

// What a command may ask of the application: the `context` handed to its
// execute(), one per invocation. An answer that arrives after the invocation
// has ended is dropped. Extensions are trusted code; this is a boundary for
// maintainability, not a sandbox.
QtObject {
  id: api
  required property var registry
  required property var catalog
  required property var themeCatalog
  required property var themes
  required property var settings
  required property var workspaceActions
  required property var picker

  function contextFor(invocation) {
    return {
      workspace: api.workspaceFor(invocation),
      ui: api.uiFor(invocation),
      themes: api.themesFor(invocation),
      settings: api.settingsFor(invocation),
      resources: api.resourcesFor(invocation),
      cancellation: api.cancellationFor(invocation)
    }
  }

  // A callback that runs only while the invocation lives, and whose own
  // failure ends the command instead of escaping into the application.
  function guarded(invocation, callback) {
    return function(result) {
      if (!api.registry.valid(invocation)) {
        return
      }
      try {
        callback(result)
      } catch (error) {
        api.registry.finish(invocation, { error: error.message })
      }
    }
  }

  function workspaceFor(invocation) {
    return {
      invoke: function(action) {
        if (!api.registry.valid(invocation) || invocation.cancelRequested || invocation.hold || invocation.handedOff) {
          return { error: "This command cannot start another workspace action." }
        }
        var reason = api.workspaceActions.unavailable(action)
        if (reason) {
          return { error: reason }
        }
        invocation.handedOff = true
        // Restore the old focus before an action opens a page, input or
        // confirmation. Closing after it would steal the new view's focus.
        api.picker.close()
        return api.workspaceActions.invoke(action)
      }
    }
  }

  function uiFor(invocation) {
    return {
      pick: function(options, callbacks) {
        if (!api.registry.valid(invocation)) {
          return null
        }
        if (callbacks.cancel) {
          invocation.cancellations.push(callbacks.cancel)
        }
        return api.picker.pick(options, {
          preview: api.guarded(invocation, callbacks.preview || function() {}),
          accept: api.guarded(invocation, callbacks.accept)
        })
      },
      notify: function(message) {
        if (api.registry.valid(invocation)) {
          api.registry.notified(String(message).slice(0, 1024))
        }
      }
    }
  }

  function themesFor(invocation) {
    return {
      list: function(callback) {
        var answer = api.guarded(invocation, function(result) {
          callback(result.error ? result : { items: api.themes.choices(), diagnostics: api.themeCatalog.diagnostics })
        })
        invocation.tasks.push(api.themeCatalog.refresh(answer))
      },
      current: function() {
        return api.themes.committedThemeId
      },
      diagnostics: function() {
        return api.themes.diagnostics
      },
      beginPreview: function() {
        var session = api.themes.beginPreview()
        invocation.cleanup.push(session.cancel)
        return session
      }
    }
  }

  function settingsFor(invocation) {
    return {
      check: function(callback) {
        api.settings.check(api.guarded(invocation, callback))
      },
      setTheme: function(id, callback) {
        if (invocation.hold || !api.registry.valid(invocation)) {
          return
        }
        var reason = api.registry.unmet(["settingsClean"])
        if (reason) {
          callback({ error: reason })
          return
        }
        // A write that has started is not abandoned half way: the palette
        // says what it is waiting for and closes once the answer is in.
        invocation.hold = "Finishing the settings save…"
        api.settings.setTheme(id, function(result) {
          invocation.hold = ""
          api.guarded(invocation, callback)(result)
          api.registry.honourCancel(invocation)
        })
      }
    }
  }

  function resourcesFor(invocation) {
    function read(path, json, callback) {
      var answer = api.guarded(invocation, callback)
      invocation.tasks.push(api.catalog.readResource(invocation.descriptor, path, json, answer))
    }
    return {
      readText: function(path, callback) {
        read(path, false, callback)
      },
      readJson: function(path, callback) {
        read(path, true, callback)
      }
    }
  }

  function cancellationFor(invocation) {
    return {
      isActive: function() {
        return api.registry.valid(invocation) && !invocation.cancelRequested
      },
      onCancel: function(callback) {
        invocation.cancellations.push(callback)
      }
    }
  }
}
