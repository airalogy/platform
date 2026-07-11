<template>
  <n-form ref="formRef" :model="model" :rules="rules" size="large" :show-label="false">
    <div class="mb-6 text-left">
      <h3 class="mb-2 text-lg font-semibold">
        {{ $t("page.login.emailLogin.heading") }}
      </h3>
      <p class="text-gray-600">
        {{ $t("page.login.emailLogin.helper") }}
      </p>
    </div>

    <n-form-item path="email">
      <n-input
        v-model:value="model.email" class="form__input" required
        :placeholder="$t('page.login.common.emailPlaceholder')" @keyup.enter="handleSubmit"
      />
    </n-form-item>
    <n-form-item path="password">
      <n-input
        v-model:value="model.password" class="form__input" show-password-on="click" type="password" required
        :maxlength="30" :placeholder="$t('page.login.common.passwordPlaceholder')" @keyup.enter="handleSubmit"
      >
        <template #password-visible-icon>
          <n-icon :size="16" :component="EyeOutline" />
        </template>
        <template #password-invisible-icon>
          <n-icon :size="16" :component="EyeOffOutline" />
        </template>
      </n-input>
    </n-form-item>
    <n-button
      type="primary" size="large" strong block :loading="authStore.loginLoading" class="mt-10"
      @click="handleSubmit"
    >
      {{ $t("page.login.emailLogin.confirm") }}
    </n-button>
    <div v-if="instanceStore.signupMode === 'open'" class="w-full text-center">
      <span>{{ $t("page.login.common.noAccount") }}</span>
      <n-button
        quaternary class="mt-4 underline"
        @click="routerPushByKey('sign-up')"
      >
        {{ $t("page.login.register.confirm") }}
      </n-button>
    </div>
    <div
      v-if="showDevQuickLogin"
      class="mt-6 rounded border border-dashed border-blue-200 bg-blue-50 px-4 py-3 text-left"
    >
      <div class="text-sm font-semibold text-blue-900">
        {{ $t("page.login.devQuick.title") }}
      </div>
      <p class="mb-3 mt-1 text-xs leading-5 text-blue-700">
        {{ $t("page.login.devQuick.description") }}
      </p>
      <div class="flex flex-wrap gap-2">
        <n-button
          v-for="account in devAccountOptions"
          :key="account.key"
          size="small"
          secondary
          type="primary"
          :disabled="devFixtureLoading && activeDevAccountKey !== account.key"
          :loading="devFixtureLoading && activeDevAccountKey === account.key"
          @click="handleDevQuickLogin(account.key)"
        >
          {{ account.label }}
        </n-button>
      </div>
      <p class="mb-0 mt-3 text-xs leading-5 text-blue-700">
        {{ $t("page.login.devQuick.hint") }}
      </p>
    </div>
  </n-form>
</template>

<script setup lang="ts">
import { createLoginPwdValidator, useFormRules, useNaiveForm } from "@/composables/useForm"
import { useRouterPush } from "@/composables/useRouterPush"
import { type DevQuickstartAccount, postDevQuickstartFixtures } from "@/service/api/auth"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { $t } from "@airalogy/shared/locales"
import EyeOffOutline from "~icons/ion/eye-off-outline"
import EyeOutline from "~icons/ion/eye-outline"
import { computed, reactive, ref } from "vue"

defineOptions({
  name: "PwdLogIn",
})

const { formRef, validate } = useNaiveForm()
const {
  formRules: { user: userFormRules },
} = useFormRules()

interface FormModel {
  email?: string
  password: string
}

const model: FormModel = reactive({
  email: "",
  password: "",
})

const { routerPushByKey } = useRouterPush()
const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const loginPwdValidator = createLoginPwdValidator()
const showDevQuickLogin = import.meta.env.DEV && import.meta.env.VITE_SERVICE_ENV !== "prod"
const devFixtureLoading = ref(false)
const activeDevAccountKey = ref<DevQuickstartAccount["key"] | null>(null)
const devAccountOptions = computed<{ key: DevQuickstartAccount["key"], label: string }[]>(() => [
  { key: "owner", label: $t("page.login.devQuick.owner") },
  { key: "collaborator", label: $t("page.login.devQuick.collaborator") },
  { key: "viewer", label: $t("page.login.devQuick.viewer") },
])

const rules: Record<keyof FormModel, App.Global.FormRule[]> = {
  email: userFormRules.email,
  password: loginPwdValidator,
}

const loginStatus = ref()
async function handleSubmit() {
  try {
    await validate()

    await authStore.login("email", model)
    await authStore.getUserAvatar()
  }
  catch (e) {
    loginStatus.value = "error"
  }
}

async function handleDevQuickLogin(accountKey: DevQuickstartAccount["key"]) {
  try {
    devFixtureLoading.value = true
    activeDevAccountKey.value = accountKey

    const { data } = await postDevQuickstartFixtures()
    if (!data) {
      window.$message?.error($t("page.login.devQuick.missingAccount"))
      return
    }

    const account = data?.accounts.find(item => item.key === accountKey)
    if (!account) {
      window.$message?.error($t("page.login.devQuick.missingAccount"))
      return
    }

    model.email = account.email
    model.password = account.password
    if (data.warnings.length > 0) {
      window.$message?.warning($t("page.login.devQuick.protocolExamplesUnavailable"))
    }
    await authStore.login("email", {
      email: account.email,
      password: account.password,
    })
    await authStore.getUserAvatar()
  }
  finally {
    devFixtureLoading.value = false
    activeDevAccountKey.value = null
  }
}
</script>

<style scoped lang="sass">
@use "../styles/common" as *
</style>
