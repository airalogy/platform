import type { ContextItem } from "../../../type"

interface RifWithContents {
  filepath: string
  range: {
    start: { line: number }
    end: { line: number }
  }
  contents: string
}

export function ctxItemToRifWithContents(item: ContextItem, includeContents = false): RifWithContents {
  if (!item.uri?.value || !item.range) {
    throw new Error("Cannot convert context item to RIF: missing uri or range")
  }

  return {
    filepath: item.uri.value,
    range: {
      start: { line: item.range.start.line },
      end: { line: item.range.end.line },
    },
    contents: includeContents ? item.content : "",
  }
}
