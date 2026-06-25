import type { AxiosError } from "axios"
import type { FormInst, FormItemRule } from "naive-ui"
import type { FormItemRuleAsyncValidator, FormItemRuleValidator, FormValidate } from "naive-ui/es/form/src/interface"
import type { MaybeRefOrGetter } from "vue"
import { useAppStore } from "@/store/modules/app"
import { REG_CODE_SIX, REG_EMAIL, REG_PHONE, REG_PWD, REG_USER_NAME } from "@airalogy/shared/constants/reg"
import { $t } from "@airalogy/shared/locales"
import { formatPydanticErrors, type PydanticError } from "@airalogy/shared/utils/errorFormatter.js"
import { ref, toValue, watch } from "vue"
import { checkUsernameDuplicate } from "../service/api/users"

const debouncedCheckUsernameDuplicate = useDebounceFn(checkUsernameDuplicate, 500)

function normalizeFormStringValue(value: unknown): string {
  if (typeof value === "string") {
    return value
  }
  return String(value ?? "")
}

export function createRequiredRule(message: string): App.Global.FormRule {
  return {
    required: true,
    message,
  }
}

export function useFormRules() {
  const appStore = useAppStore()

  const userPatternRules = {
    username: {
      pattern: REG_USER_NAME,
      message: $t("form.username.invalid"),
      trigger: ["change", "blur"],
    },
    phone: {
      pattern: REG_PHONE,
      message: $t("form.phone.invalid"),
      trigger: ["change", "blur"],
    },
    pwd: {
      pattern: REG_PWD,
      message: $t("form.pwd.invalid"),
      trigger: ["change", "blur"],
    },
    code: {
      pattern: REG_CODE_SIX,
      message: $t("form.code.invalid"),
      trigger: ["change", "blur"],
    },
    email: {
      pattern: REG_EMAIL,
      message: $t("form.email.invalid"),
      trigger: ["change", "blur"],
    },
  } satisfies Record<string, App.Global.FormRule>

  const usernameRequiredRule = createRequiredRule($t("form.username.required"))
  const usernameLengthRule = {
    min: 4,
    max: 26,
    message: $t("form.username.length"),
    trigger: ["change", "blur"],
  }
  const usernamePatternRule = {
    pattern: /^[a-z][a-z0-9_]*$/,
    message: $t("form.username.pattern"),
    trigger: ["change", "blur"],
  }
  const usernameStartRule = {
    pattern: /^[a-z]/,
    message: $t("form.username.startLowercase"),
    trigger: ["change", "blur"],
  }
  const usernameHyphenValidator: FormItemRuleValidator = (_rule, value) => {
    const normalizedValue = normalizeFormStringValue(value)
    if (/^[_-]|[_-]$/.test(normalizedValue)) {
      return new Error($t("form.username.hyphenEdges"))
    }
    if (/[_-]{2,}/.test(normalizedValue)) {
      return new Error($t("form.username.hyphenConsecutive"))
    }
    return true
  }
  const usernameHyphenRule: FormItemRule = {
    validator: usernameHyphenValidator,
    trigger: ["change", "blur"],
  }
  const usernameDuplicateValidator: FormItemRuleAsyncValidator = async (_rule, value) => {
    const normalizedValue = normalizeFormStringValue(value)
    if (
      !normalizedValue
      || normalizedValue.length < 4
      || normalizedValue.length > 26
      || !/^[a-z][a-z0-9_]*$/.test(normalizedValue)
      || /^[_-]|[_-]$/.test(normalizedValue)
      || /[_-]{2,}/.test(normalizedValue)
    ) {
      return
    }

    const { duplicated, message } = await debouncedCheckUsernameDuplicate(normalizedValue) || {}
    if (duplicated) {
      throw new Error(message as string)
    }
  }
  const usernameDuplicateRule: FormItemRule = {
    asyncValidator: usernameDuplicateValidator,
    trigger: ["change", "blur"],
    skipIfOtherErrors: true,
  }

  const phoneRequiredRule = createRequiredRule($t("form.phone.required"))
  const pwdRequiredRule = createRequiredRule($t("form.pwd.required"))
  const codeRequiredRule = createRequiredRule($t("form.code.required"))
  const emailRequiredRule = createRequiredRule($t("form.email.required"))

  const userFormRules = {
    username: [
      usernameRequiredRule,
      usernameLengthRule,
      usernamePatternRule,
      usernameStartRule,
      usernameHyphenRule,
      usernameDuplicateRule,
    ],
    phone: [phoneRequiredRule, userPatternRules.phone],
    pwd: [pwdRequiredRule, userPatternRules.pwd],
    code: [codeRequiredRule, userPatternRules.code],
    email: [
      emailRequiredRule,
      userPatternRules.email,
    ],
  } satisfies Record<string, App.Global.FormRule[]>

  /** the default required rule */
  const defaultRequiredRule = createRequiredRule($t("form.required"))

  const syncMessages = () => {
    userPatternRules.username.message = $t("form.username.invalid")
    userPatternRules.phone.message = $t("form.phone.invalid")
    userPatternRules.pwd.message = $t("form.pwd.invalid")
    userPatternRules.code.message = $t("form.code.invalid")
    userPatternRules.email.message = $t("form.email.invalid")

    usernameRequiredRule.message = $t("form.username.required")
    usernameLengthRule.message = $t("form.username.length")
    usernamePatternRule.message = $t("form.username.pattern")
    usernameStartRule.message = $t("form.username.startLowercase")

    phoneRequiredRule.message = $t("form.phone.required")
    pwdRequiredRule.message = $t("form.pwd.required")
    codeRequiredRule.message = $t("form.code.required")
    emailRequiredRule.message = $t("form.email.required")
    defaultRequiredRule.message = $t("form.required")
  }

  watch(() => appStore.locale, syncMessages, { immediate: true })

  return {
    patternRules: { user: userPatternRules },
    formRules: { user: userFormRules },
    defaultRequiredRule,
    createRequiredRule,
  }
}

export function useNaiveForm() {
  const formRef = ref<FormInst | null>(null)

  async function validate(...args: Parameters<FormValidate>) {
    await formRef.value?.validate(...args)
  }

  function restoreValidation(key?: string) {
    if (!formRef.value) {
      return
    }
    const { restoreValidation, formItems } = formRef.value
    if (key) {
      const item = formItems[key]
      if (item) {
        item.forEach(it => it.restoreValidation())
      }
    }
    else {
      restoreValidation()
    }
  }

  return {
    formRef,
    validate: validate as unknown as FormValidate,
    restoreValidation,
  }
}

export function createUidValidator<T extends string | Record<string, any>>(options: {
  fieldName: MaybeRefOrGetter<string>
  checkDuplicate?: (payload: T) => Promise<{ data?: { valid?: boolean, message?: string } | null, error?: any }>
  duplicateCheckArgs?: (() => Record<string, any>) | Record<string, any>
  payloadKey?: string
}): FormItemRule[] {
  const appStore = useAppStore()
  const {
    fieldName,
    checkDuplicate,
    duplicateCheckArgs = {},
    payloadKey = "uid",
  } = options

  const requiredRule = createRequiredRule($t("form.required"))
  const lengthRule: FormItemRule = {
    min: 3,
    max: 40,
    message: $t("form.uid.length", { field: toValue(fieldName), min: 4, max: 40 }),
    trigger: ["change", "blur"],
    key: "check:length",
  }
  const patternRule: FormItemRule = {
    pattern: /^[\w-]*$/,
    message: $t("form.uid.pattern"),
    trigger: ["change", "blur"],
    key: "check:pattern",
  }
  const hyphenValidator: FormItemRuleValidator = (_rule, value) => {
    const normalizedValue = normalizeFormStringValue(value)
    if (/^[_-]|[_-]$/.test(normalizedValue)) {
      return new Error($t("form.uid.hyphenEdges"))
    }
    if (/[_-]{2,}/.test(normalizedValue)) {
      return new Error($t("form.uid.hyphenConsecutive"))
    }
    if (!/^[a-z][a-z0-9_]*$/.test(normalizedValue)) {
      return new Error($t("form.uid.startLowercase"))
    }
    return true
  }
  const hyphenRule: FormItemRule = {
    validator: hyphenValidator,
    trigger: ["change", "blur"],
    key: "check:hyphen",
  }

  const baseValidators: FormItemRule[] = [requiredRule, lengthRule, patternRule, hyphenRule]

  const syncMessages = () => {
    const label = toValue(fieldName)
    requiredRule.message = $t("form.required")
    lengthRule.message = $t("form.uid.length", { field: label, min: 4, max: 40 })
    patternRule.message = $t("form.uid.pattern")
  }

  watch([() => appStore.locale, () => toValue(fieldName)], syncMessages, { immediate: true })

  if (checkDuplicate) {
    const duplicateValidator: FormItemRuleAsyncValidator = async (_rule, value) => {
      const normalizedValue = normalizeFormStringValue(value)
      if (!normalizedValue) {
        throw new Error($t("form.fieldRequired", { field: toValue(fieldName) }))
      }

      const payload = payloadKey === "lab"
        ? normalizedValue as T
        : {
            [payloadKey]: normalizedValue,
            ...(typeof duplicateCheckArgs === "function" ? duplicateCheckArgs() : duplicateCheckArgs),
          } as T

      try {
        const { data, error } = await checkDuplicate(payload)
        if (data) {
          if (data.valid) {
            return
          }
          throw new Error(data?.message)
        }
        else if (error) {
          throw error
        }
      }
      catch (e: any) {
        const { detail } = (e as AxiosError).response?.data as { detail: PydanticError[] | string }
        if (typeof detail === "string") {
          // eslint-disable-next-line unicorn/prefer-type-error
          throw new Error(detail)
        }
        else {
          throw formatPydanticErrors(detail)
        }
      }
    }
    baseValidators.push({
      key: "check:duplicate",
      asyncValidator: duplicateValidator,
      trigger: ["blur", "check"],
    })
  }

  return baseValidators
}

export function createDisplayNameValidator(fieldName: MaybeRefOrGetter<string>): FormItemRule[] {
  const appStore = useAppStore()
  const requiredRule = createRequiredRule($t("form.required"))
  const lengthRule: FormItemRule = {
    min: 1,
    max: 40,
    message: $t("form.displayName.length", { field: toValue(fieldName), min: 1, max: 40 }),
    trigger: ["change", "blur"],
  }
  const hyphenValidator: FormItemRuleValidator = (_rule, value) => {
    const normalizedValue = normalizeFormStringValue(value)
    if (/^[_-]|[_-]$/.test(normalizedValue)) {
      return new Error($t("form.displayName.hyphenEdges"))
    }
    if (/[_-]{2,}/.test(normalizedValue)) {
      return new Error($t("form.displayName.hyphenConsecutive"))
    }
    return true
  }
  const hyphenRule: FormItemRule = {
    validator: hyphenValidator,
    trigger: ["change", "blur"],
  }

  const syncMessages = () => {
    requiredRule.message = $t("form.required")
    lengthRule.message = $t("form.displayName.length", { field: toValue(fieldName), min: 1, max: 40 })
  }

  watch(() => appStore.locale, syncMessages, { immediate: true })

  return [requiredRule, lengthRule, hyphenRule]
}

export function createPasswordValidator(): FormItemRule[] {
  const appStore = useAppStore()
  const uppercaseValidator: FormItemRuleValidator = (_rule, value) => /[A-Z]/.test(normalizeFormStringValue(value))
  const uppercaseRule: FormItemRule = {
    validator: uppercaseValidator,
    message: $t("form.password.uppercase"),
    trigger: ["blur", "change"],
  }
  const lowercaseValidator: FormItemRuleValidator = (_rule, value) => /[a-z]/.test(normalizeFormStringValue(value))
  const lowercaseRule: FormItemRule = {
    validator: lowercaseValidator,
    message: $t("form.password.lowercase"),
    trigger: ["blur", "change"],
  }
  const digitValidator: FormItemRuleValidator = (_rule, value) => /\d/.test(normalizeFormStringValue(value))
  const digitRule: FormItemRule = {
    validator: digitValidator,
    message: $t("form.password.digit"),
    trigger: ["blur", "change"],
  }
  const specialValidator: FormItemRuleValidator = (_rule, value) => {
    const normalizedValue = normalizeFormStringValue(value)
    const supportedCharactersText = `!"#$%&'()*+,-./:;<=>?@[\\]^_\`{|}~`
    const supportedCharacters = /[!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/
    const unsupportedCharacters = normalizedValue.match(/[^\w!"#$%&'()*+,\-./:;<=>?@[\\\]^`{|}~]/gi)

    const hasSupportedCharacter = supportedCharacters.test(normalizedValue)

    const errorList: Error[] = []
    if (!hasSupportedCharacter) {
      errorList.push(new Error($t("form.password.specialMissing", { chars: supportedCharactersText })))
    }

    if (unsupportedCharacters) {
      const unsupportedCharactersList = [...new Set(unsupportedCharacters)]
      errorList.push(
        new Error(
          $t("form.password.specialUnsupported", { chars: unsupportedCharactersList.join(", ") }),
        ),
      )
    }

    if (errorList.length > 0) {
      return errorList
    }

    return true
  }
  const specialRule: FormItemRule = {
    validator: specialValidator,
    trigger: ["blur", "change"],
  }
  const lengthValidator: FormItemRuleValidator = (_rule, value) => {
    const normalizedValue = normalizeFormStringValue(value)
    return normalizedValue.length >= 8 && normalizedValue.length <= 32
  }
  const lengthRule: FormItemRule = {
    validator: lengthValidator,
    message: $t("form.password.length"),
    trigger: ["blur", "change"],
  }

  const rules = [uppercaseRule, lowercaseRule, digitRule, specialRule, lengthRule]

  const syncMessages = () => {
    uppercaseRule.message = $t("form.password.uppercase")
    lowercaseRule.message = $t("form.password.lowercase")
    digitRule.message = $t("form.password.digit")
    lengthRule.message = $t("form.password.length")
  }

  watch(() => appStore.locale, syncMessages, { immediate: true })

  return rules
}

export function createLoginPwdValidator(): FormItemRule[] {
  const appStore = useAppStore()
  const requiredRule = createRequiredRule($t("form.pwd.required"))

  watch(
    () => appStore.locale,
    () => {
      requiredRule.message = $t("form.pwd.required")
    },
    { immediate: true },
  )

  return [requiredRule]
}

export function createVersionValidator(): FormItemRule[] {
  const appStore = useAppStore()
  const requiredRule = createRequiredRule($t("form.required"))
  const patternRule: FormItemRule = {
    pattern: /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-z-][0-9a-z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-z-][0-9a-z-]*))*))?(?:\+([0-9a-z-]+(?:\.[0-9a-z-]+)*))?$/i,
    message: $t("form.version.invalid"),
    trigger: ["input", "blur"],
  }

  watch(
    () => appStore.locale,
    () => {
      requiredRule.message = $t("form.required")
      patternRule.message = $t("form.version.invalid")
    },
    { immediate: true },
  )

  return [requiredRule, patternRule]
}
