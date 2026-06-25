<template>
  <n-form ref="formRef" :model="model" :rules="rules" size="large" :show-label="false" @keydown.enter="handleNext">
    <div class="mb-6 text-left">
      <h3 class="mb-2 text-lg font-semibold">
        {{ $t("page.login.resetPwd.title") }}
      </h3>
      <p class="text-gray-600">
        {{ $t("page.login.resetPwd.helper") }}
      </p>
    </div>

    <n-form-item path="password">
      <n-input
        v-model:value="model.password"
        show-password-on="click"
        type="password"
        :minlength="8"
        :maxlength="32"
        :placeholder="$t('page.login.common.newPasswordPlaceholder')"
      >
        <template #password-visible-icon>
          <n-icon :size="16" :component="EyeOutline" />
        </template>
        <template #password-invisible-icon>
          <n-icon :size="16" :component="EyeOffOutline" />
        </template>
      </n-input>
    </n-form-item>

    <n-form-item path="confirmPassword">
      <n-input
        v-model:value="model.confirmPassword"
        show-password-on="click"
        type="password"
        :maxlength="32"
        :placeholder="$t('page.login.common.confirmPasswordPlaceholder')"
        @keyup.enter="handleNext"
      >
        <template #password-visible-icon>
          <n-icon :size="16" :component="EyeOutline" />
        </template>
        <template #password-invisible-icon>
          <n-icon :size="16" :component="EyeOffOutline" />
        </template>
      </n-input>
    </n-form-item>

    <div class="mt-6 flex justify-between">
      <n-button size="large" @click="handleBack">
        {{ $t("page.login.common.back") }}
      </n-button>
      <n-button type="primary" size="large" strong @click="handleNext">
        {{ $t("page.login.resetPwd.title") }}
      </n-button>
    </div>
  </n-form>
</template>

<script setup lang="ts">
import type { FormItemRule } from "naive-ui"
import { createPasswordValidator, useNaiveForm } from "@/composables/useForm"
import { $t } from "@airalogy/shared/locales"
import EyeOffOutline from "~icons/ion/eye-off-outline"
import EyeOutline from "~icons/ion/eye-outline"
import { reactive } from "vue"

defineOptions({
  name: "ResetPasswordStep",
})

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "complete", model: { password: string, confirmPassword: string }): void
  (e: "back"): void
}

const { formRef, validate } = useNaiveForm()
const passwordValidator = createPasswordValidator()

const model = reactive({
  password: "",
  confirmPassword: "",
})

const rules: Record<string, FormItemRule[]> = {
  password: passwordValidator,
  confirmPassword: [
    ...passwordValidator,
    {
      validator: (_, value) => {
        if (value !== model.password) {
          return new Error($t("form.confirmPwd.invalid"))
        }
        return true
      },
      trigger: ["blur", "change"],
    },
  ],
}

async function handleNext() {
  try {
    await validate()
    emit("complete", model)
  }
  catch (error) {
    // Form validation failed
  }
}

function handleBack() {
  emit("back")
}
</script>
