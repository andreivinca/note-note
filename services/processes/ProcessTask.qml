import QtQuick
import "../platform"

// Both backends supply stream transport. Framing, bounds and settlement
// belong here so every provider has the same guarantees in either host.
Item {
  id: task
  property var command: []
  property var environment: ({})
  property var payload: undefined
  property bool streaming: false
  property bool raw: false
  property int timeoutMs: 30000
  property int maxOutputBytes: 32 * 1024 * 1024
  // Started with start(), cancelled with cancel(); this says whether a run
  // is under way, and is nobody's to set.
  readonly property bool running: !task.settled
  property var process: null
  property string output: ""
  property int outputBytes: 0
  property bool settled: true
  // The ticket of the run whose start is deferred: a cancel and a new start
  // before it fires leave the old ticket behind, so the old begin does not.
  property int generation: 0
  signal started()
  signal lineReceived(string line)
  signal finished(var result)

  function parse(text) {
    try {
      var result = JSON.parse(text)
      if (result && typeof result === "object" && !Array.isArray(result)) {
        return result
      }
    } catch (error) {
      // Invalid output is never an empty note.
    }
    return { error: "the process returned an invalid reply" }
  }
  function finish(result) {
    if (settled) {
      return
    }
    settled = true
    deadline.stop()
    var child = process
    process = null
    if (child) {
      child.stop()
      child.destroy()
    }
    output = ""
    finished(result)
  }
  function cancel() {
    finish({ error: "operation cancelled", cancelled: true })
  }
  // The UTF-8 length of `text`, from its code points: what the byte limit
  // is measured in, counted once per chunk and taken off once per line.
  function byteLength(text) {
    var bytes = 0
    for (var i = 0; i < text.length; i++) {
      var code = text.charCodeAt(i)
      if (code < 0x80) {
        bytes += 1
      } else if (code < 0x800) {
        bytes += 2
      } else if (code >= 0xD800 && code <= 0xDBFF) {
        bytes += 4
        i++
      } else {
        bytes += 3
      }
    }
    return bytes
  }
  function receive(chunk) {
    if (settled) {
      return
    }
    var bytes = byteLength(chunk)
    if (outputBytes + bytes > maxOutputBytes) {
      finish({ error: "the process output exceeded its byte limit" })
      return
    }
    output += chunk
    outputBytes += bytes
    if (streaming) {
      var newline = output.indexOf("\n")
      while (newline >= 0 && !settled) {
        var line = output.substring(0, newline)
        output = output.substring(newline + 1)
        outputBytes -= byteLength(line) + 1
        lineReceived(line)
        newline = output.indexOf("\n")
      }
    }
  }
  // One run at a time: a task started while it runs is left to finish, since
  // that run's answer is the one being waited for. The process itself
  // starts once start() has returned, so an answer never arrives before the
  // caller holds its handle, however fast the process fails.
  function start() {
    if (!settled) {
      return
    }
    settled = false
    output = ""
    outputBytes = 0
    var ticket = ++generation
    Qt.callLater(function() {
      task.begin(ticket)
    })
  }
  function begin(expected) {
    if (settled || expected !== generation) {
      return
    }
    try {
      process = Platform.createProcess(task)
      process.output.connect(task.receive)
      process.failed.connect(function(message) {
        task.finish({ error: message })
      })
      process.started.connect(function() {
        task.started()
        if (!task.settled) {
          if (task.payload !== undefined) {
            task.process.write(String(task.payload))
          }
          task.process.closeInput()
        }
      })
      process.exited.connect(function(code) {
        if (task.settled) {
          return
        }
        if (task.streaming && task.output.length > 0) {
          task.lineReceived(task.output)
        }
        var result = task.raw || task.streaming ? { text: task.output } : task.parse(task.output)
        if (code !== 0 && !result.error) {
          result.error = "the process exited with code " + code
        }
        task.finish(result)
      })
      if (timeoutMs > 0) {
        deadline.start()
      }
      process.start(command, Object.assign({}, Platform.environment, environment), {
        streaming: streaming,
        maxOutputBytes: maxOutputBytes
      })
    } catch (error) {
      finish({ error: "could not start the process: " + error.message })
    }
  }
  Timer {
    id: deadline
    interval: task.timeoutMs
    onTriggered: task.finish({ error: "operation timed out" })
  }
  Component.onDestruction: {
    if (process) {
      process.stop()
    }
  }
}
