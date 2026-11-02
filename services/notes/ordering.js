.pragma library

// A provider owns the group and item identifiers. The host only knows that
// items in the same group may exchange positions, optionally with children,
// and how a drag shows where one lands: the rows make room for it (`rows`,
// the default), or a line between them marks the place (`line`).
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
           descendants: source.descendants === true,
           marker: source.marker === "line" ? "line" : "rows" }
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
  if (!(order instanceof Array) || order.length !== current.length) {
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

// The group's blocks as `rows` lists them: each member's id, the index of
// its row and the length of the block it carries. Null when a member is
// listed twice or a block carries another member.
function blocks(rows, group) {
  var seen = Object.create(null), result = []
  for (var i = 0; i < rows.length; i++) {
    if (!sameGroup(rows[i].reorder, group)) {
      continue
    }
    var id = rows[i].reorder.id, length = blockLength(rows, i)
    if (seen[id]) {
      return null
    }
    for (var child = i + 1; child < i + length; child++) {
      if (sameGroup(rows[child].reorder, group)) {
        return null
      }
    }
    seen[id] = true
    result.push({ id: id, index: i, length: length })
    i += length - 1
  }
  return result
}

// `order` once `id` has landed before what is now its `slot`th member,
// `order.length` meaning after the last one: where a line marker drops it.
function landed(order, id, slot) {
  var from = order.indexOf(id), result = order.slice()
  if (from < 0) {
    return result
  }
  result.splice(from, 1)
  result.splice(slot > from ? slot - 1 : slot, 0, id)
  return result
}

// Where each row of the reordered list comes from: indexes into `rows` that
// put the group's blocks in `order` while every other row keeps its slot.
// Null unless `order` is a complete, unique permutation of the group; a
// stale or partial list cannot remove items.
function arrangement(rows, group, order) {
  if (!group || !(order instanceof Array) || !order.length) {
    return null
  }
  var slots = blocks(rows, group)
  if (!slots) {
    return null
  }
  var byId = Object.create(null)
  slots.forEach(function(block) {
    byId[block.id] = block
  })
  if (!isPermutation(slots.map(function(block) {
    return block.id
  }), order)) {
    return null
  }
  var positions = [], cursor = 0
  for (var slot = 0; slot < slots.length; slot++) {
    var block = byId[order[slot]]
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
