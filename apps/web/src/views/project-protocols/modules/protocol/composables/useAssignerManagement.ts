import type { IAnnotationDataItem, IRecordDataKey } from "@airalogy/aimd-core/types"
import type { Assigner } from "@airalogy/shared/types/models/protocol.js"
import type { UploadFileInfo } from "naive-ui"
import type { FormValidate } from "naive-ui/es/form/src/interface"
import type { ComputedRef } from "vue"
import type { IFieldChangePayload } from "../types/types"
import { getReferenceAssets, postGetRvAssign } from "@/service/api/project-protocols"
import { request } from "@/service/request"
import { handleDependencyVal } from "@/utils/reportModel"
import { fieldEventKey } from "@/utils/template/eventKey"
import { useClosableMessage } from "@airalogy/composables"
import { getFileInfo, getFileType, getMIMEByExtension, isUploadFileType, scopeKeyRecord } from "@airalogy/shared/utils"
import { formatPydanticErrors, type PydanticError } from "@airalogy/shared/utils/errorFormatter.js"
import { useEventBus } from "@vueuse/core"
import Big from "big.js"
import { get, set } from "lodash-es"
import { nanoid } from "nanoid"
import { EMPTY_ARRAY_MESSAGE } from "../helpers/parseFieldStructure"

interface IUseAssignerManagementOptions {
  protocolId: string | number
  emit: { (e: "update:field", payload: { scope: IRecordDataKey, prop: string, value: any, payload?: any }): void }
  varScopeRecord: ComputedRef<Record<string, string>>
  validate: FormValidate
  restoreValidation: () => void
  shouldTrigger?: boolean
  updateField?: (fieldModel: any, payload: IFieldChangePayload & {
    batchId?: string
    assigner?: any
    dependent?: { scope: IRecordDataKey, name: string }[]
    shouldAssign?: boolean
    link?: Record<"source" | "target", { name: string, prop: string }> & { isSource?: boolean }
  }) => Promise<void>
}

export interface IHandleAssignerPayload {
  scope: IRecordDataKey
  prop: string
  assigner: Assigner
  fieldModel: any
  batchId?: string
  info?: Record<string, any>
  from: "assigner" | "dependent"
  /** Skip cascade triggering when in planned batch execution mode */
  skipCascade?: boolean
}

export interface IHandleDependentPayload {
  dependent: { scope: IRecordDataKey, name: string }[]
  fieldModel: any
  batchId?: string
  info?: Record<string, any>
}

interface IDependencyReadinessItem {
  field: string
  key: string
  ready: boolean
}

interface IDependencyReadinessResult {
  ready: boolean
  dependencies: IDependencyReadinessItem[]
  missing: IDependencyReadinessItem[]
}

export function useAssignerManagement(options: IUseAssignerManagementOptions) {
  const { protocolId, emit, varScopeRecord, validate, restoreValidation, shouldTrigger = true, updateField } = options
  const fieldEventBus = useEventBus<string>(fieldEventKey)
  const message = useClosableMessage()
  const assignRequestMap = new Map<string, any>()
  const assignerLoadingRecord = ref<Record<string, boolean | undefined>>({})
  const assignerErrorRecord = ref<Record<string, string | boolean | undefined>>({})
  const assignerRequestRecord = ref<Record<string, { requestId: string, prop: string }>>({})

  // Helper to clean up a request from tracking
  function cleanupRequest(formattedProp: string, requestId?: string) {
    const existingRequest = assignerRequestRecord.value[formattedProp]

    // Only clean up if this is the same request we're tracking (or if requestId not provided)
    if (!requestId || (existingRequest && existingRequest.requestId === requestId)) {
      delete assignerRequestRecord.value[formattedProp]
    }
  }

  function formatGroupProp(prop: string, info?: { group?: string, row?: number }) {
    const { group, row } = info || {}
    return group ? `${prop}[${row}]` : prop
  }

  function formatAssignerErrorDetail(error: unknown): string {
    const detail = (error as any)?.response?.data?.detail
    const errorMessage = (error as any)?.response?.data?.error_message
    const fallbackMessage = (error as Error)?.message

    if (Array.isArray(detail)) {
      const hasPydanticShape = detail.every(item =>
        item
        && typeof item === "object"
        && Array.isArray((item as Record<string, unknown>).loc)
        && typeof (item as Record<string, unknown>).msg === "string",
      )

      if (hasPydanticShape) {
        return formatPydanticErrors(detail as PydanticError[]).join("\n")
      }

      return detail
        .map((item) => {
          if (typeof item === "string") {
            return item
          }

          if (item && typeof item === "object") {
            const target = item as Record<string, unknown>
            if (typeof target.message === "string") {
              return target.message
            }
            if (typeof target.msg === "string") {
              return target.msg
            }
            return JSON.stringify(target)
          }

          return String(item)
        })
        .filter(it => it && it.trim())
        .join("\n")
    }

    if (typeof detail === "string" && detail.trim()) {
      return detail.trim()
    }

    if (detail && typeof detail === "object") {
      const target = detail as Record<string, unknown>
      if (typeof target.message === "string" && target.message.trim()) {
        return target.message.trim()
      }
      if (typeof target.error_message === "string" && target.error_message.trim()) {
        return target.error_message.trim()
      }
      return JSON.stringify(target)
    }

    if (typeof errorMessage === "string" && errorMessage.trim()) {
      return errorMessage.trim()
    }

    if (typeof fallbackMessage === "string" && fallbackMessage.trim()) {
      return fallbackMessage.trim()
    }

    return "Assignment failed"
  }

  function handleFieldUpdate(params: {
    scope: IRecordDataKey
    key: string
    value: any
    target: any
    info?: { group?: string, row?: number }
  }) {
    const { scope, key, value, target, info } = params
    const payload = {
      scope,
      prop: key,
      value,
      info,
    }

    if (target.type === "number" || target.type === "float" || target.type === "integer") {
      const bigNum = new Big(value)
      const displayedValue = bigNum.toString()

      const payloadValue = { type: target.type, displayedValue, value: bigNum }
      payload.value = payloadValue
      target.value = payloadValue
      target.displayedValue = displayedValue
      emit("update:field", payload)
      fieldEventBus.emit("form-field-change", payload)
    }
    else {
      const rawType = target.raw?.airalogy_type || target.raw?.airalogy_built_in_type
      const normalizedRawType = typeof rawType === "string" ? getFileType(rawType, true) : "unknown"
      const normalizedExtensionType = typeof target.raw?.file_extension === "string"
        ? getFileType(target.raw.file_extension, true)
        : "unknown"
      const assignedFileId = typeof value === "string"
        ? value
        : value?.airalogy_file_id || value?.id
      const isFileField = isUploadFileType(target.type)
        || isUploadFileType(normalizedRawType)
        || isUploadFileType(normalizedExtensionType)
        || rawType === "FileId"

      if (isFileField && assignedFileId) {
        return getReferenceAssets(assignedFileId).then((res) => {
          if (res.data) {
            const { id, filename, url, airalogy_file_id } = res.data
            const { ext } = getFileInfo(filename)
            const mime = ext ? getMIMEByExtension(ext) : undefined

            const fileInfo: UploadFileInfo = {
              name: filename,
              url,
              status: "finished",
              id: id || assignedFileId,
              type: mime,
            }

            if (target.type === "image") {
              fileInfo.thumbnailUrl = url
            }

            payload.value = { ...fileInfo, airalogy_file_id, filename }
            fieldEventBus.emit("file-assigned", payload)
            return
          }

          target.value = value
          emit("update:field", payload)
          fieldEventBus.emit("form-field-change", payload)
        })
      }
      else {
        target.value = value
        emit("update:field", payload)
        fieldEventBus.emit("form-field-change", payload)
      }
    }
  }

  function handleGroupField(params: {
    targetRow: any
    targetScope: IRecordDataKey
    key: string
    value: any
    group: string
    row: number
    mode?: string
  }) {
    const { targetRow, targetScope, key, value, group, row, mode } = params
    const [groupName, varName] = key.split(".")

    if (groupName !== group)
      return

    if (targetScope === "research_check" || targetScope === "research_step") {
      const { checked, annotation } = value
      set(targetRow, `${varName}.checked`, checked)
      if (mode !== "manual") {
        set(targetRow, `${varName}.annotation`, annotation)
      }
      return
    }

    const target = get(targetRow, varName)
    return handleFieldUpdate({
      scope: targetScope,
      key,
      value,
      target,
      info: { group, row },
    })
  }

  function updateAssignerStates(prop: string, assigner: Assigner | undefined, updates: { loading?: boolean, error?: any, restore?: boolean }, info?: { group?: string, row?: number }) {
    if (typeof prop !== "string") {
      return
    }

    const targetProp = formatGroupProp(prop, info)
    const { loading, error, restore } = updates

    // Always update both loading and error states, even if undefined
    assignerLoadingRecord.value[targetProp] = loading
    assignerErrorRecord.value[targetProp] = error

    if (assigner) {
      assigner.dependent_fields.forEach((key) => {
        const targetKey = formatGroupProp(key, info)
        // Always update both loading and error states for dependent fields
        assignerLoadingRecord.value[targetKey] = loading
        assignerErrorRecord.value[targetKey] = error
      })
    }
    if (restore) {
      restoreValidation()
    }
  }

  /**
   * Check if a field has a valid value
   * Considers field type and default value to determine readiness
   * - For string fields: empty string may be valid if it's the default value or user input
   * - For non-string fields: empty string is considered invalid, but 0, false are valid
   */
  function checkFieldHasValue(
    fieldValue: any,
    fieldDefinition: any,
    fieldName: string,
  ): boolean {
    // Check basic null/undefined cases
    if (typeof fieldValue === "undefined" || fieldValue === null) {
      return false
    }

    // Get field type and default value
    const fieldType = fieldDefinition?.type
    const defaultValue = fieldDefinition?.raw?.default

    // Special handling for string type fields
    const isStringField = fieldType === "text" || fieldType === "textarea" || fieldType === "string"

    if (isStringField) {
      // If default value is empty string, then empty string is a valid value
      if (defaultValue === "") {
        return true
      }
      // If no default value or default value is not empty string, empty string may represent valid user input
      // Only undefined and null are considered not ready
      return true
    }

    // For non-string fields: exclude empty string
    // Numbers like 0, false are valid values
    if (fieldValue === "") {
      return false
    }

    return true
  }

  /**
   * Check if all dependent fields have values
   * Used to avoid triggering Assigner prematurely when dependencies are incomplete
   */
  function checkDependenciesReady(
    dependent_fields: string[],
    fieldModel: any,
    varScopeRecord: ComputedRef<Record<string, string>>,
    info?: { group?: string, row?: number },
    targetRow?: any,
  ): IDependencyReadinessResult {
    const { group, row } = info || {}
    console.log("[Assigner] Checking dependencies readiness for fields:", dependent_fields)
    const dependencies: IDependencyReadinessItem[] = []

    for (const field of dependent_fields) {
      if (group) {
        // Group mode: check field values in table rows
        const [groupName, varName] = field.split(".")
        if (groupName !== group || !targetRow) {
          console.log(`[Assigner] Group field ${field} skipped (groupName: ${groupName}, group: ${group}, targetRow: ${!!targetRow})`)
          dependencies.push({
            field,
            key: typeof row === "number" ? formatGroupProp(field, info) : field,
            ready: false,
          })
          continue
        }

        const fieldValue = get(targetRow, varName)
        const hasValue = checkFieldHasValue(fieldValue.value, fieldValue, field)

        console.log(`[Assigner] Group field ${field} value:`, fieldValue?.value, "hasValue:", hasValue)
        dependencies.push({
          field,
          key: formatGroupProp(field, info),
          ready: hasValue,
        })
      }
      else {
        // Non-group mode: check regular field values
        const targetScope = varScopeRecord.value[field] as IRecordDataKey
        if (!targetScope) {
          console.log(`[Assigner] Field ${field} scope not found`)
          dependencies.push({
            field,
            key: field,
            ready: false,
          })
          continue
        }

        const fieldPath = `${targetScope}.${field}.value`
        const fieldValue = get(fieldModel, fieldPath)
        const fieldDefinition = get(fieldModel, `${targetScope}.${field}`)

        const hasValue = checkFieldHasValue(fieldValue, fieldDefinition, field)

        console.log(`[Assigner] Field ${field} (${fieldPath}) value:`, fieldValue, "type:", fieldDefinition?.type, "defaultValue:", fieldDefinition?.raw?.default, "hasValue:", hasValue)
        dependencies.push({
          field,
          key: field,
          ready: hasValue,
        })
      }
    }

    const missing = dependencies.filter(item => !item.ready)
    if (missing.length > 0) {
      console.log("[Assigner] ❌ Missing dependencies:", missing.map(item => item.field))
    }
    else {
      console.log("[Assigner] ✅ All dependencies ready for fields:", dependent_fields)
    }

    return {
      ready: missing.length === 0,
      dependencies,
      missing,
    }
  }

  function buildMissingDependencyMessage(
    formattedProp: string,
    readiness: IDependencyReadinessResult,
  ) {
    const missingList = readiness.missing.map(item => `- ${item.field}`).join("\n")

    return [
      `Cannot run assigner for ${formattedProp}.`,
      "Missing dependencies:",
      missingList,
    ].join("\n")
  }

  function setMissingDependencyErrors(
    prop: string,
    assigner: Assigner,
    readiness: IDependencyReadinessResult,
    info?: { group?: string, row?: number },
  ) {
    const formattedProp = formatGroupProp(prop, info)
    const summary = buildMissingDependencyMessage(formattedProp, readiness)

    assignerLoadingRecord.value[formattedProp] = false
    assignerErrorRecord.value[formattedProp] = summary

    const missingKeySet = new Set(readiness.missing.map(item => item.key))

    assigner.dependent_fields.forEach((field) => {
      const targetKey = info?.group ? formatGroupProp(field, info) : field
      assignerLoadingRecord.value[targetKey] = false
      assignerErrorRecord.value[targetKey] = missingKeySet.has(targetKey)
        ? `Required before running ${formattedProp}`
        : undefined
    })

    return summary
  }

  function buildInvalidDependencyMessage(
    prop: string,
    invalidMessages: { scope: IRecordDataKey, field: string, message: string[] }[],
  ) {
    return `Invalid assigner dependencies for variable ${prop}:\n${invalidMessages
      .map((item, idx) => `${idx + 1}: ${scopeKeyRecord[item.scope as keyof typeof scopeKeyRecord]}.${item.field} ${item.message.join(", ")}`)
      .join("\n")}`
  }

  function setInvalidDependencyErrors(
    prop: string,
    assigner: Assigner,
    invalidMessages: { scope: IRecordDataKey, field: string, message: string[] }[],
    info?: { group?: string, row?: number },
  ) {
    const formattedProp = formatGroupProp(prop, info)
    const summary = buildInvalidDependencyMessage(prop, invalidMessages)

    assignerLoadingRecord.value[formattedProp] = false
    assignerErrorRecord.value[formattedProp] = summary

    const errorMap = new Map<string, string[]>()
    invalidMessages.forEach((item) => {
      const key = info?.group ? formatGroupProp(item.field, info) : item.field
      const messages = errorMap.get(key) || []
      messages.push(...item.message)
      errorMap.set(key, messages)
    })

    assigner.dependent_fields.forEach((field) => {
      const targetKey = info?.group ? formatGroupProp(field, info) : field
      assignerLoadingRecord.value[targetKey] = false
      const messages = errorMap.get(targetKey)
      assignerErrorRecord.value[targetKey] = messages?.length
        ? messages.join(", ")
        : undefined
    })

    return summary
  }

  /**
   * Get all field paths that should be validated for a specific assigner operation
   * This includes the target field and all dependent fields
   */
  function getAssignerValidationFields(
    scope: IRecordDataKey,
    prop: string,
    assigner: Assigner,
    info?: { group?: string, row?: number },
  ): string[] {
    const { group } = info || {}
    const validationFields: string[] = []

    // Add the target field being assigned
    if (group) {
      validationFields.push(formatGroupProp(prop, info))
    }
    else {
      const targetScope = varScopeRecord.value[prop] as IRecordDataKey
      if (targetScope) {
        validationFields.push(`${targetScope}.${prop}.value`)
      }
    }

    // Add all dependent fields
    assigner.dependent_fields.forEach((field) => {
      if (group) {
        validationFields.push(formatGroupProp(field, info))
      }
      else {
        const targetScope = varScopeRecord.value[field] as IRecordDataKey
        if (targetScope) {
          validationFields.push(`${targetScope}.${field}.value`)
        }
      }
    })

    return validationFields
  }

  async function handleAssigner(payload: IHandleAssignerPayload): Promise<string | boolean> {
    if (!shouldTrigger) {
      return false
    }

    if (!protocolId) {
      message.error("No protocol id found")
      return false
    }

    const { scope, prop, assigner, fieldModel, batchId, info, skipCascade } = payload
    const { group, row } = info || {}
    const formattedProp = formatGroupProp(prop, info)

    // Dependency completeness pre-check
    // For auto and auto_first modes: only proceed when all dependent fields have values
    // For manual mode: skip dependency check, allow showing validation errors
    const { dependent_fields, mode } = assigner
    const targetRow = group ? get(fieldModel, ["research_variable", group, "value", row]) : null

    const dependencyReadiness = checkDependenciesReady(dependent_fields, fieldModel, varScopeRecord, info, targetRow)

    if (mode !== "manual" && !dependencyReadiness.ready) {
      // Dependencies incomplete, return silently without showing errors (only for non-manual modes)
      console.log(`[Assigner] Dependencies not ready for ${formattedProp} (mode: ${mode}), skipping...`)
      return false
    }

    if (mode === "manual") {
      if (!dependencyReadiness.ready) {
        const errorMessage = setMissingDependencyErrors(prop, assigner, dependencyReadiness, info)
        fieldEventBus.emit("error-assigner-request", {
          scope,
          prop: formattedProp,
          assigner,
          value: errorMessage,
        })
        return errorMessage
      }

      console.log(`[Assigner] Manual mode detected for ${formattedProp}, dependencies ready, proceeding with validation`)
    }

    let isValid = true
    let onlyArrayEmptyErrors = true
    const invalidMessages: { scope: IRecordDataKey, field: string, message: string[] }[] = []
    try {
      const { mode } = assigner
      const dependencies: [string, any][] = []

      // Start assigner request - update loading states
      updateAssignerStates(prop, assigner, { loading: true, error: undefined }, info)

      if (group) {
        if (targetRow) {
          dependent_fields.forEach((it) => {
            const [groupName, varName] = it.split(".")
            if (groupName !== group) {
              return
            }
            const targetVal = get(targetRow, varName)
            if (targetVal) {
              handleDependencyVal({
                fieldName: it,
                targetScope: scope,
                targetVal,
                dependencies,
                invalidMessages,
                onInvalid: () => { isValid = false },
                isRow: false,
              })
            }
          })
        }
      }
      else {
        // Build dependencies array
        await Promise.all(dependent_fields.map(async (it) => {
          const targetScope = varScopeRecord.value[it] as IRecordDataKey
          const targetPath = `${targetScope}.${it}`
          const targetValuePath = `${targetScope}.${it}.value`
          try {
            await new Promise<void>((resolve, reject) => {
              validate((errors) => {
                if (!errors) {
                  resolve()
                  return
                }

                errors.flat().forEach((error) => {
                  const { field, message } = error
                  if (!message) {
                    return
                  }

                  if (message !== EMPTY_ARRAY_MESSAGE) {
                    onlyArrayEmptyErrors = false
                  }

                  const targetMessage = invalidMessages.find(it => field === `${it.scope}.${it.field}.value`)

                  if (targetMessage) {
                    targetMessage.message.push(message)
                  }
                  else {
                    invalidMessages.push({ scope: targetScope, field: it, message: [message] })
                  }
                })

                isValid = false
                reject()
              }, (rule) => {
                return rule?.key === targetValuePath
              })
            })

            const targetModel = get(fieldModel, targetPath)
            if (!targetModel) {
              return
            }

            const targetVal = get(targetModel, "value")

            handleDependencyVal({
              fieldName: it,
              targetScope,
              targetVal,
              dependencies,
              invalidMessages,
              onInvalid: () => { isValid = false },
              isRow: targetModel.type === "table",
            })
          }
          catch (e) {
            updateAssignerStates(prop, assigner, { loading: false, error: e }, info)
          }
        }))
      }

      if (!isValid) {
        if (!onlyArrayEmptyErrors) {
          const errorMessage = setInvalidDependencyErrors(prop, assigner, invalidMessages, info)
          if (payload.from === "assigner") {
            message.error(errorMessage)
          }

          return errorMessage
        }

        if (batchId) {
          updateAssignerStates(prop, assigner, { loading: false, error: false, restore: true }, info)
        }
        else {
          updateAssignerStates(prop, assigner, { loading: false }, info)
        }

        return false
      }

      const assignerPayload = {
        name: prop,
        dependencies: Object.fromEntries(dependencies),
      }

      // Check for duplicate ongoing requests with the same payload
      const existingRequest = assignerRequestRecord.value[formattedProp]

      if (existingRequest && assignerLoadingRecord.value[formattedProp] && prop === existingRequest.prop) {
        console.log(`[Assigner] Canceling duplicate request for ${formattedProp}`, existingRequest.requestId)
        request.cancelRequest(existingRequest.requestId)
        cleanupRequest(formattedProp, existingRequest.requestId)
      }

      // Handle existing requests in other batches
      // Only cancel requests from different batches, not from the same batch
      if (batchId) {
        assignRequestMap.forEach((requests, k) => {
          if (k === batchId || !Array.isArray(requests))
            return
          // Cancel all requests in other batches
          requests.forEach((req) => {
            console.log(`[Assigner] Canceling request ${req.id} from different batch ${k}`)
            request.cancelRequest(req.id)
          })
        })
      }

      const requestAssigner = group
        ? {
            ...assigner,
            dependent_fields: assigner.dependent_fields.map(it => formatGroupProp(it, info)),
          }
        : assigner

      // Toast notifications are now fully handled by the progress modal
      // No individual toast messages needed
      fieldEventBus.emit("start-assigner-request", {
        scope,
        prop: formattedProp,
        assigner: requestAssigner,
      })

      const requestId = nanoid()

      // Track the new request
      assignerRequestRecord.value[formattedProp] = {
        requestId,
        prop,
      }

      try {
        const assignedRfs = await postGetRvAssign(protocolId, assignerPayload, requestId)

        // Clear the tracked request once completed
        cleanupRequest(formattedProp, requestId)

        // End assigner request - update loading states
        updateAssignerStates(prop, assigner, { loading: assignedRfs === null ? undefined : false, error: undefined }, info)

        fieldEventBus.emit("end-assigner-request", {
          scope,
          prop: formattedProp,
          assigner: requestAssigner,
          value: assignedRfs === null ? undefined : false,
        })

        if (assignedRfs) {
          if (group) {
            if (!targetRow)
              return false

            await Promise.all(
              Object.entries(assignedRfs).map(async ([key, rvValue]) => {
                const groupKey = formatGroupProp(key, info)
                assignerLoadingRecord.value[groupKey] = false

                // Always call handleGroupField for its specific logic
                await handleGroupField({
                  targetRow,
                  targetScope: "var_table",
                  key,
                  value: rvValue,
                  group,
                  row,
                  mode,
                })

                // Additionally call updateField if available to trigger assignment chain
                // Skip cascade when in planned batch execution mode (cascade is handled by execution plan)
                if (updateField && !skipCascade) {
                  // Get dependent information for the assigned field to trigger downstream assigners
                  const [groupName, varName] = key.split(".")
                  const assignedFieldDef = groupName === group ? get(targetRow, varName) : null
                  const assignedDependent = assignedFieldDef?.dependent

                  await updateField(fieldModel, {
                    scope: "var_table",
                    prop: key,
                    value: rvValue,
                    shouldAssign: false, // Prevent infinite recursion
                    dependent: assignedDependent, // Pass dependent info to trigger downstream assigners
                    info: { group, row },
                  })
                }
              }),
            )
          }
          else {
            await Promise.all(
              Object.entries(assignedRfs).map(async ([key, rvValue]) => {
                const targetScope = varScopeRecord.value[key] as IRecordDataKey
                assignerLoadingRecord.value[key] = false

                // Handle special cases first
                if (targetScope === "research_check" || targetScope === "research_step") {
                  const { checked, annotation } = rvValue as IAnnotationDataItem
                  set(fieldModel, [targetScope, key, "value", "checked"], checked)
                  if (mode !== "manual") {
                    set(fieldModel, [targetScope, key, "value", "annotation"], annotation)
                  }
                }
                else {
                  const target = get(fieldModel, [targetScope, key])

                  // Always call handleFieldUpdate for its specific logic
                  await handleFieldUpdate({
                    scope: targetScope,
                    key,
                    value: rvValue,
                    target,
                  })
                }

                // Additionally call updateField if available to trigger assignment chain
                // Skip cascade when in planned batch execution mode (cascade is handled by execution plan)
                if (updateField && !skipCascade) {
                  // Get dependent information for the assigned field to trigger downstream assigners
                  const assignedFieldDef = get(fieldModel, [targetScope, key])
                  const assignedDependent = assignedFieldDef?.dependent

                  await updateField(fieldModel, {
                    scope: targetScope,
                    prop: key,
                    value: rvValue,
                    shouldAssign: false, // Prevent infinite recursion
                    dependent: assignedDependent, // Pass dependent info to trigger downstream assigners
                  })
                }
              }),
            )
          }

          // Run validation after emitting end event - only validate assigner-related fields
          const validationFields = getAssignerValidationFields(scope, prop, assigner, info)
          await new Promise<void>((resolve) => {
            validate((errors) => {
              resolve()
            }, (rule) => {
              return validationFields.includes(rule?.key || "")
            })
          })

          return true
        }

        const errorMessage = `Assigner returned no assigned fields for ${formattedProp}`
        updateAssignerStates(prop, assigner, { loading: false, error: errorMessage }, info)
        fieldEventBus.emit("error-assigner-request", {
          scope,
          prop: formattedProp,
          assigner,
          value: errorMessage,
        })
        console.warn("[Assigner] No assigned rv found for", formattedProp)
        return errorMessage
      }
      catch (requestError) {
        // Clear the tracked request on error
        cleanupRequest(formattedProp, requestId)

        throw requestError // Re-throw to be caught by the outer catch
      }
    }
    catch (e) {
      // Ensure the request is cleaned up

      if ((e as any).code === "ERR_CANCELED") {
        // Make sure loading state is cleared for canceled requests
        updateAssignerStates(prop, assigner, { loading: false }, info)
        return false
      }
      const errorMessage = formatAssignerErrorDetail(e)

      if (isValid) {
        // Error assigner request - update loading states
        updateAssignerStates(prop, assigner, { loading: false, error: errorMessage }, info)
        fieldEventBus.emit("error-assigner-request", {
          scope,
          prop: formattedProp,
          assigner,
          value: errorMessage,
        })
      }

      console.error(`[Assigner] Failed to assign ${formattedProp}:`, errorMessage)
      return errorMessage
    }
  }

  async function handleAssignerCancel(payload: Pick<IHandleAssignerPayload, "prop" | "info">) {
    const { prop, info } = payload
    const formattedProp = formatGroupProp(prop, info)
    const existingRequest = assignerRequestRecord.value[formattedProp]

    if (existingRequest) {
      const { requestId } = existingRequest

      request.cancelRequest(requestId)
      cleanupRequest(formattedProp, requestId)
    }
  }

  function handleDependent(payload: IHandleDependentPayload) {
    if (!shouldTrigger) {
      return
    }

    const { dependent, fieldModel, batchId, info } = payload

    if (!Array.isArray(dependent) || dependent.length === 0)
      return

    const { group, row } = info || {}

    const errorMessages: Promise<string | undefined>[] = []

    dependent.forEach(async ({ scope, name }) => {
      const assignerPath: string[] = [scope]
      const assignedSetPath: string[] = [scope]
      if (group) {
        assignerPath.push(group, "assignerRecord", name)
        assignedSetPath.push(group, "assignedSet")
      }
      else {
        assignerPath.push(name)
        assignedSetPath.push(name, "assignedSet")
      }

      const target = get(fieldModel, assignerPath)

      if (!target)
        return

      const assignedSet = get(fieldModel, assignedSetPath)
      const assigner = group ? target : target.assigner

      if (assigner && assigner.mode !== "manual") {
        if (assigner.mode === "auto_first" && assignedSet && assignedSet.has(name))
          return

        // Check if dependent assigner's dependency fields are ready before triggering
        // For manual mode, skip dependency check; for other modes, wait for complete dependencies
        const targetRow = group ? get(fieldModel, ["research_variable", group, "value", row]) : null
        if (assigner.mode !== "manual" && !checkDependenciesReady(assigner.dependent_fields, fieldModel, varScopeRecord, info, targetRow).ready) {
          console.log(`[Assigner] Dependencies not ready for dependent field ${name} (mode: ${assigner.mode}), skipping...`)
          return
        }

        const result = handleAssigner({ scope, prop: name, assigner, fieldModel, batchId, info, from: "dependent" })
        errorMessages.push(result.then((val) => {
          if (typeof val === "string") {
            return val
          }

          if (val && assignedSet) {
            assignedSet.add(name)
          }

          return ""
        }))
      }
    })

    if (errorMessages.length > 0) {
      Promise.all(errorMessages).then((results) => {
        const messageContent = results.filter(it => it && it.trim()).join("\n\n")
        if (messageContent) {
          message.warning(messageContent)
        }
      })
    }
  }

  return {
    handleAssigner,
    handleDependent,
    handleAssignerCancel,
    assignerLoadingRecord,
    assignerErrorRecord,
    assignerRequestRecord,
  }
}

export type UseAssignerManagement = ReturnType<typeof useAssignerManagement>
