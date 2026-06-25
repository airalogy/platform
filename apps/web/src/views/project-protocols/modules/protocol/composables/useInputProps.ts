import type { JsonSchema } from "@/components/custom/aimd/types/aimd-types"
import type { IProps as ICustomCheckboxProps } from "@/components/custom/custom-checkbox.vue"
import type { IProps as ICustomInputNumberProps } from "@/components/custom/custom-input-number/custom-input-number.vue"
import type { TimePickerProps } from "@/components/custom/custom-time-picker/types"
import type { CheckboxProps, DatePickerProps, DynamicInputProps, InputProps } from "naive-ui"
import type { DatePickerType } from "naive-ui/es/date-picker/src/config"
import type { FormValidationStatus } from "naive-ui/es/form/src/interface"
import type { InputPropsOptions } from "../types/input-props"
import { getFirstTypeFromAnyOf, getSchemasFromAnyOf } from "@/components/custom/aimd/composables/useAIMDHelpers"
import { BuiltInType } from "@airalogy/shared/enum/airalogy"
import dayjs from "dayjs"
import { computed, ref } from "vue"
import { createCommonThemeOverrides, themeOverridesRecord } from "./themeOverrides"
import { useProtocolFormInject } from "./useProtocolForm"

export function useAnyOfSchemas(props: InputPropsOptions) {
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

    return getFirstTypeFromAnyOf(anyOfSchemas.value) || props.model.type
  })

  return {
    selectedSchema,
    anyOfSchemas,
    effectiveType,
  }
}

export function useInputProps(props: InputPropsOptions) {
  const injectContext = useProtocolFormInject()
  if (!injectContext) {
    throw new Error("useInputHandlers must be used within useProtocolFormProvide")
  }

  const { handleRef, handleScrollField, handleFieldChange, handleInputBlur, handleCheckedChange, assignerLoadingRecord, assignerErrorRecord } = injectContext

  const { model, info, inputId, scope, prop, assigner, dependent, readonly: readonlyProp, placeholder, themeOverrides, type, ajvInfo } = toRefs(props)

  const { selectedSchema, anyOfSchemas, effectiveType } = useAnyOfSchemas(props)

  const commonProps = computed(() => ({
    id: inputId.value,
    ref: (el: any) => handleRef(`${scope.value}_${prop.value}`, el),
    loading: !!assignerLoadingRecord.value[prop.value],
    onFocus: (e: FocusEvent) => handleScrollField(e, scope.value, prop.value, model.value.label),
    onBlur: (e: FocusEvent) => handleInputBlur(e, scope.value, prop.value),
    disabled: readonlyProp?.value || Boolean(model.value.value?.disabled) || Boolean(model.value?.disabled),
    placeholder: placeholder?.value,
    themeOverrides: createCommonThemeOverrides(model.value.type),
    status: assignerErrorRecord.value[prop.value] ? "error" as FormValidationStatus : undefined,
    onSchemaChange: handleSchemaChange,
  }))

  const checkboxProps = computed((): CheckboxProps => ({
    ...commonProps.value,
    "checkedValue": true,
    "uncheckedValue": false,
    "checked": Boolean(model.value.value?.checked),
    "onUpdate:checked": (val: boolean) => handleCheckedChange(model.value.value.raw || {}, scope.value, prop.value, val),
    "themeOverrides": (typeof model.value.value?.checked === "boolean" ? model.value.value.checked ? themeOverridesRecord.checkbox.checked : themeOverridesRecord.checkbox.unchecked : themeOverridesRecord.checkbox.init),
  }))

  const customCheckboxProps = computed((): ICustomCheckboxProps => ({
    ...checkboxProps.value,
    "onUpdate:checked": (value: boolean) => handleCheckedChange(model.value, scope.value, prop.value, value),
    "hasValue": typeof model.value.value?.checked === "boolean",
    "scope": scope.value,
    "themeOverrides": checkboxProps.value.themeOverrides as ICustomCheckboxProps["themeOverrides"],
    "onFocus": (e: FocusEvent) => handleScrollField(e, scope.value, prop.value, model.value.label, { type: "check" }),
    "onBlur": (e: FocusEvent) => handleInputBlur(e, scope.value, prop.value, { type: "check" }),
    "size": "large",
    // @ts-expect-error handle ref
    "ref": (el: any) => handleRef(`${scope.value}_${prop.value}-check`, el, true),
  }))

  const inputProps = computed((): InputProps => {
    // Pattern validation is handled by n-form-item's rule prop
    // to ensure consistent validation behavior across all form items
    return {
      ...commonProps.value,
      "value": model.value.value,
      "onUpdate:value": (value: string) => handleFieldChange({
        scope: scope.value,
        prop: prop.value,
        value,
        info: info?.value,
        assigner: assigner?.value,
        dependent: dependent?.value,
      }),
    }
  })

  const annotationInputProps = computed((): InputProps => ({
    ...commonProps.value,
    "resizable": true,
    "autosize": true,
    "value": model.value?.value?.annotation,
    "placeholder": model.value?.title,
    "type": "textarea",
    // @ts-expect-error handle ref
    "ref": (el: any) => handleRef(`${scope.value}_${prop.value}-annotation`, el),
    "onFocus": (e: FocusEvent) => handleScrollField(e, scope.value, prop.value, model.value.label, { type: "annotation" }),
    "onBlur": (e: FocusEvent) => handleInputBlur(e, scope.value, prop.value, { type: "annotation" }),
    "onUpdate:value": value => handleFieldChange({ scope: scope.value, prop: prop.value, value: { ...model.value.value, annotation: value }, assigner: assigner?.value, dependent: dependent?.value, info: info?.value }),
  }))

  const numberProps = computed((): ICustomInputNumberProps => ({
    ...commonProps.value,
    "displayedValue": model.value?.value?.displayedValue,
    "precision": 100,
    "inputProps": { size: 5 },
    "value": model.value?.value?.value,
    "type": model.value?.type as "number" | "integer" | "float" | undefined,
    "onUpdate:value": value => handleFieldChange({ scope: scope.value, prop: prop.value, value: value === null ? undefined : value, assigner: assigner?.value, dependent: dependent?.value, info: info?.value }),
    "onInvalidInput": value => handleFieldChange({ scope: scope.value, prop: prop.value, value: { displayedValue: value }, assigner: assigner?.value, dependent: dependent?.value, info: info?.value }),
  }))

  const datePickerProps = computed((): DatePickerProps => {
    const { value } = toValue(model)
    const currentType = effectiveType.value

    return {
      ...commonProps.value,
      "themeOverrides": createCommonThemeOverrides(currentType, "form") as DatePickerProps["themeOverrides"],
      "formattedValue": value?.formattedValue,
      "type": currentType === BuiltInType.CurrentTime ? "datetime" : (currentType as DatePickerType),
      "onUpdate:value": undefined,
      "value": typeof value !== "object" ? value : value?.value && dayjs(value.value).valueOf(),
      "onUpdate:formattedValue": value => handleFieldChange({
        scope: scope.value,
        prop: prop.value,
        value: value ? { value: dayjs(value).format(currentType === "date" ? "YYYY-MM-DD" : undefined), formattedValue: value } : undefined,
        info: info?.value,
        assigner: assigner?.value,
        dependent: dependent?.value,
      }),
    }
  })

  const timePickerProps = computed((): TimePickerProps => {
    const { value } = toValue(model)
    const currentType = toValue(effectiveType)

    return {
      ...commonProps.value,
      "valueFormat": "HH:mm:ss",
      "format": currentType === "time" ? "timestamp" : "timedelta",
      // "actions": ["confirm"],
      // "onUpdate:value": undefined,
      "value": typeof value === "object" ? value?.value : value,
      // @ts-expect-error event handler
      "onUpdate:value": value => handleFieldChange({
        scope: scope.value,
        prop: prop.value,
        value,
        info: info?.value,
        assigner: assigner?.value,
        dependent: dependent?.value,
      }),
    }
  })

  const dynamicInputProps = computed((): DynamicInputProps => {
    const items = (ajvInfo?.value?.schema as any)?.items
    const properties = items?.properties
    const hasObjectItems = items?.type === "object" && properties

    return {
      ...commonProps.value,
      "themeOverrides": createCommonThemeOverrides(effectiveType.value, "form") as DynamicInputProps["themeOverrides"],
      "placeholder": placeholder?.value,
      "value": Array.isArray(model.value.value) ? model.value.value : [],
      "onUpdate:value": value => handleFieldChange({ scope: scope.value, prop: prop.value, value, assigner: assigner?.value, dependent: dependent?.value, info: info?.value }),
      // Add create function for object arrays to show validation for each field
      ...(hasObjectItems && {
        create: (index: number) => {
          const obj: Record<string, any> = {}
          // Initialize each property with default value
          for (const key in properties) {
            obj[key] = properties[key].default ?? ""
          }
          return obj
        },
        showSortButton: false,
      }),
    }
  })

  function handleSchemaChange(schema: JsonSchema) {
    selectedSchema.value = schema
    // When schema changes, update type and reset value if needed
    if (schema.type && type?.value !== undefined && schema.type !== type.value) {
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
    status,
    commonProps,
    checkboxProps,
    inputProps,
    annotationInputProps,
    numberProps,
    customCheckboxProps,
    datePickerProps,
    timePickerProps,
    dynamicInputProps,
    anyOfSchemas,
    effectiveType,
    handleSchemaChange,
  }
}
