<template>
  <div class="step-container">
    <!-- Phone Input Phase -->
    <div v-if="!codeSent" class="phone-input-phase">
      <div class="mb-6 text-left">
        <h3 class="mb-2 text-lg font-semibold">
          {{ $t("page.login.codeLogin.heading") }}
        </h3>
        <p class="text-gray-600">
          {{ $t("page.login.codeLogin.helper") }}
        </p>
      </div>

      <n-form
        ref="formRef"
        :model="model"
        :rules="rules"
        size="large"
        :show-label="false"
        @keydown.enter="handlePhoneSubmit"
      >
        <n-form-item path="phone">
          <country-phone-input
            v-model="model.phone"
            v-model:full-phone="model.fullPhone"
            v-model:country="model.country"
            size="large"
            :default-country="model.country?.isoCode"
            :placeholder="$t('page.login.common.phonePlaceholder')"
          />
        </n-form-item>

        <n-button
          type="primary"
          size="large"
          strong
          block
          class="mt-6"
          :disabled="!model.phone || loadingKeys.length > 0"
          :loading="loadingState.code"
          @click="handleSendCode"
        >
          {{ $t("page.login.common.sendCode") }}
        </n-button>
      </n-form>

      <div class="mt-6 w-full text-center">
        <span class="text-gray-600">{{ $t("page.login.common.noAccount") }}</span>
        <n-button
          quaternary
          class="ml-1 underline !hover:text-primary"
          @click="routerPushByKey('sign-up')"
        >
          {{ $t("page.login.register.confirm") }}
        </n-button>
      </div>
    </div>

    <!-- Verification Code Phase -->
    <div v-else class="verification-phase">
      <div class="mb-8 text-center">
        <h3 class="mb-2 text-lg font-semibold">
          {{ $t("page.login.codeLogin.verificationTitle") }}
        </h3>
        <p class="text-gray-600">
          {{ $t("page.login.codeLogin.codeSentTo") }}
        </p>
        <div class="flex items-center justify-center gap-2">
          <n-icon v-if="model.country?.icon" :component="model.country.icon" size="18" />
          <p class="text-primary font-medium">
            {{ maskedPhone }}
          </p>
        </div>
      </div>

      <div class="verification-form" @keydown.enter="handleCodeSubmit">
        <div class="mb-6">
          <label class="mb-3 block text-sm text-gray-700 font-medium">
            {{ $t('page.login.common.codePlaceholder') }}
          </label>
          <pin-input
            v-model="model.code"
            :length="6"
            :error="codeError"
            :disabled="loadingKeys.length > 0"
            auto-focus
            @complete="handleCodeComplete"
          />
        </div>

        <n-button
          type="primary"
          size="large"
          strong
          block
          :disabled="model.code.length !== 6"
          class="mb-4"
          @click="handleSubmit"
        >
          {{ $t("page.login.codeLogin.confirm") }}
        </n-button>

        <div class="mb-4 text-center">
          <span class="text-gray-600">{{ $t("page.login.common.didntReceiveCode") }}</span>
          <n-button
            quaternary
            type="primary"
            :disabled="isActive"
            :loading="loadingState.code"
            class="ml-1"
            @click="handleResendCode"
          >
            {{ isActive ? $t("page.login.common.resendCooldown", { seconds: remaining }) : $t("page.login.common.resend") }}
          </n-button>
        </div>

        <div class="text-center">
          <n-button
            quaternary
            class="text-gray-500"
            @click="handleBackToPhone"
          >
            ← {{ $t("page.login.common.changePhoneNumber") }}
          </n-button>
        </div>
        <!--
        <div class="mt-6 w-full text-center">
          <n-button quaternary type="primary" class="inline-block">
            {{ $t("page.login.codeLogin.notAvailable") }}
          </n-button>
        </div> -->
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useLoading } from "@/composables"
import { createRequiredRule, useFormRules, useNaiveForm } from "@/composables/useForm"
import { useRouterPush } from "@/composables/useRouterPush"
import { postSendCode } from "@/service/api/auth"
import { useAuthStore } from "@/store/modules/auth"
import CountryPhoneInput from "@airalogy/components/country-phone-input.vue"
import PinInput from "@airalogy/components/pin-input.vue"
import { useClosableMessage } from "@airalogy/composables"
import { countryData, type CountryData } from "@airalogy/shared/constants/country-code"
import { $t } from "@airalogy/shared/locales"
import { useCountdown } from "@vueuse/core"
import { useDialog } from "naive-ui"
import { computed, reactive, ref } from "vue"

defineOptions({
  name: "CodeLogIn",
})

const emits = defineEmits<IEmits>()
const { formRef, validate } = useNaiveForm()
const {
  formRules: { user: userFormRules },
} = useFormRules()

interface FormModel {
  phone?: string
  fullPhone?: string
  code: string
  country?: CountryData | null
}
interface IEmits {
  (e: "login:code", val: FormModel): void
}

const model: FormModel = reactive({
  phone: "",
  fullPhone: "",
  code: "",
  country: countryData.find(country => country.isoCode === "CN") || null,
})

const codeSent = ref(false)
const codeError = ref("")

const authStore = useAuthStore()

const { loadingState, startTargetLoading, endTargetLoading, loadingKeys } = useLoading(false, ["code"])

const { remaining, start, stop, isActive } = useCountdown(60, {
  onComplete() {
    stop()
  },
})

const rules = computed((): Record<"phone" | "code", App.Global.FormRule[]> => {
  if (model.country?.isoCode === "CN") {
    return {
      phone: userFormRules.phone,
      code: userFormRules.code,
    }
  }

  return {
    phone: [createRequiredRule($t("form.phone.required"))],
    code: userFormRules.code,
  }
})

const { routerPushByKey } = useRouterPush()

const message = useClosableMessage()
const dialog = useDialog()

// Common error handling for postSendCode
function handleSendCodeError(error: any, context: "send" | "resend") {
  if (error?.response?.status === 400 && error?.response?.data?.detail === "User not found") {
    // message.error("No account found with this phone number. Please sign up first.", {
    //   duration: 6000,
    //   closable: true,
    // })

    // Show additional sign-up option
    dialog?.info({
      title: $t("page.login.codeLogin.noAccountTitle"),
      content: $t("page.login.codeLogin.noAccountContent"),
      positiveText: $t("page.login.register.confirm"),
      negativeText: $t("common.cancel"),
      onPositiveClick: () => {
        routerPushByKey("sign-up")
      },
    })
  }
  else {
    // Generic error handling for other cases
    const errorMessage = error?.response?.data?.detail
      || error?.message
      || (context === "send"
        ? $t("page.login.codeLogin.sendFailed")
        : $t("page.login.codeLogin.resendFailed"))
    message.error(errorMessage)

    // Log other errors for debugging
    console.error(`${context} Code Error:`, {
      status: error?.response?.status,
      detail: error?.response?.data?.detail,
      message: error?.message,
      phone: model.phone,
      dialCode: model.country?.dialCode,
    })
  }
}

const maskedPhone = computed(() => {
  const phone = model.phone || ""
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

function handleCodeComplete(code: string) {
  if (code.length === 6) {
    codeError.value = ""
    // Code is complete, user can now submit
  }
}

function handlePhoneSubmit(event: KeyboardEvent) {
  // Prevent default form submission
  event.preventDefault()

  // Check if send code button would be disabled
  if (!model.phone || loadingKeys.value.length > 0) {
    return
  }

  // Call the existing send code handler
  handleSendCode()
}

function handleCodeSubmit(event: KeyboardEvent) {
  // Prevent default form submission
  event.preventDefault()

  // Check if submit button would be disabled
  if (model.code.length !== 6) {
    return
  }

  // Call the existing submit handler
  handleSubmit()
}

async function handleSendCode() {
  if (isActive.value) {
    message.warning($t("page.login.common.resendCooldown", { seconds: remaining.value }))
    return
  }

  try {
    startTargetLoading("code")
    // Validate only phone field
    await validate(undefined, (rule) => {
      return !rules.value.phone.includes(rule)
    })

    // Add diagnostic logging for phone number formatting
    console.log("Send Code Debug Info:", {
      phone: model.phone,
      dialCode: model.country?.dialCode,
      fullPhone: model.fullPhone,
      country: model.country?.name,
      isoCode: model.country?.isoCode,
      formattedNumber: `${model.country?.dialCode || ""}${model.phone}`,
    })

    const { data, error } = await postSendCode(model.phone!, model.country?.dialCode || "", "signin")

    if (data && data.success) {
      codeSent.value = true
      start()
      message.success($t("page.login.common.sendCodeSuccess"))
    }
    else if (error) {
      // Handle the error from postSendCode response
      throw error
    }
  }
  catch (error: any) {
    handleSendCodeError(error, "send")
  }
  finally {
    endTargetLoading("code")
  }
}

async function handleResendCode() {
  if (isActive.value) {
    message.warning($t("page.login.common.resendCooldown", { seconds: remaining.value }))
    return
  }

  try {
    startTargetLoading("code")

    // Add diagnostic logging for resend
    console.log("Resend Code Debug Info:", {
      phone: model.phone,
      dialCode: model.country?.dialCode,
      fullPhone: model.fullPhone,
      country: model.country?.name,
    })

    const { data, error } = await postSendCode(model.phone!, model.country?.dialCode || "", "signin")

    if (data && data.success) {
      start()
      model.code = ""
      codeError.value = ""
      message.success($t("page.login.common.sendCodeSuccess"))
    }
    else if (error) {
      // Handle the error from postSendCode response
      throw error
    }
  }
  catch (error: any) {
    handleSendCodeError(error, "resend")
  }
  finally {
    endTargetLoading("code")
  }
}

function handleBackToPhone() {
  codeSent.value = false
  model.code = ""
  codeError.value = ""
  stop()
}

async function handleSubmit() {
  if (model.code.length !== 6) {
    codeError.value = "Please enter the complete code"
    return
  }

  try {
    codeError.value = ""
    await validate(undefined, (rule) => {
      return !rules.value.phone.includes(rule)
    })
    await authStore.login("code", {
      ...model,
      countryCode: model.country?.dialCode.slice(1),
    })
    await authStore.getUserAvatar()
  }
  catch (e) {
    if ((e as Error).message.includes("code") || (e as Error).message.includes("verification")) {
      codeError.value = "Invalid code. Please try again."
    }
    message.error((e as Error).message)
  }
}
</script>

<style scoped lang="sass">
@use "../styles/common" as *

.step-container
  width: 100%

.verification-phase
  max-width: 400px
  margin: 0 auto

.verification-form
  padding: 0 20px

:deep(.pin-input-container)
  margin-bottom: 1rem

:deep(.n-input-wrapper)
  width: 100%
</style>
