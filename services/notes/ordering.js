.pragma library

// A provider owns the group and item identifiers. The host only knows that
// items in the same group may exchange positions, optionally with children.
function descriptor(provider, section, row) {
  var source = row.reorder
  // A row that says nothing about ordering keeps the legacy meaning: under
  // `canReorder` an unfixed note belongs to its tab's group. An explicit
  // `reorder`, null included, is the provider's answer and always wins.
  if (source === undefined && provider.canReorder && !row.fixed && (row.kind || "note") === "note") {
    source = { scope: section, id: row.path }
  }
  if (!source || typeof source.scope !== "string" || typeof source.id !== "string" || !source.id) {
    return null
  }
  return { provider: provider.id, scope: source.scope, id: source.id,
           descendants: source.descendants === true }
}

function key(group) {
  return JSON.stringify([group.provider, group.scope])
}

function sameGroup(left, right) {
  return !!left && !!right && left.provider === right.provider && left.scope === right.scope
}

function ids(rows, group) {
  return rows.filter(function(row) {
    return sameGroup(row.reorder, group)
  }).map(function(row) {
    return row.reorder.id
  })
}

// Whether `order` names every one of `current`'s (unique) ids exactly once
// and nothing else: the only shape a reorder request may take. Providers
// check their own membership with it before writing.
function isPermutation(current, order) {
  if (!Array.isArray(order) || order.length !== current.length) {
    return false
  }
  var unique = new Set(order)
  return unique.size === order.length && current.every(function(id) {
    return unique.has(id)
  })
}

function blockLength(rows, index) {
  var row = rows[index]
  if (!row || !row.reorder || !row.reorder.descendants) {
    return 1
  }
  var end = index + 1
  while (end < rows.length && (rows[end].level || 0) > (row.level || 0)) {
    end++
  }
  return end - index
}

function pushRange(positions, from, to) {
  for (var position = from; position < to; position++) {
    positions.push(position)
  }
}

// Where each row of the reordered list comes from: indexes into `rows` that
// put the group's blocks in `order` while every other row keeps its slot.
// Null unless `order` is a complete, unique permutation of the group; a
// stale or partial list cannot remove items.
function arrangement(rows, group, order) {
  if (!group || !Array.isArray(order) || !order.length) {
    return null
  }
  var blocks = Object.create(null), slots = [], members = []
  for (var i = 0; i < rows.length; i++) {
    if (!sameGroup(rows[i].reorder, group)) {
      continue
    }
    var id = rows[i].reorder.id, length = blockLength(rows, i)
    if (blocks[id]) {
      return null
    }
    for (var child = i + 1; child < i + length; child++) {
      if (sameGroup(rows[child].reorder, group)) {
        return null
      }
    }
    blocks[id] = { index: i, length: length }
    slots.push(blocks[id])
    members.push(id)
    i += length - 1
  }
  if (!isPermutation(members, order)) {
    return null
  }
  var positions = [], cursor = 0
  for (var slot = 0; slot < slots.length; slot++) {
    var block = blocks[order[slot]]
    pushRange(positions, cursor, slots[slot].index)
    pushRange(positions, block.index, block.index + block.length)
    cursor = slots[slot].index + slots[slot].length
  }
  pushRange(positions, cursor, rows.length)
  return positions
}

// Return a new projection, leaving provider snapshots untouched.
function apply(rows, group, order) {
  var positions = arrangement(rows, group, order)
  if (!positions) {
    return null
  }
  return positions.map(function(position) {
    return rows[position]
  })
}
