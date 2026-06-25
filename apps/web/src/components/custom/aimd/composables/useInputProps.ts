import type { IProps as FormUploadFileProps } from "@/components/common/form-upload-file.vue"
import type { IProps as ICustomCheckboxProps } from "@/components/custom/custom-checkbox.vue"
import type { IProps as ICustomInputNumberProps } from "@/components/custom/custom-input-number/custom-input-number.vue"
import type { TimePickerProps } from "@/components/custom/custom-time-picker/types"
import type { DatePickerType } from "naive-ui/es/date-picker/src/config"
import type { FormValidationStatus } from "naive-ui/es/form/src/interface"
import type { JsonSchema } from "../types/aimd-types"
import type { IAIMDInputProps } from "../types/props"
import CustomInputNumber from "@/components/custom/custom-input-number/custom-input-number.vue"
import { getUploadProps } from "@/utils/fileType"
import { BuiltInType } from "@airalogy/shared/enum/airalogy"
import dayjs from "dayjs"
import { type CheckboxProps, type DatePickerProps, type InputProps, NInput, type SelectProps as NSelectProps, NTooltip, type UploadSettledFileInfo } from "naive-ui"
import { computed, ref, watch } from "vue"
import CustomRecordIdInput from "../../custom-record-id-input.vue"
import { themeOverridesRecord } from "./themeOverrides"
import { getFirstTypeFromAnyOf, getSchemasFromAnyOf, useAIMDInject } from "./useAIMDHelpers"

export function useAnyOfSchemas(props: IAIMDInputProps) {
  // Add support for anyOf schema
  const selectedSchema = ref<JsonSchema | null>(null)
  const rawAnyOfSchemas = computed(() => getSchemasFromAnyOf(props.info?.anyOf))

  // Filter out anyOf schemas if they are all FileId types
  // This prevents showing type selector for file uploads
  const anyOfSchemas = computed(() => {
    const schemas = rawAnyOfSchemas.value
    if (schemas.length === 0)
      return schemas

    // Check if all schemas are FileId types
    const allFileId = schemas.every(schema =>
      schema.airalogy_type === "FileId" || schema.airalogy_built_in_type === "FileId",
    )

    // If all are FileId, don't show the selector
    return allFileId ? [] : schemas
  })

  // Use selected schema's type if available, otherwise use props.type
  const effectiveType = computed(() => {
    if (selectedSchema.value && selectedSchema.value.type) {
      return selectedSchema.value.type
    }

    return getFirstTypeFromAnyOf(anyOfSchemas.value) || props.type
  })

  return {
    selectedSchema,
    anyOfSchemas,
    effectiveType,
  }
}

export function useInputProps(props: IAIMDInputProps) {
  const injectContext = useAIMDInject()!
  if (!injectContext) {
    throw new Error("useInputProps must be used within useAIMDProvide")
  }

  const { handleRef, handleFieldChange, handleInputBlur, handleCheckedChange, protocolId, handlePreviewFile, handleScrollField, assignerErrorRecord, assignerLoadingRecord } = injectContext
  const { type, model, id, scope, prop, info, assigner, dependent, placeholder, disabled, themeOverrides, enumInfo } = toRefs(props)

  const { selectedSchema, anyOfSchemas, effectiveType } = useAnyOfSchemas(props)

  const assignerErrorKey = computed(() => {
    const { group, row } = info?.value || {}
    return group !== undefined && row !== undefined
      ? `${group}.${prop.value}[${row}]`
      : prop.value
  })

  const status = computed((): FormValidationStatus | undefined => assignerErrorRecord.value[assignerErrorKey.value] ? "error" : undefined)

  // Check if this is a reference field (used for ref_var)
  const isReferenceField = computed(() => props.isReference === true)

  // Use a different ref key for reference fields to avoid conflicts
  const refKey = computed(() => {
    if (isReferenceField.value) {
      return `ref-var_${scope.value}_${prop.value}`
    }
    return `${scope.value}_${prop.value}`
  })

  // Local text value buffer to prevent character swallowing during fast typing
  // The input is bound to this local ref, and we sync to store on blur or after typing stops
  const localTextValue = ref<string | undefined>(
    typeof model.value?.value === "string" ? model.value.value : undefined,
  )

  // Track if user is actively typing (to prevent external updates from interrupting)
  const isTyping = ref(false)
  let typingTimeout: ReturnType<typeof setTimeout> | null = null

  // Watch for external changes to model.value and sync to local value
  // Only sync when user is NOT actively typing (to prevent overwriting user input)
  watch(
    () => model.value?.value,
    (newVal) => {
      if (!isTyping.value) {
        localTextValue.value = typeof newVal === "string" ? newVal : undefined
      }
    },
    { immediate: true },
  )

  // Track checkbox checked state with a local ref for better reactivity
  const localCheckedState = ref<boolean | null | undefined>(model.value?.value?.checked)

  // Watch for changes in the model's checked value and update local state
  watch(
    () => model.value?.value?.checked,
    (newVal) => {
      localCheckedState.value = newVal
    },
    { immediate: true },
  )

  const commonProps = computed(() => ({
    "id": id.value,
    "ref": (el: any) => handleRef(refKey.value, el, effectiveType.value, info.value),
    // Allow editing for all fields including assigner fields
    "disabled": disabled?.value,
    "placeholder": placeholder?.value,
    "themeOverrides": themeOverrides?.value,
    "scope": scope.value,
    "onBlur": (e: any) => {
      // Reference fields don't need to trigger blur events
      if (!isReferenceField.value) {
        handleInputBlur(e, scope.value, prop.value)
      }
    },
    "onFocus": () => {
      // Reference fields don't need to trigger scroll events
      if (!isReferenceField.value) {
        handleScrollField(null, scope.value, prop.value)
      }
    },
    "value": model.value.value,
    "onUpdate:value": (value: any) => {
      // Reference fields don't allow updates (they're disabled anyway)
      if (!isReferenceField.value) {
        handleFieldChange({ scope: scope.value, prop: prop.value, value, assigner: assigner?.value, dependent: dependent?.value, info: info.value })
      }
    },
    "status": status.value,
    "loading": assignerLoadingRecord.value[prop.value],
    "onSchemaChange": handleSchemaChange,
  }))

  const inputProps = computed((): InputProps & { id: string } => {
    const baseProps = {
      ...commonProps.value,
      "id": `${id.value}-input`,
      "autosize": true,
      "type": "textarea" as const,
      // Use local text value buffer to prevent character swallowing during fast typing
      "value": localTextValue.value,
      "onUpdate:value": (value: any) => {
        // Update local value immediately for responsive UI
        localTextValue.value = value
        // Mark as typing to prevent external updates from interrupting
        isTyping.value = true
        // Clear previous timeout
        if (typingTimeout) {
          clearTimeout(typingTimeout)
        }
        // Reset typing flag after a short delay (when user stops typing)
        typingTimeout = setTimeout(() => {
          isTyping.value = false
          // Sync to store after typing stops
          if (!isReferenceField.value) {
            handleFieldChange({ scope: scope.value, prop: prop.value, value, assigner: assigner?.value, dependent: dependent?.value, info: info.value })
          }
        }, 300)
      },
      "onBlur": (e: any) => {
        // Clear typing state on blur
        isTyping.value = false
        if (typingTimeout) {
          clearTimeout(typingTimeout)
          typingTimeout = null
        }
        // Sync final value to store on blur
        if (!isReferenceField.value) {
          handleFieldChange({ scope: scope.value, prop: prop.value, value: localTextValue.value, assigner: assigner?.value, dependent: dependent?.value, info: info.value })
          handleInputBlur(e, scope.value, prop.value)
        }
      },
    }

    // Pattern validation is handled by n-form-item's rule prop (cellRule in aimd-item.vue)
    // to ensure consistent validation behavior across all form items
    return baseProps
  })

  const annotationInputProps = computed((): InputProps & { id: string } => ({
    ...inputProps.value,
    id: `${id.value}-annotation`,
    defaultValue: model.value.value.annotation,
    value: model.value.value.annotation,
    // @ts-expect-error handle ref
    ref: (el: any) => handleRef(`${scope.value}_${prop.value}-annotation`, el, effectiveType.value, info.value),
    onBlur: (e: any) => handleInputBlur(e, scope.value, prop.value, { type: "annotation" }),
    onFocus: () => handleScrollField(null, scope.value, prop.value, model.value.label, { type: "annotation" }),
  }))

  const enumProps = computed(() => {
    const enumValues = Array.isArray(enumInfo?.value) ? enumInfo?.value : enumInfo?.value?.enum
    if (!enumValues) {
      return null
    }

    return {
      ...commonProps.value,
      consistentMenuWidth: false,
      class: "enum-select-input",
      themeOverrides: { ...themeOverridesRecord.select, peers: { InternalSelection: { ...themeOverridesRecord.select.peers.InternalSelection, borderRadius: "0 0 6px 6px" } } },
      options: enumValues.map((it: string) => ({ label: it, value: it })),
      renderOption: ({ node, option }: { node: any, option: any }) => h(NTooltip, { contentClass: "w-fit !whitespace-nowrap" }, {
        trigger: () => node,
        default: () => option.label,
      }),
    }
  })

  const checkboxProps = computed((): CheckboxProps & { id: string } => ({
    ...commonProps.value,
    "id": `${id.value}-check`,
    "checkedValue": true,
    "uncheckedValue": false,
    "checked": Boolean(localCheckedState.value),
    // @ts-expect-error onUpdate:value not exist in type
    "onUpdate:value": undefined,
    "onUpdate:checked": (val: boolean) => {
      localCheckedState.value = val
      handleCheckedChange(info.value || {}, scope.value, prop.value, val)
    },
    "themeOverrides": (typeof localCheckedState.value === "boolean" ? localCheckedState.value ? themeOverridesRecord.checkbox.checked : themeOverridesRecord.checkbox.unchecked : themeOverridesRecord.checkbox.init),
  }))

  const customCheckboxProps = computed((): ICustomCheckboxProps & { id: string } => ({
    ...checkboxProps.value,
    "id": `${id.value}-custom-check`,
    "value": undefined,
    "hasValue": typeof localCheckedState.value === "boolean",
    "checked": localCheckedState.value ?? undefined,
    "size": "large",
    "scope": scope.value,
    "onUpdate:checked": (val: boolean) => {
      localCheckedState.value = val
      handleCheckedChange(info.value || {}, scope.value, prop.value, val)
    },
    "showLabel": true,
    // @ts-expect-error ref is a custom prop handled by the component
    "ref": (el: any) => handleRef(`${scope.value}_${prop.value}-check`, el, effectiveType.value, info.value, true),
  }))

  const numberProps = computed((): ICustomInputNumberProps & { id: string } => ({
    ...commonProps.value,
    "id": `${id.value}-number`,
    "displayedValue": model.value?.value?.displayedValue,
    "precision": 100,
    "inputProps": { size: 5 },
    "value": model.value?.value?.value,
    "type": model.value?.type as "number" | "integer" | "float" | undefined,
    "onUpdate:value": value => handleFieldChange({ scope: scope.value, prop: prop.value, value: value === null ? undefined : value, assigner: assigner?.value, dependent: dependent?.value, info: info.value }),
    "onInvalidInput": value => handleFieldChange({ scope: scope.value, prop: prop.value, value: { displayedValue: value }, assigner: assigner?.value, dependent: dependent?.value, info: info.value }),
  }))

  const uploadProps = computed((): FormUploadFileProps & { style: Record<string, string>, id: string, protocolId?: string } => {
    // Compute fileList: handle various value formats
    // - array of file objects: use directly
    // - single file object: wrap in array
    // - string (airalogy_file_id): skip, let watchEffect in file-input.vue handle loading
    let fileList: any[] = []
    const value = model.value.value

    if (Array.isArray(value)) {
      // Filter out string values (airalogy_file_id) from the array
      fileList = value.filter(item => typeof item === "object" && item !== null)
    }
    else if (typeof value === "object" && value !== null) {
      // Single file object
      fileList = [value]
    }
    // If value is a string (airalogy_file_id), fileList remains empty
    // The file-input.vue watchEffect will detect this and load the file info

    return {
      ...commonProps.value,
      disabled: false, // Allow editing for all fields including assigner
      id: `${id.value}-upload`,
      fileList,
      // endpoint: `/researches/${researchId.value}/upload`,
      endpoint: "/airalogy_files",
      protocolId: protocolId.value,
      max: 1,
      uploadProps: getUploadProps(effectiveType.value, undefined, props.ajvInfo?.schema?.file_extension),
      fileType: effectiveType.value as any, // Pass fileType to ensure consistent rendering
      type: assigner?.value ? "assigner" : dependent?.value ? "dependent" : "field",
      style: { minWidth: Array.isArray(model.value) ? `${model.value.length * 96}px` : "100%" },
      showPreview: effectiveType.value !== "image",
      onPreview: effectiveType.value === "image" ? undefined : (info: UploadSettledFileInfo) => handlePreviewFile(id.value, info),
      // @ts-expect-error showDownloadButton is a custom prop for FormUploadFile component
      showDownloadButton: true,
      showRemoveButton: true,
    }
  })

  const datePickerProps = computed((): DatePickerProps & { id: string } => {
    const { value } = toValue(model)

    /*
    [date](https://docs.pydantic.dev/2.1/usage/types/datetime/)
    date fields will accept values of type:

      date; an existing date object

      int or float; handled the same as described for datetime above
      str; the following formats are accepted:

      YYYY-MM-DD
      int or float as a string (assumed as Unix time)
    */
    return {
      ...commonProps.value,
      "id": `${id.value}-date`,
      "formattedValue": value?.formattedValue,
      "type": effectiveType.value === BuiltInType.CurrentTime ? "datetime" : (effectiveType.value as DatePickerType),
      "onUpdate:value": undefined,
      "value": typeof value === "object" ? value?.value && dayjs(value.value).valueOf() : value,
      "onUpdate:formattedValue": value => handleFieldChange({
        scope: scope.value,
        prop: prop.value,
        value: value ? { value: dayjs(value).format(effectiveType.value === "date" ? "YYYY-MM-DD" : undefined), formattedValue: value } : undefined,
        info: info.value,
        assigner: assigner?.value,
        dependent: dependent?.value,
      }),
    }
  })

  const timePickerProps = computed((): TimePickerProps & { id: string } => {
    const { value } = toValue(model)

    return {
      ...commonProps.value,
      themeOverrides: themeOverridesRecord.timePicker,
      id: `${id.value}-time`,
      // "formattedValue": type.value === "duration" ? parseISODuration(model.value.value)?.formatted : model.value.value,
      valueFormat: "HH:mm:ss",
      // "actions": ["confirm"],
      value: typeof value === "object" ? value?.value : value,
      format: effectiveType.value === "duration" ? "timedelta" : "timestamp",
    }
  })

  const dynamicInputProps = computed((): {
    placeholder?: string
    addButtonText?: string
    value?: string[]
    inputComponent?: Component
    themeOverrides?: any
  } => {
    const schemaType = selectedSchema.value?.type || props.ajvInfo?.schema?.items?.type
    const isRecordId
    = (
      selectedSchema.value?.airalogy_built_in_type === BuiltInType.RecordId
      || props.ajvInfo?.schema?.items?.airalogy_built_in_type === BuiltInType.RecordId) || (
      selectedSchema.value?.airalogy_type === BuiltInType.RecordId
      || props.ajvInfo?.schema?.items?.airalogy_type === BuiltInType.RecordId
    )

    let inputComponent: Component | undefined

    if (isRecordId) {
      inputComponent = CustomRecordIdInput
    }
    else if (schemaType === "string") {
      inputComponent = NInput
    }
    else if (schemaType === "number") {
      inputComponent = CustomInputNumber
    }

    return {
      ...commonProps.value,
      inputComponent,
      themeOverrides: themeOverridesRecord.dynamicInput,
    }
  })

  const booleanSelectProps = computed((): NSelectProps & { id: string } => {
    // Convert boolean value to string for NSelect compatibility
    const currentValue = model.value.value
    const stringValue = currentValue === true ? "true" : currentValue === false ? "false" : currentValue

    return {
      ...commonProps.value,
      "value": stringValue,
      "options": [{ label: "True", value: "true" }, { label: "False", value: "false" }],
      "onUpdate:value": (value: string) => {
        // Convert string back to boolean
        const boolValue = value === "true" ? true : value === "false" ? false : value
        handleFieldChange({
          scope: scope.value,
          prop: prop.value,
          value: boolValue,
          assigner: assigner?.value,
          dependent: dependent?.value,
          info: info.value,
        })
      },
    }
  })

  function handleSchemaChange(schema: JsonSchema) {
    selectedSchema.value = schema
    // When schema changes, update type and reset value if needed
    if (schema.type && schema.type !== type.value) {
      // Reset the model value if the type changes dramatically
      handleFieldChange({
        ...props,
        value: undefined,
        type: schema.type,
      })
    }
  }
  return {
    ...injectContext,
    anyOfSchemas,
    baseInputProps: inputProps,
    customCheckboxProps,
    enumProps,
    uploadProps,
    checkboxProps,
    numberProps,
    inputProps,
    annotationInputProps,
    datePickerProps,
    timePickerProps,
    dynamicInputProps,
    booleanSelectProps,
    handleSchemaChange,
    effectiveType,
  }
}
