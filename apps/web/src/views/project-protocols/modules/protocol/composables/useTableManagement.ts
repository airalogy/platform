import type { IFieldItem } from "../types/types"
import { get, set } from "lodash-es"

export function useTableManagement() {
  function handleTableRowUpdate(
    type: "add-row" | "remove-row",
    payload: { row: number, model: any, info: any },
    tableEmitterRecord: any,
    fieldModel: any,
  ) {
    const { row, info, model } = payload
    const { name } = info || {}

    const masterEmitters = tableEmitterRecord.value.slave[name]
    const slaveEmitters = tableEmitterRecord.value.master[name]

    if (Array.isArray(masterEmitters)) {
      masterEmitters.forEach(emitter => emitter({ type, payload }))
    }

    if (Array.isArray(slaveEmitters)) {
      slaveEmitters.forEach(emitter => emitter({ type, payload }))
    }

    const target = get(fieldModel.research_variable, `${name}.value`) as IFieldItem[]

    if (type === "add-row") {
      if (target) {
        target.push(model)
      }
      else {
        set(fieldModel.research_variable, `${name}.value`, [model])
      }
    }

    if (type === "remove-row") {
      if (Array.isArray(target)) {
        target.splice(row, 1)
      }
    }
  }

  return {
    handleTableRowUpdate,
  }
}
