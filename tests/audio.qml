import QtQuick
import QtTest
import "app/ui" as UI
import "app/hosts/standalone" as Native
import "app/services/markdown" as Markdown
import "app/services/platform"
import "app/services/shortcuts" as Shortcuts
import "app/services/clipboard" as Clipboard

Window {
  id: window
  visible: true
  width: 760
  height: 460
  color: "#1e1e2e"
  property int edits: 0
  property bool ready: false
  property string fixture: Platform.env("NOTE_NOTE_AUDIO_FIXTURE")
  property string screenshot: Platform.env("NOTE_NOTE_AUDIO_SCREENSHOT")

  Native.Backend { id: backend }
  Markdown.Markdown { id: markdown }
  Shortcuts.KeybindingRegistry { id: keybindings }
  Clipboard.Clipboard { id: clipboard }
  UI.NoteEditor {
    id: editor
    anchors.fill: parent
    hasNote: true
    readOnly: true
    markdown: markdown
    keybindings: keybindings
    clipboard: clipboard
    canImages: true
    foreground: "#cdd6f4"
    background: "#1e1e2e"
    accent: "#89b4fa"
    onEdited: window.edits++
  }
  Component.onCompleted: {
    backend.install()
    ready = true
  }

  TestCase {
    id: checks
    name: "Audio playback"
    when: false

    function body(title) {
      return '<audio src="' + window.fixture + '" title="' + title + '"></audio>'
    }

    function load(note, title) {
      var shown = false
      editor.setNote("Untitled", note, function(ok) {
        verify(ok)
        shown = true
      })
      tryVerify(function() {
        return shown
      }, 5000)
      tryVerify(function() {
        var player = findChild(editor, "audioPlayer")
        return player !== null && player.recordingTitle === title
      }, 5000)
      var player = findChild(editor, "audioPlayer")
      tryVerify(function() {
        return player.duration > 0 && player.seekable
      }, 5000)
      return player
    }

    function test_01_play_stop_seek_and_layout() {
      var player = load("Before\n\n" + body("Audio Recording.3gp") + "\n\nAfter", "Audio Recording.3gp")
      verify(player.width > 200)
      verify(player.height > 80)
      verify(!player.failure)
      var button = findChild(player, "audioPlayStop")
      mouseClick(button)
      tryVerify(function() {
        return player.playing && player.position > 100
      }, 5000)
      editor.updateDecorations()
      compare(findChild(editor, "audioPlayer"), player)
      verify(player.playing)
      window.width = 620
      wait(150)
      compare(findChild(editor, "audioPlayer"), player)
      verify(player.playing)

      var seek = findChild(player, "audioSeek")
      verify(seek.enabled)
      mousePress(seek, seek.width * 0.25, seek.height / 2)
      mouseMove(seek, seek.width * 0.65, seek.height / 2, 50)
      mouseRelease(seek, seek.width * 0.65, seek.height / 2)
      tryVerify(function() {
        return player.position > player.duration * 0.5
      }, 1500)
      var position = player.position
      tryVerify(function() {
        return player.position > position + 100
      }, 2000)
      compare(seek.value, player.position)
      mouseClick(button)
      tryVerify(function() {
        return !player.playing && player.position === 0
      }, 1000)
      compare(window.edits, 0)
      if (window.screenshot) {
        var saved = false
        editor.grabToImage(function(result) {
          verify(result.saveToFile(window.screenshot))
          saved = true
        })
        tryVerify(function() {
          return saved
        }, 3000)
      }
    }

    function test_02_end_and_note_switch_stop_playback() {
      var player = load(body("Recording"), "Recording")
      player.toggle()
      tryVerify(function() {
        return player.playing
      }, 1000)
      var seek = findChild(player, "audioSeek")
      seek.value = player.duration - 200
      seek.moved()
      tryVerify(function() {
        return !player.playing && player.position === 0
      }, 3000)
      player.toggle()
      tryVerify(function() {
        return player.playing
      }, 1000)
      editor.visible = false
      tryVerify(function() {
        return !player.playing && player.position === 0
      }, 1000)
      editor.visible = true
      player.toggle()
      editor.setNote("Next", "Plain text")
      compare(editor.activeAudioPlayer, null)
      compare(findChild(editor, "audioPlayer"), null)
      compare(window.edits, 0)
    }

    function test_03_fallback_and_unavailable_recording() {
      editor.inspectorUrl = ""
      var player = load(body("Without the native inspector"), "Without the native inspector")
      player.toggle()
      tryVerify(function() {
        return player.playing && player.position > 100
      }, 5000)
      player.stop()
      editor.setNote("Missing", '<audio src="" title="Unavailable recording"></audio>')
      tryVerify(function() {
        var missing = findChild(editor, "audioPlayer")
        return missing && !!missing.failure
      }, 5000)
      var missing = findChild(editor, "audioPlayer")
      verify(!findChild(missing, "audioPlayStop").enabled)
      verify(!findChild(missing, "audioSeek").enabled)
    }

    function test_04_only_one_recording_plays_at_a_time() {
      load(body("First") + "\n\n" + body("Second"), "First")
      var objects = findChild(editor, "audioObjects")
      tryCompare(objects, "count", 2)
      var first = objects.itemAt(0), second = objects.itemAt(1)
      tryVerify(function() {
        return second.duration > 0
      }, 5000)
      first.toggle()
      tryVerify(function() {
        return first.playing && first.position > 100
      }, 5000)
      second.toggle()
      tryVerify(function() {
        return second.playing && !first.playing && first.position === 0
      }, 1000)
      editor.updateDecorations()
      compare(objects.itemAt(1), second)
      verify(second.playing)
      editor.setNote("Next", "Plain text")
      compare(window.edits, 0)
    }

    function savedBody() {
      var result = null
      editor.requestMarkdown(function(markdown, ok) {
        verify(ok)
        result = markdown
      })
      tryVerify(function() {
        return result !== null
      }, 5000)
      return result
    }

    function test_05_edit_undo_save_and_reload_preserve_recording() {
      var player = load("Before\n\n" + body("Editable recording") + "\n\nAfter", "Editable recording")
      editor.readOnly = false
      editor.focusBody()
      var area = findChild(editor, "noteBody")
      verify(area !== null)
      area.cursorPosition = 0
      for (var character of "Edited ") {
        keyClick(character)
      }
      tryVerify(function() {
        return window.edits > 0
      }, 3000)
      var changed = savedBody()
      verify(changed.indexOf("Edited Before") >= 0, changed)
      verify(changed.indexOf(body("Editable recording")) >= 0, changed)
      compare(findChild(editor, "audioPlayer"), player)
      editor.undo()
      tryVerify(function() {
        return editor.plainText().indexOf("Edited") < 0
      }, 1000)
      var restored = savedBody()
      verify(restored.indexOf(body("Editable recording")) >= 0, restored)
      load(changed, "Editable recording")
      verify(editor.plainText().indexOf("Edited Before") >= 0)
      var before = window.edits
      player = findChild(editor, "audioPlayer")
      player.toggle()
      tryVerify(function() {
        return player.playing && player.position > 100
      }, 5000)
      player.stop()
      compare(window.edits, before)
    }

    function test_06_copy_paste_assigns_distinct_recording_instances() {
      load("Before\n\n" + body("Copied recording") + "\n\nAfter", "Copied recording")
      editor.readOnly = false
      var area = findChild(editor, "noteBody")
      var original = editor.plainText().indexOf("\ufffc")
      verify(original >= 0)
      area.select(original, original + 1)
      area.copy()
      area.deselect()
      area.cursorPosition = area.length
      editor.focusBody()
      keyClick(Qt.Key_Return)
      keyClick(Qt.Key_Return)
      editor.paste()
      var objects = findChild(editor, "audioObjects")
      tryCompare(objects, "count", 2, 5000)
      var firstPaste = savedBody()
      compare((firstPaste.match(/<audio\b/g) || []).length, 2)
      var firstId = /data-id="([^"]+)"/.exec(firstPaste)
      verify(firstId !== null, firstPaste)
      area.cursorPosition = 0
      editor.paste()
      tryCompare(objects, "count", 3, 5000)
      var secondPaste = savedBody()
      compare((secondPaste.match(/<audio\b/g) || []).length, 3)
      var ids = [], expression = /data-id="([^"]+)"/g, match
      while ((match = expression.exec(secondPaste)) !== null) {
        ids.push(match[1])
      }
      compare(ids.length, 2)
      verify(ids[0] !== ids[1])
      verify(ids.indexOf(firstId[1]) >= 0)
      load(secondPaste, "Copied recording")
      tryCompare(objects, "count", 3, 5000)
      compare(savedBody(), secondPaste)
    }

    function test_07_copy_paste_into_another_note_preserves_playback() {
      var original = body("Recording from another note").replace(
            "></audio>", ' data-id="nn-audio-source"></audio>')
      var source = "Source text\n\n" + original
      load(source, "Recording from another note")
      var savedSource = savedBody()
      var area = findChild(editor, "noteBody")
      var position = editor.plainText().indexOf("\ufffc")
      verify(position >= 0)
      area.select(position, position + 1)
      area.copy()
      var shown = false
      editor.setNote("Target", "Target text", function(ok) {
        verify(ok)
        shown = true
      })
      tryVerify(function() {
        return shown
      }, 5000)
      compare(findChild(editor, "audioPlayer"), null)
      area.cursorPosition = area.length
      editor.focusBody()
      keyClick(Qt.Key_Return)
      keyClick(Qt.Key_Return)
      editor.paste()
      var objects = findChild(editor, "audioObjects")
      tryCompare(objects, "count", 1, 5000)
      var saved = savedBody()
      verify(saved.indexOf("Target text") >= 0, saved)
      verify(saved.indexOf('title="Recording from another note"') >= 0, saved)
      var identifier = /data-id="([^"]+)"/.exec(saved)
      verify(identifier !== null, saved)
      verify(identifier[1] !== "nn-audio-source")
      var player = load(saved, "Recording from another note")
      player.toggle()
      tryVerify(function() {
        return player.playing && player.position > 100
      }, 5000)
      player.stop()
      compare(savedBody(), saved)
      load(source, "Recording from another note")
      compare(savedBody(), savedSource)
    }
  }

  Timer {
    interval: 20
    running: window.ready
    onTriggered: {
      var currentTest = "play_stop_seek_and_layout"
      try {
        checks.test_01_play_stop_seek_and_layout()
        currentTest = "end_and_note_switch"
        checks.test_02_end_and_note_switch_stop_playback()
        currentTest = "fallback_and_unavailable"
        checks.test_03_fallback_and_unavailable_recording()
        currentTest = "single_recording_playback"
        checks.test_04_only_one_recording_plays_at_a_time()
        currentTest = "editing_and_save"
        checks.test_05_edit_undo_save_and_reload_preserve_recording()
        currentTest = "copy_and_paste"
        checks.test_06_copy_paste_assigns_distinct_recording_instances()
        currentTest = "copy_into_another_note"
        checks.test_07_copy_paste_into_another_note_preserves_playback()
        console.log("<<<AUDIO_DONE>>>")
      } catch (error) {
        console.error("AUDIO_FAIL:", currentTest, error.stack)
      } finally {
        Qt.quit()
      }
    }
  }
}
