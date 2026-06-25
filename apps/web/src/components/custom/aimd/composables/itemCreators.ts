import type { FieldKey, ScopeFieldKey } from "@airalogy/aimd-core/types"
import type { InputProps } from "naive-ui"
import type { IAIMDItemProps } from "../types/aimd-types"
import { getRefValue, scopeKeyRecord } from "@airalogy/shared/utils"
import { commonOverrides, createCommonThemeOverrides, themeOverridesRecord } from "./themeOverrides"

export function createResultItem(props: Partial<IAIMDItemProps>): IAIMDItemProps {
  return {
    disabled: false,
    id: "",
    scope: "research_variable",
    prop: "",
    fieldType: "",
    placeholder: undefined,
    model: { value: null },
    // to: "",
    type: "",
    tooltip: "",
    info: {},
    required: false,
    themeOverrides: undefined,
    ...props,
  }
}

export function createResearchStepItems(
  item: any,
  scopeName: ScopeFieldKey,
  to: string,
  fieldModel: any,
): IAIMDItemProps[] {
  const items: IAIMDItemProps[] = []
  const {
    disabled,
    label,
    required,
    scope,
    title,
    description,
    raw,
    assigner,
    dependent,
    typed,
    link,
  } = item
  const info = {
    ...typed?.[scopeName]?.[label],
    ...raw,
    link,
  }

  if (raw?.check) {
    items.push(
      createResultItem({
        disabled,
        id: `aimd-${to}-check`,
        scope,
        prop: label,
        fieldType: scopeKeyRecord[scopeName],
        placeholder: description || title || "",
        model: fieldModel[scopeName][label],
        // to: `#${to}-check`,
        type: "rs-check",
        tooltip: description || title || "",
        info,
        required,
        assigner,
        dependent,
        themeOverrides: themeOverridesRecord.checkbox,
      }),
    )
  }

  items.push(
    createResultItem({
      disabled,
      id: `aimd-${to}`,
      scope,
      prop: label,
      fieldType: scopeKeyRecord[scopeName],
      placeholder: `Annotation for step ${raw?.name}`,
      model: fieldModel[scopeName][label],
      // to: `#${to}`,
      type: "rs-annotation",
      tooltip: description || title || "",
      info,
      required,
      assigner,
      dependent,
      themeOverrides: {
        ...themeOverridesRecord.input,
        border: "1px solid rgba(255, 157, 0, 0.6)",
        borderDisabled: "1px solid rgba(255, 157, 0, 0.6)",
        borderFocus: "2px solid rgba(255, 157, 0, 1)",
        borderHover: "2px solid rgba(255, 157, 0, 0.8)",
        boxShadowFocus: "0 0 0 2px rgba(255, 157, 0, 0.6)",
      },
    }),
  )

  return items
}

export function createResearchCheckItems(
  item: any,
  scopeName: ScopeFieldKey,
  to: string,
  fieldModel: any,
): IAIMDItemProps[] {
  const {
    disabled,
    label,
    required,
    scope,
    title,
    description,
    raw,
    assigner,
    dependent,
    typed,
    link,
  } = item
  const info = { ...typed?.[scopeName]?.[label], ...raw, link }

  return [
    createResultItem({
      disabled,
      id: `aimd-${to}`,
      scope,
      prop: label,
      fieldType: scopeKeyRecord[scopeName],
      placeholder: title || "",
      model: fieldModel[scopeName][label],
      // to: `#${to}-check`,
      type: "rc-check",
      tooltip: description || title || "",
      info,
      required,
      assigner,
      dependent,
      themeOverrides: themeOverridesRecord.checkbox,
    }),
    createResultItem({
      disabled,
      id: `aimd-${to}-annotation`,
      scope,
      prop: label,
      fieldType: scopeKeyRecord[scopeName],
      placeholder: `Annotation for check ${raw?.name}`,
      model: fieldModel[scopeName][label],
      // to: `#${to}-annotation`,
      type: "rc-annotation",
      tooltip: description || title || "",
      info: { ...raw },
      required,
      assigner,
      dependent,
      themeOverrides: {
        ...themeOverridesRecord.input,
        border: "1px solid rgba(24, 160, 88, 0.6)",
        borderFocus: "2px solid rgba(24, 160, 88, 1)",
        borderHover: "2px solid rgba(24, 160, 88, 0.8)",
        boxShadowFocus: "0 0 0 2px rgba(24, 160, 88, 0.6)",
      },
    }),
  ]
}

export function createDefaultItem(
  item: any,
  scopeName: ScopeFieldKey,
  to: string,
  fieldModel: any,
  rules: any,
): IAIMDItemProps {
  const {
    disabled,
    label,
    required,
    scope,
    title,
    type,
    description,
    assigner,
    dependent,
    value: val,
    fieldType,
    typed,
    raw,
    link,
  } = item
  const ajvInfo = rules?.[scope as FieldKey]?.[label]?.ajv
  const enumPath = ajvInfo?.schema
    ? (ajvInfo.schema as any)?.allOf?.[0]?.$ref || (ajvInfo.schema as any)?.$ref
    : undefined
  const enumInfo = ajvInfo?.schema ? (ajvInfo.schema as any).enum ? ajvInfo.schema : getRefValue(ajvInfo.schema, enumPath) : undefined
  const info = { ...typed?.[scopeName]?.[label], ...raw, link }

  let themeOverrides: InputProps["themeOverrides"] | Record<string, any>

  if (enumPath || ((type === "boolean" || type === "enum") && scope === "research_variable")) {
    themeOverrides = {
      peers: {
        InternalSelection: {
          ...commonOverrides,
          paddingSingle: "6px 10px",
          borderRadius: "0 0 6px 6px",
        },
      },
    }
  }
  else {
    themeOverrides = createCommonThemeOverrides(type)

    if (scope === "research_variable") {
      if (type === "checkbox") {
        themeOverrides = themeOverridesRecord.checkbox
      }
      else if (themeOverrides) {
        if (themeOverrides === themeOverridesRecord.input) {
          themeOverrides = { ...themeOverrides, borderRadius: "0 0 6px 6px" }
        }
        else if (type !== "image") {
          themeOverrides = {
            ...themeOverrides,
            peers: {
              ...themeOverrides.peers,
              Input: { ...themeOverrides.peers.Input, borderRadius: "0 0 6px 6px" },
            },
          }
        }
      }
    }
  }

  if (val !== null && typeof val === "object" && Boolean(val.rrec_airalogy_id)) {
    return {
      disabled: true,
      id: `aimd-${to}`,
      scope,
      prop: label,
      fieldType,
      placeholder: title || "",
      model: fieldModel[scopeName][label],
      // to: `#${to}`,
      type: "text",
      tooltip: description || title || "",
      info,
      required,
      themeOverrides: commonOverrides,
      assigner,
      dependent,
      ajvInfo,
      enumInfo,
    }
  }

  return createResultItem({
    disabled: assigner?.mode === "auto_force" ? true : disabled,
    id: `aimd-${to}`,
    scope,
    prop: label,
    fieldType: scopeKeyRecord[scopeName],
    placeholder: title || undefined,
    model: fieldModel[scopeName][label],
    // to: `#${to}`,
    type,
    tooltip: description || title || "",
    info,
    required,
    themeOverrides,
    assigner,
    dependent,
    ajvInfo,
    enumInfo,
  })
}
