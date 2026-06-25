import type { Node } from "@tiptap/pm/model"

// @ts-expect-error declare missing types in prosemirror-tables
import { addToCache, readFromCache, TableMap as TableMapBase } from "@tiptap/pm/tables"
import { computeMap, type TableMap } from "./tableMap"

declare module "@tiptap/pm/tables" {
  export const addToCache: (key: Node, value: TableMap) => TableMap
  export const readFromCache: (key: Node) => TableMap | undefined
}

Object.assign(TableMapBase, {
  get: (table: Node): TableMap => {
    return readFromCache(table) || addToCache(table, computeMap(table))
  },
})
