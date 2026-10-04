import QtQuick
import QtQuick.Controls as Controls
import QtMultimedia
import "../design"
import "../design/controls" as DesignControls

Rectangle {
  id: root

  property url audioSource
  property string recordingTitle: "Audio recording"
  property bool playbackAllowed: true
  property color foreground: Color.menu.text
  property color backgroundColor: Color.menu.background
  property color accent: Color.accent
  readonly property bool playing: media.playbackState === MediaPlayer.PlayingState
  readonly property int position: media.position
  readonly property int duration: media.duration
  readonly property bool seekable: media.seekable
  readonly property string failure: !media.source.toString() ? "Recording unavailable"
    : media.error !== MediaPlayer.NoError ? "Cannot play this recording" : ""
  signal started()

  implicitWidth: 360
  implicitHeight: 112
  radius: Style.controlRadius
  color: Qt.tint(root.backgroundColor, Util.alpha(root.foreground, 0.04))
  border.width: 1
  border.color: Util.alpha(root.foreground, 0.14)

  function stop() {
    media.stop()
    media.position = 0
  }

  function toggle() {
    if (root.playing) {
      root.stop()
    } else if (root.playbackAllowed && !root.failure) {
      root.started()
      media.play()
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
  Component.onDestruction: media.stop()

  MediaPlayer {
    id: media
    // OneNote resources are fetched into the private cache by the provider.
    // Qt never receives a bearer token or a URL from remote page content.
    source: root.audioSource.toString().indexOf("file://") === 0 ? root.audioSource : ""
    audioOutput: AudioOutput {}
    onMediaStatusChanged: {
      if (mediaStatus === MediaPlayer.EndOfMedia) {
        root.stop()
      }
    }
  }

  Text {
    x: 12
    y: 10
    width: parent.width - 24
    height: 18
    text: root.recordingTitle
    textFormat: Text.PlainText
    elide: Text.ElideRight
    color: root.foreground
    font.family: Style.font.menuFamily
    font.pixelSize: Style.font.body
  }

  DesignControls.Button {
    id: playButton
    objectName: "audioPlayStop"
    x: 12
    y: 34
    width: 40
    height: 40
    focusable: true
    enabled: root.playbackAllowed && !root.failure
    tooltipText: root.playing ? "Stop recording" : "Play recording"
    foreground: root.foreground
    accent: root.accent
    backgroundColor: Util.alpha(root.accent, 0.12)
    onClicked: root.toggle()

    contentItem: Item {
      Rectangle {
        visible: root.playing
        anchors.centerIn: parent
        width: 12
        height: 12
        color: root.accent
      }
      Canvas {
        id: playGlyph
        visible: !root.playing
        anchors.centerIn: parent
        width: 14
        height: 16
        onVisibleChanged: requestPaint()
        Connections {
          target: root
          function onAccentChanged() {
            playGlyph.requestPaint()
          }
        }
        onPaint: {
          var context = getContext("2d")
          context.clearRect(0, 0, width, height)
          context.fillStyle = root.accent
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

  Item {
    id: waveform
    x: 68
    y: 34
    width: Math.max(0, parent.width - x - 12)
    height: 40
    visible: !root.failure
    // Decorative, fixed square bars; playback progress is the seek bar below.
    Repeater {
      model: Math.floor(waveform.width / 8)
      Rectangle {
        required property int index
        x: index * 8
        y: (waveform.height - height) / 2
        width: 4
        height: 8 + ((index * 7 + index % 5 * 9) % 9) * 4
        color: Util.alpha(root.foreground, 0.35)
      }
    }
  }

  Text {
    x: 68
    y: 44
    width: Math.max(0, parent.width - x - 12)
    height: 20
    visible: !!root.failure
    text: root.failure
    textFormat: Text.PlainText
    elide: Text.ElideRight
    color: Util.alpha(root.foreground, 0.65)
    font.family: Style.font.menuFamily
    font.pixelSize: Style.font.body
  }

  Controls.Slider {
    id: seek
    objectName: "audioSeek"
    x: 12
    y: 79
    width: Math.max(0, parent.width - 112)
    height: 24
    from: 0
    to: Math.max(1, root.duration)
    value: root.position
    enabled: root.playbackAllowed && root.seekable && root.duration > 0 && !root.failure
    live: true
    Accessible.name: "Recording position"
    onMoved: media.position = Math.round(value)

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

  Text {
    x: parent.width - width - 12
    y: 83
    width: 88
    height: 18
    text: root.failure ? "" : root.timeLabel(seek.pressed ? seek.value : root.position) + " / " + root.timeLabel(root.duration)
    textFormat: Text.PlainText
    elide: Text.ElideRight
    horizontalAlignment: Text.AlignRight
    color: Util.alpha(root.foreground, 0.65)
    font.family: Style.font.menuFamily
    font.pixelSize: Style.font.bodySmall
  }
}
