<template>
  <div class="phone-signup-container">
    <!-- Step 1: Email and Password -->
    <div v-if="currentStep === 1">
      <div class="step-hint mb-2">
        <span class="text-xs text-gray-400">{{ $t("page.login.phoneSignUp.step1") }}</span>
      </div>
      <account-credentials-step
        v-model="stepAccountData"
        @next="handleAccountCredentialsComplete"
      />
    </div>

    <!-- Step 2: Username and Display Name -->
    <div v-if="currentStep === 2">
      <div class="mb-2 flex items-center justify-between">
        <span class="step-hint text-xs text-gray-400">{{ $t("page.login.phoneSignUp.step2") }}</span>
      </div>
      <user-info-step
        v-model="stepProfileData"
        @next="handleUserInfoComplete"
        @back="handleGoBackToStep1"
      />
    </div>

    <!-- Step 3: Phone and Verification -->
    <div v-if="currentStep === 3">
      <div class="mb-2 flex items-center justify-between">
        <span class="step-hint text-xs text-gray-400">
          {{ $t("page.login.phoneSignUp.step3") }} • {{ $t("page.login.phoneSignUp.finalStep") }}
        </span>
        <n-dropdown
          :options="backButtonOptions"
          trigger="hover"
          size="small"
          @select="handleStepNavigation"
        >
          <n-button quaternary size="tiny">
            <template #icon>
              <n-icon>
                <icon-mdi-chevron-left />
              </n-icon>
            </template>
            <span class="text-xs">{{ $t("page.login.phoneSignUp.jumpToStep") }}</span>
          </n-button>
        </n-dropdown>
      </div>
      <verify-phone-step
        ref="phoneStepRef"
        v-model="stepPhoneData"
        type="signup"
        :confirm-button="$t('page.login.phoneSignUp.confirmButton')"
        :user-data="combinedUserData"
        @back="handleGoBackToStep2"
        @confirm="handleSignupComplete($event as CompleteFormModel)"
      />
    </div>

    <!-- Footer with sign in link -->
    <div class="mt-6 w-full text-center">
      <span>{{ $t("page.login.common.alreadyHaveAccount") }}</span>
      <n-button
        quaternary
        class="mt-4 underline !hover:text-primary"
        @click="routerPushByKey('login')"
      >
        {{ $t("page.login.emailLogin.confirm") }}
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouterPush } from "@/composables/useRouterPush"
import { useClosableMessage } from "@airalogy/composables"
import { countryData, type CountryData } from "@airalogy/shared/constants/country-code"
import { $t } from "@airalogy/shared/locales"
import { useAuthStore } from "../../../store/modules/auth"
import AccountCredentialsStep from "./account-credentials-step.vue"
import UserInfoStep from "./user-info-step.vue"
import VerifyPhoneStep from "./verify-phone-step.vue"

defineOptions({
  name: "PhoneSignUp",
})

const emit = defineEmits<IEmits>()

interface Step1Data {
  email: string
  password: string
  confirmPassword: string
}

interface Step2Data {
  username: string
  displayName: string
}

interface Step3Data {
  phone: string
  fullPhone?: string
  country?: CountryData | null
}

interface CompleteFormModel {
  email: string
  password: string
  confirmPassword: string
  username: string
  displayName: string
  phone: string
  code: string
}

interface IEmits {
  (e: "sign-up:password", val: CompleteFormModel): void
}

const { routerPushByKey } = useRouterPush()

const currentStep = ref(1)

const stepAccountData = ref<Step1Data>({
  email: "",
  password: "",
  confirmPassword: "",
})

const stepProfileData = ref<Step2Data>({
  username: "",
  displayName: "",
})

const stepPhoneData = ref<Step3Data>({
  phone: "",
  country: countryData.find(country => country.isoCode === "CN") || null,
})
const phoneStepRef = ref<{ verificationError: Ref<string> }>()

const combinedUserData = computed(() => ({
  ...stepAccountData.value,
  ...stepProfileData.value,
}))

const backButtonOptions = computed(() => {
  const options = []

  if (currentStep.value >= 2) {
    options.push({
      label: $t("page.login.phoneSignUp.step1Label"),
      key: 1,
    })
  }

  if (currentStep.value >= 3) {
    options.push({
      label: $t("page.login.phoneSignUp.step2Label"),
      key: 2,
    })
  }

  return options
})

function handleStepNavigation(key: number) {
  currentStep.value = key
}

function handleAccountCredentialsComplete(data: Step1Data) {
  stepAccountData.value = data
  currentStep.value = 2
}

function handleUserInfoComplete(data: Step2Data) {
  stepProfileData.value = data
  currentStep.value = 3
}

function handleGoBackToStep1() {
  currentStep.value = 1
}

function handleGoBackToStep2() {
  currentStep.value = 2
}

const authStore = useAuthStore()
const message = useClosableMessage()
async function handleSignupComplete(data: CompleteFormModel) {
  if (!phoneStepRef.value) {
    return
  }

  const res = await authStore.signup("phone", data)

  const { verificationError } = phoneStepRef.value
  if (res === true) {
    message.success($t("page.login.phoneSignUp.success"))
    emit("sign-up:password", data)
  }
  else if (res) {
    const msg = (res as any)?.response?.data?.detail

    if (typeof msg === "string") {
      verificationError.value = msg
    }
    else {
      verificationError.value = $t("page.login.phoneSignUp.failure")
    }
  }
}
// onMounted(() => {
//   handleSignupComplete({
//     email: "test@test.com",
//     password: "123456",
//     confirmPassword: "123456",
//     username: "test",
//     displayName: "test",
//     phone: "1234567890",
//     code: "123456",
//   })
// })
</script>

<style scoped lang="sass">
@use "../styles/common" as *

.phone-signup-container
  width: 100%

.step-hint
  font-weight: 400

:deep(.n-input-wrapper)
  width: 100%
</style>
