<template>
  <n-card
    :bordered="false"
    class="m-auto h-fit min-w-320px w-full md:w-520px"
    size="huge"
  >
    <div class="mb-6">
      <div class="text-xs font-medium uppercase text-gray-500">
        {{ $t("page.instance.administrator") }}
      </div>
      <h1 class="mb-0 mt-2 text-2xl font-semibold">
        {{ $t("page.instance.setupTitle") }}
      </h1>
      <p class="mb-0 mt-2 text-sm leading-6 text-gray-500">
        {{ $t("page.instance.setupDescription") }}
      </p>
    </div>

    <n-form ref="formRef" :model="model" :rules="rules" size="large" :show-label="false">
      <n-form-item v-if="instanceStore.status.bootstrap_token_required" path="setupToken">
        <n-input
          v-model:value="model.setupToken"
          type="password"
          show-password-on="click"
          :placeholder="$t('page.instance.setupCode')"
        />
      </n-form-item>
      <n-form-item path="name">
        <n-input v-model:value="model.name" :placeholder="$t('page.instance.displayName')" />
      </n-form-item>
      <n-form-item path="username">
        <n-input v-model:value="model.username" :placeholder="$t('page.instance.username')" />
      </n-form-item>
      <n-form-item path="email">
        <n-input v-model:value="model.email" :placeholder="$t('page.instance.email')" />
      </n-form-item>
      <n-form-item path="password">
        <n-input
          v-model:value="model.password"
          type="password"
          show-password-on="click"
          :placeholder="$t('page.instance.password')"
        />
      </n-form-item>
      <n-form-item path="confirmPassword">
        <n-input
          v-model:value="model.confirmPassword"
          type="password"
          show-password-on="click"
          :placeholder="$t('page.instance.confirmPassword')"
          @keyup.enter="handleSubmit"
        />
      </n-form-item>
      <n-button type="primary" size="large" block :loading="submitting" @click="handleSubmit">
        {{ $t("page.instance.completeSetup") }}
      </n-button>
    </n-form>
  </n-card>
</template>

<script setup lang="ts">
import { createPasswordValidator, useFormRules, useNaiveForm } from "@/composables/useForm"
import { postInstanceBootstrap } from "@/service/api/instance"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { useClosableMessage, useLoading } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { reactive } from "vue"

const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const message = useClosableMessage()
const { formRef, validate } = useNaiveForm()
const { loading: submitting, startLoading, endLoading } = useLoading()
const { formRules: { user }, defaultRequiredRule } = useFormRules()
const passwordRules = createPasswordValidator()

const model = reactive({
  setupToken: "",
  name: "",
  username: "",
  email: "",
  password: "",
  confirmPassword: "",
})

const rules = {
  setupToken: instanceStore.status.bootstrap_token_required ? [defaultRequiredRule] : [],
  name: [defaultRequiredRule],
  username: user.username,
  email: user.email,
  password: passwordRules,
  confirmPassword: [
    ...passwordRules,
    {
      validator: () => model.password === model.confirmPassword,
      message: $t("form.confirmPwd.invalid"),
      trigger: ["blur", "change"],
    },
  ],
}

async function handleSubmit() {
  await validate()
  startLoading()
  try {
    const { data, error } = await postInstanceBootstrap(model)
    if (!data || error) {
      return
    }
    await instanceStore.load()
    await authStore.login("email", {
      email: model.email,
      password: model.password,
    })
  }
  catch (error) {
    message.error((error as Error).message || $t("page.instance.setupFailed"))
  }
  finally {
    endLoading()
  }
}
</script>
