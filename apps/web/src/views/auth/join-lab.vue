<template>
  <n-card :bordered="false" class="m-auto h-fit min-w-320px w-full md:w-500px" size="huge">
    <n-result
      :status="status"
      :title="title"
      :description="description"
    >
      <template v-if="actionLabel" #footer>
        <n-button type="primary" :loading="loading" @click="handleAction">
          {{ actionLabel }}
        </n-button>
      </template>
    </n-result>
  </n-card>
</template>

<script setup lang="ts">
import { acceptInvitation, fetchInvitation, type InvitationInfo } from "@/service/api/instance"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { $t } from "@airalogy/shared/locales"

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const token = computed(() => typeof route.query.token === "string" ? route.query.token : "")
const invitation = ref<InvitationInfo | null>(null)
const loading = ref(true)
const failed = ref(false)

const status = computed(() => failed.value ? "error" : "info")
const title = computed(() => {
  if (failed.value)
    return $t("page.instance.invitationInvalid")
  if (invitation.value)
    return $t("page.instance.invitedTo", { lab: invitation.value.lab.name })
  return $t("page.instance.invitationLoading")
})
const description = computed(() => invitation.value?.existing_account && !authStore.isLogin
  ? $t("page.instance.existingAccount")
  : "")
const actionLabel = computed(() => {
  if (!invitation.value || failed.value)
    return ""
  if (!authStore.isLogin) {
    return invitation.value.existing_account
      ? $t("page.instance.signInToJoin")
      : $t("page.login.register.confirm")
  }
  return $t("page.instance.joining")
})

async function loadInvitation() {
  if (!token.value) {
    failed.value = true
    loading.value = false
    return
  }
  const { data } = await fetchInvitation(token.value)
  invitation.value = data || null
  failed.value = !data
  loading.value = false

  if (data && authStore.isLogin) {
    await acceptCurrentInvitation()
  }
}

async function acceptCurrentInvitation() {
  loading.value = true
  try {
    const { data } = await acceptInvitation(token.value)
    if (!data) {
      failed.value = true
      return
    }
    await instanceStore.load()
    window.$message?.success($t("page.instance.joinSuccess"))
    await router.replace({
      name: "lab-projects",
      params: { labUid: data.lab.uid },
    })
  }
  finally {
    loading.value = false
  }
}

async function handleAction() {
  if (!invitation.value)
    return
  if (authStore.isLogin) {
    await acceptCurrentInvitation()
    return
  }
  if (invitation.value.existing_account) {
    await router.push({
      name: "login",
      query: { redirect: route.fullPath },
    })
  }
  else {
    await router.push({
      name: "sign-up",
      query: { inviteToken: token.value },
    })
  }
}

onMounted(loadInvitation)
</script>
