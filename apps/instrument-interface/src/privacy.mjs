// Self-contained so Playwright can serialize this trusted predicate into the page.
export function overlapsPrivate(node, masks) {
  const contains = (ancestor, child) => {
    for (let current = child; current; current = current.assignedSlot || current.parentElement || current.getRootNode()?.host) {
      if (current === ancestor)
        return true
    }
    return false
  }
  return masks.some(mask => contains(mask, node) || contains(node, mask))
}
