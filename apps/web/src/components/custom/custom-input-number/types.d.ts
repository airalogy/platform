export interface ICustomInputNumberPayload {
  value: Big.Big | number | null
  displayedValue: string
  type: "integer" | "float" | "number"
}
