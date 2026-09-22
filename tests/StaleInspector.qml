import QtQuick

// A native text inspector built from older sources, as the editor's Loader
// sees one: the interface version is not the editor's.
QtObject {
  property int version: 0
  property var document: null
}
