<template>
  <div class="phone-signup-container">
    <div v-if="currentStep === 1">
      <div class="step-hint mb-2">
        <span class="text-xs text-gray-400">{{ $t("page.login.phoneSignUp.step1") }}</span>
      </div>
      <verify-phone-step
        v-model="stepPhoneData"
        type="signup"
        :show-back="false"
        :confirm-button="$t('page.login.phoneSignUp.verifyButton')"
        :user-data="{}"
        @confirm="handlePhoneVerified"
      />
    </div>

    <div v-if="currentStep === 2">
      <div class="step-hint mb-2">
        <span class="text-xs text-gray-400">{{ $t("page.login.phoneSignUp.step2") }}</span>
      </div>
      <n-alert type="success" class="mb-5">
        {{ $t("page.login.phoneSignUp.phoneVerified", { phone: verifiedPhoneLabel }) }}
      </n-alert>
      <account-credentials-step
        v-model="stepAccountData"
        show-back
        :email-readonly="Boolean(invitation)"
        @next="handleAccountCredentialsComplete"
        @back="currentStep = 1"
      />
    </div>

    <div v-if="currentStep === 3">
      <div class="step-hint mb-2">
        <span class="text-xs text-gray-400">
          {{ $t("page.login.phoneSignUp.step3") }} • {{ $t("page.login.phoneSignUp.finalStep") }}
        </span>
      </div>
      <user-info-step
        v-model="stepProfileData"
        :loading="authStore.loginLoading || invitationLoading"
        :next-label="$t('page.login.phoneSignUp.confirmButton')"
        @next="handleSignupComplete"
        @back="currentStep = 2"
      />
    </div>

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
import type { CountryData } from "@airalogy/shared/constants/country-code"
import { useRouterPush } from "@/composables/useRouterPush"
import { fetchInvitation, type InvitationInfo } from "@/service/api/instance"
import { useAuthStore } from "@/store/modules/auth"
import { useClosableMessage } from "@airalogy/composables"
import { countryData } from "@airalogy/shared/constants/country-code"
import { $t } from "@airalogy/shared/locales"
import AccountCredentialsStep from "./account-credentials-step.vue"
import UserInfoStep from "./user-info-step.vue"
import VerifyPhoneStep from "./verify-phone-step.vue"

interface AccountData {
  email: string
  password: string
  confirmPassword: string
}

interface ProfileData {
  username: string
  displayName: string
}

interface PhoneData {
  phone: string
  fullPhone?: string
  country?: CountryData | null
}

interface VerifiedPhoneData extends Partial<PhoneData> {
  countryCode?: string
  signupVerificationToken?: string
}

interface CompleteFormModel extends AccountData, ProfileData {
  signupVerificationToken: string
  inviteToken?: string
}

defineOptions({
  name: "PhoneSignUp",
})

const emit = defineEmits<{
  (e: "sign-up:password", val: CompleteFormModel): void
}>()

const { routerPushByKey } = useRouterPush()
const route = useRoute()
const authStore = useAuthStore()
const message = useClosableMessage()

const currentStep = ref(1)
const signupVerificationToken = ref("")
const verifiedCountryCode = ref("")
const stepAccountData = ref<AccountData>({
  email: "",
  password: "",
  confirmPassword: "",
})
const stepProfileData = ref<ProfileData>({
  username: "",
  displayName: "",
})
const stepPhoneData = ref<PhoneData>({
  phone: "",
  country: countryData.find(country => country.isoCode === "CN") || null,
})
const inviteToken = computed(() => typeof route.query.inviteToken === "string" ? route.query.inviteToken : "")
const invitation = ref<InvitationInfo | null>(null)
const invitationLoading = ref(Boolean(inviteToken.value))
const verifiedPhoneLabel = computed(() => {
  const dialCode = verifiedCountryCode.value ? `+${verifiedCountryCode.value}` : ""
  return `${dialCode} ${stepPhoneData.value.phone}`.trim()
})

function handlePhoneVerified(data: VerifiedPhoneData) {
  if (!data.signupVerificationToken || !data.countryCode) {
    return
  }
  signupVerificationToken.value = data.signupVerificationToken
  verifiedCountryCode.value = data.countryCode
  currentStep.value = 2
}

function handleAccountCredentialsComplete(data: AccountData) {
  stepAccountData.value = data
  currentStep.value = 3
}

async function handleSignupComplete(data: ProfileData) {
  stepProfileData.value = data
  const payload: CompleteFormModel = {
    ...stepAccountData.value,
    ...stepProfileData.value,
    signupVerificationToken: signupVerificationToken.value,
    inviteToken: inviteToken.value || undefined,
  }
  const result = await authStore.signup("phone", payload)
  if (result === true) {
    message.success($t("page.login.phoneSignUp.success"))
    emit("sign-up:password", payload)
    return
  }

  const detail = (result as any)?.response?.data?.detail
  message.error(typeof detail === "string" ? detail : $t("page.login.phoneSignUp.failure"))
  if (detail === "Signup phone verification is invalid or expired") {
    signupVerificationToken.value = ""
    currentStep.value = 1
  }
}

async function loadInvitation() {
  if (!inviteToken.value) {
    invitationLoading.value = false
    return
  }
  const { data } = await fetchInvitation(inviteToken.value)
  invitation.value = data || null
  if (data) {
    stepAccountData.value.email = data.email
  }
  invitationLoading.value = false
}

onMounted(loadInvitation)
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
