import type { JSONSchemaType } from "ajv"

import { get as _get } from "lodash-es"

// 遍历$defs对象来获取#/$defs/xxx指向的值

/**
 * Traverse the `$defs` object to get the value referenced by `#/$defs/xxx`.
 *
 * @param schema - The JSON Schema object.
 * @param refPath - The reference path, starting from `#/$defs/`.
 * @returns The referenced value, or `undefined` if the path is invalid.
 */
export function getRefValue<T = any>(schema: any, refPath: string) {
  if (!schema || !refPath) {
    return undefined
  }

  const parts = refPath.split("/").slice(2) // 从第三个斜杠后开始分割路径
  const { $defs } = schema
  if (!$defs) {
    return undefined
  }

  return _get($defs, parts) as JSONSchemaType<T>
}

export function mergeEnumRefValue(schema: any, list: { $ref: string }[]) {
  if (!schema || !Array.isArray(list) || list.length === 0)
    return {}

  const result = list
    .map(({ $ref }) => getRefValue(schema, $ref))
    .reduce(
      (acc, it) => {
        if (!it)
          return acc

        const { enum: enumVal } = it
        if (Array.isArray(enumVal)) {
          acc.enum.push(...enumVal)
        }
        return acc
      },
      { enum: [] as string[] },
    )

  return result
}
