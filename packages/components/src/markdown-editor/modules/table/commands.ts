import type { NodeType } from "@tiptap/pm/model"
import type { EditorState, Transaction } from "@tiptap/pm/state"
import { tableNodeTypes } from "@tiptap/pm/tables"
import { tableDepth, tableHasCaption, type TableRole } from "./utils"

/**
 * Add a caption to the table, if not already present.
 *
 * @public
 */
export function addCaption(
  state: EditorState,
  dispatch?: (tr: Transaction) => void,
): boolean {
  const $anchor = state.selection.$anchor
  const d = tableDepth($anchor)
  if (d < 0)
    return false
  const table = $anchor.node(d)
  if (tableHasCaption(table))
    return false
  if (dispatch) {
    const pos = $anchor.start(d)
    const types = tableNodeTypes(state.schema) as Record<TableRole, NodeType>

    const caption = types.caption.createAndFill()
    dispatch(state.tr.insert(pos, caption!))
  }
  return true
}
