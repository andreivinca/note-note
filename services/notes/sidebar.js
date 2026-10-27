.pragma library
.import "ordering.js" as Ordering

// A tab's key is the provider's id and the section's own key, and this is
// the one place that spelling is known: everything else goes through
// these three, in one direction or the other.
function sectionKey(provider, section) {
  return provider.id + "/" + section.key
}

function providerIdOf(key) {
  return key.substring(0, key.indexOf("/"))
}

function ownKey(key) {
  return key.substring(key.indexOf("/") + 1)
}

// The tabs' order is the keys the user dragged them into. All of it is
// every key the order names, kept for a tab that is not there just now (a
// provider still listing) as for the ones on screen, with each of `keys`,
// the tabs there are in their providers' order, that it does not name. Such
// a tab, a new notebook or a provider's tab while it lists, stands after
// its provider's last; one whose provider the order does not name, as a
// provider turned back on, comes last.
function placed(order, keys) {
  var result = order.slice()
  keys.forEach(function(key) {
    if (result.indexOf(key) >= 0) {
      return
    }
    var at = result.length
    while (at > 0 && providerIdOf(result[at - 1]) !== providerIdOf(key)) {
      at--
    }
    result.splice(at > 0 ? at : result.length, 0, key)
  })
  return result
}

// The tabs there are, as the strip shows them.
function arranged(order, keys) {
  return placed(order, keys).filter(function(key) {
    return keys.indexOf(key) >= 0
  })
}

// The order with the tab `key` dragged before the tab `before`, or last.
function moved(order, keys, key, before) {
  var result = placed(order, keys).filter(function(other) {
    return other !== key
  })
  var at = result.indexOf(before)
  result.splice(at < 0 ? result.length : at, 0, key)
  return result
}

// The order without a provider's tabs, which come last when it is back.
function without(order, keys, providerId) {
  return placed(order, keys).filter(function(key) {
    return providerIdOf(key) !== providerId
  })
}

function matchesQuery(row, query) {
  return (row.title || "").toLowerCase().indexOf(query) >= 0
      || (row.preview || "").toLowerCase().indexOf(query) >= 0
}

function row(provider, key, source) {
  return { provider: provider.id, notebook: key, kind: source.kind || "note", path: source.path || "",
           title: source.title || "", hasTitle: provider.hasTitle !== false,
           preview: source.preview || "", icon: source.icon || "",
           reorder: Ordering.descriptor(provider, ownKey(key), source), level: source.level || 0,
           expanded: source.expanded === true, count: source.count, menu: source.menu || [],
           modified: source.modified || "" }
}

function timestamp(value) {
  var result = typeof value === "number" ? value : Date.parse(value || "")
  return isFinite(result) && result > 0 ? result : 0
}

// Reads provider snapshots; never selects, loads, saves, or mutates a provider.
function footerAction(provider, key, action) {
  return { provider: provider.id, section: key, path: action.path, title: action.title,
           icon: action.icon || "", prompt: action.prompt || "", shortcut: action.shortcut || "" }
}

function build(providers, active, query, contentHits) {
  var rows = [], footerActions = [], tabs = [], hits = {}, content = {}
  var q = query.toLowerCase()
  for (var id in contentHits) {
    for (var path in contentHits[id]) {
      content[path] = contentHits[id][path] === true
    }
  }
  providers.forEach(function(provider) {
    if (!active && !(provider.sections || []).length) {
      footerActions = footerActions.concat((provider.footerActions || []).map(function(action) {
        return footerAction(provider, "", action)
      }))
    }
    (provider.sections || []).forEach(function(section) {
      var key = sectionKey(provider, section)
      var all = section.rows || []
      var notes = section.notes || all.filter(function(item) { return item.kind === "note" })
      var found = q ? notes.filter(function(item) {
        return matchesQuery(item, q) || content[item.path] === true
      }) : []
      tabs.push({ key: key, provider: provider.id, name: section.name, color: section.color || "", logo: provider.logo || "",
                  count: section.count !== undefined ? section.count : notes.length })
      hits[key] = found.length
      if (key === active) {
        rows = (q ? found : all).map(function(item) { return row(provider, key, item) })
        footerActions = (section.footerActions || []).map(function(action) {
          return footerAction(provider, section.key, action)
        })
      }
    })
  })
  return { rows: rows, footerActions: footerActions, tabs: tabs, hits: hits }
}
