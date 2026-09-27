.pragma library

function score(text, query) {
  var label = text.toLocaleLowerCase()
  if (label === query) {
    return 0
  }
  if (label.split(/[\s:/.\-]+/).some(function(word) { return word.indexOf(query) === 0 })) {
    return 1
  }
  return label.indexOf(query) >= 0 ? 2 : -1
}

function filter(items, query, activeId) {
  var search = query.trim().slice(0, 256).toLocaleLowerCase()
  var result = []
  items.forEach(function(item) {
    var rank = search ? score(item.label, search) : 0
    if (rank < 0) {
      var keywords = [item.detail || ""].concat(item.keywords || []).join(" ")
      var keywordScore = score(keywords, search)
      rank = keywordScore < 0 ? -1 : keywordScore + 3
    }
    if (rank >= 0) {
      result.push({ item: item, score: rank })
    }
  })
  result.sort(function(a, b) {
    return a.score - b.score || a.item.label.localeCompare(b.item.label) || a.item.id.localeCompare(b.item.id)
  })
  var matches = result.slice(0, 4096).map(function(entry) { return entry.item })
  var index = matches.findIndex(function(item) { return item.id === activeId })
  return { items: matches, index: index >= 0 ? index : matches.length ? 0 : -1 }
}
