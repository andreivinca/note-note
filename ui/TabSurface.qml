import QtQuick
import QtQuick.Shapes

// Fixed shoulder bounds keep the faces in place as selection changes.
// Selected shoulders and hover corners have independent radii.
Item {
  id: surface
  property bool selected: false
  property color color: "transparent"
  property real radius: 10
  property real selectedRadius: radius
  property real bottomInset: 0
  // Bounds contain the whole contour, with one shoulder radius on each side
  // of the face. The face itself must also fit its two upper corner radii.
  readonly property real arc: Math.min(radius, width / 4, height / 2)
  readonly property real cornerRadius: selected ? Math.max(0, Math.min(selectedRadius, arc))
    : Math.max(0, arc - bottomInset)
  readonly property real bottomY: selected ? height : Math.max(0, height - bottomInset)
  readonly property bool hovered: hover.hovered
  // True while the tab is dragged. `dragOrigin` is where the pointer took
  // hold and `dragPosition` where it is now, in scene coordinates, which
  // the tab moving under it does not change.
  readonly property bool dragged: drag.active
  readonly property point dragOrigin: drag.centroid.scenePressPosition
  readonly property point dragPosition: drag.centroid.scenePosition
  signal clicked()
  signal menuRequested()

  // The same path draws the tab and defines its pointer region, including
  // selected shoulders that extend beyond the face into neighboring slots.
  Shape {
    id: contour
    width: surface.width
    height: surface.height
    containsMode: Shape.FillContains
    preferredRendererType: Shape.CurveRenderer

    HoverHandler {
      id: hover
      cursorShape: Qt.PointingHandCursor
    }

    TapHandler {
      acceptedButtons: Qt.LeftButton
      onTapped: surface.clicked()
    }

    TapHandler {
      acceptedButtons: Qt.RightButton
      onTapped: surface.menuRequested()
    }

    // The strip moves the tab; this only says where the pointer took it.
    DragHandler {
      id: drag
      target: null
      cursorShape: Qt.ClosedHandCursor
    }

    ShapePath {
      fillColor: surface.color
      strokeColor: "transparent"
      strokeWidth: -1
      startX: surface.arc + surface.cornerRadius
      startY: 0
      PathLine {
        x: contour.width - surface.arc - surface.cornerRadius
        y: 0
      }
      PathArc {
        x: contour.width - surface.arc
        y: surface.cornerRadius
        radiusX: surface.cornerRadius
        radiusY: surface.cornerRadius
      }
      PathLine {
        x: contour.width - surface.arc
        y: surface.bottomY - surface.cornerRadius
      }
      PathArc {
        x: contour.width - surface.arc + (surface.selected ? surface.cornerRadius : -surface.cornerRadius)
        y: surface.bottomY
        radiusX: surface.cornerRadius
        radiusY: surface.cornerRadius
        direction: surface.selected ? PathArc.Counterclockwise : PathArc.Clockwise
      }
      PathLine {
        x: surface.arc + (surface.selected ? -surface.cornerRadius : surface.cornerRadius)
        y: surface.bottomY
      }
      PathArc {
        x: surface.arc
        y: surface.bottomY - surface.cornerRadius
        radiusX: surface.cornerRadius
        radiusY: surface.cornerRadius
        direction: surface.selected ? PathArc.Counterclockwise : PathArc.Clockwise
      }
      PathLine {
        x: surface.arc
        y: surface.cornerRadius
      }
      PathArc {
        x: surface.arc + surface.cornerRadius
        y: 0
        radiusX: surface.cornerRadius
        radiusY: surface.cornerRadius
      }
    }
  }
}
