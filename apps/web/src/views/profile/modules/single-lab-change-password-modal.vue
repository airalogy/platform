<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    class="max-w-[calc(100vw-32px)] w-130"
    :title="$t('page.profile.changePassword')"
    :mask-closable="false"
    @after-leave="resetForm"
  >
    <n-form ref="formRef" :model="model" :rules="rules" label-placement="top">
      <n-form-item :label="$t('page.instance.currentPassword')" path="currentPassword">
        <n-input v-model:value="model.currentPassword" type="password" show-password-on="click" />
      </n-form-item>
      <n-form-item :label="$t('page.instance.newPassword')" path="password">
        <n-input v-model:value="model.password" type="password" show-password-on="click" />
      </n-form-item>
      <n-form-item :label="$t('page.instance.confirmPassword')" path="confirmPassword">
        <n-input
          v-model:value="model.confirmPassword"
          type="password"
          show-password-on="click"
          @keyup.enter="submit"
        />
      </n-form-item>
    </n-form>

    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button :disabled="submitting" @click="visible = false">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button type="primary" :loading="submitting" @click="submit">
          {{ $t("common.confirm") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { createLoginPwdValidator, createPasswordValidator, useNaiveForm } from "@/composables/useForm"
import { putOwnPassword } from "@/service/api/instance"
import { useAuthStore } from "@/store/modules/auth"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"

const visible = defineModel<boolean>("show", { default: false })
const submitting = ref(false)
const message = useClosableMessage()
const authStore = useAuthStore()
const { formRef, validate, restoreValidation } = useNaiveForm()
const model = reactive({ currentPassword: "", password: "", confirmPassword: "" })
const rules = {
  currentPassword: createLoginPwdValidator(),
  password: createPasswordValidator(),
  confirmPassword: [
    ...createPasswordValidator(),
    {
      validator: () => model.password === model.confirmPassword,
      message: $t("form.confirmPwd.invalid"),
      trigger: ["blur", "change"],
    },
  ],
}

function resetForm() {
  model.currentPassword = ""
  model.password = ""
  model.confirmPassword = ""
  restoreValidation()
}

async function submit() {
  await validate()
  submitting.value = true
  try {
    const { data } = await putOwnPassword(model)
    if (data) {
      authStore.setToken(data.token)
      message.success($t("page.profile.changePasswordSuccess" as any))
      visible.value = false
    }
  }
  finally {
    submitting.value = false
  }
}
</script>
