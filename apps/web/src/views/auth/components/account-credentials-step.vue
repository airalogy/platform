<template>
  <div class="step-container">
    <div class="mb-6 text-left">
      <h3 class="mb-2 text-lg font-semibold">
        {{ $t("page.login.register.createAccountTitle") }}
      </h3>
      <p class="text-gray-600">
        {{ $t("page.login.register.createAccountHelper") }}
      </p>
    </div>

    <n-form ref="formRef" :model="model" :rules="rules" size="large" :show-label="false">
      <n-form-item path="email">
        <n-input
          v-model:value="model.email"
          class="form__input"
          :readonly="props.emailReadonly"
          :placeholder="$t('page.login.common.emailPlaceholder')"
        />
      </n-form-item>

      <n-form-item path="password">
        <n-input
          v-model:value="model.password"
          class="form__input"
          show-password-on="click"
          type="password"
          required
          :minlength="8"
          :maxlength="32"
          :placeholder="$t('page.login.common.passwordPlaceholder')"
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
          class="form__input"
          show-password-on="click"
          type="password"
          autocomplete="new-password"
          required
          :maxlength="30"
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

      <div class="mt-10 flex gap-3">
        <n-button
          v-if="props.showBack"
          size="large"
          plain
          class="flex-1"
          @click="emit('back')"
        >
          {{ $t("page.login.common.back") }}
        </n-button>
        <n-button
          type="primary"
          size="large"
          strong
          :block="!props.showBack"
          class="flex-1"
          :disabled="!!(loadingKeys.length || isValidating)"
          :loading="isValidating"
          @click="handleNext"
        >
          {{ $t("page.login.common.continue") }}
        </n-button>
      </div>
    </n-form>
  </div>
</template>

<script setup lang="ts">
import type { FormItemRule } from "naive-ui"
import { useLoading } from "@/composables"
import { createPasswordValidator, useFormRules, useNaiveForm } from "@/composables/useForm"
import { $t } from "@airalogy/shared/locales"
import { useVModel } from "@vueuse/core"
import EyeOffOutline from "~icons/ion/eye-off-outline"
import EyeOutline from "~icons/ion/eye-outline"
import { ref } from "vue"
import { checkEmailDuplicate } from "../../../service/api/auth"

interface FormModel {
  email: string
  password: string
  confirmPassword: string
}

interface Props {
  modelValue: FormModel
  emailReadonly?: boolean
  showBack?: boolean
}

defineOptions({
  name: "AccountCredentialsStep",
})

const props = withDefaults(defineProps<Props>(), {
  emailReadonly: false,
  showBack: false,
})

const emit = defineEmits<{
  "update:modelValue": [value: FormModel]
  "next": [data: FormModel]
  "back": []
}>()

const model = useVModel(props, "modelValue", emit)
const debouncedCheckEmailDuplicate = useDebounceFn(checkEmailDuplicate, 500)
const { formRef, validate } = useNaiveForm()
const {
  formRules: { user: userFormRules },
} = useFormRules()
const { loadingKeys } = useLoading(false, [])
const isValidating = ref(false)
const passwordValidator = createPasswordValidator()

const rules: Record<
  Exclude<keyof FormModel, "password" | "confirmPassword">,
  App.Global.FormRule[]
> & {
  confirmPassword: FormItemRule[]
  password: FormItemRule[]
} = {
  email: [...userFormRules.email, {
    asyncValidator: async (_, value) => {
      const { duplicated, message } = await debouncedCheckEmailDuplicate(value) || {}
      if (duplicated) {
        throw new Error(message as string)
      }
    },
    trigger: ["change", "blur"],
    skipIfOtherErrors: true,
  }],
  password: passwordValidator,
  confirmPassword: [
    ...passwordValidator,
    {
      validator: (_, value) => {
        if (value !== model.value.password) {
          return new Error($t("form.confirmPwd.invalid"))
        }
        return true
      },
      trigger: ["blur", "change"],
    },
  ] as FormItemRule[],
}

async function handleNext() {
  if (isValidating.value)
    return

  try {
    isValidating.value = true

    // Validate all form fields including password complexity
    await validate()

    // If validation passes, emit next event
    emit("next", model.value)
  }
  catch (error) {
    // Validation errors will be shown by the form
    console.warn("Account credentials validation failed:", error)
  }
  finally {
    isValidating.value = false
  }
}
</script>

<style scoped lang="sass">
@use "../styles/common" as *

.step-container
  width: 100%

:deep(.n-input-wrapper)
  width: 100%
</style>
