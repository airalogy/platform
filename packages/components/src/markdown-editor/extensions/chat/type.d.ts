export interface Uri {
  value: string
}

export interface Range {
  start: {
    line: number
    character: number
  }
  end: {
    line: number
    character: number
  }
}

export interface ContextItemId {
  itemId: string
  providerTitle: "file" | "code" | "virtual"
}

export interface ContextItem {
  id: ContextItemId
  name: string
  content: string
  description?: string
  uri?: Uri
  range?: Range
}

export type ContextItemWithId = ContextItem & { id: ContextItemId }

export interface RangeInFileWithContents {
  filepath: string
  range: {
    start: { line: number, character: number }
    end: { line: number, character: number }
  }
  contents: string
}
