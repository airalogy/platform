<template>
  <div class="step-container">
    <transition name="fade" mode="out-in">
      <verify-phone-step
        v-if="currentStep === 0"
        ref="phoneStepRef"
        v-model="model"
        :user-data="model"
        type="reset_password"
        confirm-button="New password"
        @confirm="handleNext"
      />
      <reset-password-step v-else @complete="handleComplete" />
    </transition>

    <div class="mt-6 w-full text-center">
      <n-button
        quaternary
        class="text-decoration-line: underline; text-decoration-style: solid"
        @click="handleBackToLogin"
      >
        Back to Login
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useLoading } from "@/composables"
import { useRouterPush } from "@/composables/useRouterPush"
import { useAuthStore } from "@/store/modules/auth"
import { useClosableMessage } from "@airalogy/composables"
import { countryData, type CountryData } from "@airalogy/shared/constants"
import { reactive, ref } from "vue"
import ResetPasswordStep from "./reset-password-step.vue"
import VerifyPhoneStep from "./verify-phone-step.vue"

defineOptions({
  name: "ForgetPwd",
})

const authStore = useAuthStore()
const message = useClosableMessage()
const { routerPushByKey } = useRouterPush()
const { loading, startLoading, endLoading } = useLoading()

const currentStep = ref(0)

interface FormModel {
  phone: string
  fullPhone?: string
  country?: CountryData | null
  code: string
  password: string
  confirmPassword: string
}

const model = reactive<FormModel>({
  phone: "",
  fullPhone: "",
  country: countryData.find(country => country.isoCode === "CN") || null,
  code: "",
  password: "",
  confirmPassword: "",
})

const phoneStepRef = ref<{ verificationError: Ref<string> }>()

function handleNext(data: any) {
  if (currentStep.value === 0) {
    Object.assign(model, data)
    currentStep.value++
  }
}

async function handleComplete(data: any) {
  if (currentStep.value === 0) {
    model.code = data.code
    currentStep.value++
  }
  else if (currentStep.value === 1) {
    Object.assign(model, data)
    await handleResetPassword()
  }
}

function handleBack() {
  if (currentStep.value > 0) {
    currentStep.value--
  }
  else {
    routerPushByKey("login")
  }
}

function handleBackToLogin() {
  routerPushByKey("login")
}

async function handleResetPassword() {
  try {
    startLoading()
    await authStore.changePassword(model)
    message.success("Password reset successfully")
    setTimeout(() => routerPushByKey("login"), 1500)
  }
  catch (error) {
    message.error("Password reset failed")
  }
  finally {
    endLoading()
  }
}
</script>

<style scoped lang="sass">
.step-container
  width: 100%

.fade-enter-active,
.fade-leave-active
  transition: opacity 0.3s ease

.fade-enter-from,
.fade-leave-to
  opacity: 0
</style>
