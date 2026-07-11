<template>
  <n-card :bordered="false" class="m-auto h-fit min-w-320px w-full md:w-500px" size="huge">
    <n-spin :show="loading">
      <n-result
        v-if="invalid"
        status="error"
        :title="$t('page.instance.resetInvalid')"
      >
        <template #footer>
          <n-button @click="router.push({ name: 'login' })">
            {{ $t("page.instance.backToLogin") }}
          </n-button>
        </template>
      </n-result>
      <template v-else>
        <h1 class="mb-0 text-2xl font-semibold">
          {{ $t("page.instance.resetTitle") }}
        </h1>
        <p class="mb-6 mt-2 text-sm leading-6 text-gray-500">
          {{ $t("page.instance.resetDescription") }}
        </p>
        <n-form ref="formRef" :model="model" :rules="rules" size="large" :show-label="false">
          <n-form-item path="password">
            <n-input v-model:value="model.password" type="password" show-password-on="click" :placeholder="$t('page.instance.password')" />
          </n-form-item>
          <n-form-item path="confirmPassword">
            <n-input v-model:value="model.confirmPassword" type="password" show-password-on="click" :placeholder="$t('page.instance.confirmPassword')" @keyup.enter="handleSubmit" />
          </n-form-item>
          <n-button type="primary" block size="large" :loading="submitting" @click="handleSubmit">
            {{ $t("page.instance.resetAction") }}
          </n-button>
        </n-form>
      </template>
    </n-spin>
  </n-card>
</template>

<script setup lang="ts">
import { createPasswordValidator, useNaiveForm } from "@/composables/useForm"
import { fetchPasswordReset, postPasswordReset } from "@/service/api/instance"
import { $t } from "@airalogy/shared/locales"
import { reactive } from "vue"

const route = useRoute()
const router = useRouter()
const token = computed(() => typeof route.query.token === "string" ? route.query.token : "")
const loading = ref(true)
const submitting = ref(false)
const invalid = ref(false)
const { formRef, validate } = useNaiveForm()
const passwordRules = createPasswordValidator()
const model = reactive({ password: "", confirmPassword: "" })
const rules = {
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

async function checkToken() {
  if (!token.value) {
    invalid.value = true
    loading.value = false
    return
  }
  const { data } = await fetchPasswordReset(token.value)
  invalid.value = !data
  loading.value = false
}

async function handleSubmit() {
  await validate()
  submitting.value = true
  try {
    const { data } = await postPasswordReset(token.value, model)
    if (data) {
      window.$message?.success($t("page.instance.resetSuccess"))
      await router.replace({ name: "login" })
    }
  }
  finally {
    submitting.value = false
  }
}

onMounted(checkToken)
</script>
