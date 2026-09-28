import NoteNote.Extensions 1.0

// Choosing a theme: look while moving through the list, keep on Enter. The
// themes and what this host can show are the theme service's to say; the
// selection is the settings' to keep.
Command {
  function execute(context, parameters, done) {
    context.settings.check(function(checked) {
      if (checked.error) {
        done(checked)
        return
      }
      context.themes.list(function(listing) {
        if (listing.error) {
          done(listing)
          return
        }
        choose(context, listing, done)
      })
    })
  }

  function unloaded(diagnostics) {
    if (!diagnostics.length) {
      return ""
    }
    var more = diagnostics.length > 1 ? " (and " + (diagnostics.length - 1) + " more)" : ""
    return diagnostics[0].id + ": " + diagnostics[0].message + more
  }

  function choose(context, listing, done) {
    var preview = context.themes.beginPreview()
    var picker = context.ui.pick({
      title: "Color Theme",
      items: listing.items,
      selectedId: context.themes.current(),
      message: unloaded(listing.diagnostics)
    }, {
      preview: function(id) {
        var item = listing.items.find(function(candidate) {
          return candidate.id === id
        })
        preview.preview(item && item.enabled ? id : "")
        var reason = item ? item.reason : ""
        picker.setMessage(reason || context.themes.diagnostics()[0] || unloaded(listing.diagnostics))
      },
      accept: function(id) {
        picker.setBusy(true, "Saving theme…")
        context.settings.setTheme(id, function(saved) {
          if (saved.error) {
            preview.preview("")
            picker.showError(saved.error)
            return
          }
          preview.commit(id)
          done({ ok: true })
        })
      }
    })
  }
}
