// Various helper function for working with tables

import type { Fragment, Node, NodeType, ResolvedPos, Schema } from "@tiptap/pm/model"

export function isTableRow(node: Node): boolean {
  return node.type.spec.tableRole === "row"
}

export function isTableSection(node: Node): boolean {
  const role = node.type.spec.tableRole
  return role === "body" || role === "head" || role === "foot"
}
export function isTableDelimiterRow(node: Node): boolean {
  return node.type.spec.tableRole === "head"
}
/**
 * @public
 */
export interface CellAttrs {
  colspan: number
  rowspan: number
  colwidth: number[] | null
}

/// returns an object with the node, the position and the section index of a row in a table
export function getRow(
  table: Node,
  row: number,
  // debug: boolean = false,
): { node: Node | null, pos: number, section: number } {
  let rPos = 0
  let prevSectionsRows = 0
  let sectionIndex = -1
  for (let tc = 0; tc < table.childCount; tc++) {
    const section = table.child(tc)
    if (isTableSection(section)) {
      sectionIndex++
      const sectionRows = section.childCount
      if (sectionRows > 0) {
        // if (debug)
        //   console.log(
        //     `looking for row ${row} in section ${s}: ${section.type.name} with ${sectionRows} rows; prevSectionRows=${prevSectionsRows}`,
        //   );
        if (prevSectionsRows + sectionRows <= row) {
          if (tc === table.childCount - 1) {
            return {
              node: null,
              pos: rPos + section.nodeSize - 1,
              section: sectionIndex,
            }
          }
          rPos += section.nodeSize
          prevSectionsRows += sectionRows
        }
        else {
          rPos++ // section opening tag
          let r = 0
          while (r < sectionRows) {
            if (prevSectionsRows + r === row)
              break
            rPos += section.child(r).nodeSize
            r++
          }
          if (r === sectionRows)
            rPos++
          // if (debug)
          //   console.log(`row ${row} found @ pos ${rPos}, section ${s}`);
          return {
            node: r >= sectionRows ? null : section.child(r),
            pos: rPos,
            section: sectionIndex,
          }
        }
      }
    }
    else {
      // caption
      rPos += section.nodeSize
    }
  }
  return { node: null, pos: rPos, section: sectionIndex }
}

export function getColgroup(table: HTMLTableElement): HTMLElement {
  let colgroup = table.firstChild as HTMLElement
  let childIndex = 0
  while (colgroup) {
    const nodeName = colgroup.nodeName
    if (nodeName === "COLGROUP") {
      break
    }
    else if (nodeName === "CAPTION") {
      colgroup = colgroup.nextSibling as HTMLElement
      childIndex++
    }
    else {
      break
    }
  }
  if (colgroup) {
    if (colgroup.nodeName !== "COLGROUP") {
      colgroup = table.insertBefore(
        document.createElement("COLGROUP"),
        table.children[childIndex],
      )
    }
  }
  else {
    if (table.children.length === 0) {
      colgroup = table.appendChild(document.createElement("COLGROUP"))
    }
    else {
      colgroup = table.insertBefore(
        document.createElement("COLGROUP"),
        table.children[0],
      )
    }
  }
  return colgroup
}

export function tableDepth($pos: ResolvedPos): number {
  for (let d = $pos.depth; d >= 0; d--) {
    if ($pos.node(d).type.spec.tableRole === "table")
      return d
  }
  return -1
}

/**
 * Get the table node from a resolved position
 * Traverses up the document tree to find the node with tableRole="table"
 */
export function getTableNode($pos: ResolvedPos): { table: Node, depth: number, start: number } | null {
  const depth = tableDepth($pos)
  if (depth === -1) {
    return null
  }
  return {
    table: $pos.node(depth),
    depth,
    start: $pos.start(depth),
  }
}

/// returns true when the table has a caption
export function tableHasCaption(table: Node): boolean {
  if (table && table.type.spec.tableRole === "table") {
    return table.child(0).type.spec.tableRole === "caption"
  }
  return false
}

export type TableRole = "table" | "caption" | "head" | "body" | "foot" | "row" | "cell" | "header_cell" | "colgroup" | "col"

export function getTableNodeTypes(schema: Schema): { [key: string]: NodeType } {
  if (schema.cached.tableNodeTypes) {
    return schema.cached.tableNodeTypes
  }

  const roles: { [key: string]: NodeType } = {}

  Object.keys(schema.nodes).forEach((type) => {
    const nodeType = schema.nodes[type]

    if (nodeType.spec.tableRole) {
      roles[nodeType.spec.tableRole] = nodeType
    }
  })

  schema.cached.tableNodeTypes = roles

  return roles
}
export function createCell(
  cellType: NodeType,
  cellContent?: Fragment | Node | Array<Node>,
): Node | null | undefined {
  if (cellContent) {
    return cellType.createChecked(null, cellContent)
  }

  return cellType.createAndFill()
}

export function createTable(
  schema: Schema,
  rowsCount: number,
  colsCount: number,
  withHeaderRow: boolean,
  cellContent?: Fragment | Node | Array<Node>,
): Node {
  const types = getTableNodeTypes(schema)
  const colgroupCells: Node[] = []
  const headerCells: Node[] = []
  const cells: Node[] = []

  for (let index = 0; index < colsCount; index += 1) {
    const cell = createCell(types.cell, cellContent)

    const colgroupCell = createCell(types.col)
    if (colgroupCell) {
      colgroupCells.push(colgroupCell)
    }

    if (cell) {
      cells.push(cell)
    }

    if (withHeaderRow) {
      const headerCell = createCell(types.header_cell, cellContent)

      if (headerCell) {
        headerCells.push(headerCell)
      }
    }
  }

  const colgroup = createCell(types.colgroup, colgroupCells)

  const tableContent: Node[] = colgroup ? [colgroup] : []

  if (withHeaderRow) {
    const theadRow = types.row.createChecked(null, headerCells)
    const thead = types.head.createChecked(null, [theadRow])
    tableContent.push(thead)
  }

  const bodyRows: Node[] = []
  const startIndex = withHeaderRow ? 1 : 0

  for (let index = startIndex; index < rowsCount; index++) {
    // Create new cells for each row to avoid reusing the same node instances
    const rowCells: Node[] = []
    for (let colIndex = 0; colIndex < colsCount; colIndex++) {
      const cell = createCell(types.cell, cellContent)
      if (cell) {
        rowCells.push(cell)
      }
    }
    const row = types.row.createChecked(null, rowCells)
    bodyRows.push(row)
  }

  const tbody = types.body.createChecked(null, bodyRows)
  tableContent.push(tbody)

  return types.table.createChecked(null, tableContent)
}

export function getRows(table: Node, rows: Node[] = []): Node[] {
  for (let index = 0; index < table.childCount; index++) {
    const node = table.child(index)
    if (isTableRow(node)) {
      rows.push(node)
    }
    else if (isTableSection(node)) {
      getRows(node, rows)
    }
  }

  return rows
}
