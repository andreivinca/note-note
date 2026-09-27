import QtQml

// One instance per invocation. Executable extensions are trusted host code.
QtObject {
  readonly property int apiVersion: 1

  function execute(context, parameters, done) {
    done({ error: "This command has no execute implementation." })
  }
}
