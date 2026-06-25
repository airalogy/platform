import type { IRecordDataKey } from "@airalogy/aimd-core/types"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { UploadFileInfo } from "naive-ui"
import type { IFieldChangePayload } from "../types/types"
import { useClosableMessage } from "@airalogy/composables"
import { get, set } from "lodash-es"

interface IFieldManagementOptions {
  fieldModel: any
  emit: { (e: "update:field", payload: { scope: IRecordDataKey, prop: string, value: any, info?: any }): void }
}

export function useFieldManagement(options: IFieldManagementOptions) {
  const { fieldModel, emit } = options
  const message = useClosableMessage()

  async function handleFieldChange(payload: IFieldChangePayload) {
    const { prop, value, scope, info, shouldAssign = true, shouldUpdate = true } = payload

    try {
      if (shouldUpdate && fieldModel) {
        await updateField(fieldModel, payload)
      }

      const mdField = document.getElementById(`${scope}-${prop}`)
      if (mdField) {
        emit("update:field", { scope, prop, value })
      }
    }
    catch (e) {
      message.error((e as Error).message)
    }
  }

  async function updateField(
    fieldModel: any,
    payload: IFieldChangePayload & {
      batchId?: string
      assigner?: ProtocolModels.Assigner
      dependent?: { scope: IRecordDataKey, name: string }[]
      shouldAssign?: boolean
      link?: Record<"source" | "target", { name: string, prop: string }> & { isSource?: boolean }
    },
  ) {
    const { scope, prop, value, info, fileInfo, assigner } = payload

    const controlledValue = typeof value === "undefined" ? null : value
    let path = scope === "var_table"
      ? `research_variable.${info!.group}.value[${info!.row}].${prop}`
      : `${scope}.${prop}.value`

    if (scope === "research_step" || scope === "research_check") {
      if (typeof value === "boolean") {
        path = `${path}.checked`
      }
      if (typeof value === "string") {
        path = `${path}.annotation`
      }
    }

    // Only skip setting value if assigner mode is auto_force (value will be set by assigner)
    if (!assigner || assigner.mode !== "auto_force") {
      if (typeof controlledValue === "object" && controlledValue && "airalogy_file_id" in controlledValue) {
        const { airalogy_file_id } = controlledValue
        const fileList = (get(fieldModel, path)) as any as UploadFileInfo[]

        if (fileInfo && Array.isArray(fileList)) {
          const targetFile = fileList.find(it => it.id === airalogy_file_id)
          if (targetFile) {
            // targetFile.id = fileInfo.id
            // TODO: fix this
            targetFile.airalogyId = airalogy_file_id
            targetFile.url = fileInfo.url
            targetFile.name = fileInfo.name
          }
        }
      }

      set(fieldModel, path, controlledValue)
      if (scope === "var_table") {
        const { group } = info || {}
        emit("update:field", {
          scope,
          prop: `${group}.${prop}`,
          info,
          value: controlledValue,
        })
      }
      else {
        emit("update:field", { scope, prop, value: controlledValue })
      }
    }

    // Handle dependent fields
    // if (dependent && shouldAssign) {
    //   for (const dep of dependent) {
    //     await handleFieldChange({
    //       scope: dep.scope,
    //       prop: dep.name,
    //       value: controlledValue,
    //       shouldAssign: false, // Prevent infinite recursion
    //     })
    //   }
    // }

    // Note: Assigner triggering is now handled by the queue mechanism in useFieldEventBus
    // All field changes go through preview-field-change event -> queue -> batch execution
  }
  return {
    updateField,
    handleFieldChange,
  }
}
