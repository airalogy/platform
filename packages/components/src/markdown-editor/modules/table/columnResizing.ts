import type { Attrs, Node as ProsemirrorNode } from "@tiptap/pm/model"
import type { EditorState } from "@tiptap/pm/state"
import type { CellAttrs } from "./tableMap"
import { Plugin } from "@tiptap/pm/state"
import { cellAround, type ColumnResizingOptions, columnResizingPluginKey, type Dragging, ResizeState } from "@tiptap/pm/tables"
import { Decoration, DecorationSet, type EditorView } from "@tiptap/pm/view"
import { TableMap } from "./tableMap"
import { getColgroup, getRow, getTableNode } from "./utils"

export function handleDecorations(
  state: EditorState,
  cell: number,
): DecorationSet {
  const decorations = []
  const $cell = state.doc.resolve(cell)
  const tableInfo = getTableNode($cell)
  if (!tableInfo) {
    return DecorationSet.empty
  }
  const { table, start } = tableInfo
  const map = TableMap.get(table)
  const col
    = map.colCount($cell.pos - start) + $cell.nodeAfter!.attrs.colspan - 1
  for (let row = 0; row < map.height; row++) {
    const index = col + row * map.width
    // For positions that have either a different cell or the end
    // of the table to their right, and either the top of the table or
    // a different cell above them, add a decoration
    if (
      (col === map.width - 1 || map.map[index] !== map.map[index + 1])
      && (row === 0 || map.map[index] !== map.map[index - map.width])
    ) {
      const cellPos = map.map[index]
      const pos = start + cellPos + table.nodeAt(cellPos)!.nodeSize - 1
      const dom = document.createElement("div")
      dom.className = "column-resize-handle"
      if (columnResizingPluginKey.getState(state)?.dragging) {
        decorations.push(
          Decoration.node(
            start + cellPos,
            start + cellPos + table.nodeAt(cellPos)!.nodeSize,
            {
              class: "column-resize-dragging",
            },
          ),
        )
      }

      decorations.push(Decoration.widget(pos, dom))
    }
  }
  return DecorationSet.create(state.doc, decorations)
}

/**
 * @public
 */
export function columnResizing({
  handleWidth = 5,
  cellMinWidth = 25,
  defaultCellMinWidth = 100,
  lastColumnResizable = true,
}: ColumnResizingOptions = {}): Plugin {
  const plugin = new Plugin<ResizeState>({
    key: columnResizingPluginKey,
    state: {
      init(_: any, state: { schema: any }) {
        return new ResizeState(-1, false)
      },
      apply(tr: any, prev: { apply: (arg0: any) => any }) {
        return prev.apply(tr)
      },
    },
    props: {
      attributes: (state: any): Record<string, string> => {
        const pluginState = columnResizingPluginKey.getState(state)
        return pluginState && pluginState.activeHandle > -1
          ? { class: "resize-cursor" }
          : {}
      },

      handleDOMEvents: {
        mousemove: (view: any, event: MouseEvent) => {
          handleMouseMove(view, event, handleWidth, lastColumnResizable)
        },
        mouseleave: (view: any) => {
          handleMouseLeave(view)
        },
        mousedown: (view: any, event: MouseEvent) => {
          handleMouseDown(view, event, cellMinWidth, defaultCellMinWidth)
        },
      },

      decorations: (state: any) => {
        const pluginState = columnResizingPluginKey.getState(state)
        if (pluginState && pluginState.activeHandle > -1) {
          return handleDecorations(state, pluginState.activeHandle)
        }
      },
    },
  })
  return plugin
}

function handleMouseMove(
  view: EditorView,
  event: MouseEvent,
  handleWidth: number,
  lastColumnResizable: boolean,
): void {
  if (!view.editable)
    return

  const pluginState = columnResizingPluginKey.getState(view.state)
  if (!pluginState)
    return

  if (!pluginState.dragging) {
    const target = domCellAround(event.target as HTMLElement)
    let cell = -1
    if (target) {
      const { left, right } = target.getBoundingClientRect()
      if (event.clientX - left <= handleWidth)
        cell = edgeCell(view, event, "left", handleWidth)
      else if (right - event.clientX <= handleWidth)
        cell = edgeCell(view, event, "right", handleWidth)
    }

    if (cell !== pluginState.activeHandle) {
      if (!lastColumnResizable && cell !== -1) {
        const $cell = view.state.doc.resolve(cell)
        const tableInfo = getTableNode($cell)
        if (!tableInfo) {
          return
        }
        const { table, start: tableStart } = tableInfo
        const map = TableMap.get(table)
        const col
          = map.colCount($cell.pos - tableStart)
          + $cell.nodeAfter!.attrs.colspan
          - 1

        if (col === map.width - 1) {
          return
        }
      }

      updateHandle(view, cell)
    }
  }
}

function handleMouseLeave(view: EditorView): void {
  if (!view.editable)
    return

  const pluginState = columnResizingPluginKey.getState(view.state)
  if (pluginState && pluginState.activeHandle > -1 && !pluginState.dragging)
    updateHandle(view, -1)
}

function handleMouseDown(
  view: EditorView,
  event: MouseEvent,
  cellMinWidth: number,
  defaultCellMinWidth: number,
): boolean {
  if (!view.editable)
    return false

  const win = view.dom.ownerDocument.defaultView ?? window

  const pluginState = columnResizingPluginKey.getState(view.state)
  if (!pluginState || pluginState.activeHandle === -1 || pluginState.dragging)
    return false

  const cell = view.state.doc.nodeAt(pluginState.activeHandle)!
  const width = currentColWidth(view, pluginState.activeHandle, cell.attrs)
  view.dispatch(
    view.state.tr.setMeta(columnResizingPluginKey, {
      setDragging: { startX: event.clientX, startWidth: width },
    }),
  )

  function finish(event: MouseEvent) {
    win.removeEventListener("mouseup", finish)
    win.removeEventListener("mousemove", move)
    const pluginState = columnResizingPluginKey.getState(view.state)
    if (pluginState?.dragging) {
      updateColumnWidth(
        view,
        pluginState.activeHandle,
        draggedWidth(pluginState.dragging, event, cellMinWidth),
      )
      view.dispatch(
        view.state.tr.setMeta(columnResizingPluginKey, { setDragging: null }),
      )
    }
  }

  function move(event: MouseEvent): void {
    if (!event.which)
      return finish(event)
    const pluginState = columnResizingPluginKey.getState(view.state)
    if (!pluginState)
      return
    if (pluginState.dragging) {
      const dragged = draggedWidth(pluginState.dragging, event, cellMinWidth)
      displayColumnWidth(
        view,
        pluginState.activeHandle,
        dragged,
        defaultCellMinWidth,
      )
    }
  }

  displayColumnWidth(
    view,
    pluginState.activeHandle,
    width,
    defaultCellMinWidth,
  )

  win.addEventListener("mouseup", finish)
  win.addEventListener("mousemove", move)
  event.preventDefault()
  return true
}

function currentColWidth(
  view: EditorView,
  cellPos: number,
  { colspan, colwidth }: Attrs,
): number {
  const width = colwidth && colwidth[colwidth.length - 1]
  if (width)
    return width
  const dom = view.domAtPos(cellPos)
  const node = dom.node.childNodes[dom.offset] as HTMLElement
  let domWidth = node.offsetWidth
  let parts = colspan
  if (colwidth) {
    for (let i = 0; i < colspan; i++) {
      if (colwidth[i]) {
        domWidth -= colwidth[i]
        parts--
      }
    }
  }
  return domWidth / parts
}

function domCellAround(target: HTMLElement | null): HTMLElement | null {
  while (target && target.nodeName !== "TD" && target.nodeName !== "TH") {
    target
      = target.classList && target.classList.contains("ProseMirror")
        ? null
        : (target.parentNode as HTMLElement)
  }
  return target
}

function edgeCell(
  view: EditorView,
  event: MouseEvent,
  side: "left" | "right",
  handleWidth: number,
): number {
  // posAtCoords returns inconsistent positions when cursor is moving
  // across a collapsed table border. Use an offset to adjust the
  // target viewport coordinates away from the table border.
  const offset = side === "right" ? -handleWidth : handleWidth
  const found = view.posAtCoords({
    left: event.clientX + offset,
    top: event.clientY,
  })
  if (!found)
    return -1
  const { pos } = found
  const $cell = cellAround(view.state.doc.resolve(pos))
  if (!$cell)
    return -1
  if (side === "right")
    return $cell.pos
  const tableInfo = getTableNode($cell)
  if (!tableInfo)
    return -1
  const { table, start } = tableInfo
  const map = TableMap.get(table)
  const index = map.map.indexOf($cell.pos - start)
  return index % map.width === 0 ? -1 : start + map.map[index - 1]
}

function draggedWidth(
  dragging: Dragging,
  event: MouseEvent,
  resizeMinWidth: number,
): number {
  const offset = event.clientX - dragging.startX
  return Math.max(resizeMinWidth, dragging.startWidth + offset)
}

function updateHandle(view: EditorView, value: number): void {
  view.dispatch(
    view.state.tr.setMeta(columnResizingPluginKey, { setHandle: value }),
  )
}

function updateColumnWidth(
  view: EditorView,
  cell: number,
  width: number,
): void {
  const $cell = view.state.doc.resolve(cell)
  const tableInfo = getTableNode($cell)
  if (!tableInfo)
    return
  const { table, start } = tableInfo
  const map = TableMap.get(table)
  const col
    = map.colCount($cell.pos - start) + $cell.nodeAfter!.attrs.colspan - 1
  const tr = view.state.tr
  for (let row = 0; row < map.height; row++) {
    const mapIndex = row * map.width + col
    // Rowspanning cell that has already been handled
    if (row && map.map[mapIndex] === map.map[mapIndex - map.width])
      continue
    const pos = map.map[mapIndex]
    const attrs = table.nodeAt(pos)!.attrs as CellAttrs
    const index = attrs.colspan === 1 ? 0 : col - map.colCount(pos)
    if (attrs.colwidth && attrs.colwidth[index] === width)
      continue
    const colwidth = attrs.colwidth
      ? attrs.colwidth.slice()
      : zeroes(attrs.colspan)
    colwidth[index] = width
    tr.setNodeMarkup(start + pos, null, { ...attrs, colwidth })
  }
  if (tr.docChanged)
    view.dispatch(tr)
}

function displayColumnWidth(
  view: EditorView,
  cell: number,
  width: number,
  defaultCellMinWidth: number,
): void {
  const $cell = view.state.doc.resolve(cell)
  const tableInfo = getTableNode($cell)
  if (!tableInfo)
    return
  const { table, start } = tableInfo
  const col
    = TableMap.get(table).colCount($cell.pos - start)
    + $cell.nodeAfter!.attrs.colspan
    - 1
  let dom: Node | null = view.domAtPos($cell.start(-1)).node
  while (dom && dom.nodeName !== "TABLE") {
    dom = dom.parentNode
  }
  if (!dom)
    return

  updateColumnsOnResize(
    table,
    dom as HTMLTableElement,
    defaultCellMinWidth,
    col,
    width,
  )
}

function zeroes(n: number): 0[] {
  return Array.from({ length: n }, () => 0)
}

/**
 * @public
 */
export function updateColumnsOnResize(
  node: ProsemirrorNode,
  table: HTMLTableElement,
  cellMinWidth: number,
  overrideCol?: number,
  overrideValue?: number,
): void {
  let totalWidth = 0
  let fixedWidth = true
  const colgroup = getColgroup(table)
  if (!colgroup)
    return

  let nextDOM = colgroup.firstChild as HTMLElement
  const row = getRow(node, 0).node
  if (!row) {
    return
  }

  for (let i = 0, col = 0; i < row.childCount; i++) {
    const { colspan, colwidth } = row.child(i).attrs as CellAttrs
    for (let j = 0; j < colspan; j++, col++) {
      const hasWidth = overrideCol === col ? overrideValue : colwidth && colwidth[j]

      const cssWidth = hasWidth ? `${hasWidth}px` : ""
      totalWidth += hasWidth || cellMinWidth

      if (!hasWidth) {
        fixedWidth = false
      }
      if (!nextDOM) {
        const col = document.createElement("col")
        col.style.width = cssWidth
        colgroup.appendChild(col)
      }
      else {
        if (nextDOM.style.width !== cssWidth)
          nextDOM.style.width = cssWidth
        nextDOM = nextDOM.nextSibling as HTMLElement
      }
    }
  }

  while (nextDOM) {
    const after = nextDOM.nextSibling
    nextDOM.parentNode?.removeChild(nextDOM)
    nextDOM = after as HTMLElement
  }

  if (fixedWidth) {
    table.style.width = `${totalWidth}px`
    table.style.minWidth = ""
  }
  else {
    table.style.width = ""
    table.style.minWidth = `${totalWidth}px`
  }
}
