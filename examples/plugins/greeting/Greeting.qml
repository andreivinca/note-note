import NoteNote.Extensions 1.0

Command {
  function execute(context, parameters, done) {
    context.resources.readJson("greetings.json", function(result) {
      if (result.error) {
        done(result)
        return
      }
      context.ui.pick({ title: "Greeting", items: result.value }, {
        accept: function(id) {
          var item = result.value.find(function(item) { return item.id === id })
          context.ui.notify(item.label)
          done({ ok: true })
        }
      })
    })
  }
}
