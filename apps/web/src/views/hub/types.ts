import type { SelectOption } from "naive-ui"

export type CategoryOption = SelectOption & {
  type: "category"
  value: string | undefined
}
