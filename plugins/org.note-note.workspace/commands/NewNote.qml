import NoteNote.Extensions 1.0

Command {
  function execute(context, parameters, done) {
    done(context.workspace.invoke("newNote"))
  }
}
