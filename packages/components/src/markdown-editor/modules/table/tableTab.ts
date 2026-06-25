import type { Command } from "@tiptap/pm/state"
import type { Direction } from "@tiptap/pm/tables"
import { keydownHandler } from "@tiptap/pm/keymap"
import { Plugin, PluginKey, TextSelection } from "@tiptap/pm/state"

import { TableMap } from "./tableMap"

export const handleKeyDown = keydownHandler({
  "Tab": tabulation(1),
  "Shift-Tab": tabulation(-1),
})

function tabulation(dir: Direction): Command {
  return (state, dispatch, view) => {
    if (!view)
      return false
    const sel = state.selection
    const r = state.doc.resolve(sel.head)
    let d = r.depth
    let inCaption = false
    for (; d > 0; d--) {
      const role = r.node(d).type.spec.tableRole
      if (role === "row")
        break
      if (role === "caption" && dir > 0) {
        inCaption = true
        break
      }
    }
    const tableDepth = d - (inCaption ? 1 : 2)
    const table = r.node(tableDepth)
    if (!table || table.type.spec.tableRole !== "table")
      return false
    const tableStart = r.start(tableDepth)
    const tmap = TableMap.get(table)
    let nextCellPos
    if (inCaption) {
      nextCellPos = tmap.map[0]
    }
    else {
      const map = tmap.map
      const cellStart = inCaption
        ? tmap.positionAt(0, 0, table)
        : r.start(d + 1)
      const cellPos = cellStart - tableStart - 1
      let i
      for (
        i = dir < 0 ? 0 : map.length - 1;
        i >= 0 && i < map.length;
        i -= dir
      ) {
        if (cellPos === map[i])
          break
      }
      if (i < 0 || i >= map.length)
        return false
      i += dir
      if (i < 0 || i >= map.length)
        return false
      nextCellPos = map[i]
    }
    if (nextCellPos) {
      const cell = table.nodeAt(nextCellPos)
      if (!cell)
        return false
      if (dispatch) {
        const from = tableStart + nextCellPos
        const to = from + cell.nodeSize - 1
        dispatch(
          state.tr.setSelection(TextSelection.create(state.doc, from, to)),
        )
      }
      return true
    }
    return false
  }
}

export const tableTabKey = new PluginKey("tableTab")
export function tableTab(): Plugin {
  return new Plugin({
    key: tableTabKey,
    props: {
      handleKeyDown,
    },
  })
}
