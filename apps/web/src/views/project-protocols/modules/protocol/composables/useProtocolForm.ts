import type { IRecordDataKey } from "@airalogy/aimd-core/types"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { FormItemInst, UploadFileInfo, UploadSettledFileInfo } from "naive-ui"
import type { ComponentInstance } from "vue"
import type { IFieldChangePayload, IFieldItem } from "../types/types"
import { getInputType } from "@/components/custom/aimd/composables/useAIMDHelpers"

import { request } from "@/service/request"
import { fieldEventKey } from "@/utils/template/eventKey"
import { useClosableMessage } from "@airalogy/composables"
import { createInjectionState, useEventBus } from "@vueuse/core"
import Big from "big.js"
import { reactive, ref } from "vue"

export interface IEmits {
  (e: "field:scroll", scope: IRecordDataKey, prop: string, varName?: string): void
  (e: "field:change", payload: IFieldChangePayload): void
}

const typeMap: Record<string, any> = {
  string: "primary",
  number: "success",
  boolean: "info",
  method: "default",
  regexp: "default",
  integer: "warning",
  float: "warning",
  array: "info",
  object: "default",
  default: "default",
}

// Create injection state
const [useProtocolFormProvide, useProtocolFormInject] = createInjectionState(
  (props: any, emit: IEmits) => {
    const imageFileList = ref<UploadFileInfo[]>([])
    const imageFileListRecord = ref<Record<string, UploadFileInfo[]>>({})

    const previewFileRecord = ref<
      Record<string, { file: File | null, content: string | null, visible: boolean }>
    >({})
    const protocolId = computed(() => props.protocolId)

    const { readonly, varScopeRecord, tableRecord, assignerLoadingRecord, assignerErrorRecord, shouldScroll } = toRefs(props)

    const itemRef = reactive<Record<string, { value: ComponentInstance<any> | null }>>({})
    const formItemRef = reactive<Record<string, { value: FormItemInst | null }>>({})

    const expandedNamesRef = ref<string[]>([])
    const fieldEventBus = useEventBus<string>(fieldEventKey)
    const message = useClosableMessage()

    function clearAssignerState(prop: string, info?: { group?: string, row?: number }) {
      const { group, row } = info || {}
      const keys = group
        ? [`${group}.${prop}[${row}]`, group]
        : [prop]

      keys.forEach((key) => {
        assignerLoadingRecord.value[key] = undefined
        assignerErrorRecord.value[key] = undefined
      })
    }

    function handleFieldChange(payload: IFieldChangePayload) {
      clearAssignerState(payload.prop, payload.info)

      fieldEventBus.emit("form-field-change", payload)

      emit("field:change", payload)

      if (payload?.info?.link) {
        const { isSource } = payload.info.link
        if (isSource) {
          fieldEventBus.emit("assign-table-link", payload)
        }
      }

      if (typeof payload.value === "undefined") {
        assignerLoadingRecord.value[payload.prop] = undefined
      }
    }

    function handleScrollField(
      _: FocusEvent | null,
      scope: IRecordDataKey,
      prop: string,
      varName?: string,
      info?: any,
    ) {
      fieldEventBus.emit("preview-field-scroll", { scope, prop, varName, info })
    }

    function handleInputBlur(e: FocusEvent, scope: IRecordDataKey, prop: string, info?: any) {
      const { currentTarget } = e
      const parentTarget = (currentTarget as HTMLElement).closest(".aimd-field--focus")

      if (parentTarget) {
        parentTarget.classList.remove("aimd-field--focus")
      }

      fieldEventBus.emit("form-field-blur", { scope, prop, info })
    }

    function handleRef(path: string, el: any, isCustomRef: boolean = false) {
      const targetRef = itemRef[path]
      const targetEl = isCustomRef ? (el?.getRef() as Element) || null : el

      if (targetRef) {
        targetRef.value = targetEl
      }
      else {
        itemRef[path] = {
          value: targetEl,
        }
      }
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

    async function formItemValidate(scope: IRecordDataKey, prop: string) {
      if (!scope || !prop)
        return false

      const targetRef = formItemRef[`${scope}_${prop}`]
      if (targetRef) {
        try {
          return await targetRef.value?.validate()
        }
        catch (_) {
          return false
        }
      }
      return false
    }

    function handleAddVarTableRow(payload: any) {
      fieldEventBus.emit("add-var-table-row", payload)
    }

    function handleFileChange(scope: IRecordDataKey, prop: string, options: { file: UploadFileInfo, fileList: Array<UploadFileInfo>, event?: Event }, info?: any) {
      const { file: { status }, fileList } = options

      if (info?.group) {
        // For table cells, create a unique key using group, row, and col
        const cellKey = `${info.group}_${info.row}_${info.col}_${prop}`

        if (status === "removed") {
          // Remove the file record when file is removed
          delete imageFileListRecord.value[cellKey]
        }
        else {
          // Store the latest file for this cell
          imageFileListRecord.value[cellKey] = fileList
        }
      }
      else {
        // For non-table fields, use the original imageFileList
        imageFileList.value = fileList
      }

      fieldEventBus.emit("form-file-change", {
        scope,
        prop,
        value: { file: options, type: status === "removed" ? "remove" : "add" },
        fileList,
        info,
      })

      if (status === "removed") {
        handleFieldChange({
          scope,
          prop,
          value: null,
          shouldUpdate: true,
          shouldAssign: true,
          info,
        })
      }
    }

    // Add a helper function to get file for a specific table cell
    function getTableCellFile(group: string, row: number, col: number, prop: string): UploadFileInfo[] | undefined {
      const cellKey = `${group}_${row}_${col}_${prop}`
      return imageFileListRecord.value[cellKey]
    }

    async function handlePreviewFile(id: string | null, info: UploadSettledFileInfo) {
      if (!id)
        return

      const { file, url, name } = info
      const prevFile = previewFileRecord.value[id]

      if (file) {
        previewFileRecord.value[id] = { file: info.file, visible: true, content: null }
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
          // Handle error
        }
      }
    }

    function handleCheckedChange(
      info: Record<string, any>,
      scope: IRecordDataKey,
      prop: string,
      value: boolean,
      assigner?: ProtocolModels.Assigner,
      dependent?: { name: string, scope: IRecordDataKey }[],
    ) {
      const { checked_message } = info.raw || {}

      if (value && checked_message) {
        message.info(checked_message)
      }

      handleFieldChange({
        scope,
        prop,
        value: { ...info.value, checked: value },
        assigner,
        dependent,
      })
    }

    function handleUploadFile(payload: {
      scope: IRecordDataKey
      prop: string
      type: string
      fileInfo: any
      attachmentInfo: Api.Attachment.AttachmentItem
      info?: any
      assigner?: ProtocolModels.Assigner
      dependent?: { name: string, scope: IRecordDataKey }[]
    }) {
      const { fileInfo, prop, scope, type, assigner, dependent, attachmentInfo, info } = payload
      const value = { ...attachmentInfo, type }

      // fieldEventBus.emit("form-file-uploaded", {
      //   scope,
      //   prop,
      //   value,
      //   assigner,
      //   dependent,
      //   fileInfo,
      //   info,
      // })

      // TODO: update file url

      // const targetFile = imageFileList.value.find(it => it.id === fileInfo.id)
      // if (targetFile) {
      //   targetFile.url = fileInfo.url
      // }

      handleFieldChange({ scope, prop, value: value as any, assigner, dependent, attachmentInfo, info, fileInfo })
      void formItemValidate(scope, prop)
    }

    function handleAssignerClick(item: any) {
      const { assigner, scope, prop } = item

      fieldEventBus.emit("assigner-request", { assigner, scope, prop })
    }

    function createTableCellModel(payload: {
      schema: any
      value: any
      label: string
      scope: IRecordDataKey
      title: string
      info: any
    }): IFieldItem {
      const { schema, value, label, scope, title, info } = payload

      // Determine input type
      const type = getInputType(schema)
      // const type = airalogy_built_in_type === "FileId" && getFileType(file_extension) !== "unknown"
      //   ? getFileType(file_extension)
      //   : airalogy_built_in_type
      //     || build_in_rv_type
      //     || rawInputType
      //     || (schemaToInputType[rawType]?.(format) ?? (rawType === "check" ? "boolean" : rawType || "textarea"))

      let controlledValue = value

      if (
        (type === "float" || type === "number" || type === "integer")
        && typeof value !== "object"
      ) {
        const bigNumber = new Big(value)
        controlledValue = { displayedValue: bigNumber.toString(), type, value: bigNumber }
      }

      let disabled = false
      if (info?.link) {
        disabled = info.link.target.prop === label
      }

      return {
        type,
        value: controlledValue,
        disabled,
        required: schema.required || false,
        label,
        scope: scope as any,
        title,
        id: `aimd-${scope}-${label}-table-cell`,
        pattern: schema.pattern,
        raw: schema,
      }
    }

    function createThumbnailUrl(file: File | null): Promise<string> | undefined {
      if (!file)
        return

      const reader = new FileReader()
      reader.readAsDataURL(file)

      return new Promise((resolve) => {
        reader.addEventListener(
          "load",
          () => {
            resolve(reader.result as string)
          },
          { once: true },
        )
      })
    }

    function isVarTable(prop: string) {
      if (!varScopeRecord.value[prop]) {
        return false
      }

      return !!tableRecord.value[prop]
    }

    fieldEventBus.on(
      async (
        event,
        payload: {
          scope: IRecordDataKey
          prop: string
          value?: any
          autoBlur?: boolean
          info?: any
          assigner?: ProtocolModels.Assigner
          dependent?: { name: string, scope: IRecordDataKey }[]
          source?: "preview" | "form"
        },
      ) => {
        if (
          event !== "preview-field-focus"
          && event !== "preview-field-blur"
          && event !== "field-update-complete"
          && event !== "preview-file-change"
          && event !== "preview-file-uploaded"
          && event !== "draft-restored"
          && event !== "preview-file-renamed"
          && event !== "file-assigned"
          && event !== "start-assigner-request"
          && event !== "end-assigner-request"
          && event !== "error-assigner-request"
          && event !== "field-tag-focus"
        ) {
          return
        }

        const { scope, prop, value, autoBlur = false, info, source } = payload
        const isTable = Boolean(payload.info) && payload.info.group === props.propInfo

        if (!isTable && (scope !== props.scope || prop !== props.propInfo)) {
          return
        }

        const path
          = scope === "research_check" || scope === "research_step"
            ? `${scope}_${prop}-${info?.type || "check"}`
            : isTable
              ? `research_variable_${prop}`
              : `${scope}_${prop}`

        const inputInst = itemRef[path]?.value
        const inputWrapperEl = isTable || !inputInst ? null : (inputInst.$el as HTMLElement | null)

        if (event === "preview-field-focus" || event === "field-tag-focus") {
          if (inputWrapperEl && shouldScroll.value) {
            inputWrapperEl.scrollIntoView({ block: "center", behavior: "smooth" })
            if (event === "field-tag-focus" && source) {
              if (expandedNamesRef.value.findIndex(it => it === `${scope}-${prop}`) === -1) {
                expandedNamesRef.value.push(`${scope}-${prop}`)
              }

              return
            }

            inputWrapperEl.classList.add("aimd-field--focus")
            if (autoBlur) {
              setTimeout(() => {
                inputWrapperEl.classList.remove("aimd-field--focus")
              }, 500)
            }
          }
          return
        }

        if (event === "preview-field-blur") {
          if (inputWrapperEl) {
            inputWrapperEl.classList.remove("aimd-field--focus")
          }
          return
        }

        if (event === "field-update-complete") {
          const formItem = isTable
            ? formItemRef[`research_variable_${payload.info.group}`]
            : formItemRef[`${scope}_${prop}`]
          if (formItem) {
            try {
              const result = await formItem.value?.validate?.()
              if (result?.warnings) {
                message.warning(result.warnings.map(m => m.message).join("\n"))
              }
              // If validation passed with no warnings, restore validation state
              else {
                formItem.value?.restoreValidation?.()
              }
            }
            catch (e) {
              // Validation failed, error state should remain
              if (e) {
                console.error("Validation error:", e)
              }
            }
          }
          return
        }

        /** Handle File */
        if (event === "preview-file-change") {
          if (inputWrapperEl && shouldScroll.value) {
            inputWrapperEl.scrollIntoView({ block: "center", behavior: "smooth" })
            inputWrapperEl.classList.add("aimd-field--focus")
            setTimeout(() => {
              inputWrapperEl.classList.remove("aimd-field--focus")
            }, 2000)
          }

          const {
            file: { fileList },
            type,
          } = value as {
            file: {
              file: UploadFileInfo
              fileList: UploadFileInfo[]
              event?: Event | undefined
            }
            type: "add" | "remove" | "rename"
          }

          if (info?.group) {
            const cellKey = `${info.group}_${info.row}_${info.col}_${prop}`
            imageFileListRecord.value[cellKey] = fileList
          }
          else {
            imageFileList.value = fileList
          }

          if (type === "remove") {
            emit("field:change", {
              scope,
              prop,
              value: null,
              shouldUpdate: true,
              shouldAssign: true,
              info,
            })
          }
          else if (type === "add") {
            // Also sync fileList to main fieldModel when adding files
            // This ensures validation can access the file value before upload completes
            emit("field:change", {
              scope,
              prop,
              value: fileList,
              shouldUpdate: true,
              shouldAssign: false, // Don't trigger assigner until upload completes
              info,
            })
          }
          // Emit field-update-complete after file change
          fieldEventBus.emit("field-update-complete", payload)
        }

        if (event === "draft-restored") {
          // When draft is restored, trigger field re-processing
          // This will handle files and other data types through the normal field processing pipeline
          // const { data, mode } = value as { data: any, mode: "merge" | "replace" }
          // console.debug(`Draft ${mode} completed, triggering field updates`)

          // Emit field-update-complete to trigger validation and UI updates
          fieldEventBus.emit("field-update-complete", payload)
          return
        }

        if (event === "preview-file-uploaded") {
          const { assigner, dependent } = payload
          emit("field:change", { scope, prop, value, assigner, dependent, info })
          // Emit field-update-complete after file upload
          fieldEventBus.emit("field-update-complete", payload)
          return
        }

        if (event === "preview-file-renamed") {
          emit("field:change", {
            scope,
            prop,
            value: { ...value, type: "image" },
            shouldUpdate: true,
            shouldAssign: false,
            info,
          })
          return
        }

        /** Handle assigner */
        if (event === "file-assigned") {
          if (info?.group) {
            const cellKey = `${info.group}_${info.row}_${info.col}_${prop}`
            imageFileListRecord.value[cellKey] = value
          }
          else {
            imageFileList.value = [value]
          }
          emit("field:change", {
            scope,
            prop,
            value,
            shouldUpdate: true,
            shouldAssign: false,
            info,
          })
        }
      },
    )

    // Add event listener for table link assignments
    fieldEventBus.on((event, payload: IFieldChangePayload) => {
      const { scope, value, info } = payload

      const notTable = !info || info.group !== props.propInfo
      if (notTable)
        return

      /** Handle var_table */
      if (event === "assign-table-link") {
        const targetInfo = props.item
        const { target } = info.link
        if (target.name !== targetInfo.label)
          return

        const { row } = info

        emit("field:change", {
          scope,
          prop: target.prop,
          value,
          info: { ...toRaw(targetInfo.raw), group: target.name, row },
        })
      }
    })

    return {
      handleFieldChange,
      handleScrollField,
      handleInputBlur,
      handleRef,
      handleFormItemRef,
      handleAddVarTableRow,
      handleFileChange,
      handlePreviewFile,
      handleAssignerClick,
      formItemValidate,
      assignerLoadingRecord,
      assignerErrorRecord,
      imageFileList,
      previewFileRecord,
      itemRef,
      formItemRef,
      handleCheckedChange,
      handleUploadFile,
      createTableCellModel,
      createThumbnailUrl,
      typeMap,
      protocolId,
      varScopeRecord,
      tableRecord: tableRecord as Ref<
        Record<
          string,
          Record<
            string,
            Record<"title" | "type" | "description" | "format", string> & { sequence: number, assigner?: ProtocolModels.Assigner }
          >
        >
      >,
      readonly,
      expandedNamesRef,
      getTableCellFile,
      imageFileListRecord,
      isVarTable,
    }
  },
)

export { useProtocolFormInject, useProtocolFormProvide }
