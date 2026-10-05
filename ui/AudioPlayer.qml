import QtQuick
import QtQuick.Controls as Controls
import "../design"
import "../design/controls" as DesignControls

// An inline recording: a round Play/Stop button beside the title, with the
// seek bar and the time beneath the title. It draws no surface of its own,
// so it reads as part of the note around it.
//
// A recording that is not a local file, such as a OneNote attachment, is
// fetched only when Play is pressed: the player asks for it (fetchRequested)
// and plays the private file the editor answers with (`fetched`).
Item {
  id: root

  property url audioSource
  property string recordingTitle: "Audio recording"
  property bool playbackAllowed: true
  property color foreground: Color.menu.text
  property color backgroundColor: Color.menu.background
  property color accent: Color.accent
  // The answer to fetchRequested: { url } with a private file:// URL, or
  // { error } when it could not be fetched; null before anyone asked.
  property var fetched: null
  // Play was pressed and the recording is being fetched for it.
  property bool fetching: false
  // Qt only ever plays a local file: a remote attachment is fetched into the
  // private cache by the provider, and Qt never receives a bearer token or a
  // URL from page content.
  readonly property bool localFile: root.audioSource.toString().indexOf("file://") === 0
  readonly property url playableSource: root.localFile ? root.audioSource
    : root.fetched && root.fetched.url && root.fetched.url.indexOf("file://") === 0 ? root.fetched.url : ""
  // Null when Qt Multimedia is not installed (AudioPlayback.qml).
  readonly property var media: playback.status === Loader.Ready ? playback.item : null
  readonly property bool playing: root.media !== null && root.media.playing
  readonly property int position: root.media ? root.media.position : 0
  readonly property int duration: root.media ? root.media.duration : 0
  readonly property bool seekable: root.media !== null && root.media.seekable
  // What keeps this recording from playing at all; Play is disabled.
  readonly property string failure: root.media === null ? "Playback needs Qt Multimedia"
    : !root.audioSource.toString() ? "Recording unavailable"
    : root.playableSource.toString() && root.media.failed ? "Cannot play this recording" : ""
  // What the line beneath the title says in place of the seek bar. A failed
  // fetch is said here, and Play tries again.
  readonly property string status: root.failure ? root.failure
    : root.fetching ? "Downloading…"
    : root.fetched && root.fetched.error ? root.fetched.error : ""
  // Where the title, seek bar and time begin, right of the button.
  readonly property real detailsX: playButton.width + 14
  signal started()
  signal fetchRequested()

  // Mirrors DISPLAY_WIDTH and DISPLAY_HEIGHT in services/markdown/audio.py:
  // the space the note's document reserves for the player.
  implicitWidth: 360
  implicitHeight: 56

  function stop() {
    root.fetching = false
    if (root.media) {
      root.media.rewind()
    }
  }

  function toggle() {
    if (root.playing || root.fetching) {
      root.stop()
    } else if (root.playbackAllowed && !root.failure) {
      root.started()
      if (root.playableSource.toString()) {
        root.media.play()
      } else {
        root.fetching = true
        root.fetchRequested()
      }
    }
  }

  onFetchedChanged: {
    if (root.fetched && root.fetched.error) {
      root.fetching = false
    }
  }
  // The fetched file arrives as the player's new source; play it if Play is
  // still what was asked for.
  Connections {
    target: root.media
    function onSourceChanged() {
      if (root.fetching && root.media.source.toString()) {
        root.fetching = false
        root.media.play()
      }
    }
  }

  function timeLabel(milliseconds) {
    var seconds = Math.max(0, Math.floor(milliseconds / 1000))
    return Math.floor(seconds / 60) + ":" + (seconds % 60 < 10 ? "0" : "") + seconds % 60
  }

  onPlaybackAllowedChanged: {
    if (!root.playbackAllowed) {
      root.stop()
    }
  }
  onAudioSourceChanged: root.stop()
  Component.onDestruction: root.stop()

  Loader {
    id: playback
    source: "AudioPlayback.qml"
  }
  Binding {
    target: root.media
    property: "source"
    value: root.playableSource
    when: root.media !== null
  }

  DesignControls.Button {
    id: playButton
    objectName: "audioPlayStop"
    y: (parent.height - height) / 2
    width: 40
    height: 40
    radius: width / 2
    focusable: true
    enabled: root.playbackAllowed && !root.failure
    tooltipText: root.fetching ? "Cancel download" : root.playing ? "Stop playback" : "Play recording"
    foreground: root.foreground
    accent: root.accent
    backgroundColor: root.accent
    hoverColor: Qt.lighter(root.accent, 1.12)
    pressedColor: Qt.darker(root.accent, 1.12)
    onClicked: root.toggle()

    // The glyphs take the note's background colour, which stands out on the
    // accent fill in light and dark themes alike.
    contentItem: Item {
      Connections {
        target: root
        function onBackgroundColorChanged() {
          playGlyph.requestPaint()
          spinner.requestPaint()
        }
      }
      Rectangle {
        visible: root.playing
        anchors.centerIn: parent
        width: 12
        height: 12
        radius: 2
        color: root.backgroundColor
      }
      Canvas {
        id: spinner
        visible: root.fetching
        anchors.centerIn: parent
        width: 18
        height: 18
        onVisibleChanged: requestPaint()
        onPaint: {
          var context = getContext("2d")
          context.clearRect(0, 0, width, height)
          context.strokeStyle = root.backgroundColor
          context.lineWidth = 2.5
          context.lineCap = "round"
          context.beginPath()
          context.arc(width / 2, height / 2, width / 2 - 2, 0, Math.PI * 1.5)
          context.stroke()
        }
        RotationAnimator on rotation {
          running: spinner.visible
          from: 0
          to: 360
          duration: 900
          loops: Animation.Infinite
        }
      }
      Canvas {
        id: playGlyph
        visible: !root.playing && !root.fetching
        // A triangle's visual centre sits left of its box's centre.
        anchors.centerIn: parent
        anchors.horizontalCenterOffset: 1
        width: 14
        height: 16
        onVisibleChanged: requestPaint()
        onPaint: {
          var context = getContext("2d")
          context.clearRect(0, 0, width, height)
          context.fillStyle = root.backgroundColor
          context.beginPath()
          context.moveTo(1, 1)
          context.lineTo(13, 8)
          context.lineTo(1, 15)
          context.closePath()
          context.fill()
        }
      }
    }
  }

  Text {
    x: root.detailsX
    y: 6
    width: Math.max(0, parent.width - x)
    height: 20
    text: root.recordingTitle
    textFormat: Text.PlainText
    elide: Text.ElideRight
    verticalAlignment: Text.AlignVCenter
    color: root.foreground
    font.family: Style.font.menuFamily
    font.pixelSize: Style.font.body
  }

  Text {
    x: root.detailsX
    y: 30
    width: Math.max(0, parent.width - x)
    height: 20
    visible: !!root.status
    text: root.status
    textFormat: Text.PlainText
    elide: Text.ElideRight
    verticalAlignment: Text.AlignVCenter
    color: Util.alpha(root.foreground, 0.65)
    font.family: Style.font.menuFamily
    font.pixelSize: Style.font.bodySmall
  }

  Controls.Slider {
    id: seek
    objectName: "audioSeek"
    x: root.detailsX
    y: 30
    width: Math.max(0, time.x - x - 12)
    height: 20
    leftPadding: 0
    rightPadding: 0
    visible: !root.status
    from: 0
    to: Math.max(1, root.duration)
    value: root.position
    enabled: root.playbackAllowed && root.seekable && root.duration > 0 && !root.failure
    live: true
    Accessible.name: "Recording position"
    onMoved: root.media.position = Math.round(value)

    background: Rectangle {
      x: seek.leftPadding
      y: seek.topPadding + (seek.availableHeight - height) / 2
      width: seek.availableWidth
      height: 4
      radius: 2
      color: Util.alpha(root.foreground, 0.18)
      Rectangle {
        width: seek.visualPosition * parent.width
        height: parent.height
        radius: parent.radius
        color: root.accent
      }
    }
    handle: Rectangle {
      x: seek.leftPadding + seek.visualPosition * (seek.availableWidth - width)
      y: seek.topPadding + (seek.availableHeight - height) / 2
      width: 12
      height: 12
      radius: 6
      color: root.accent
      border.width: seek.activeFocus ? 2 : 0
      border.color: root.foreground
    }
  }

  // Sized for the longest label this recording shows, so the seek bar keeps
  // its length while the position counts up.
  TextMetrics {
    id: timeExtent
    font: time.font
    text: root.timeLabel(root.duration) + " / " + root.timeLabel(root.duration)
  }
  Text {
    id: time
    x: parent.width - width
    y: 30
    width: Math.ceil(timeExtent.advanceWidth)
    height: 20
    visible: !root.status
    // A recording that was not fetched yet has no known length.
    text: root.duration > 0 ? root.timeLabel(seek.pressed ? seek.value : root.position) + " / " + root.timeLabel(root.duration)
      : "--:--"
    textFormat: Text.PlainText
    horizontalAlignment: Text.AlignRight
    verticalAlignment: Text.AlignVCenter
    color: Util.alpha(root.foreground, 0.65)
    font.family: Style.font.menuFamily
    font.pixelSize: Style.font.bodySmall
  }
}
