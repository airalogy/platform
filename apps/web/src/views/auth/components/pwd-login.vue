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
    <div class="w-full text-center">
      <span>{{ $t("page.login.common.noAccount") }}</span>
      <n-button
        quaternary class="mt-4 underline"
        @click="routerPushByKey('sign-up')"
      >
        {{ $t("page.login.register.confirm") }}
      </n-button>
    </div>
  </n-form>
</template>

<script setup lang="ts">
import { createLoginPwdValidator, useFormRules, useNaiveForm } from "@/composables/useForm"
import { useRouterPush } from "@/composables/useRouterPush"
import { useAuthStore } from "@/store/modules/auth"
import { $t } from "@airalogy/shared/locales"
import EyeOffOutline from "~icons/ion/eye-off-outline"
import EyeOutline from "~icons/ion/eye-outline"
import { reactive } from "vue"

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
const loginPwdValidator = createLoginPwdValidator()

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
</script>

<style scoped lang="sass">
@use "../styles/common" as *
</style>
