<template>
  <div class="min-h-screen flex items-center justify-center bg-#f5f7fb px-4 py-8">
    <n-card class="w-full max-w-560px rounded-6" :bordered="false" size="large">
      <div class="flex flex-col gap-6">
        <div class="flex flex-col gap-2">
          <div class="text-3xl text-#111827 font-600">
            OAuth Authorization
          </div>
          <div class="text-sm line-height-6 text-#6b7280">
            Confirm that you want to authorize this website to access your Airalogy account.
          </div>
        </div>

        <div class="rounded-4 bg-white p-4 shadow-sm ring-1 ring-#e5e7eb">
          <div class="text-xs text-#9ca3af uppercase tracking-0.08em">
            Target Site
          </div>
          <div class="mt-2 text-lg text-#111827 font-600 break-all">
            {{ siteHost }}
          </div>
          <div class="mt-1 text-sm text-#6b7280 break-all">
            {{ requestParams.redirectUri || "Invalid redirect URI" }}
          </div>
        </div>

        <div class="grid gap-3 rounded-4 bg-#f9fafb p-4 text-sm text-#374151 md:grid-cols-2">
          <div>
            <div class="text-xs text-#9ca3af uppercase tracking-0.08em">
              Account
            </div>
            <div class="mt-1 break-all">
              {{ authStore.userInfo.name || authStore.userInfo.username || `User #${authStore.userInfo.id}` }}
            </div>
          </div>
          <div>
            <div class="text-xs text-#9ca3af uppercase tracking-0.08em">
              Scope
            </div>
            <div class="mt-1 break-all">
              {{ requestParams.scope || "basic" }}
            </div>
          </div>
          <div>
            <div class="text-xs text-#9ca3af uppercase tracking-0.08em">
              Client ID
            </div>
            <div class="mt-1 break-all">
              {{ requestParams.clientId || "-" }}
            </div>
          </div>
          <div>
            <div class="text-xs text-#9ca3af uppercase tracking-0.08em">
              Response Type
            </div>
            <div class="mt-1">
              {{ requestParams.responseType || "-" }}
            </div>
          </div>
        </div>

        <n-alert v-if="!isValidRequest" type="error" :show-icon="false">
          Missing or invalid OAuth parameters. Please check the authorization link and try again.
        </n-alert>

        <div class="flex justify-end gap-3">
          <n-button :disabled="authorizing" @click="routerBack()">
            Cancel
          </n-button>
          <n-button
            type="primary"
            :loading="authorizing"
            :disabled="!isValidRequest"
            @click="handleAuthorize"
          >
            Confirm Authorization
          </n-button>
        </div>
      </div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import type { LocationQueryValue } from "vue-router"
import { useRouterPush } from "@/composables/useRouterPush"
import { fetchOAuthAuthorize } from "@/service/api/oauth"
import { useAuthStore } from "@/store/modules/auth"
import { useClosableMessage } from "@airalogy/composables"
import { computed, ref } from "vue"

interface OAuthRequestParams {
  responseType: string
  clientId: string
  redirectUri: string
  state: string
  scope: string
}

const route = useRoute()
const { routerBack, routerPushByKey } = useRouterPush()
const authStore = useAuthStore()
const message = useClosableMessage()

const authorizing = ref(false)

function normalizeQueryValue(value: LocationQueryValue | LocationQueryValue[]) {
  if (Array.isArray(value)) {
    return value[0] || ""
  }

  return value || ""
}

const requestParams = computed<OAuthRequestParams>(() => ({
  responseType: normalizeQueryValue(route.query.response_type),
  clientId: normalizeQueryValue(route.query.client_id),
  redirectUri: normalizeQueryValue(route.query.redirect_uri),
  state: normalizeQueryValue(route.query.state),
  scope: normalizeQueryValue(route.query.scope) || "basic",
}))

const isValidRequest = computed(() => {
  const { responseType, clientId, redirectUri } = requestParams.value

  if (responseType !== "code" || !clientId || !redirectUri) {
    return false
  }

  try {
    const url = new URL(redirectUri)
    return ["http:", "https:"].includes(url.protocol)
  }
  catch {
    return false
  }
})

const siteHost = computed(() => {
  if (!requestParams.value.redirectUri) {
    return "Unknown site"
  }

  try {
    return new URL(requestParams.value.redirectUri).host
  }
  catch {
    return "Unknown site"
  }
})

onMounted(() => {
  if (!authStore.token) {
    void routerPushByKey("login", { query: { redirect: route.fullPath } })
    return
  }

  if (!isValidRequest.value) {
    message.error("Invalid OAuth authorization request")
  }
})

async function handleAuthorize() {
  if (!authStore.token) {
    void routerPushByKey("login", { query: { redirect: route.fullPath } })
    return
  }

  if (!isValidRequest.value) {
    message.error("Invalid OAuth authorization request")
    return
  }

  authorizing.value = true

  const { data, error } = await fetchOAuthAuthorize({
    response_type: "code",
    client_id: requestParams.value.clientId,
    redirect_uri: requestParams.value.redirectUri,
    state: requestParams.value.state || undefined,
    scope: requestParams.value.scope || undefined,
    auto_redirect: false,
  }).finally(() => {
    authorizing.value = false
  })
  if (error || !data?.redirect_to) {
    message.error("OAuth authorization failed")
    return
  }

  window.location.href = data.redirect_to
}
</script>
