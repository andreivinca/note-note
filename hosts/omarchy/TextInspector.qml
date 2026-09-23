import "../../cpp/build/NoteNote/Native"

// The native text inspector (cpp/textblocks.h) as the Omarchy shell loads
// it: a module the user builds (`sh cpp/build.sh`), imported by directory.
// The import is *optional* — NoteEditor loads this file through a Loader,
// and when the module has not been built the import fails, the Loader
// errors, and the editor falls back to scanning the document's HTML
// (ui/QuoteBars.js). The standalone host ships its own TextInspector.qml
// over the types linked into the executable.
TextBlocks {}
