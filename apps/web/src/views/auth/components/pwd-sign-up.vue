<template>
  <n-form ref="formRef" :model="model" :rules="rules" size="large" :show-label="false">
    <n-alert v-if="invitation" type="info" class="mb-5">
      {{ $t("page.instance.invitedTo", { lab: invitation.lab.name }) }}
    </n-alert>
    <n-alert v-else-if="invitationRequired" type="warning" class="mb-5">
      {{ $t("page.instance.invitationRequired") }}
    </n-alert>
    <n-form-item path="email">
      <n-input
        v-model:value="model.email"
        class="form__input"
        :readonly="Boolean(invitation)"
        :placeholder="$t('page.login.common.emailPlaceholder')"
      />
    </n-form-item>
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
        {{ $t("page.login.register.displayNameHint") }}
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
            @update:value="restoreFormValidation"
          />
        </template>
        {{ $t("page.login.register.usernameHint") }}
      </n-tooltip>
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
    <n-button
      type="primary"
      size="large"
      strong
      block
      :loading="authStore.loginLoading"
      :disabled="invitationLoading || invitationRequired || Boolean(invitation?.existing_account)"
      class="mt-10"
      @click="handleSubmit"
    >
      {{ $t("page.login.register.confirm") }}
    </n-button>
    <div class="w-full text-center">
      <span>{{ $t("page.login.common.alreadyHaveAccount") }}</span>
      <n-button
        quaternary
        class="mt-4 underline !hover:text-primary"
        @click="routerPushByKey('login')"
      >
        {{ $t("page.login.emailLogin.confirm") }}
      </n-button>
    </div>
  </n-form>
</template>

<script setup lang="ts">
import type { FormItemRule } from "naive-ui"
import { createPasswordValidator, useFormRules, useNaiveForm } from "@/composables/useForm"
import { useRouterPush } from "@/composables/useRouterPush"
import { fetchInvitation, type InvitationInfo } from "@/service/api/instance"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { $t } from "@airalogy/shared/locales"
import EyeOffOutline from "~icons/ion/eye-off-outline"
import EyeOutline from "~icons/ion/eye-outline"
import { reactive } from "vue"

defineOptions({
  name: "PwdSignUp",
})

const emits = defineEmits<IEmits>()
const { formRef, validate } = useNaiveForm()
const {
  formRules: { user: userFormRules },
} = useFormRules()
const { routerPushByKey } = useRouterPush()
const usernameRef = ref<{ restoreValidation: () => void } | null>(null)

interface FormModel {
  username: string
  displayName: string
  email: string
  password: string
  confirmPassword: string
}
interface IEmits {
  (e: "sign-up:password", val: FormModel): void
}
const model: FormModel = reactive({
  username: "",
  displayName: "",
  email: "",
  password: "",
  confirmPassword: "",
})

const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const route = useRoute()
const inviteToken = computed(() => typeof route.query.inviteToken === "string" ? route.query.inviteToken : "")
const invitation = ref<InvitationInfo | null>(null)
const invitationLoading = ref(Boolean(inviteToken.value))
const invitationRequired = computed(() => instanceStore.isSingleLab
  && instanceStore.signupMode !== "open"
  && !invitation.value)
const { defaultRequiredRule } = useFormRules()
const passwordValidator = createPasswordValidator()

const rules: Record<
  Exclude<keyof FormModel, "password" | "confirmPassword">,
  App.Global.FormRule[]
> & {
  confirmPassword: FormItemRule[]
  password: FormItemRule[]
} = {
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
  email: userFormRules.email,
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
  ] as FormItemRule[],
}

function restoreFormValidation() {
  if (!usernameRef.value)
    return
  const { restoreValidation } = usernameRef.value

  restoreValidation()
}
async function handleSubmit() {
  await validate()

  await authStore.signup("email", {
    ...model,
    inviteToken: inviteToken.value || undefined,
  })
  emits("sign-up:password", model)
}

async function loadInvitation() {
  if (!inviteToken.value) {
    invitationLoading.value = false
    return
  }
  const { data } = await fetchInvitation(inviteToken.value)
  invitation.value = data || null
  if (data) {
    model.email = data.email
  }
  invitationLoading.value = false
}

onMounted(loadInvitation)
</script>

<style scoped lang="sass">
@use "../styles/common" as *

:deep(.n-input-wrapper)
  width: 100%
</style>
