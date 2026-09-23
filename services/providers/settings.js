.pragma library

function equal(a, b) {
  if (a === b) {
    return true
  }
  if (!a || !b || typeof a !== "object" || typeof b !== "object") {
    return false
  }
  var keys = Object.keys(a), other = Object.keys(b)
  if (keys.length !== other.length) {
    return false
  }
  return keys.every(function(key) { return key in b && equal(a[key], b[key]) })
}

// The keys of an entry that name the provider's resources: everything but
// `enabled` and the settings the provider applies to a live instance.
function resources(entry, live) {
  var result = {}
  for (var key in entry) {
    if (key !== "enabled" && live.indexOf(key) < 0) {
      result[key] = entry[key]
    }
  }
  return result
}

function picked(entry, keys) {
  var result = {}
  keys.forEach(function(key) { result[key] = entry[key] })
  return result
}

// What each provider needs done for the config to go from old to new: a
// changed resource, or being turned on or off, replaces the instance; a
// changed live setting — one the provider declared in `liveSettings`
// (PROVIDERS.md) — is handed to the instance it has. `liveOf(id)` answers a
// provider's live settings, and none for one not running.
function plan(oldConfig, newConfig, ids, liveOf) {
  return ids.map(function(id) {
    var before = (oldConfig.providers || {})[id] || {}
    var after = (newConfig.providers || {})[id] || {}
    var live = liveOf(id)
    var was = before.enabled !== false, now = after.enabled !== false
    return { id: id, enabled: now,
             replace: was !== now || (now && !equal(resources(before, live), resources(after, live))),
             presentation: was && now && !equal(picked(before, live), picked(after, live)) }
  }).filter(function(change) { return change.replace || change.presentation })
}
