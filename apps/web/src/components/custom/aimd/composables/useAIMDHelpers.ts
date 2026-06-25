import type { IDynamicTableNode, IRecordDataKey, ScopeFieldKey } from "@airalogy/aimd-core/types"
import type { Assigner } from "@airalogy/shared/types/models/protocol"
import type { SomeJSONSchema } from "ajv/dist/types/json-schema"
import type { FormItemInst, UploadFileInfo, UploadSettledFileInfo } from "naive-ui"
import type { MaybeRef } from "vue"
import type {
  IAIMDItemProps,
  IAIMDWrapperProps,
  ICustomInputNumberPayload,
  IEmits,
  IFieldModel,
  JsonSchema,
} from "../types/aimd-types"
import { request } from "@/service/request"
import { useAuthStore } from "@/store/modules/auth"

import { fieldEventKey } from "@/utils/template/eventKey"

import { getSubvarDef, getSubvarNames } from "@airalogy/aimd-core"
import { useClosableMessage } from "@airalogy/composables"
import { formatRawValue, getFileType, schemaToInputType, scopeKeyRecord } from "@airalogy/shared/utils"
import { createInjectionState, useDebounceFn, useEventBus } from "@vueuse/core"
import { get as _get, set as _set, get } from "lodash-es"
import { computed, nextTick, reactive, ref, toRefs, watchEffect } from "vue"

import {
  createDefaultItem,
  createResearchCheckItems,
  createResearchStepItems,
  createResultItem,
} from "./itemCreators"
import { createTableCellThemeOverrides } from "./themeOverrides"

interface IAIMDEventBusPayload {
  scope: ScopeFieldKey
  prop: string
  assigner?: Assigner
  varName?: string
  info?: Record<string, any>
  fileInfo?: UploadFileInfo
  value?:
    | string
    | {
      file: {
        file: UploadFileInfo
        fileList: UploadFileInfo[]
        event?: Event | undefined
      }
      status: "remove" | "add"
    }
    | {
      airalogy_file_id: string
      id: string
      url: string
      filename: string
      asset_airalogy_id: string
      type: "image" | "video" | "audio" | "file"
    }
}

function isAssignedFileValue(
  value: IAIMDEventBusPayload["value"],
): value is {
  airalogy_file_id: string
  id: string
  url: string
  filename: string
  asset_airalogy_id: string
  type: "image" | "video" | "audio" | "file"
} {
  return Boolean(
    value
    && typeof value === "object"
    && !("file" in value)
    && "airalogy_file_id" in value
    && "url" in value
    && "filename" in value,
  )
}

export function getSchemasFromAnyOf(anyOf?: JsonSchema[]) {
  if (anyOf && Array.isArray(anyOf) && anyOf.length > 0) {
    return anyOf.filter(({ type }) => type !== "null")
  }

  return []
}

export function getFirstTypeFromAnyOf(anyOf: JsonSchema[]) {
  if (anyOf.length > 0) {
    return anyOf[0].type
  }
  return null
}

function mergeDependents(
  ...lists: Array<Array<{ name: string, scope: IRecordDataKey }> | undefined>
): Array<{ name: string, scope: IRecordDataKey }> | undefined {
  const merged = lists
    .flatMap(list => list || [])
    .filter((item): item is { name: string, scope: IRecordDataKey } => Boolean(item?.name && item?.scope))

  if (merged.length === 0) {
    return undefined
  }

  const seen = new Set<string>()
  return merged.filter((item) => {
    const key = `${item.scope}.${item.name}`
    if (seen.has(key)) {
      return false
    }
    seen.add(key)
    return true
  })
}

export function getInputType(info: JsonSchema & { anyOf?: JsonSchema[] } | undefined | null) {
  if (!info) {
    return "text" // Default to text input if no schema info
  }
  const { airalogy_type, airalogy_built_in_type, build_in_rv_type, input_type, type: rawType, format, file_extension, anyOf } = info

  const fileType = getFileType(file_extension, true)
  if ((airalogy_type === "FileId" || airalogy_built_in_type === "FileId")) {
    return fileType === "unknown" ? "file" : fileType
  }

  if (anyOf) {
    const schemas = getSchemasFromAnyOf(anyOf)

    // Check if any schema in anyOf is a FileId type
    for (const schema of schemas) {
      if (schema.airalogy_type === "FileId" || schema.airalogy_built_in_type === "FileId") {
        const schemaFileType = getFileType(schema.file_extension, true)
        return schemaFileType === "unknown" ? "file" : schemaFileType
      }
    }

    const type = getFirstTypeFromAnyOf(schemas)

    if (type) {
      return type
    }
  }

  return airalogy_type
    || airalogy_built_in_type
    || build_in_rv_type
    || input_type
    || (schemaToInputType[rawType]?.(format) ?? (rawType === "check" ? "boolean" : rawType || "textarea"))
}

// Core state composable
function useAIMDState(props: MaybeRef<IAIMDWrapperProps>) {
  const fieldModel = reactive<IFieldModel>({} as IFieldModel)
  const tableVariableRecord = ref<Record<string, Record<string, any>>>({})
  const previewFileRecord = ref<
    Record<string, { content: null | string, file: null | File, visible: boolean } & Partial<UploadSettledFileInfo>>
  >({})
  const itemRef = ref<Record<string, { value: any, type: string }>>({})
  const formItemRef = reactive<Record<string, { value: FormItemInst | null }>>({})

  const { varScopeRecord, typed, readonly = ref(undefined), protocolId, assignerLoadingRecord, assignerErrorRecord, assignerRequestRecord, tableRecord, record } = toRefs(reactive(toValue(props)))
  const authStore = useAuthStore()

  return {
    fieldModel,
    tableVariableRecord,
    previewFileRecord,
    itemRef,
    formItemRef,
    varScopeRecord,
    typed,
    readonly,
    protocolId,
    assignerLoadingRecord,
    assignerErrorRecord,
    assignerRequestRecord,
    tableRecord,
    record,
    authStore,
  }
}

// Event handling composable
function useAIMDEventHandling(props: MaybeRef<IAIMDWrapperProps>, minimal: boolean) {
  const fieldEventBus = minimal ? { emit: () => {}, on: () => {} } : useEventBus<string>(fieldEventKey)
  const message = minimal ? { error: () => {}, info: () => {}, warning: () => {} } : useClosableMessage()

  return {
    fieldEventBus,
    message,
  }
}

// Computed properties composable
function useAIMDComputed(props: MaybeRef<IAIMDWrapperProps>, fieldModel: IFieldModel, authStore: any, tableRecord: Ref<Record<string, Record<string, any>> | undefined>, minimal: boolean) {
  const variableList = computed((): IAIMDItemProps[] => {
    const result: IAIMDItemProps[] = []
    const { scopeList, propList, record, typed } = toValue(props)
    const { userInfo } = authStore
    if (
      !record
      || !record.field
      || !userInfo
      || !Array.isArray(propList)
      || propList.length === 0
    ) {
      return result
    }

    const { field, rules } = record

    scopeList.forEach((scopeName, idx) => {
      if (scopeName === "research_workflow")
        return

      const scopePropList = propList[idx]

      scopePropList.forEach((prop) => {
        if (Array.isArray(prop))
          return

        const item = field[scopeName]?.[prop]
        if (!item)
          return

        const { scope, type, raw } = item
        const link = (item as any).link
        const to = `${scopeName}-${prop}`

        if (scope === "research_step") {
          if (minimal) {
            const items = createResearchStepItems(item, scopeName, to, fieldModel)
            const annotationItem = items.find(it => it.type === "rs-annotation")
            const checkItem = items.find(it => it.type === "rs-check")

            // Create a combined minimal item for research step
            if (annotationItem) {
              result.push({
                ...annotationItem,
                type: "rs-minimal",
                fieldType: "rs-minimal",
                info: {
                  ...annotationItem.info,
                  hasCheck: !!checkItem,
                  checkItem: checkItem || null,
                  annotationItem,
                  stepName: item.raw?.name || item.title || item.label,
                },
              })
            }
          }
          else {
            result.push(...createResearchStepItems(item, scopeName, to, fieldModel))
          }
        }
        else if (scope === "research_check") {
          if (minimal) {
            const [checkItem, annotationItem] = createResearchCheckItems(item, scopeName, to, fieldModel)

            // Create a combined minimal item for research check
            result.push({
              ...annotationItem,
              type: "rc-minimal",
              fieldType: "rc-minimal",
              info: {
                ...annotationItem.info,
                hasCheck: !!checkItem,
                checkItem: checkItem || null,
                annotationItem,
                stepName: item.raw?.name || item.title || item.label,
              },
            })
          }
          else {
            result.push(...createResearchCheckItems(item, scopeName, to, fieldModel))
          }
        }
        else if (type === "table") {
          // Get subvars from multiple sources
          const subvars = raw?.subvars
            || typed?.[scopeName]?.[prop]?.subvars
            || (tableRecord.value?.[prop] ? Object.keys(tableRecord.value[prop]) : [])
            || []

          result.push(
            createResultItem({
              disabled: minimal || item.disabled,
              id: `aimd-${to}`,
              scope: scopeName as ScopeFieldKey, // Use scopeName instead of scope for table fields
              prop,
              fieldType: scopeKeyRecord[scopeName],
              model: fieldModel[scopeName][prop],
              // to: `#var_table-${prop}-wrapper`,
              type: "var-table-wrapper",
              info: { ...typed?.[scopeName]?.[prop], ...raw, link, name: prop, subvars, schema: rules?.research_variable?.[prop] },
              required: item.required,
            }),
          )
        }
        else {
          result.push(createDefaultItem(item, scopeName, to, fieldModel, rules))
        }
      })
    })

    return result
  })

  const refList = computed((): IAIMDItemProps[] => {
    const { ref_step, rv_ref } = toValue(props).refRecord
    const result: IAIMDItemProps[] = []

    if (ref_step) {
      const entries = Object.entries(ref_step)
      entries.forEach(([key, item]) => {
        const { indent, suffix, dependent } = item

        if (Array.isArray(dependent)) {
          dependent.forEach(({ line, sequence }) => {
            result.push({
              id: `aimd-${key}-step-ref`,
              scope: "ref_step",
              prop: key,
              fieldType: "step-ref",
              placeholder: "",
              model: { value: indent },
              // to: `research_step-${key}-label-${line}-${sequence}`,
              type: "step-ref",
              tooltip: `${indent}:${suffix}`,
              info: item,
              disabled: undefined,
              required: undefined,
              themeOverrides: undefined,
            })
          })
        }
        else {
          result.push({
            id: `aimd-${key}-step-ref`,
            scope: "ref_step",
            prop: key,
            fieldType: "step-ref",
            placeholder: "",
            model: { value: indent },
            // to: `[id^=research_step-${key}-label]`,
            type: "step-ref",
            tooltip: `${indent}:${suffix}`,
            info: item,
            disabled: undefined,
            required: undefined,
            themeOverrides: undefined,
          })
        }
      })
    }

    if (rv_ref) {
      const entries = Object.entries(rv_ref)

      entries.forEach(([key, item]) => {
        const { title, description, dependent } = item as {
          title?: string
          description?: string
          raw?: string
          dependent: { name: string, line: number, sequence: number }[]
        }

        const model = fieldModel.research_variable[key]
        if (Array.isArray(dependent)) {
          dependent.forEach(({ line, sequence }) => {
            result.push({
              id: `aimd-${key}-rv-ref`,
              scope: "rv_ref",
              prop: key,
              fieldType: "rv-ref",
              placeholder: title || "",
              model,
              // to: `#research_variable-${key}-ref-${line}-${sequence}`,
              type: "rv-ref",
              tooltip: description || title || key,
              title,
              info: {},
              themeOverrides: undefined,
            })
          })
        }
        else {
          result.push({
            id: `aimd-${key}-rv-ref`,
            scope: "rv_ref",
            prop: key,
            fieldType: "rv-ref",
            placeholder: title || "",
            model,
            // to: `[id^=research_variable-${key}-ref]`,
            type: "rv-ref",
            tooltip: description || title || key,
            title,
            info: {},
            themeOverrides: undefined,
          })
        }
      })
    }

    return result
  })

  const tableList = computed((): IAIMDItemProps[] => {
    const result: IAIMDItemProps[] = []
    const { tableRecord } = toValue(props)
    const groupList = Object.entries(tableRecord)

    groupList.forEach(([groupKey, items]) => {
      const propList = Object.entries(items)

      propList.forEach(([propKey, propItem]) => {
        const { title, description, assigner, dependent } = propItem

        result.push({
          id: `aimd-${groupKey}-${propKey}-table`,
          scope: "var_table",
          prop: propKey,
          fieldType: "var-table-header",
          placeholder: title || "",
          model: { value: null },
          // to: `#var_table-${groupKey}-${propKey}-header`,
          type: "var-table-header",
          tooltip: description || title || propKey,
          info: { ...propItem, group: groupKey },
          assigner,
          dependent,
          disabled: assigner?.mode === "auto_force",
          required: undefined,
          themeOverrides: undefined,
        })
      })
    })

    return result
  })

  // Create a list for step references
  const stepRefList = ref<IAIMDItemProps[]>([])

  // Process step references from the environment
  if (!minimal) {
    watchEffect(() => {
      const { typed } = toValue(props)
      if (!typed || !typed.research_step_ref) {
        stepRefList.value = []
        return
      }

      const stepRefs = Object.entries(typed.research_step_ref).map(([name, info]) => {
        return {
          id: `research_step_ref-${name}`,
          to: `#research_step_ref-${name}`,
          type: "research_step_ref",
          fieldType: "research_step_ref",
          scope: "research_step_ref" as ScopeFieldKey,
          prop: name,
          refStep: name,
          model: fieldModel,
          info: { env: typed },
          disabled: undefined,
          required: undefined,
          themeOverrides: undefined,
        }
      })

      stepRefList.value = stepRefs
    })
  }

  return {
    variableList,
    refList,
    tableList,
    stepRefList,
  }
}

// Field handlers composable
function useAIMDFieldHandlers(
  _props: MaybeRef<IAIMDWrapperProps>,
  fieldModel: IFieldModel,
  tableVariableRecord: Ref<Record<string, Record<string, any>>>,
  assignerLoadingRecord: Ref<Record<string, boolean | undefined>>,
  assignerErrorRecord: Ref<Record<string, string | boolean | undefined>>,
  formItemRef: Record<string, { value: FormItemInst | null }>,
  fieldEventBus: any,
  message: any,
  minimal: boolean,
  // emit: IEmits,
) {
  const debouncedSave = minimal
    ? () => {}
    : useDebounceFn(
      (payload: {
        scope: IRecordDataKey
        prop: string
        value:
          | string
          | number
          | boolean
          | { value: Big.Big | number | null, displayedValue: string }
          | { checked: boolean | null, annotation: string }
          | undefined
        assigner?: Assigner
        dependent?: { name: string, scope: IRecordDataKey }[]
      }) => {
        fieldEventBus.emit("preview-field-change", payload)
      },
      50,
    )

  function handleFieldChange(payload: {
    scope: ScopeFieldKey
    prop: string
    value: any
    assigner?: Assigner
    dependent?: { name: string, scope: IRecordDataKey }[]
    type?: string
    info: any
  }) {
    if (minimal)
      return

    const { scope, prop, value, info, type } = payload

    const { group, row } = info || {}
    const keys = group
      ? [`${group}.${prop}[${row}]`, group]
      : [prop]

    keys.forEach((key) => {
      assignerLoadingRecord.value[key] = undefined
      assignerErrorRecord.value[key] = undefined
    })

    let savePayload = payload
    if (scope === "var_table") {
      const { row, group } = info

      const targetGroup = fieldModel.research_variable?.[group]
      if (targetGroup) {
        const target = Array.isArray(targetGroup.value) ? targetGroup.value[row] : null
        if (target) {
          target[prop] = value as any
          _set(tableVariableRecord.value, `${group}[${row}].${prop}.model.value`, value)
          if (type) {
            _set(tableVariableRecord.value, `${group}[${row}].${prop}.type`, type)
          }

          if (info.link) {
            const { source: linkSource, target: linkTarget, isSource } = info.link
            if (isSource && linkSource.prop === prop) {
              _set(
                fieldModel.research_variable,
                `${linkTarget.name}.value[${row}].${linkTarget.prop}`,
                value,
              )
              _set(
                tableVariableRecord.value,
                `${linkTarget.name}[${row}].${linkTarget.prop}.model.value`,
                value,
              )
              if (type) {
                _set(
                  tableVariableRecord.value,
                  `${linkTarget.name}[${row}].${linkTarget.prop}.type`,
                  type,
                )
              }
            }
          }
        }
        else {
          message.error("Failed to update table row")
        }
      }
    }
    else {
      if (fieldModel?.[scope]?.[prop]) {
        if (scope === "research_step" || scope === "research_check") {
          const targetModel = fieldModel[scope][prop].value as {
            checked: boolean | null
            annotation: string
          }
          if (typeof value === "boolean") {
            targetModel.checked = value
            // Trigger reactivity by reassigning the entire value object
            fieldModel[scope][prop].value = { ...targetModel }
          }
          if (typeof value === "string") {
            targetModel.annotation = value
            // Trigger reactivity by reassigning the entire value object
            fieldModel[scope][prop].value = { ...targetModel }
          }

          savePayload = { ...payload, value: { ...targetModel } }
        }
        else {
          fieldModel[scope][prop].value = value
          if (type) {
            _set(fieldModel, `${scope}.${prop}.type`, type)
          }
        }
      }

      if (typeof value === "undefined") {
        assignerLoadingRecord.value[prop] = undefined
      }
    }

    void debouncedSave(savePayload)
  }

  function handleCheckedChange(
    info: Record<string, any>,
    scope: ScopeFieldKey,
    prop: string,
    value: boolean,
    assigner?: any,
    dependent?: any,
  ) {
    if (minimal)
      return

    const { checked_message } = info

    if (value && checked_message) {
      message.info(checked_message)
    }

    handleFieldChange({ scope, prop, value, assigner, dependent, info })
  }

  return {
    handleFieldChange,
    handleCheckedChange,
  }
}

// File handlers composable
function useAIMDFileHandlers(
  fieldModel: IFieldModel,
  previewFileRecord: Ref<Record<string, { content: null | string, file: null | File, visible: boolean } & Partial<UploadSettledFileInfo>>>,
  formItemRef: Record<string, { value: FormItemInst | null }>,
  fieldEventBus: any,
  minimal: boolean,
) {
  function handleFileChange(payload: {
    scope: IRecordDataKey
    prop: string
    fileInfo: {
      file: UploadFileInfo
      fileList: UploadFileInfo[]
      event?: Event | undefined
    }
    id: string
    info?: any
  }) {
    if (minimal)
      return

    const { fileInfo, id, scope, prop, info } = payload

    const { status } = fileInfo.file
    if (status === "removed") {
      fieldEventBus.emit("preview-file-change", {
        scope,
        prop,
        value: { file: fileInfo, type: "remove" },
        info,
      })
      _set(fieldModel, `${scope}.${prop}.value`, undefined)

      previewFileRecord.value[id] = { content: null, file: null, visible: false }
      return
    }

    fieldEventBus.emit("preview-file-change", {
      scope,
      prop,
      value: { file: fileInfo, type: "add" },
      info,
    })
    _set(fieldModel, `${scope}.${prop}.value`, fileInfo.fileList)
  }

  function handleUploadFile(payload: {
    scope: ScopeFieldKey
    prop: string
    type: string
    file: Api.Attachment.AttachmentItem | null
    rawFile: UploadFileInfo
    assigner?: any
    dependent?: any
    info?: any
  }) {
    if (minimal)
      return

    const { scope, prop, type, file: fileInfo, rawFile, assigner, dependent, info } = payload
    if (!fileInfo) {
      return
    }
    fieldEventBus.emit("preview-file-uploaded", {
      scope,
      prop,
      value: { ...fileInfo, type },
      assigner,
      dependent,
      info,
    })

    const targetFile = (fieldModel[scope]?.[prop]?.value as unknown as UploadFileInfo[])?.find(
      it => it.id === rawFile.id,
    )
    if (targetFile) {
      targetFile.airalogyId = fileInfo.id
      targetFile.url = fileInfo.url
      targetFile.status = "finished"
      targetFile.thumbnailUrl = fileInfo.url
    }

    const formItem = formItemRef[`${scope}.${prop}.value`]?.value
    if (formItem) {
      formItem.restoreValidation()
    }
  }

  function handleRename(
    scope: ScopeFieldKey,
    prop: string,
    fileInfo: Partial<Api.Attachment.AttachmentItem>,
    info?: any,
  ) {
    if (minimal)
      return

    const { id, filename, url } = fileInfo
    const targetFile = (fieldModel[scope]?.[prop]?.value as unknown as UploadFileInfo[])?.find(
      (f: any) => f.id === id,
    )

    if (!targetFile) {
      return
    }

    targetFile.name = filename ?? targetFile.name
    targetFile.url = url
    targetFile.thumbnailUrl = url

    fieldEventBus.emit("preview-file-renamed", {
      scope,
      prop,
      value: fileInfo,
      info,
    })
  }

  async function handlePreviewFile(id: string, info: UploadSettledFileInfo) {
    if (minimal)
      return

    if (!id) {
      return
    }

    const { file, url, name } = info

    const prevFile = previewFileRecord.value[id]

    if (file) {
      previewFileRecord.value[id] = { ...info, visible: true, content: null }
    }
    else if (prevFile) {
      prevFile.visible = true
    }
    else if (url) {
      try {
        const res = await request({
          method: "get",
          url,
          headers: { "Content-Type": "application/octet-stream" },
          baseURL: "/",
        })

        if (typeof res.data === "string") {
          previewFileRecord.value[id] = { file: null, content: res.data, visible: true }
        }
        else {
          const currFile = new File(res.data, name)

          previewFileRecord.value[id] = { file: currFile, content: null, visible: true }
        }
      }
      catch (e) {
        //
      }
    }
  }

  return {
    handleFileChange,
    handleUploadFile,
    handleRename,
    handlePreviewFile,
  }
}

// Table operations composable
function useAIMDTableOperations(
  props: MaybeRef<IAIMDWrapperProps>,
  fieldModel: IFieldModel,
  tableVariableRecord: Ref<Record<string, Record<string, any>>>,
  record: Ref<any>,
  readonly: Ref<boolean | undefined>,
  message: any,
  minimal: boolean,
  emit: IEmits,
) {
  function handleGetTableHeader(group: string, prop: string) {
    const { tableRecord } = toValue(props)
    return _get(tableRecord, [group, prop])
  }

  function restoreTableVariableRecord() {
    Object.entries(toValue(props).tableRecord).forEach(([group, targetGroup]) => {
      const tableData = fieldModel.research_variable?.[group]?.value

      // Try to get info from record.field.research_variable[group].raw
      // If not available (e.g. in readonly mode), construct minimal info from targetGroup
      let info = get(record?.value, ["field", "research_variable", group, "raw"])

      // Fallback: if info is not available, construct it from tableRecord
      if (!info && targetGroup) {
        const subvars = Object.keys(targetGroup).map(key => ({ name: key }))
        info = {
          name: group,
          subvars,
          link: null,
          schema: {},
        }
      }

      if (!tableData || !Array.isArray(tableData) || tableData.length === 0) {
        tableVariableRecord.value[group] = []
        return
      }

      tableVariableRecord.value[group] = []

      if (!targetGroup || !info)
        return

      tableData.forEach((rowData, rowIdx) => {
        handleSetTableVariableRecord(
          info,
          tableData,
          rowIdx,
        )
      })
    })
  }

  function handleSetTableVariableRecord(info: { name: string, subvars: any[], link: any, schema: SomeJSONSchema }, data?: any, rowIdx = 0, commit = true) {
    const { tableRecord } = toValue(props)
    if (!tableRecord) {
      message.error("Failed to add table row")
      return
    }

    const { name, subvars, link } = info
    const targetGroup = tableRecord[name]

    if (!targetGroup) {
      return
    }

    // Normalize subvars to string array (handles both string[] and {name: string}[] formats)
    const subvarNames = getSubvarNames(subvars)

    const { row, model } = subvarNames.reduce(
      (acc, cur, colIdx) => {
        const item = targetGroup[cur] || {}
        const { description, title, assigner } = item
        const dependent = mergeDependents(
          item.dependent,
          (fieldModel.research_variable?.[name] as any)?.dependent,
        )
        const inputType = getInputType(item)
        const targetThemeOverrides = createTableCellThemeOverrides(inputType)
        const isLinkProp = link && link.target === cur

        // Get target value from data, or use default value from subvar definition or tableRecord
        let targetValue = data ? _get(data, [rowIdx, cur], undefined) : undefined
        if (targetValue === undefined && !data) {
          // When adding a new row (data is undefined), use default value
          // First try from subvar definition
          const subvarDef = getSubvarDef(subvars, cur)
          if (subvarDef?.default !== undefined) {
            targetValue = subvarDef.default
          }
          // Also try from tableRecord item (which may have default from schema)
          else if ((item as any).default !== undefined) {
            targetValue = (item as any).default
          }
        }

        const value = isLinkProp
          ? _get(
            fieldModel.research_variable,
            `${link.node.name}.value[${rowIdx}].${link.source}`,
            undefined,
          )
          : formatRawValue(targetValue, inputType)

        acc.row[cur] = {
          id: `aimd-${name}-${cur}-table-cell-row-${rowIdx}-col-${colIdx}`,
          scope: "var_table",
          prop: cur,
          fieldType: "var-table-cell",
          placeholder: title || "",
          model: { value },
          type: inputType,
          tooltip: (description || title || name) as string,
          info: { ...item, row: rowIdx, col: colIdx, group: name, link, prop: cur },
          // to: "",
          disabled: readonly.value || isLinkProp || assigner?.mode === "auto_force",
          required: undefined,
          themeOverrides: targetThemeOverrides,
          assigner,
          dependent,
          enumInfo: item.enum,
        }

        if (isLinkProp) {
          acc.model[cur] = value as any
        }
        else if (inputType === "integer" || inputType === "float" || inputType === "number") {
          // Use default value if available, otherwise null
          const numValue = targetValue !== undefined ? targetValue : null
          acc.model[cur] = {
            displayedValue: numValue !== null ? String(numValue) : "",
            type: inputType,
            value: numValue,
          } as ICustomInputNumberPayload
        }
        else {
          // Use default value if available
          acc.model[cur] = targetValue !== undefined ? targetValue : undefined
        }

        return acc
      },
      { row: {}, model: {} } as {
        row: Record<string, IAIMDItemProps>
        model: Record<string, undefined | string | ICustomInputNumberPayload>
      },
    )

    if (commit) {
      if (Array.isArray(tableVariableRecord.value[name])) {
        tableVariableRecord.value[name].push(row)
      }
      else {
        tableVariableRecord.value[name] = [row]
      }
    }

    return { row, model }
  }

  function handleAddVarTableRow(info: Record<string, any>, shouldEmit = true) {
    if (minimal)
      return

    const { name } = info
    const rowIdx = tableVariableRecord.value[name]?.length ?? 0

    const { row, model } = handleSetTableVariableRecord(info as any, undefined, rowIdx) || {}
    if (!row || !model) {
      return
    }

    const targetModel = fieldModel.research_variable?.[name]?.value
    if (Array.isArray(targetModel)) {
      targetModel.push(model)
    }
    else if (fieldModel.research_variable[name]) {
      fieldModel.research_variable[name].value = [model] as any
    }
    else {
      fieldModel.research_variable[name] = { value: [model] as any }
    }

    if (shouldEmit) {
      emit("add-row:table", { row, model, info })
    }

    return { row, model }
  }

  function handleRemoveVarTableRow(group: string, row: number, shouldEmit = true) {
    if (minimal)
      return

    if (!group || !Array.isArray(tableVariableRecord.value[group])) {
      return
    }

    tableVariableRecord.value[group] = tableVariableRecord.value[group].filter(
      (_: any, idx: number) => idx !== row,
    )
    const targetModel = fieldModel.research_variable[group].value

    if (Array.isArray(targetModel)) {
      fieldModel.research_variable[group].value = targetModel.filter((_, idx) => idx !== row)
    }

    // Update row indices for all remaining rows in the group
    tableVariableRecord.value[group].forEach((rowData: any, newIndex: number) => {
      Object.keys(rowData).forEach((colKey: string) => {
        if (rowData[colKey] && rowData[colKey].info) {
          rowData[colKey].info.row = newIndex
          if (rowData[colKey].id) {
            const idParts = rowData[colKey].id.split("-row-")
            if (idParts.length > 1) {
              const suffixParts = idParts[1].split("-col-")
              if (suffixParts.length > 1) {
                rowData[colKey].id = `${idParts[0]}-row-${newIndex}-col-${suffixParts[1]}`
              }
            }
          }
        }
      })
    })

    if (shouldEmit) {
      emit("remove-row:table", { row, info: { name: group } })
    }
  }

  return {
    handleGetTableHeader,
    restoreTableVariableRecord,
    handleSetTableVariableRecord,
    handleAddVarTableRow,
    handleRemoveVarTableRow,
  }
}

// Utility functions composable
function useAIMDUtilities(
  props: MaybeRef<IAIMDWrapperProps>,
  itemRef: Ref<Record<string, { value: any, type: string }>>,
  formItemRef: Record<string, { value: FormItemInst | null }>,
  fieldEventBus: any,
  minimal: boolean,
) {
  const message = useClosableMessage()
  function handleRef(
    path: string,
    el: Element | ComponentPublicInstance<{ getRef: () => Element | null }> | null,
    type: string,
    info?: Record<string, any>,
    isCustomRef: boolean = false,
  ) {
    if (info && info.group) {
      const { row, group, prop } = info
      const rowPath = `var_table_${group}_${prop}_${row}`
      const targetRef = itemRef.value[rowPath]

      const targetEl = isCustomRef
        ? ((
            el as ComponentPublicInstance<{ getRef: () => Element | null }>
          )?.getRef() as Element) || null
        : el

      if (targetRef) {
        targetRef.value = targetEl
        targetRef.type = type
      }
      else {
        itemRef.value[rowPath] = {
          value: targetEl,
          type,
        }
      }
    }
    else {
      const targetRef = itemRef.value[path]
      const targetEl = isCustomRef ? ((el as any)?.getRef() as Element) || null : el

      if (targetRef) {
        targetRef.value = targetEl
        targetRef.type = type
      }
      else {
        itemRef.value[path] = {
          value: targetEl,
          type,
        }
      }
    }
  }

  function handleInputBlur(e: FocusEvent, scope: IRecordDataKey, prop: string, info?: any) {
    if (minimal)
      return

    const { currentTarget } = e
    const parentTarget = (currentTarget as HTMLElement).closest(".aimd-field--focus")

    if (parentTarget) {
      parentTarget.classList.remove("aimd-field--focus")
    }
    fieldEventBus.emit("preview-field-blur", { scope, prop, info })
  }

  function handleAssignerClick(item: IAIMDItemProps) {
    if (minimal)
      return

    const { assigner, scope, prop } = item
    fieldEventBus.emit("assigner-request", { assigner, scope, prop })
  }

  function handleAssignerCancel(item: IAIMDItemProps) {
    if (minimal)
      return

    const { assigner, scope, prop, dependent } = item
    if (assigner) {
      fieldEventBus.emit("assigner-cancel", { assigner, scope, prop })
    }
    else if (dependent) {
      fieldEventBus.emit("assigner-cancel-batch", { dependent, scope, prop })
    }
    else {
      message.error("Failed to stop assigner")
    }
  }

  function handleScrollField(
    _: FocusEvent | null,
    scope: IRecordDataKey,
    prop: string,
    varName?: string,
    info?: any,
  ) {
    if (minimal)
      return

    fieldEventBus.emit("preview-field-focus", { scope, prop, info, varName })
  }

  function handleFormItemRef(path: string, el: FormItemInst | null) {
    const targetRef = formItemRef[path]

    if (targetRef) {
      targetRef.value = el
    }
    else {
      formItemRef[path] = {
        value: el,
      }
    }
  }

  function isVarTable(prop: string) {
    const { tableRecord, varScopeRecord } = toValue(props)
    if (_get(tableRecord, prop)) {
      return true
    }

    return !varScopeRecord[prop]
  }

  return {
    handleRef,
    handleInputBlur,
    handleAssignerClick,
    handleAssignerCancel,
    handleScrollField,
    handleFormItemRef,
    isVarTable,
  }
}

/**
 * Compute field activation status for assigner dependencies
 * @param dependentFields - Array of field names to check
 * @param fieldModel - The field model containing field values
 * @param varScopeRecord - Record mapping field names to their scopes
 * @param tableRecord - Record for table fields
 * @returns Record mapping field names to their activation status
 */
export function computeFieldActivationStatus(
  dependentFields: string[],
  fieldModel: IFieldModel,
  varScopeRecord: Record<string, ScopeFieldKey>,
  tableRecord: Record<string, any> = {},
): Record<string, boolean> {
  const activationStatus: Record<string, boolean> = {}

  dependentFields.forEach((fieldName) => {
    try {
      // Check if it's a var_table field
      if (tableRecord[fieldName]) {
        activationStatus[fieldName] = true // Table fields are considered active if they exist
        return
      }

      // Get the field scope
      const fieldScope = varScopeRecord[fieldName] as ScopeFieldKey
      if (!fieldScope) {
        activationStatus[fieldName] = false
        return
      }

      // Get the field value
      const fieldPath = `${fieldScope}.${fieldName}.value`
      const fieldValue = _get(fieldModel, fieldPath)
      const fieldDefinition = _get(fieldModel, `${fieldScope}.${fieldName}`)

      // Use the same logic as checkFieldHasValue from useAssignerManagement
      activationStatus[fieldName] = checkFieldHasValue(fieldValue, fieldDefinition, fieldName)
    }
    catch (error) {
      console.warn(`Error checking field activation status for ${fieldName}:`, error)
      activationStatus[fieldName] = false
    }
  })

  return activationStatus
}

/**
 * Check if a field has a valid value
 * Replicates the logic from useAssignerManagement's checkFieldHasValue
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

// Event bus handling composable
function useAIMDEventBusHandlers(
  fieldModel: IFieldModel,
  tableVariableRecord: Ref<Record<string, Record<string, any>>>,
  itemRef: Ref<Record<string, { value: any, type: string }>>,
  formItemRef: Record<string, { value: FormItemInst | null }>,
  fieldEventBus: any,
  message: any,
  minimal: boolean,
  handleAddVarTableRow: (info: Record<string, any>) => void,
  handleRemoveVarTableRow: (group: string, row: number) => void,
) {
  if (minimal)
    return

  fieldEventBus.on((event: string, payload: IAIMDEventBusPayload) => {
    if (
      event !== "preview-field-scroll"
      && event !== "draft-restored"
      && event !== "form-field-blur"
      && event !== "form-field-change"
      && event !== "form-file-change"
      && event !== "start-assigner-request"
      && event !== "end-assigner-request"
      && event !== "error-assigner-request"
      && event !== "file-assigned"
      && event !== "field-update-complete"
    ) {
      return
    }

    const { scope, prop, value, info } = payload
    let path: string | undefined

    if (info && info.type === "table") {
      const { row, group, name } = info
      path = `var_table_${group}_${name}_${row}`
    }
    else if (scope === "research_check" || scope === "research_step") {
      path = `${scope}_${prop}-${info?.type || "check"}`
    }
    else {
      path = `${scope}_${prop}`
    }

    const inputInst = path ? itemRef.value[path]?.value : null
    if (inputInst) {
      const inputWrapperEl = inputInst.$el as HTMLElement | null
      if (inputWrapperEl) {
        const wrapperEl = inputWrapperEl.closest(".aimd-field-wrapper")
        if (event === "preview-field-scroll") {
          inputWrapperEl.scrollIntoView({ block: "center", behavior: "smooth" })
          if (wrapperEl) {
            wrapperEl.classList.add("aimd-field--focus")
          }
        }

        if (event === "form-field-blur") {
          if (wrapperEl) {
            wrapperEl.classList.remove("aimd-field--focus")
          }
        }
      }
    }

    if (event === "form-field-change") {
      const controlledValue = typeof value === "undefined" ? null : value
      const { info: fieldInfo } = payload as any

      let modelPath = `${scope}.${prop}.value`

      if (scope === "research_step" || scope === "research_check") {
        if (typeof value === "boolean") {
          modelPath = `${modelPath}.checked`
        }
        if (typeof value === "string") {
          modelPath = `${modelPath}.annotation`
        }
      }

      if (scope === "var_table") {
        const { group, row } = fieldInfo
        const [groupName, varName] = prop.split(".")
        if (groupName === group && varName) {
          modelPath = `research_variable.${group}.value[${row}].${varName}`
          _set(
            tableVariableRecord.value,
            `${group}[${row}].${varName}.model.value`,
            controlledValue,
          )
        }
        else {
          modelPath = `research_variable.${group}.value[${row}].${prop}`
          _set(
            tableVariableRecord.value,
            `${group}[${row}].${prop}.model.value`,
            controlledValue,
          )
        }
      }
      else if (typeof controlledValue === "object" && controlledValue && "airalogy_file_id" in controlledValue) {
        const { airalogy_file_id, url, filename } = controlledValue
        const fileList = (_get(fieldModel, modelPath)) as any as UploadFileInfo[]

        if (Array.isArray(fileList)) {
          const targetId = payload.fileInfo?.id
          const targetFile = targetId ? fileList.find(it => it.id === targetId) : null
          if (targetFile) {
            targetFile.id = airalogy_file_id
            targetFile.url = url
            targetFile.name = filename
            targetFile.status = "finished"
          }
        }
      }
      else {
        _set(fieldModel, modelPath, controlledValue)
      }
      if (typeof value === "string") {
        const mirrorEl = (inputInst as any)?.inputMirrorElRef as HTMLDivElement
        if (mirrorEl) {
          if (value) {
            mirrorEl.textContent = value
          }
          else {
            mirrorEl.innerHTML = "&nbsp;"
          }
        }
      }

      void nextTick(async () => {
        const formItem = formItemRef[`${scope}.${prop}.value`]
        if (formItem) {
          try {
            const result = await formItem.value?.validate?.()
            if (result?.warnings) {
              message.warning(result.warnings.map(m => m.message).join("\n"))
            }
            else {
              formItem.value?.restoreValidation?.()
            }
          }
          catch (e) {
            // NOPE
          }
        }
      })
    }

    if (event === "draft-restored") {
      return
    }

    if (event === "form-file-change") {
      const { file } = value as {
        file: {
          file: UploadFileInfo
          fileList: UploadFileInfo[]
          event?: Event | undefined
        }
        status: "remove" | "add"
      }

      if (info?.group) {
        const { group, row } = info
        const [groupName, varName] = prop.split(".")
        if (groupName === group && varName) {
          const modelPath = `research_variable.${group}.value[${row}].${varName}`
          _set(fieldModel, modelPath, file.fileList)
        }
      }
      else {
        _set(fieldModel, `${scope}.${prop}.value`, file.fileList)
      }
    }

    if (event === "file-assigned") {
      if (!isAssignedFileValue(value)) {
        return
      }

      // Ensure the file object has proper structure for n-upload
      const fileValue = {
        ...value,
        status: "finished" as const,
      }
      // Use direct assignment for better reactivity
      if (fieldModel[scope]?.[prop]) {
        fieldModel[scope][prop].value = [fileValue]
      }
      else {
        _set(fieldModel, `${scope}.${prop}.value`, [fileValue])
      }
    }

    if (event === "field-update-complete") {
      const formItemKey = `${scope}.${prop}.value`
      const formItem = formItemRef[formItemKey]
      if (formItem?.value?.validate) {
        formItem.value.validate().catch(() => {
          // Silently ignore validation errors during batch processing
          // These errors are expected when fields have complex types
        })
      }
    }
  })

  fieldEventBus.on(
    (event: string, payload: { source: IDynamicTableNode, payload: Record<string, any> }) => {
      if (
        event !== "add-slave-table-row"
        && event !== "remove-slave-table-row"
        && event !== "add-var-table-row"
      ) {
        return
      }
      if (event === "add-var-table-row") {
        handleAddVarTableRow(payload)
      }

      if (event === "add-slave-table-row") {
        const { source } = payload

        handleAddVarTableRow({
          name: source.name,
          subvars: source.props,
          link: source.link,
          raw: payload,
        })
      }

      if (event === "remove-slave-table-row") {
        const {
          source,
          payload: { row },
        } = payload as Record<string, any>

        handleRemoveVarTableRow(source.name, row)
      }
    },
  )
}

// Create the injection state
const [useAIMDProvide, useAIMDInject] = createInjectionState(
  (props: MaybeRef<IAIMDWrapperProps>, emit: IEmits, minimal = false) => {
    const { fieldModel, tableVariableRecord, previewFileRecord, itemRef, formItemRef, varScopeRecord, typed, readonly, protocolId, assignerLoadingRecord, assignerErrorRecord, assignerRequestRecord, record, authStore, tableRecord } = useAIMDState(props)
    const { fieldEventBus, message } = useAIMDEventHandling(props, minimal)
    const { variableList, refList, tableList, stepRefList } = useAIMDComputed(props, fieldModel, authStore, tableRecord, minimal)
    const { handleFieldChange, handleCheckedChange } = useAIMDFieldHandlers(props, fieldModel, tableVariableRecord, assignerLoadingRecord, assignerErrorRecord, formItemRef, fieldEventBus, message, minimal)
    const { handleFileChange, handleUploadFile, handleRename, handlePreviewFile } = useAIMDFileHandlers(fieldModel, previewFileRecord, formItemRef, fieldEventBus, minimal)
    const { handleGetTableHeader, restoreTableVariableRecord, handleSetTableVariableRecord, handleAddVarTableRow, handleRemoveVarTableRow } = useAIMDTableOperations(props, fieldModel, tableVariableRecord, record, readonly, message, minimal, emit)
    const { handleRef, handleInputBlur, handleAssignerClick, handleAssignerCancel, handleScrollField, handleFormItemRef, isVarTable } = useAIMDUtilities(props, itemRef, formItemRef, fieldEventBus, minimal)

    // Event bus handlers (conditional based on minimal mode)
    useAIMDEventBusHandlers(fieldModel, tableVariableRecord, itemRef, formItemRef, fieldEventBus, message, minimal, handleAddVarTableRow, handleRemoveVarTableRow)

    return {
      fieldModel,
      tableVariableRecord,
      isVarTable,
      itemRef,
      previewFileRecord,
      variableList,
      refList,
      tableList,
      fieldEventBus,
      varScopeRecord,
      typed,
      readonly,
      protocolId,
      assignerErrorRecord,
      assignerLoadingRecord,
      assignerRequestRecord,
      authStore,
      formItemRef,
      handleGetTableHeader,
      handleFormItemRef,
      handleFieldChange,
      handleCheckedChange,
      handleRef,
      handleInputBlur,
      handleFileChange,
      handleUploadFile,
      handleRename,
      handleAddVarTableRow,
      handleRemoveVarTableRow,
      handleAssignerClick,
      handleAssignerCancel,
      handlePreviewFile,
      handleScrollField,
      handleSetTableVariableRecord,
      restoreTableVariableRecord,
      stepRefList,
    }
  },
)

export { useAIMDInject, useAIMDProvide }
