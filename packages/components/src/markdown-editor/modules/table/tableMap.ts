import type { Node } from "@tiptap/pm/model"
// @ts-expect-error declare missing types in prosemirror-tables
import { addToCache, type ColWidths, findBadColWidths, type Problem, readFromCache, type Rect, TableMap as TableMapBase } from "@tiptap/pm/tables"
import { getRow, isTableSection } from "./utils"

declare module "@tiptap/pm/tables" {
  export const findBadColWidths: (map: TableMap, colWidths: ColWidths, table: Node) => void

}

class TableMap extends TableMapBase {
  static override get(table: Node): TableMap {
    return readFromCache(table) || addToCache(table, computeMap(table))
  }

  /**
   * The number of rows of each table section
   */
  public sectionRows: number[] = []

  constructor(width: number, height: number, map: number[], sectionRows: number[], problems: Problem[] | null) {
    super(width, height, map, problems)
    this.sectionRows = sectionRows
  }

  // Return the indices of all sections that are touched (overlapped, even partially)
  // by the given rectangle.
  // Indices start from 0 and don't consider the caption, so if there's a caption
  // section n is table.child(n+1), otherwise it's table.child(n)
  sectionsInRect(rect: Rect): number[] {
    const result: number[] = []
    const sectionRows = this.sectionRows
    let top = 0
    let bottom = 0
    for (let i = 0; i < sectionRows.length; i++) {
      bottom += sectionRows[i]
      if (rect.top < bottom && rect.bottom > top)
        result.push(i)
      top = bottom
    }
    return result
  }

  isLastRowInSection(row: number): boolean {
    const srows = this.sectionRows
    let lastRow = 0
    for (let s = 0; s < srows.length; s++) {
      lastRow += srows[s]
      if (lastRow === row)
        return true
      if (lastRow > row)
        return false
    }
    return false
  }

  findSection(pos: number): Rect {
    const { top } = this.findCell(pos)
    let rows = 0
    let nextRows = 0
    for (let s = 0; s < this.sectionRows.length; s++) {
      nextRows = rows + this.sectionRows[s]
      if (top < rows) {
        return {
          left: 0,
          top: rows,
          right: this.width,
          bottom: nextRows,
        }
      }
      rows = nextRows
    }
    return {
      left: 0,
      top: 0,
      right: this.width,
      bottom: this.height,
    }
  }

  sectionOfRow(row: number): number {
    let countRows = 0
    for (let i = 0; i < this.sectionRows.length; i++) {
      countRows += this.sectionRows[i]
      if (row < countRows)
        return i
    }
    return -1
  }

  rectOverOneSection(rect: Rect) {
    const topSection = this.sectionOfRow(rect.top)
    return topSection >= 0 && topSection === this.sectionOfRow(rect.bottom - 1)
  }

  // Return the position at which the cell at the given row and column
  // starts, or would start, if a cell started there.
  override positionAt(row: number, col: number, table: Node): number {
    for (let i = 0; ; i++) {
      const { node, pos: rowStart } = getRow(table, row)
      const rowEnd = rowStart + node!.nodeSize
      if (i === row) {
        let index = col + row * this.width
        const rowEndIndex = (row + 1) * this.width
        // Skip past cells from previous rows (via rowspan)
        while (index < rowEndIndex && this.map[index] < rowStart) index++
        return index === rowEndIndex ? rowEnd - 1 : this.map[index]
      }
    }
  }
}

// Compute a table map.
export function computeMap(table: Node): TableMap {
  if (table.type.spec.tableRole !== "table")
    throw new RangeError(`Not a table node: ${table.type.name}`)
  const width = findWidth(table)
  const height = findHeight(table)
  const tmap = new TableMap(width, height, [], [], null)

  let offset = 0
  const colWidths: ColWidths = []
  let rowsOffset = 0
  for (let c = 0; c < table.childCount; c++) {
    const section = table.child(c)
    if (isTableSection(section)) {
      tmap.sectionRows.push(section.childCount)
      const smap = computeSectionMap(section, width, offset + 1, colWidths)
      tmap.map = tmap.map.concat(smap.map)
      if (smap.problems) {
        tmap.problems = tmap.problems || []
        smap.problems.forEach((prob) => {
          if (prob.type === "missing" || prob.type === "collision")
            prob.row += rowsOffset
          tmap.problems?.push(prob)
        })
      }
      rowsOffset += section.childCount
    }
    offset += section.nodeSize
  }
  let badWidths = false

  // For columns that have defined widths, but whose widths disagree
  // between rows, fix up the cells whose width doesn't match the
  // computed one.
  for (let i = 0; !badWidths && i < colWidths.length; i += 2) {
    if (colWidths[i] != null && colWidths[i + 1] < height)
      badWidths = true
  }
  if (badWidths)
    findBadColWidths(tmap, colWidths, table)

  return tmap
}

export function findWidth(table: Node): number {
  let width = -1
  let hasRowSpan = false
  for (let cIndex = 0; cIndex < table.childCount; cIndex++) {
    const sectionNode = table.child(cIndex)
    if (isTableSection(sectionNode)) {
      for (let row = 0; row < sectionNode.childCount; row++) {
        const rowNode = sectionNode.child(row)
        let rowWidth = 0
        if (hasRowSpan) {
          for (let j = 0; j < row; j++) {
            const prevRow = sectionNode.child(j)
            for (let i = 0; i < prevRow.childCount; i++) {
              const cell = prevRow.child(i)
              if (j + cell.attrs.rowspan > row)
                rowWidth += cell.attrs.colspan
            }
          }
        }
        for (let i = 0; i < rowNode.childCount; i++) {
          const cell = rowNode.child(i)
          rowWidth += cell.attrs.colspan
          if (cell.attrs.rowspan > 1)
            hasRowSpan = true
        }
        if (width === -1)
          width = rowWidth
        else if (width !== rowWidth)
          width = Math.max(width, rowWidth)
      }
    }
  }
  return width
}

export function findHeight(table: Node): number {
  let height = 0
  for (let cIndex = 0; cIndex < table.childCount; cIndex++) {
    const sectionNode = table.child(cIndex)
    if (isTableSection(sectionNode)) {
      height += sectionNode.childCount
    }
  }
  return height
}

export function computeSectionMap(
  section: Node,
  width: number,
  offset: number,
  colWidths: ColWidths,
): TableMap {
  if (!isTableSection(section))
    throw new Error(`Not a table section node: ${section.type.name}`)
  const height = section.childCount
  const map = []
  let mapPos = 0
  let problems: Problem[] | null = null
  for (let i = 0, e = width * height; i < e; i++) map[i] = 0

  for (let row = 0, pos = offset; row < height; row++) {
    const rowNode = section.child(row)
    pos++
    for (let i = 0; ; i++) {
      while (mapPos < map.length && map[mapPos] !== 0) mapPos++
      if (i === rowNode.childCount)
        break
      const cellNode = rowNode.child(i)
      const { colspan, rowspan, colwidth } = cellNode.attrs
      for (let h = 0; h < rowspan; h++) {
        if (h + row >= height) {
          (problems || (problems = [])).push({
            type: "overlong_rowspan",
            pos,
            n: rowspan - h,
          })
          break
        }
        const start = mapPos + h * width
        for (let w = 0; w < colspan; w++) {
          if (map[start + w] === 0) {
            map[start + w] = pos
          }
          else {
            (problems || (problems = [])).push({
              type: "collision",
              row,
              pos,
              n: colspan - w,
            })
          }
          const colW = colwidth && colwidth[w]
          if (colW) {
            const widthIndex = ((start + w) % width) * 2
            const prev = colWidths[widthIndex]
            if (
              prev === null
              || (prev !== colW && colWidths[widthIndex + 1] === 1)
            ) {
              colWidths[widthIndex] = colW
              colWidths[widthIndex + 1] = 1
            }
            else if (prev === colW) {
              colWidths[widthIndex + 1]++
            }
          }
        }
      }
      mapPos += colspan
      pos += cellNode.nodeSize
    }
    const expectedPos = (row + 1) * width
    let missing = 0
    while (mapPos < expectedPos) {
      if (map[mapPos++] === 0)
        missing++
    }
    if (missing)
      (problems || (problems = [])).push({ type: "missing", row, n: missing })
    pos++
  }
  const tableMap = new TableMap(width, height, map, [], problems)
  return tableMap
}

export interface CellAttrs {
  colspan: number
  rowspan: number
  colwidth: number[] | null
}

export { TableMap }
