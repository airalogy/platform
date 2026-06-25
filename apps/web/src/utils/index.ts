import { h } from "vue"
import { baseURL } from "../service/request"

export * from "./auth"
export * from "./user"
/**
 * Transform record to option
 *
 * @example
 *   ```ts
 *   const record = {
 *     key1: 'label1',
 *     key2: 'label2'
 *   };
 *   const options = transformRecordToOption(record);
 *   // [
 *   //   { value: 'key1', label: 'label1' },
 *   //   { value: 'key2', label: 'label2' }
 *   // ]
 *   ```
 *
 * @param record
 */
export function transformRecordToOption<T extends Record<string, string>>(record: T) {
  return Object.entries(record).map(([value, label]) => ({
    value,
    label,
  })) as CommonType.Option<keyof T>[]
}
export function insertWbr(str: string) {
  return h(
    "span",
    null,
    str
      .split("_")
      .map((segment, index, array) => [
        h("span", null, segment),
        index < array.length - 1 ? h("wbr") : null, // Add <wbr> only if it's not the last element
      ])
      .flat(),
  )
}

export function getAssetUrl(id?: string) {
  return `${baseURL}/attachments/${id}`
}
