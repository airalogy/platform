<template>
  <n-button :aria-label="$t('page.instance.inviteMember')" :title="$t('page.instance.inviteMember')" @click="showModal">
    <template #icon>
      <icon-local-user-plus />
    </template>
    <span v-if="!isMobile">{{ $t("page.instance.inviteMember") }}</span>
  </n-button>
  <n-modal
    :show="isShown"
    preset="card"
    :title="$t('page.instance.inviteMember')"
    class="max-w-[calc(100vw-32px)] w-150"
    :mask-closable="false"
    @update:show="setModalStatus"
  >
    <p class="mb-5 mt-0 text-sm text-gray-500">
      {{ $t("page.instance.inviteDescription") }}
    </p>
    <n-form ref="formRef" :model="model" :rules="rules" label-placement="top">
      <n-form-item :label="$t('page.instance.email')" path="email">
        <n-input v-model:value="model.email" type="text" />
      </n-form-item>
      <n-form-item :label="$t('page.instance.labRole')" path="labRole">
        <n-select v-model:value="model.labRole" :options="labRoleOptions" :disabled="Boolean(inviteUrl)" />
      </n-form-item>
      <n-form-item :label="$t('page.instance.projectRole')" path="projectRole">
        <n-select v-model:value="model.projectRole" :options="projectRoleOptions" :disabled="Boolean(inviteUrl)" />
      </n-form-item>
    </n-form>

    <div v-if="inviteUrl" class="mt-4 border border-gray-200 rounded p-3">
      <div class="mb-2 text-sm font-medium">
        {{ $t("page.instance.inviteLink") }}
      </div>
      <div class="flex flex-col gap-2 sm:flex-row">
        <n-input :value="inviteUrl" readonly type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
        <n-button class="self-end sm:self-auto" secondary @click="copyInviteUrl">
          {{ $t("page.instance.copyInviteLink") }}
        </n-button>
      </div>
      <p v-if="expiresAt" class="mb-0 mt-2 text-xs text-gray-500">
        {{ $t("page.instance.linkExpiresAt", { time: formatExpiry(expiresAt) }) }}
      </p>
    </div>

    <template #footer>
      <div class="flex justify-end gap-3">
        <n-button @click="hideModal">
          {{ inviteUrl ? $t("common.close") : $t("common.cancel") }}
        </n-button>
        <n-button v-if="!inviteUrl" type="primary" :loading="loading" @click="handleCreate">
          {{ $t("page.instance.createInvite") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { useBasicLayout, useLoading, useShowModal } from "@/composables"
import { useFormRules, useNaiveForm } from "@/composables/useForm"
import { LabRole, ProjectRole } from "@/enum"
import { postInvitation } from "@/service/api/instance"
import { copyToClip } from "@airalogy/shared"
import { $t } from "@airalogy/shared/locales"
import { reactive } from "vue"

interface Props {
  currentRole: LabRole
}

const props = defineProps<Props>()
const { isMobile } = useBasicLayout()
const { isShown, showModal, hideModal, setModalStatus } = useShowModal()
const { loading, startLoading, endLoading } = useLoading()
const { formRef, validate } = useNaiveForm()
const { formRules: { user }, defaultRequiredRule } = useFormRules()
const inviteUrl = ref("")
const expiresAt = ref("")
const model = reactive({
  email: "",
  labRole: LabRole.MEMBER,
  projectRole: ProjectRole.RECORDER,
})

const rules = {
  email: user.email,
  labRole: [defaultRequiredRule],
  projectRole: [defaultRequiredRule],
}
const labRoleOptions = computed(() => [
  ...(props.currentRole === LabRole.OWNER
    ? [{ label: $t("role.manager"), value: LabRole.MANAGER }]
    : []),
  { label: $t("role.member"), value: LabRole.MEMBER },
])
const projectRoleOptions = [
  { label: $t("role.manager"), value: ProjectRole.MANAGER },
  { label: $t("role.collaborator"), value: ProjectRole.COLLABORATOR },
  { label: $t("role.recorder"), value: ProjectRole.RECORDER },
]

async function handleCreate() {
  await validate()
  startLoading()
  try {
    const { data } = await postInvitation(model)
    if (data) {
      inviteUrl.value = data.url
      expiresAt.value = data.expires_at
    }
  }
  finally {
    endLoading()
  }
}

async function copyInviteUrl() {
  await copyToClip(inviteUrl.value)
  window.$message?.success($t("page.instance.linkCopied"))
}

watch(isShown, (shown) => {
  if (!shown) {
    model.email = ""
    model.labRole = LabRole.MEMBER
    model.projectRole = ProjectRole.RECORDER
    inviteUrl.value = ""
    expiresAt.value = ""
  }
})

function formatExpiry(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}
</script>
