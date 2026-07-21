import type { ExtractedAimdFields } from "@airalogy/aimd-core/types"
import type {
  AimdProtocolRecordData,
  AimdRecorderLocale,
  AimdRecorderValidationResult,
} from "@airalogy/aimd-recorder"
import type { FormItemRule } from "naive-ui"
import type { InjectionKey, MaybeRefOrGetter } from "vue"
import type { IFieldItem } from "../types/types"
import {
  createAimdRecorderMessages,
  validateAimdRecord,
  validateAimdField as validateSharedAimdField,
} from "@airalogy/aimd-recorder"
import { parseAndExtract } from "@airalogy/aimd-renderer"
import { computed, inject, provide, toValue } from "vue"

type PlatformFieldModel = Record<string, any>
type PlatformValidationRules = Record<string, Record<string, { value: FormItemRule }>>

interface UseAimdRecordValidationOptions {
  content: MaybeRefOrGetter<string>
  fieldModel: PlatformFieldModel
  locale?: MaybeRefOrGetter<string | undefined>
  schema?: MaybeRefOrGetter<Record<string, unknown> | undefined>
}

export interface PlatformAimdValidationContext {
  validateField: (fieldKey: string, exact?: boolean) => true | Error
}

export const PLATFORM_AIMD_VALIDATION_KEY = Symbol("platform-aimd-validation") as InjectionKey<PlatformAimdValidationContext>

function getRecorderLocale(locale: string | undefined): AimdRecorderLocale {
  return locale?.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US"
}

function getFieldName(key: string, field: IFieldItem): string {
  return field.originalName || field.label || key
}

function getSectionValues(fields: Record<string, IFieldItem> | undefined): Record<string, unknown> {
  if (!fields) {
    return {}
  }

  return Object.fromEntries(
    Object.entries(fields)
      .filter(([key]) => key !== "__SCOPE__")
      .map(([key, field]) => [getFieldName(key, field), field.value]),
  )
}

function toAimdRecord(fieldModel: PlatformFieldModel): AimdProtocolRecordData {
  return {
    var: getSectionValues(fieldModel.research_variable),
    step: getSectionValues(fieldModel.research_step) as AimdProtocolRecordData["step"],
    check: getSectionValues(fieldModel.research_check) as AimdProtocolRecordData["check"],
    quiz: getSectionValues(fieldModel.research_question),
  }
}

function getValidationFieldKey(
  scope: string,
  name: string,
  tableIds: Set<string>,
): string | undefined {
  if (scope === "research_variable") {
    return tableIds.has(name) ? `var_table:${name}` : `var:${name}`
  }
  if (scope === "research_step") {
    return `step:${name}`
  }
  if (scope === "research_check") {
    return `check:${name}`
  }
  if (scope === "research_question") {
    return `quiz:${name}`
  }
  return undefined
}

function createValidationRules(
  fieldModel: PlatformFieldModel,
  fields: ExtractedAimdFields,
  validateField: PlatformAimdValidationContext["validateField"],
): PlatformValidationRules {
  const rules: PlatformValidationRules = {}
  const tableIds = new Set(fields.var_table.map(field => field.id))

  Object.entries(fieldModel).forEach(([scope, scopeFields]) => {
    if (!scopeFields || typeof scopeFields !== "object") {
      return
    }
    Object.entries(scopeFields).forEach(([key, field]) => {
      if (key === "__SCOPE__" || !field || typeof field !== "object") {
        return
      }

      const validationFieldKey = getValidationFieldKey(scope, getFieldName(key, field as IFieldItem), tableIds)
      if (!validationFieldKey) {
        return
      }

      rules[scope] ??= {}
      rules[scope][key] = {
        value: {
          trigger: ["change", "blur"],
          validator: () => validateField(validationFieldKey, true),
        },
      }
    })
  })

  return rules
}

export function useAimdRecordValidation(options: UseAimdRecordValidationOptions) {
  const fields = computed(() => parseAndExtract(toValue(options.content)))

  function getValidationOptions() {
    return {
      messages: createAimdRecorderMessages(getRecorderLocale(toValue(options.locale))).validation,
      schema: toValue(options.schema),
    }
  }

  function validateRecord(): AimdRecorderValidationResult {
    return validateAimdRecord(fields.value, toAimdRecord(options.fieldModel), getValidationOptions())
  }

  function validateField(fieldKey: string, exact = false): true | Error {
    const result = validateSharedAimdField(
      fields.value,
      toAimdRecord(options.fieldModel),
      fieldKey,
      getValidationOptions(),
    )
    const issue = exact
      ? result.issues.find(candidate => candidate.fieldKey === fieldKey)
      : result.issues[0]
    return issue ? new Error(issue.message) : true
  }

  const context: PlatformAimdValidationContext = { validateField }
  provide(PLATFORM_AIMD_VALIDATION_KEY, context)

  return {
    fields,
    rules: computed(() => createValidationRules(options.fieldModel, fields.value, validateField)),
    validateField,
    validateRecord,
  }
}

export function usePlatformAimdValidation() {
  return inject(PLATFORM_AIMD_VALIDATION_KEY, null)
}
