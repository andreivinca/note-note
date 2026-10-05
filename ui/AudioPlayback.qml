import QtQuick
import QtMultimedia

// The recording player's only use of Qt Multimedia. The module is optional:
// the Omarchy shell does not install it. AudioPlayer loads this file through
// a Loader, so without the module a note still opens and edits, and its
// recordings say why they cannot play.
MediaPlayer {
  readonly property bool playing: playbackState === MediaPlayer.PlayingState
  readonly property bool failed: error !== MediaPlayer.NoError

  // Stopped means back at the beginning, after Stop and at the end alike.
  function rewind() {
    stop()
    position = 0
  }

  audioOutput: AudioOutput {}
  onMediaStatusChanged: {
    if (mediaStatus === MediaPlayer.EndOfMedia) {
      rewind()
    }
  }
}
