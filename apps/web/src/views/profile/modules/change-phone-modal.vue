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

  <verification-code-template v-slot="{ description, countryKey, codeKey, type, maskedPhone, isCountdownActive, countdownRemaining, onKeydownEnter, onCodeComplete, onResendCode }">
    <div class="text-left">
      <!-- <h3 class="mb-2 text-lg font-semibold">
        {{ title }}
      </h3> -->
      <p class="text-gray-600">
        {{ description }}
      </p>
      <div class="my-4 flex items-center justify-center gap-2">
        <n-icon v-if="model[countryKey]?.icon" :component="model[countryKey].icon" size="18" />
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
          :error="codeError[type]"
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
      {{ $t('page.profile.changePhone') }}
    </template>

    <!-- Steps for quick navigation -->
    <n-scrollbar x-scrollable>
      <n-steps :current="currentStep" :status="stepStatus" class="steps-custom">
        <n-step
          :ref="node => stepRefs[1] = node"
          :title="$t('page.profile.verifyCurrentPhone')"
          :description="$t('page.profile.sendSmsToCurrentPhoneDescription')"
          :class="{ 'cursor-pointer': canNavigateToStep(1) }"
          @click="navigateToStep(1)"
        >
          <template #icon>
            <n-icon>
              <icon-hugeicons-sms-code />
            </n-icon>
          </template>
        </n-step>
        <n-step
          :ref="node => stepRefs[2] = node"
          :title="$t('page.profile.enterNewPhone')"
          :description="$t('page.profile.enterNewPhoneDescription')"
          :class="{ 'cursor-pointer': canNavigateToStep(2) }"
          @click="navigateToStep(2)"
        >
          <template #icon>
            <n-icon>
              <icon-uil-dialpad-alt />
            </n-icon>
          </template>
        </n-step>
        <n-step
          :ref="node => stepRefs[3] = node"
          :title="$t('page.profile.sendSmsToNewPhone')"
          :description="$t('page.profile.sendSmsToNewPhoneDescription')"
          :class="{ 'cursor-pointer': canNavigateToStep(3) }"
          @click="navigateToStep(3)"
        >
          <template #icon>
            <n-icon>
              <icon-hugeicons-sms-code />
            </n-icon>
          </template>
        </n-step>
      </n-steps>
    </n-scrollbar>

    <!-- Step 1: Verify Current Phone -->
    <div v-if="currentStep === 1">
      <!-- SMS Sending Phase -->
      <div v-if="smsSending.current" class="py-8 text-center">
        <n-spin size="large" />
        <p class="mt-4 text-gray-600">
          {{ $t('page.login.common.sendingCode') }}
        </p>
      </div>

      <!-- Send Code Button Phase -->
      <div v-else-if="!smsSent.current" class="py-8 text-center">
        <p class="mb-6 text-gray-600">
          {{ $t('page.profile.sendCodeToCurrentPhone') }}
        </p>
        <n-button
          type="primary"
          size="large"
          strong
          :loading="loadingState.submit"
          @click="sendCurrentPhoneSms"
        >
          {{ $t('page.login.common.sendCode') }}
        </n-button>
      </div>

      <!-- Verification Code Phase -->
      <verification-code
        v-else
        :title="$t('page.profile.verifyCurrentPhone')"
        :description="$t('page.profile.enterCodeForPhone')"
        phone-key="currentPhone"
        full-phone-key="currentFullPhone"
        country-key="currentCountry"
        code-key="currentCode"
        type="current"
        :masked-phone="$t('page.profile.yourCurrentPhone')"
        :is-countdown-active="isCurrActive"
        :countdown-remaining="currRemaining"
        :on-keydown-enter="handleConfirmAction"
        :on-code-complete="(code) => handleCodeComplete('current', code)"
        :on-resend-code="() => handleResendCode('current')"
      />
    </div>

    <!-- Step 2: Enter New Phone -->
    <div v-else-if="currentStep === 2">
      <phone-input
        :title="$t('page.profile.enterNewPhone')"
        :description="$t('page.profile.enterNewPhoneDescription')"
        phone-key="newPhone"
        full-phone-key="fullPhone"
        country-key="country"
        form-item-path="newPhone"
        :model="model"
        :rules="rules"
        :form-ref="formRef"
        :on-keydown-enter="handleConfirmAction"
      />
    </div>

    <!-- Step 3: Send SMS to New Phone -->
    <div v-else-if="currentStep === 3">
      <!-- SMS Sending Phase -->
      <div v-if="smsSending.new" class="py-8 text-center">
        <n-spin size="large" />
        <p class="mt-4 text-gray-600">
          {{ $t('page.login.common.sendingCode') }}
        </p>
      </div>

      <!-- Verification Code Phase -->
      <verification-code
        v-else
        :title="$t('page.profile.verifyNewPhone')"
        :description="$t('page.profile.enterCodeForNewPhone')"
        phone-key="newPhone"
        full-phone-key="fullPhone"
        country-key="country"
        code-key="newCode"
        type="new"
        :model="model"
        :code-error="codeError"
        :loading-keys="loadingKeys"
        :masked-phone="maskedNewPhone"
        :is-countdown-active="isNewActive"
        :countdown-remaining="newRemaining"
        :on-keydown-enter="handleConfirmAction"
        :on-code-complete="(code) => handleCodeComplete('new', code)"
        :on-resend-code="() => handleResendCode('new')"
      />
    </div>

    <template #footer>
      <n-button
        v-if="currentStep === 3"
        quaternary
        block
        size="large"
        @click="handleBackToPhoneInput"
      >
        ← {{ $t('page.login.common.changePhoneNumber') }}
      </n-button>
      <n-button
        v-if="currentStep !== 1 || smsSent.current"
        type="primary"
        size="large"
        strong
        class="ml-auto"
        block
        :disabled="isButtonDisabled"
        :loading="loadingState.submit"
        @click="handleConfirmAction"
      >
        {{ buttonText }}
      </n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { useLoading } from "@/composables"
import { useFormRules, useNaiveForm } from "@/composables/useForm"
import { $t } from "@/locales"
import { postSendCode, postSendCodeToCurrentPhone, putChangePhone } from "@/service/api/auth"
import { useAuthStore } from "@/store/modules/auth"
import CountryPhoneInput from "@airalogy/components/country-phone-input.vue"
import PinInput from "@airalogy/components/pin-input.vue"
import { useClosableMessage } from "@airalogy/composables"
import { countryData, type CountryData } from "@airalogy/shared/constants/country-code"
import { createReusableTemplate, useCountdown } from "@vueuse/core"
import { computed, reactive, ref } from "vue"

defineOptions({
  name: "ChangePhoneModal",
  inheritAttrs: false,
})

interface TemplateBaseProps {
  title: string
  description: string
  phoneKey: "currentPhone" | "newPhone"
  fullPhoneKey: "fullPhone" | "currentFullPhone"
  countryKey: "country" | "currentCountry"
  onKeydownEnter: () => void

}

interface PhoneInputProps extends TemplateBaseProps {
  formItemPath: string
}

// Create reusable templates
const [PhoneInputTemplate, PhoneInput] = createReusableTemplate<PhoneInputProps>()

interface VerificationProps extends TemplateBaseProps {
  codeKey: "currentCode" | "newCode"
  type: "current" | "new"
  maskedPhone: string
  isCountdownActive: boolean
  countdownRemaining: number
  onCodeComplete: (code: string) => void
  onResendCode: () => void
}

const [VerificationCodeTemplate, VerificationCode] = createReusableTemplate<VerificationProps>()

const authStore = useAuthStore()
const { formRef, validate } = useNaiveForm()
const { formRules: { user: userFormRules } } = useFormRules()
const message = useClosableMessage()

const modalVisible = defineModel<boolean>("show", { default: false })

interface FormModel {
  currentCode: string
  newCode: string
  currentPhone?: string
  currentFullPhone?: string
  currentCountry?: CountryData | null
  newPhone?: string
  fullPhone?: string
  country?: CountryData | null
}

const model = reactive<FormModel>({
  currentCode: "",
  newCode: "",
  currentPhone: "",
  currentFullPhone: "",
  currentCountry: countryData.find(c => c.isoCode === "CN") || null,
  newPhone: "",
  fullPhone: "",
  country: countryData.find(c => c.isoCode === "CN") || null,
})

// Store original phone numbers to track if they changed before SMS was sent
const originalCurrentPhone = ref("")
const originalNewPhone = ref("")

// Step management following protocol-steps pattern
const currentStep = ref(1) // 1: verifyCurrentPhone, 2: enterNewPhone, 3: sendSmsToNew
const stepStatus = ref<"process" | "finish" | "error" | "wait">("process")
const stepRefs = ref<(Record<string, Element | ComponentPublicInstance | null>)>({})

// Map step values to step names
const step = computed<"verifyCurrentPhone" | "enterNewPhone" | "sendSmsToNew">(() => {
  switch (currentStep.value) {
    case 1: return "verifyCurrentPhone"
    case 2: return "enterNewPhone"
    case 3: return "sendSmsToNew"
    default: return "verifyCurrentPhone"
  }
})

const codeError = reactive({
  current: "",
  new: "",
})

const smsSent = reactive({
  current: false,
  new: false,
})

// Track SMS sending status
const smsSending = reactive({
  current: false,
  new: false,
})

const { loadingState, startTargetLoading, endTargetLoading, loadingKeys } = useLoading(false, [
  "currentCode",
  "newCode",
  "submit",
])

function useConfiguredCountdown() {
  const { remaining, start, stop, isActive } = useCountdown(60, { onComplete() {
    stop()
  } })
  return { remaining, start, stop, isActive }
}

const { remaining: currRemaining, start: startCurr, stop: stopCurr, isActive: isCurrActive } = useConfiguredCountdown()
const { remaining: newRemaining, start: startNew, stop: stopNew, isActive: isNewActive } = useConfiguredCountdown()

// Track if current phone verification is complete
const isCurrentPhoneVerified = computed(() => {
  return smsSent.current && model.currentCode.length === 6
})

// Function to check if navigation to a specific step is allowed
function canNavigateToStep(targetStep: number) {
  // Always allow navigation to the current step
  if (currentStep.value === targetStep) {
    return true
  }

  // Allow navigation to step 1 (verifyCurrentPhone) from any step
  if (targetStep === 1) {
    return true
  }

  // Allow navigation to step 2 (enterNewPhone) only if current phone is verified
  if (targetStep === 2 && isCurrentPhoneVerified.value) {
    return true
  }

  // Allow navigation to step 3 (sendSmsToNew) only if new phone is entered
  if (targetStep === 3 && model.newPhone) {
    return true
  }

  return false
}

// Function to check if navigation to SMS phase is allowed
function canNavigateToSmsPhase(phoneType: "current" | "new") {
  // For current phone SMS phase
  if (phoneType === "current") {
    // Allow if SMS has been sent for current phone
    return smsSent.current
  }

  // For new phone SMS phase
  if (phoneType === "new") {
    // Allow if we're in the new phone step and SMS has been sent
    return currentStep.value === 2 && smsSent.new
  }

  return false
}

// Function to navigate to SMS phase
function navigateToSmsPhase(phoneType: "current" | "new") {
  if (!canNavigateToSmsPhase(phoneType)) {
    return
  }

  // For current phone SMS phase, ensure we're in the right step
  if (phoneType === "current" && currentStep.value !== 1) {
    currentStep.value = 1
  }

  // For new phone SMS phase, ensure we're in the right step
  if (phoneType === "new" && currentStep.value !== 2) {
    currentStep.value = 2
  }
}

// Function to navigate to a specific step
function navigateToStep(targetStep: number) {
  if (!canNavigateToStep(targetStep)) {
    return
  }

  // If navigating back to step 1, reset the new phone form
  if (targetStep === 1) {
    resetNewPhoneForm()
  }

  currentStep.value = targetStep
}

// Function to reset the new phone form
function resetNewPhoneForm() {
  smsSent.new = false
  model.newCode = ""
  codeError.new = ""
  model.newPhone = ""
  model.fullPhone = ""
  stopNew()
}

// Step navigation functions following protocol-steps pattern
function handlePrevStep() {
  if (currentStep.value > 1) {
    currentStep.value--
    // If navigating back to step 1, reset the new phone form
    if (currentStep.value === 1) {
      resetNewPhoneForm()
    }
    // If navigating back to step 3, reset the new phone SMS state
    if (currentStep.value === 3) {
      smsSent.new = false
      model.newCode = ""
      codeError.new = ""
      stopNew()
    }
  }
}

function handleNextStep() {
  if (currentStep.value < 3) {
    // Special handling for step 3 (send SMS to new phone)
    if (currentStep.value === 2 && model.newPhone) {
      currentStep.value = 3
      return
    }

    // For other steps, advance only if current phone is verified
    if (isCurrentPhoneVerified.value || currentStep.value === 1) {
      currentStep.value++
    }
  }
}

const rules = computed(() => ({
  currentPhone: [
    ...userFormRules.phone,
    {
      validator: (rule: any, value: string) => {
        if (!value) {
          return true
        }

        // Check if the entered phone matches the user's current phone
        const userPhone = authStore.userInfo?.phone
        const userCountryCode = authStore.userInfo?.country_code

        if (!value) {
          return new Error($t("form.required"))
        }

        // Compare phone numbers with country code
        // const fullEnteredPhone = `${model.currentCountry?.dialCode || ""}${value}`
        // const fullUserPhone = `${userCountryCode || ""}${userPhone}`

        if (model.currentCountry?.dialCode !== `+${userCountryCode}` || value !== userPhone) {
          return new Error($t("page.profile.phoneMismatch"))
        }

        return true
      },
      trigger: "blur",
    },
  ],
  newPhone: [
    ...userFormRules.phone,
    {
      validator: (rule: any, value: string) => {
        if (!value || !model.currentPhone) {
          return true
        }

        // Check if the new phone is different from the current phone
        if (value === model.currentPhone) {
          return new Error($t("page.profile.newPhoneMustBeDifferent"))
        }

        return true
      },
      trigger: "blur",
    },
  ],
}))

// Masked phone display for current phone
const maskedCurrentPhone = computed(() => {
  const phone = model.currentPhone || ""
  const country = model.currentCountry

  if (!phone || phone.length <= 4) {
    return phone
  }

  const visibleStart = phone.slice(0, 3)
  const visibleEnd = phone.slice(-2)
  const maskedMiddle = "*".repeat(phone.length - 5)
  const maskedNumber = `${visibleStart}${maskedMiddle}${visibleEnd}`

  // Return with country info if available
  if (country) {
    return `${country.dialCode} ${maskedNumber}`
  }

  return maskedNumber
})

// Masked phone display for new phone
const maskedNewPhone = computed(() => {
  const phone = model.newPhone || ""
  const country = model.country

  if (!phone || phone.length <= 4) {
    return phone
  }

  const visibleStart = phone.slice(0, 3)
  const visibleEnd = phone.slice(-2)
  const maskedMiddle = "*".repeat(phone.length - 5)
  const maskedNumber = `${visibleStart}${maskedMiddle}${visibleEnd}`

  // Return with country info if available
  if (country) {
    return `${country.dialCode} ${maskedNumber}`
  }

  return maskedNumber
})

const confirmButtonAction = computed(() => {
  switch (currentStep.value) {
    case 1: // Verify Current Phone
      return smsSent.current ? "validateCurrentCodeAndAdvance" : "sendCurrentSms"
    case 2: // Enter New Phone
      return "sendNewSms"
    case 3: // Send SMS to New Phone (Verification Code Phase)
      return "submitPhoneChange"
    default:
      return "sendCurrentSms"
  }
})

// Computed properties for button text and disabled state
const buttonText = computed(() => {
  switch (currentStep.value) {
    case 1: // Verify Current Phone
      if (smsSending.current) {
        return $t("page.login.common.sendingCode")
      }
      return smsSent.current ? $t("common.next") : $t("page.login.common.sendCode")
    case 2: // Enter New Phone
      return $t("page.login.common.sendCode")
    case 3: // Send SMS to New Phone
      if (smsSending.new) {
        return $t("page.login.common.sendingCode")
      }
      return $t("page.profile.confirmPhoneChange")
    default:
      return $t("page.login.common.sendCode")
  }
})

const isButtonDisabled = computed(() => {
  switch (currentStep.value) {
    case 1: // Verify Current Phone
      if (!smsSent.current) {
        return loadingKeys.value.length > 0
      }
      return smsSending.current || model.currentCode.length !== 6
    case 2: // Enter New Phone
      return !model.newPhone || loadingKeys.value.length > 0
    case 3: // Send SMS to New Phone
      return smsSending.new || model.newCode.length !== 6
    default:
      return false
  }
})

function handleCodeComplete(type: "current" | "new", code: string) {
  if (code.length === 6) {
    codeError[type] = ""
  }
}

async function handleConfirmAction() {
  try {
    startTargetLoading("submit")

    switch (confirmButtonAction.value) {
      case "sendCurrentSms":
        await sendCurrentPhoneSms()
        break
      case "validateCurrentCodeAndAdvance":
        await validateCurrentCodeAndAdvance()
        break
      case "sendNewSms":
        await sendNewPhoneSms()
        break
      case "submitPhoneChange":
        await submitPhoneChange()
        break
    }
  }
  finally {
    endTargetLoading("submit")
  }
}

async function sendCurrentPhoneSms() {
  smsSending.current = true
  try {
    const { data, error } = await postSendCodeToCurrentPhone("change_phone")

    if (data?.success) {
      smsSent.current = true
      startCurr()
      message.success($t("page.login.common.sendCodeSuccess"))
    }
    else if (error) {
      throw error
    }
  }
  finally {
    smsSending.current = false
  }
}

async function sendNewPhoneSms() {
  smsSending.new = true
  try {
    // Validate only the new phone field
    await formRef.value?.validate(undefined, (rule) => {
      return rule?.key === "newPhone"
    })

    // Store the original phone number before sending SMS
    originalNewPhone.value = model.newPhone || ""

    const { data, error } = await postSendCode(
      model.newPhone!,
      model.country?.dialCode || "",
      "change_phone",
    )

    if (data?.success) {
      smsSent.new = true
      currentStep.value = 3
      startNew()
      message.success($t("page.login.common.sendCodeSuccess"))
    }
    else if (error) {
      throw error
    }
  }
  finally {
    smsSending.new = false
  }
}

async function validateCurrentCodeAndAdvance() {
  // In a real implementation, you would validate the code with the backend
  // For now, we'll just advance to the next step
  if (model.currentCode.length === 6) {
    currentStep.value = 2
  }
}

async function submitPhoneChange() {
  await validate() // Validate all fields

  const { data, error } = await putChangePhone({
    currentCode: model.currentCode,
    newCode: model.newCode,
    newPhone: model.newPhone!,
    newCountryCode: model.country?.dialCode,
  })

  if (data) {
    message.success($t("page.profile.changePhoneSuccess"))
    await authStore.updateUserInfo()
    modalVisible.value = false
  }
  else if (error) {
    throw error
  }
}

function resetForm() {
  currentStep.value = 1
  stepStatus.value = "process"
  smsSent.current = false
  smsSent.new = false
  model.currentCode = ""
  model.newCode = ""
  model.currentPhone = ""
  model.currentFullPhone = ""
  model.newPhone = ""
  model.fullPhone = ""
  codeError.current = ""
  codeError.new = ""
  originalCurrentPhone.value = ""
  originalNewPhone.value = ""
  stopCurr()
  stopNew()
}

async function handleResendCode(type: "current" | "new") {
  if (type === "current" && isCurrActive.value) {
    message.warning(`Please wait ${currRemaining} seconds before sending again`)
    return
  }

  if (type === "new" && isNewActive.value) {
    message.warning(`Please wait ${newRemaining.value} seconds before sending again`)
    return
  }

  try {
    startTargetLoading("submit")

    if (type === "current") {
      const { data, error } = await postSendCodeToCurrentPhone("change_phone")

      if (data?.success) {
        startCurr()
        model.currentCode = ""
        codeError.current = ""
        message.success($t("page.login.common.sendCodeSuccess"))
      }
      else if (error) {
        throw error
      }
    }
    else {
      const { data, error } = await postSendCode(
        model.newPhone!,
        model.country?.dialCode || "",
        "change_phone",
      )

      if (data?.success) {
        startNew()
        model.newCode = ""
        codeError.new = ""
        message.success($t("page.login.common.sendCodeSuccess"))
      }
      else if (error) {
        throw error
      }
    }
  }
  catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || "Failed to send verification code")
  }
  finally {
    endTargetLoading("submit")
  }
}

function handleBackToPhoneInput() {
  smsSent.new = false
  model.newCode = ""
  codeError.new = ""
  // Only stop the countdown timer if the phone number was changed before sending SMS
  if (originalNewPhone.value !== model.newPhone) {
    stopNew()
  }
  currentStep.value--
}
watch(currentStep, (val) => {
  const el = unrefElement(stepRefs.value[val] as any) as HTMLElement | null
  if (el) {
    el.scrollIntoView()
  }
})
</script>

<style scoped lang="sass">
:deep(.pin-input-container)
  margin-bottom: 1rem

:deep(.n-input-wrapper)
  width: 100%

// Steps styles following protocol-steps pattern
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
