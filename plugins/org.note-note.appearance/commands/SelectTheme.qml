import NoteNote.Extensions 1.0

Command {
  function execute(context, parameters, done) {
    context.settings.check(function(result) {
      if (result.error) {
        done(result)
        return
      }
      context.themes.list(function(result) {
        if (result.error) {
          done(result)
          return
        }
        var preview = context.themes.beginPreview()
        var picker = null
        var pending = false
        var items = result.items.map(function(item) {
          var supported = context.themes.supported || item.id === "org.note-note.appearance/system"
          return Object.assign({}, item, { enabled: supported,
            detail: item.detail + (item.id === context.themes.current() ? " · Current" : ""),
            reason: supported ? "" : "Custom themes require the native display helper. Build it and restart." })
        })
        picker = context.ui.pick({ title: "Color Theme", items: items, selectedId: context.themes.current(),
          message: result.diagnostics.length ? "Some themes could not be loaded; see the application log." : "" }, {
          preview: function(id) {
            var item = items.find(function(item) { return item.id === id })
            preview.preview(item && item.enabled ? id : "")
            if (picker) {
              var warnings = context.themes.diagnostics()
              picker.setMessage(item && item.reason ? item.reason : warnings.length ? warnings[0] : "")
            }
          },
          accept: function(id) {
            if (pending) {
              return
            }
            pending = true
            picker.setBusy(true, "Saving theme…")
            context.settings.setTheme(id, context.settings.revision, function(result) {
              pending = false
              if (result.error) {
                preview.preview("")
                picker.showError(result.error)
                return
              }
              preview.commit(id)
              done({ ok: true })
            })
          },
          cancel: preview.cancel
        })
      })
    })
  }
}
