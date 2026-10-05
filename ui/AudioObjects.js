.pragma library

// The rich text image is a presentation object. Only its fragment carries
// media metadata; the note serializer turns it back into an audio element.
function recording(source) {
  var marker = "#notenote-audio="
  var at = source.indexOf(marker)
  if (at < 0) {
    return null
  }
  try {
    var value = JSON.parse(decodeURIComponent(source.substring(at + marker.length)))
    if (value && typeof value.source === "string" && typeof value.title === "string") {
      return value
    }
  } catch (error) {
    return null
  }
  return null
}

function newIdentifier() {
  // Instance IDs distinguish copies that share the same playback bytes.
  return "nn-audio-" + "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function(character) {
    var random = Math.floor(Math.random() * 16)
    return (character === "x" ? random : (random & 3) | 8).toString(16)
  })
}

// A host's answer to a recording fetch, as the player reads it: { url } or
// { error } with a sentence to show beneath the recording's title.
function fetchAnswer(answer) {
  if (answer && answer.url) {
    return { url: answer.url }
  }
  var error = (answer && answer.error) || "the recording could not be downloaded"
  return { error: error.charAt(0).toUpperCase() + error.slice(1) }
}

// The instance IDs among a document's images, as a set: { id: true }.
function identifiers(images) {
  var found = {}
  for (var index = 0; index < images.length; index++) {
    var value = recording(images[index].source)
    if (value && value.id) {
      found[value.id] = true
    }
  }
  return found
}

// A pasted recording is a copy and gets a new instance ID, unless it puts
// back one that this note held and no longer holds: that is a move, and the
// recording keeps its identity and therefore its OneNote resource.
// `present` and `held` are ID sets: the document now, and since it was shown.
function pastedHtml(html, present, held) {
  var taken = Object.assign({}, present)
  return html.replace(/(<img\b[^>]*\bsrc=")([^"]*)(")/gi, function(match, before, source, after) {
    var value = recording(source)
    if (!value) {
      return match
    }
    if (!value.id || taken[value.id] || !held[value.id]) {
      value.id = newIdentifier()
    }
    taken[value.id] = true
    var marker = source.indexOf("#notenote-audio=")
    var pasted = source.substring(0, marker) + "#notenote-audio=" + encodeURIComponent(JSON.stringify(value))
    return before + pasted + after
  })
}

// Qt exports images in the same order as their object characters, including
// images inside table cells. This keeps players available in the shell when
// its optional native inspector is absent.
function imagesFromHtml(html, text) {
  var images = [], expression = /<img\b[^>]*>/g, match, position = -1
  while ((match = expression.exec(html)) !== null) {
    position = text.indexOf("\ufffc", position + 1)
    if (position < 0) {
      break
    }
    var source = /\bsrc="([^"]*)"/.exec(match[0])
    var width = /\bwidth="(\d+(?:\.\d+)?)"/.exec(match[0])
    var height = /\bheight="(\d+(?:\.\d+)?)"/.exec(match[0])
    if (source && width && height) {
      images.push({ position: position, source: source[1], width: Number(width[1]),
                    height: Number(height[1]), ascent: Number(height[1]) })
    }
  }
  return images
}

// Updating geometry must keep the player alive. Replacing a Repeater array
// would restart playback on every layout change, keystroke or resize.
function reconcile(model, entries) {
  for (var index = 0; index < entries.length; index++) {
    var entry = entries[index], found = -1
    for (var candidate = index; candidate < model.count; candidate++) {
      if (model.get(candidate).key === entry.key) {
        found = candidate
        break
      }
    }
    if (found < 0) {
      model.insert(index, entry)
    } else {
      if (found !== index) {
        model.move(found, index, 1)
      }
      model.set(index, entry)
    }
  }
  if (model.count > entries.length) {
    model.remove(entries.length, model.count - entries.length)
  }
}
