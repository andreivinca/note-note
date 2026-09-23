pragma Singleton
import QtQuick

QtObject {
  function flat(color, width) {
    return { color: color, width: width }
  }
  function none() {
    return flat("transparent", 0)
  }
  // A spec is one width all round; none is a width of zero.
  function width(spec) {
    return spec ? spec.width : 0
  }
}
