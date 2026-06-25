<template>
  <div class="step-container">
    <div class="mb-6 text-left">
      <h3 class="mb-2 text-lg font-semibold">
        {{ $t("page.login.register.profileTitle") }}
      </h3>
      <p class="text-gray-600">
        {{ $t("page.login.register.profileHelper") }}
      </p>
    </div>

    <n-form ref="formRef" :model="model" :rules="rules" size="large" :show-label="false">
      <n-form-item path="displayName">
        <n-tooltip trigger="focus" placement="top-start" class="max-w-70%">
          <template #trigger>
            <n-input
              v-model:value="model.displayName"
              class="form__input"
              :minlength="1"
              :maxlength="32"
              show-count
              :placeholder="$t('page.login.common.displayNamePlaceholder')"
            />
          </template>
          {{ $t("page.login.register.displayNameHintShort") }}
        </n-tooltip>
      </n-form-item>

      <n-form-item ref="usernameRef" path="username">
        <n-tooltip trigger="focus" placement="top-start" class="max-w-70%">
          <template #trigger>
            <n-input
              v-model:value="model.username"
              class="form__input"
              :minlength="1"
              :maxlength="32"
              show-count
              :placeholder="$t('page.login.common.usernamePlaceholder')"
              :loading="isValidating"
              @update:value="restoreFormValidation"
            />
          </template>
          {{ $t("page.login.register.usernameHintShort") }}
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
import { useLoading } from "@/composables"
import { useFormRules, useNaiveForm } from "@/composables/useForm"
import { $t } from "@airalogy/shared/locales"

interface FormModel {
  username: string
  displayName: string
}

interface Props {
  modelValue: FormModel
}

const props = defineProps<Props>()

const emit = defineEmits<{
  "update:modelValue": [value: FormModel]
  "next": [data: FormModel]
  "back": []
}>()

const model = useVModel(props, "modelValue", emit)

const { formRef, validate } = useNaiveForm()
const {
  formRules: { user: userFormRules },
} = useFormRules()
const { loadingKeys } = useLoading(false, [])
const usernameRef = ref<{ restoreValidation: () => void } | null>(null)
const isValidating = ref(false)

const { defaultRequiredRule } = useFormRules()

const rules: Record<keyof FormModel, App.Global.FormRule[]> = {
  username: userFormRules.username,
  displayName: [
    defaultRequiredRule,
    {
      min: 1,
      max: 26,
      message: $t("form.displayName.length", { field: $t("page.login.common.displayNamePlaceholder"), min: 1, max: 26 }),
      trigger: ["change", "blur"],
    },
    {
      validator: (rule, value, callback) => {
        if (/^[_-]|[_-]$/.test(value)) {
          return new Error($t("form.displayName.hyphenEdges"))
        }
        if (/[_-]{2,}/.test(value)) {
          return new Error($t("form.displayName.hyphenConsecutive"))
        }
        return true
      },
      trigger: ["change", "blur"],
    },
  ],
}

function restoreFormValidation() {
  if (!usernameRef.value)
    return
  const { restoreValidation } = usernameRef.value

  restoreValidation()
}

async function handleNext() {
  if (isValidating.value)
    return

  try {
    isValidating.value = true

    // Validate all form fields including async username duplicate check
    await validate()

    // If validation passes, emit next event
    emit("next", model.value)
  }
  catch (error) {
    // Validation errors will be shown by the form
    // The async username duplicate check will prevent progression if username exists
    console.warn("Form validation failed:", error)
  }
  finally {
    isValidating.value = false
  }
}

function handleBack() {
  emit("back")
}
</script>

<style scoped lang="sass">
@use "../styles/common" as *

.step-container
  width: 100%

:deep(.n-input-wrapper)
  width: 100%
</style>
