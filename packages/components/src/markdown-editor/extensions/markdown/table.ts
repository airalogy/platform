import type { Editor } from "@tiptap/core"
import type { Node as ProseMirrorNode } from "@tiptap/pm/model"
import { isTableDelimiterRow, isTableSection } from "../../modules/table/utils"

function childNodes(node: ProseMirrorNode) {
  return node?.content?.content ?? []
}

function serialize(this: { editor: Editor }, state: any, node: any, parent: any) {
  state.inTable = true

  // First pass: calculate column widths
  const columnWidths: number[] = []
  node.forEach((row: any) => {
    if (row.type.name === "tableBody") {
      row.content.forEach((bodyRow: any) => {
        calculateColumnWidths(bodyRow, columnWidths)
      })
    }
    else if (row.type.name !== "tableColgroup") {
      calculateColumnWidths(row, columnWidths)
    }
  })

  // Second pass: write formatted rows
  node.forEach((row: any, p: any, i: any) => {
    if (row.type.name === "tableBody") {
      row.content.forEach((row: any) => {
        handleRow(state, row, columnWidths)
        state.ensureNewLine()
      })
    }
    else {
      handleRow(state, row, columnWidths)
    }
  })

  state.closeBlock(node)
  state.inTable = false
}

function calculateColumnWidths(row: any, columnWidths: number[]) {
  if (row.type.name === "tableColgroup") {
    return
  }

  const isRowInTableSection = isTableSection(row)
  const cols = isRowInTableSection ? row.firstChild.content : row

  // Make sure cols is an array-like object we can iterate over
  if (cols && typeof cols.forEach === "function") {
    cols.forEach((col: any, index: number) => {
      if (col && col.firstChild) {
        const cellContent = col.firstChild
        // Clean up the text content to match what will be rendered (remove newlines and extra spaces)
        const cleanedText = cellContent.textContent.replace(/\n+/g, " ").replace(/\s+/g, " ").trim()
        const textLength = cleanedText.length

        // Ensure minimum width of 3 for delimiter cells (---)
        const cellWidth = Math.max(textLength, 3)

        if (!columnWidths[index] || columnWidths[index] < cellWidth) {
          columnWidths[index] = cellWidth
        }
      }
    })
  }
}

function handleRow(state: any, row: any, columnWidths: number[]) {
  if (row.type.name === "tableColgroup") {
    return
  }

  state.write("| ")

  const isRowInTableSection = isTableSection(row)
  const isHeaderRow = isRowInTableSection && isTableDelimiterRow(row)
  const cols = isRowInTableSection ? row.firstChild.content : row
  let colCount = 0

  // Get actual column count for this row
  if (cols && typeof cols.forEach === "function") {
    cols.forEach(() => colCount++)
  }

  // Handle normal row content (including header row content)
  if (cols && typeof cols.forEach === "function") {
    cols.forEach((col: any, index: number) => {
      if (index > 0) {
        state.write(" | ")
      }

      if (col) {
        // Always render the cell content, even if it appears empty
        col.forEach((cell: any) => {
          const startPos = state.out.length
          // Always use renderInline for table cells to avoid block-level formatting
          // that could introduce unwanted newlines
          if (state.nodes[cell.type.name]) {
            if (cell.childCount > 0) {
              state.renderInline(cell)
            }
            // For empty cells, don't render anything (will be handled by padding)
          }
          else {
            state.render(cell)
          }

          // Get the rendered text
          const renderedText = state.out.slice(startPos)

          // Clean up newlines in table cells to maintain table format
          // Replace all newlines and multiple spaces with single spaces
          const cleanedText = renderedText.replace(/\n+/g, " ").replace(/\s+/g, " ").trim()

          // Update state.out with cleaned text
          state.out = state.out.slice(0, startPos) + cleanedText

          // Pad with spaces to align with columnWidth
          const padding = columnWidths[index] - cleanedText.length
          if (padding > 0) {
            state.write(" ".repeat(padding))
          }
        })
      }
      else {
        // Handle missing cell
        state.write(" ".repeat(3))
      }
    })
  }

  state.write(" |")
  state.ensureNewLine()

  // After header row, add a delimiter row
  if (isHeaderRow) {
    state.write("| ")

    for (let i = 0; i < colCount; i++) {
      if (i > 0) {
        state.write(" | ")
      }
      const width = columnWidths[i] || 3 // Default to 3 if no width found
      state.write("-".repeat(width))
    }

    state.write(" |")
    state.ensureNewLine()
  }
}

function hasSpan(node: ProseMirrorNode) {
  return node.attrs.colspan > 1 || node.attrs.rowspan > 1
}

// function isMarkdownSerializable(node: ProseMirrorNode) {
//   const rows = childNodes(node)
//   const firstRow = rows[0]
//   const bodyRows = rows.slice(1)

//   if (childNodes(firstRow).some(cell => cell.type.name !== "tableHeader" || hasSpan(cell) || cell.childCount > 1)) {
//     return false
//   }

//   if (bodyRows.some(row =>
//     childNodes(row).some(cell => cell.type.name === "tableHeader" || hasSpan(cell) || cell.childCount > 1),
//   )) {
//     return false
//   }

//   return true
// }

export default serialize
