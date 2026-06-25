<template>
  <phone-input-template v-slot="{ description, phoneKey, fullPhoneKey, countryKey, formItemPath, onKeydownEnter }">
    <div class="mb-6 text-left">
      <p class="text-gray-600">
        {{ description }}
      </p>
    </div>

    <n-form
      ref="formRef"
      :model="model"
      :rules="rules"
      size="large"
      :show-label="false"
      :show-require-mark="false"
      @keydown.enter="onKeydownEnter"
    >
      <n-form-item :path="formItemPath">
        <country-phone-input
          v-model="model[phoneKey]"
          v-model:full-phone="model[fullPhoneKey]"
          v-model:country="model[countryKey]"
          size="large"
          :default-country="model[countryKey]?.isoCode"
          :placeholder="$t('page.login.common.phonePlaceholder')"
        />
      </n-form-item>
    </n-form>
  </phone-input-template>

  <verification-code-template v-slot="{ description, codeKey, maskedPhone, isCountdownActive, countdownRemaining, onKeydownEnter, onCodeComplete, onResendCode, loadingKeys, codeError }">
    <div class="text-left">
      <p class="text-gray-600">
        {{ description }}
      </p>
      <div class="my-4 flex items-center justify-center gap-2">
        <n-icon v-if="model.currentCountry?.icon" :component="model.currentCountry.icon" size="18" />
        <p class="text-primary font-medium">
          {{ maskedPhone }}
        </p>
      </div>
    </div>

    <div class="verification-form" @keydown.enter="onKeydownEnter">
      <div class="mb-6">
        <label class="mb-3 block text-sm text-gray-700 font-medium">
          {{ $t('page.login.common.codePlaceholder') }}
        </label>
        <pin-input
          v-model="model[codeKey]"
          :length="6"
          :error="codeError.current"
          :disabled="loadingKeys.length > 0"
          auto-focus
          @complete="onCodeComplete"
        />
      </div>

      <div class="w-full flex items-center justify-center">
        <span class="text-gray-600">{{ $t('page.login.common.didntReceiveCode') }}</span>
        <n-button
          quaternary
          type="primary"
          :disabled="isCountdownActive"
          :loading="loadingKeys.length > 0"
          class="ml-1"
          @click="onResendCode"
        >
          {{ isCountdownActive ? `${$t('page.login.common.resend')} (${countdownRemaining}s)` : $t('page.login.common.resend') }}
        </n-button>
      </div>
    </div>
  </verification-code-template>

  <n-modal
    v-model:show="modalVisible"
    preset="card"
    class="max-w-60vw"
    :mask-closable="false"
    v-bind="$attrs"
    content-class="flex justify-center flex-col"
    footer-class="space-y-3"
    @after-leave="resetForm"
  >
    <template #header>
      {{ $t('page.profile.changePassword') }}
    </template>

    <n-scrollbar x-scrollable>
      <n-steps :current="currentStep" :status="stepStatus" class="steps-custom">
        <n-step
          :ref="node => stepRefs[1] = node"
          :title="$t('page.profile.enterCurrentPhone')"
          :description="$t('page.profile.enterCurrentPhoneDescription')"
          :class="{ 'cursor-pointer': canNavigateToStep(1) }"
          @click="navigateToStep(1)"
        >
          <template #icon>
            <n-icon>
              <icon-uil-dialpad-alt />
            </n-icon>
          </template>
        </n-step>
        <n-step
          :ref="node => stepRefs[2] = node"
          :title="$t('page.profile.sendSmsToCurrentPhone')"
          :description="$t('page.profile.enterCodeForPhone')"
          :class="{ 'cursor-pointer': canNavigateToStep(2) }"
          @click="navigateToStep(2)"
        >
          <template #icon>
            <n-icon>
              <icon-hugeicons-sms-code />
            </n-icon>
          </template>
        </n-step>
        <n-step
          :ref="node => stepRefs[3] = node"
          :title="$t('page.profile.changePassword')"
          :description="$t('page.profile.changePasswordDescription')"
          :class="{ 'cursor-pointer': canNavigateToStep(3) }"
          @click="navigateToStep(3)"
        >
          <template #icon>
            <n-icon>
              <icon-hugeicons-lock />
            </n-icon>
          </template>
        </n-step>
      </n-steps>
    </n-scrollbar>

    <div v-if="currentStep === 1">
      <phone-input
        :title="$t('page.profile.enterCurrentPhone')"
        :description="$t('page.profile.changePasswordDescription')"
        phone-key="currentPhone"
        full-phone-key="currentFullPhone"
        country-key="currentCountry"
        form-item-path="currentPhone"
        :rules="rules"
        :form-ref="formRef"
        :on-keydown-enter="handleConfirmAction"
      />
    </div>

    <div v-else-if="currentStep === 2">
      <div v-if="smsSending" class="py-8 text-center">
        <n-spin size="large" />
        <p class="mt-4 text-gray-600">
          {{ $t('page.login.common.sendingCode') }}
        </p>
      </div>

      <verification-code
        v-else
        :title="$t('page.profile.verifyCurrentPhone')"
        :description="$t('page.profile.enterCodeForPhone')"
        phone-key="currentPhone"
        full-phone-key="currentFullPhone"
        country-key="currentCountry"
        code-key="currentCode"
        type="current"
        :masked-phone="maskedCurrentPhone"
        :is-countdown-active="isCountdownActive"
        :countdown-remaining="countdownRemainingSeconds"
        :on-keydown-enter="handleConfirmAction"
        :on-code-complete="handleCodeComplete"
        :on-resend-code="handleResendCode"
        :code-error="codeError"
        :loading-keys="loadingKeys"
      />
    </div>

    <div v-else-if="currentStep === 3">
      <div class="mb-6 text-left">
        <p class="text-gray-600">
          {{ $t('page.profile.changePasswordDescription') }}
        </p>
      </div>

      <n-form
        ref="formRef"
        :model="model"
        :rules="rules"
        :show-label="false"
        :show-require-mark="false"
        size="large"
        @keydown.enter.prevent="handleConfirmAction"
      >
        <div class="form-section space-y-5">
          <div class="flex flex-col gap-2 md:flex-row md:items-start md:gap-6">
            <span class="text-sm text-gray-500 font-medium md:w-48">
              {{ $t('page.profile.currentPassword') }}
            </span>
            <n-form-item class="flex-1" path="oldPassword">
              <n-input
                v-model:value="model.oldPassword"
                type="password"
                show-password-on="click"
                autocomplete="current-password"
                :maxlength="30"
                :placeholder="$t('page.login.common.passwordPlaceholder')"
                class="w-full md:w-80"
              >
                <template #password-visible-icon>
                  <n-icon :size="16" :component="EyeOutline" />
                </template>
                <template #password-invisible-icon>
                  <n-icon :size="16" :component="EyeOffOutline" />
                </template>
              </n-input>
            </n-form-item>
          </div>

          <div class="flex flex-col gap-2 md:flex-row md:items-start md:gap-6">
            <span class="text-sm text-gray-500 font-medium md:w-48">
              {{ $t('page.profile.newPassword') }}
            </span>
            <n-form-item class="flex-1" path="password">
              <n-input
                v-model:value="model.password"
                type="password"
                show-password-on="click"
                autocomplete="new-password"
                :maxlength="30"
                :placeholder="$t('page.login.common.passwordPlaceholder')"
                class="w-full md:w-80"
              >
                <template #password-visible-icon>
                  <n-icon :size="16" :component="EyeOutline" />
                </template>
                <template #password-invisible-icon>
                  <n-icon :size="16" :component="EyeOffOutline" />
                </template>
              </n-input>
            </n-form-item>
          </div>

          <div class="flex flex-col gap-2 md:flex-row md:items-start md:gap-6">
            <span class="text-sm text-gray-500 font-medium md:w-48">
              {{ $t('page.profile.confirmPassword') }}
            </span>
            <n-form-item class="flex-1" path="confirmPassword">
              <n-input
                v-model:value="model.confirmPassword"
                type="password"
                show-password-on="click"
                autocomplete="new-password"
                :maxlength="30"
                class="w-full md:w-80"
                :placeholder="$t('page.login.common.confirmPasswordPlaceholder')"
              >
                <template #password-visible-icon>
                  <n-icon :size="16" :component="EyeOutline" />
                </template>
                <template #password-invisible-icon>
                  <n-icon :size="16" :component="EyeOffOutline" />
                </template>
              </n-input>
            </n-form-item>
          </div>
        </div>
      </n-form>
    </div>

    <template #footer>
      <n-button
        v-if="currentStep === 3"
        quaternary
        block
        size="large"
        @click="handleForgotPassword"
      >
        {{ $t('page.profile.forgotPassword') }}
      </n-button>
      <n-button
        type="primary"
        size="large"
        strong
        block
        :disabled="isButtonDisabled"
        :loading="currentStep === 3 ? loadingState.submit : loadingState.sendCode"
        @click="handleConfirmAction"
      >
        {{ buttonText }}
      </n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { FormItemRule } from "naive-ui"
import type { ComponentPublicInstance } from "vue"
import { useLoading } from "@/composables"
import { createLoginPwdValidator, createPasswordValidator, useFormRules, useNaiveForm } from "@/composables/useForm"
import { $t } from "@/locales"
import { postSendCode, postSendResetPasswordCode, putChangePassword } from "@/service/api/auth"
import { useAuthStore } from "@/store/modules/auth"
import CountryPhoneInput from "@airalogy/components/country-phone-input.vue"
import PinInput from "@airalogy/components/pin-input.vue"
import { useClosableMessage } from "@airalogy/composables"
import { countryData, type CountryData } from "@airalogy/shared/constants/country-code"
import { createReusableTemplate, unrefElement, useCountdown } from "@vueuse/core"
import EyeOffOutline from "~icons/ion/eye-off-outline"
import EyeOutline from "~icons/ion/eye-outline"
import { computed, reactive, ref, watch } from "vue"

defineOptions({
  name: "ChangePasswordModal",
  inheritAttrs: false,
})

const emit = defineEmits<{ (e: "forgotPassword"): void }>()

interface TemplateBaseProps {
  title: string
  description: string
  phoneKey: "currentPhone"
  fullPhoneKey: "currentFullPhone"
  countryKey: "currentCountry"
  onKeydownEnter: () => void
}

interface PhoneInputProps extends TemplateBaseProps {
  formItemPath: "currentPhone"
}

const [PhoneInputTemplate, PhoneInput] = createReusableTemplate<PhoneInputProps>()

interface VerificationProps extends TemplateBaseProps {
  codeKey: "currentCode"
  type: "current"
  maskedPhone: string
  isCountdownActive: boolean
  countdownRemaining: number
  onCodeComplete: (code: string) => void
  onResendCode: () => void
  loadingKeys: boolean[]
  codeError: { current: string }
}

const [VerificationCodeTemplate, VerificationCode] = createReusableTemplate<VerificationProps>()

const modalVisible = defineModel<boolean>("show", { default: false })

const authStore = useAuthStore()
const message = useClosableMessage()

interface FormModel {
  currentPhone: string
  currentFullPhone: string
  currentCountry: CountryData | null
  currentCode: string
  oldPassword: string
  password: string
  confirmPassword: string
}

const model = reactive<FormModel>({
  currentPhone: "",
  currentFullPhone: "",
  currentCountry: null,
  currentCode: "",
  oldPassword: "",
  password: "",
  confirmPassword: "",
})

const codeError = reactive({ current: "" })

const { formRef, validate, restoreValidation } = useNaiveForm()
const { formRules: { user: userFormRules } } = useFormRules()
const { loadingState, startTargetLoading, endTargetLoading, loadingKeys } = useLoading(false, [
  "submit",
  "sendCode",
])

const loginPwdValidator = createLoginPwdValidator()
const passwordValidator = createPasswordValidator()

const smsSent = ref(false)
const smsSending = ref(false)

const currentStep = ref(1)
const stepStatus = ref<"process" | "finish" | "error" | "wait">("process")
const stepRefs = ref<Record<number, ComponentPublicInstance | Element | null>>({})

function useConfiguredCountdown() {
  const { remaining, start, stop, isActive } = useCountdown(60, {
    onComplete() {
      stop()
    },
  })
  return { remaining, start, stop, isActive }
}

const {
  remaining: countdownRemainingRef,
  start: startCountdown,
  stop: stopCountdown,
  isActive: countdownActiveRef,
} = useConfiguredCountdown()

const countdownRemainingSeconds = computed(() => Math.max(0, Math.ceil(countdownRemainingRef.value)))
const isCountdownActive = computed(() => countdownActiveRef.value)

const rules = computed<Record<string, FormItemRule[]>>(() => ({
  currentPhone: [
    ...userFormRules.phone,
    {
      validator: (_rule, value: string) => {
        if (!value) {
          return new Error($t("form.required"))
        }

        const userPhone = authStore.userInfo?.phone
        const userCountryCode = authStore.userInfo?.country_code

        if (!userPhone || !userCountryCode) {
          return new Error($t("page.profile.phoneOrCountryCodeMissing"))
        }

        if (model.currentCountry?.dialCode !== `+${userCountryCode}` || value !== userPhone) {
          return new Error($t("page.profile.phoneMismatch"))
        }

        return true
      },
      trigger: "blur",
    },
  ],
  oldPassword: [...loginPwdValidator],
  password: [...passwordValidator],
  confirmPassword: [
    ...passwordValidator,
    {
      validator: (_rule, value: string) => {
        if (value !== model.password) {
          return new Error($t("page.profile.passwordMismatch" as any))
        }
        return true
      },
      trigger: ["blur", "change"],
    },
  ],
}))

const maskedCurrentPhone = computed(() => {
  const phone = model.currentPhone || ""
  const country = model.currentCountry

  if (!phone) {
    return ""
  }

  if (phone.length <= 4) {
    return country ? `${country.dialCode} ${phone}` : phone
  }

  const visibleStart = phone.slice(0, 3)
  const visibleEnd = phone.slice(-2)
  const maskedMiddle = "*".repeat(Math.max(phone.length - 5, 0))
  const maskedNumber = `${visibleStart}${maskedMiddle}${visibleEnd}`

  return country ? `${country.dialCode} ${maskedNumber}` : maskedNumber
})

const isCurrentPhoneVerified = computed(() => smsSent.value && model.currentCode.length === 6)

const confirmButtonAction = computed<"sendCurrentSms" | "validateCurrentCodeAndAdvance" | "submitPasswordChange">(() => {
  switch (currentStep.value) {
    case 1:
      return "sendCurrentSms"
    case 2:
      return "validateCurrentCodeAndAdvance"
    case 3:
      return "submitPasswordChange"
    default:
      return "sendCurrentSms"
  }
})

const buttonText = computed(() => {
  switch (currentStep.value) {
    case 1:
      return loadingState.value.sendCode ? $t("page.login.common.sendingCode") : $t("page.login.common.sendCode")
    case 2:
      return $t("common.next")
    case 3:
      return $t("page.profile.savePassword" as any)
    default:
      return $t("page.login.common.sendCode")
  }
})

const isButtonDisabled = computed(() => {
  switch (currentStep.value) {
    case 1:
      return !model.currentPhone || !!loadingState.value.sendCode
    case 2:
      return !!loadingState.value.sendCode || smsSending.value || model.currentCode.length !== 6
    case 3: {
      const hasPasswords = model.oldPassword && model.password && model.confirmPassword
      return !hasPasswords || !!loadingState.value.submit
    }
    default:
      return false
  }
})

function canNavigateToStep(targetStep: number) {
  if (currentStep.value === targetStep) {
    return true
  }

  if (targetStep === 1) {
    return true
  }

  if (targetStep === 2) {
    return smsSent.value
  }

  if (targetStep === 3) {
    return isCurrentPhoneVerified.value
  }

  return false
}

function navigateToStep(targetStep: number) {
  if (!canNavigateToStep(targetStep)) {
    return
  }

  if (targetStep === 1) {
    resetVerificationState()
  }

  currentStep.value = targetStep
}

function handleForgotPassword() {
  emit("forgotPassword")
}

function handleCodeComplete(code: string) {
  if (code.length === 6) {
    codeError.current = ""
  }
}

async function handleConfirmAction() {
  switch (confirmButtonAction.value) {
    case "sendCurrentSms":
      await sendCurrentPhoneSms()
      break
    case "validateCurrentCodeAndAdvance":
      await validateCurrentCodeAndAdvance()
      break
    case "submitPasswordChange":
      await submitPasswordChange()
      break
  }
}

async function sendCurrentPhoneSms() {
  if (!model.currentPhone || !model.currentCountry?.dialCode) {
    message.warning($t("page.profile.phoneOrCountryCodeMissing"))
    return
  }

  smsSending.value = true
  startTargetLoading("sendCode")
  codeError.current = ""

  try {
    await formRef.value?.validate(undefined, rule => rule?.key === "currentPhone")

    const { data, error } = await postSendResetPasswordCode()

    if (data?.success) {
      smsSent.value = true
      currentStep.value = 2
      startCountdown()
      message.success($t("page.login.common.sendCodeSuccess"))
    }
    else if (error) {
      throw error
    }
  }
  catch (error: any) {
    const detail = error?.response?.data?.detail || error?.message
    codeError.current = detail || codeError.current
    message.error(detail || $t("page.login.common.sendCodeFailure"))
  }
  finally {
    endTargetLoading("sendCode")
    smsSending.value = false
  }
}

async function handleResendCode() {
  if (!smsSent.value) {
    await sendCurrentPhoneSms()
    return
  }

  if (isCountdownActive.value) {
    message.warning(`Please wait ${countdownRemainingSeconds.value} seconds before sending again`)
    return
  }

  const dialCode = model.currentCountry?.dialCode
  if (!dialCode) {
    message.warning($t("page.profile.phoneOrCountryCodeMissing"))
    return
  }

  try {
    startTargetLoading("sendCode")

    const { data, error } = await postSendCode(
      model.currentPhone,
      dialCode,
      "reset_password",
    )

    if (data?.success) {
      startCountdown()
      model.currentCode = ""
      codeError.current = ""
      message.success($t("page.login.common.sendCodeSuccess"))
    }
    else if (error) {
      throw error
    }
  }
  catch (error: any) {
    const detail = error?.response?.data?.detail || error?.message
    message.error(detail || $t("page.login.common.sendCodeFailure"))
  }
  finally {
    endTargetLoading("sendCode")
  }
}

async function validateCurrentCodeAndAdvance() {
  if (model.currentCode.length !== 6) {
    codeError.current = $t("form.required")
    return
  }

  codeError.current = ""
  currentStep.value = 3
}

async function submitPasswordChange() {
  try {
    await validate(undefined, (rule) => {
      return ["oldPassword", "password", "confirmPassword"].includes(rule?.key as string)
    })
  }
  catch {
    return
  }

  if (model.currentCode.length !== 6) {
    currentStep.value = 2
    codeError.current = $t("form.required")
    return
  }

  startTargetLoading("submit")

  try {
    const { data, error } = await putChangePassword({
      code: model.currentCode,
      password: model.password,
      confirmPassword: model.confirmPassword,
    })

    if (data?.message === "success" || data) {
      message.success($t("page.profile.changePasswordSuccess" as any))
      modalVisible.value = false
    }
    else if (error) {
      throw error
    }
  }
  catch (error: any) {
    const detail = error?.response?.data?.detail || error?.message
    message.error(detail || $t("page.profile.changePasswordFailure" as any))
  }
  finally {
    endTargetLoading("submit")
  }
}

function resetVerificationState() {
  smsSent.value = false
  smsSending.value = false
  model.currentCode = ""
  codeError.current = ""
  stopCountdown()
}

function resetPasswordFields() {
  model.oldPassword = ""
  model.password = ""
  model.confirmPassword = ""
}

function resolveUserCountry(): CountryData | null {
  const userCountryCode = authStore.userInfo?.country_code

  if (userCountryCode) {
    const normalized = userCountryCode.startsWith("+") ? userCountryCode : `+${userCountryCode}`
    const matched = countryData.find(country => country.dialCode === normalized)
    if (matched) {
      return matched
    }
  }

  return countryData.find(country => country.isoCode === "CN") || null
}

function initializePhoneFromUser() {
  model.currentCountry = resolveUserCountry()
  model.currentPhone = authStore.userInfo?.phone || ""
  model.currentFullPhone = ""
}

function resetForm() {
  currentStep.value = 1
  stepStatus.value = "process"
  resetVerificationState()
  resetPasswordFields()
  restoreValidation()
  endTargetLoading("submit")
  endTargetLoading("sendCode")
  initializePhoneFromUser()
}

watch(() => modalVisible.value, (visible) => {
  if (visible) {
    initializePhoneFromUser()
  }
})

watch(currentStep, (val) => {
  const el = unrefElement(stepRefs.value[val] as any) as HTMLElement | null
  if (el) {
    el.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" })
  }
})

watch(
  () => authStore.userInfo,
  () => {
    if (!modalVisible.value) {
      initializePhoneFromUser()
    }
  },
  { deep: true },
)

initializePhoneFromUser()
</script>

<style scoped lang="sass">
:deep(.pin-input-container)
  margin-bottom: 1rem

:deep(.n-input-wrapper)
  width: 100%

.form-section
  :deep(.n-form-item)
    margin-bottom: 0

.verification-form
  :deep(.pin-input-container)
    width: 100%

.steps-custom
  :deep(.n-step-splitor)
    min-width: 120px
  :deep(.n-step)
    &:last-of-type
      flex-grow: 0
      flex-basis: fit-content

    .n-step-indicator
      @apply bg-white transition-all h-fit p-1 shadow-sm
      flex-grow: 0
      flex-basis: fit-content

    &.n-step--finish
      .n-step-indicator
        @apply bg-primary-50

      .n-step-indicator__icon
        @apply text-primary

    &.n-step--process
      .n-step-indicator
        @apply bg-primary-50 shadow-md ring-2 ring-primary/20

      .n-step-indicator__icon
        @apply text-primary

    &.cursor-pointer
      cursor: pointer

      &:hover
        .n-step-content__title
          color: var(--primary-color)
</style>
