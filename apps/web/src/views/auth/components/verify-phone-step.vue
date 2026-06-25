<template>
  <div class="step-container">
    <!-- Phone Input Phase -->
    <div v-if="!codeSent" class="phone-input-phase">
      <div class="mb-6 text-left">
        <h3 class="mb-2 text-lg font-semibold">
          {{ $t("page.login.verifyPhone.title") }}
        </h3>
        <p class="text-gray-600">
          {{ $t("page.login.verifyPhone.helper") }}
        </p>
      </div>

      <n-form ref="formRef" :model="model" :rules="rules" size="large" :show-label="false" @keydown.enter="handleSendCode">
        <n-form-item
          path="phone"
          :validation-status="phoneInputFeedback ? 'error' : undefined"
          :feedback="phoneInputFeedback"
        >
          <n-tooltip trigger="focus" placement="top-start" class="max-w-70%">
            <template #trigger>
              <country-phone-input
                v-model="model.phone"
                v-model:full-phone="model.fullPhone"
                v-model:country="model.country"
                :loading="loadingState.sendCode"
                size="large"
                default-country="CN"
                :placeholder="$t('page.login.common.phonePlaceholder')"
              />
            </template>
            {{ $t("page.login.verifyPhone.permanentHint") }}
          </n-tooltip>
        </n-form-item>

        <div class="mt-10 flex gap-3">
          <n-button
            size="large"
            plain
            class="flex-1"
            @click="handleBack"
          >
            {{ $t("page.login.common.back") }}
          </n-button>
          <n-button
            type="primary"
            size="large"
            strong
            class="flex-1"
            :disabled="!model.phone || !!loadingKeys.length"
            :loading="loadingState.sendCode"
            @click="handleSendCode"
          >
            {{ $t("page.login.common.sendCode") }}
          </n-button>
        </div>
      </n-form>
    </div>

    <!-- Verification Code Phase -->
    <div v-else class="verification-phase">
      <div class="mb-8 text-center">
        <h3 class="mb-2 text-lg font-semibold">
          {{ $t("page.login.verifyPhone.verificationTitle") }}
        </h3>
        <p class="text-gray-600">
          {{ $t("page.login.verifyPhone.codeSentTo") }}
        </p>
        <div class="flex items-center justify-center gap-2">
          <n-icon v-if="model.country?.icon" :component="model.country.icon" size="18" />
          <p class="text-primary font-medium">
            {{ maskedPhone }}
          </p>
        </div>
      </div>

      <div class="verification-form">
        <div class="mb-6">
          <label class="mb-3 block text-sm text-gray-700 font-medium">
            {{ $t("page.login.verifyPhone.enterCodeLabel") }}
          </label>
          <pin-input
            v-model="verificationCode"
            :length="6"
            :error="verificationError"
            :disabled="loading"
            auto-focus
            @complete="handleCodeComplete"
            @confirm="handleVerify"
          />
        </div>

        <n-button
          type="primary"
          size="large"
          strong
          block
          :disabled="verificationCode.length !== 6 || loading"
          :loading="loadingState.verify"
          class="mb-4"
          @click="handleVerify"
        >
          {{ props.confirmButton }}
        </n-button>

        <div class="text-center">
          <span class="text-gray-600">{{ $t("page.login.common.didntReceiveCode") }}</span>
          <n-button
            quaternary
            type="primary"
            :disabled="isActive || loading"
            :loading="loadingState.resend"
            class="ml-1"
            @click="handleResendCode"
          >
            {{ isActive ? $t("page.login.common.resendCooldown", { seconds: remaining }) : $t("page.login.common.resend") }}
          </n-button>
        </div>

        <div class="mt-6 text-center">
          <n-button
            quaternary
            class="text-gray-500"
            @click="handleBackToPhone"
          >
            ← {{ $t("page.login.common.changePhoneNumber") }}
          </n-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { CountryData } from "@airalogy/shared/constants"
import { useLoading } from "@/composables"
import { createRequiredRule, useFormRules, useNaiveForm } from "@/composables/useForm"
import { postSendCode } from "@/service/api/auth"
import CountryPhoneInput from "@airalogy/components/country-phone-input.vue"
import PinInput from "@airalogy/components/pin-input.vue"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { useCountdown } from "@vueuse/core"

interface FormModel {
  phone: string
  fullPhone?: string
  country?: CountryData | null
}

interface UserData {
  email: string
  password: string
  confirmPassword: string
  username: string
  displayName: string
}

interface Props {
  modelValue: FormModel
  userData: Partial<UserData>
  type: "signup" | "signin" | "reset_password"
  confirmButton: string
}

const props = defineProps<Props>()

const emit = defineEmits<IEmits>()

interface IEmits {
  (e: "update:modelValue", value: FormModel): void
  (e: "back"): void
  (e: "confirm", data: Partial<UserData & FormModel > & { code: string }): void
}

const model = useVModel(props, "modelValue", emit)

const codeSent = ref(false)
const verificationCode = ref("")
const verificationError = ref("")
const loading = ref(false)
const phoneInputFeedback = ref<string | undefined>(undefined)

const { formRef, validate } = useNaiveForm()
const {
  formRules: { user: userFormRules },
} = useFormRules()
const { loadingState, startTargetLoading, endTargetLoading, loadingKeys } = useLoading(false, ["sendCode", "verify", "resend"])
const message = useClosableMessage()

const { remaining, start, stop, isActive } = useCountdown(60, {
  onComplete() {
    stop()
  },
})

const rules = computed((): Record<"phone" | "code", App.Global.FormRule[]> => {
  if (model.value.country?.isoCode === "CN") {
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
const maskedPhone = computed(() => {
  const phone = model.value.phone
  const country = model.value.country

  if (!phone || phone.length <= 4) {
    return phone || ""
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

async function handleSendCode() {
  try {
    startTargetLoading("sendCode")
    await validate()

    const { data, error } = await postSendCode(model.value.phone, model.value.country?.dialCode || "", props.type)
    if (data && data.success) {
      codeSent.value = true
      start()
      message.success($t("page.login.common.sendCodeSuccess"))
      phoneInputFeedback.value = undefined
    }
    else if ((error as any)?.response?.data?.detail) {
      phoneInputFeedback.value = (error as any)?.response?.data?.detail
    }
  }
  catch (error) {
    message.error((error as Error).message || $t("page.login.verifyPhone.sendFailed"))
  }
  finally {
    endTargetLoading("sendCode")
  }
}

function handleCodeComplete(code: string) {
  if (code.length === 6) {
    verificationError.value = ""
    // Code complete - user can now manually click verify button
  }
}

async function handleVerify() {
  if (verificationCode.value.length !== 6) {
    verificationError.value = $t("page.login.verifyPhone.codeIncomplete")
    return
  }

  try {
    startTargetLoading("verify")
    verificationError.value = ""

    // Complete the signup process
    const inputData = {
      ...props.userData,
      ...model.value,
      countryCode: model.value.country?.dialCode?.slice(1),
      code: verificationCode.value,
    }

    emit("confirm", inputData)
  }
  catch (error) {
    verificationError.value = $t("page.login.verifyPhone.codeInvalid")
    message.error((error as Error).message || $t("page.login.verifyPhone.verifyFailed"))
  }
  finally {
    endTargetLoading("verify")
  }
}

async function handleResendCode() {
  if (isActive.value) {
    message.warning($t("page.login.common.resendCooldown", { seconds: remaining.value }))
    return
  }

  try {
    startTargetLoading("resend")

    await postSendCode(model.value.phone, model.value.country?.dialCode || "", "signup")

    start()
    verificationCode.value = ""
    verificationError.value = ""
    message.success($t("page.login.common.sendCodeSuccess"))
  }
  catch (error) {
    message.error((error as Error).message || $t("page.login.verifyPhone.resendFailed"))
  }
  finally {
    endTargetLoading("resend")
  }
}

function handleBack() {
  emit("back")
}

function handleBackToPhone() {
  codeSent.value = false
  verificationCode.value = ""
  verificationError.value = ""
  stop()
}

defineExpose({
  verificationError,
})
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
