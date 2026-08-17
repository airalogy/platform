<template>
  <main class="help-center mx-auto max-w-6xl w-full px-4 py-10 lg:px-8 sm:px-6">
    <header class="mb-8 max-w-3xl">
      <p class="mb-2 text-sm text-primary font-semibold">
        {{ $t("page.help.eyebrow") }}
      </p>
      <h1 class="m-0 text-3xl text-gray-900 font-bold sm:text-4xl">
        {{ $t("page.help.title") }}
      </h1>
      <p class="mt-4 text-base text-gray-600 leading-7">
        {{ $t("page.help.intro") }}
      </p>
    </header>

    <n-spin :show="labsLoading">
      <n-grid cols="1 m:2" responsive="screen" :x-gap="20" :y-gap="20">
        <n-grid-item>
          <n-card
            class="help-card h-full"
            hoverable
            role="link"
            tabindex="0"
            @click="openDocumentation('user-guide')"
            @keydown.enter="openDocumentation('user-guide')"
          >
            <template #header>
              <div class="flex items-center gap-3">
                <span class="help-card__icon">
                  <n-icon :size="24"><icon-ion-book-outline /></n-icon>
                </span>
                <span>{{ $t("page.help.userGuide.title") }}</span>
              </div>
            </template>
            <p class="help-card__description">
              {{ $t("page.help.userGuide.description") }}
            </p>
            <template #footer>
              <div class="help-card__footer">
                <n-tag size="small" :bordered="false" type="info">
                  {{ $t("page.help.audience.allUsers") }}
                </n-tag>
                <span>{{ $t("page.help.open") }} →</span>
              </div>
            </template>
          </n-card>
        </n-grid-item>

        <n-grid-item v-if="canViewLabAdministration">
          <n-card
            class="help-card h-full"
            hoverable
            role="link"
            tabindex="0"
            @click="openDocumentation('lab-admin')"
            @keydown.enter="openDocumentation('lab-admin')"
          >
            <template #header>
              <div class="flex items-center gap-3">
                <span class="help-card__icon help-card__icon--admin">
                  <n-icon :size="24"><icon-ion-people-outline /></n-icon>
                </span>
                <span>{{ $t("page.help.labAdmin.title") }}</span>
              </div>
            </template>
            <p class="help-card__description">
              {{ $t("page.help.labAdmin.description") }}
            </p>
            <template #footer>
              <div class="help-card__footer">
                <n-tag size="small" :bordered="false" type="success">
                  {{ $t("page.help.audience.labManagers") }}
                </n-tag>
                <span>{{ $t("page.help.open") }} →</span>
              </div>
            </template>
          </n-card>
        </n-grid-item>

        <n-grid-item v-if="canViewSelfHosting">
          <n-card
            class="help-card h-full"
            hoverable
            role="link"
            tabindex="0"
            @click="openDocumentation('self-hosting')"
            @keydown.enter="openDocumentation('self-hosting')"
          >
            <template #header>
              <div class="flex items-center gap-3">
                <span class="help-card__icon help-card__icon--operations">
                  <n-icon :size="24"><icon-ion-server-outline /></n-icon>
                </span>
                <span>{{ $t("page.help.selfHosting.title") }}</span>
              </div>
            </template>
            <p class="help-card__description">
              {{ $t("page.help.selfHosting.description") }}
            </p>
            <template #footer>
              <div class="help-card__footer">
                <n-tag size="small" :bordered="false" type="warning">
                  {{ $t("page.help.audience.instanceOperators") }}
                </n-tag>
                <span>{{ $t("page.help.open") }} →</span>
              </div>
            </template>
          </n-card>
        </n-grid-item>

        <n-grid-item v-if="canViewManagedSupport">
          <n-card
            class="help-card h-full"
            hoverable
            role="link"
            tabindex="0"
            @click="openSupport"
            @keydown.enter="openSupport"
          >
            <template #header>
              <div class="flex items-center gap-3">
                <span class="help-card__icon help-card__icon--support">
                  <n-icon :size="24"><icon-ion-headset-outline /></n-icon>
                </span>
                <span>{{ $t("page.help.managedSupport.title") }}</span>
              </div>
            </template>
            <p class="help-card__description">
              {{ $t("page.help.managedSupport.description") }}
            </p>
            <template #footer>
              <div class="help-card__footer">
                <n-tag size="small" :bordered="false" type="error">
                  {{ $t("page.help.audience.vendorManaged") }}
                </n-tag>
                <span>{{ $t("page.help.open") }} →</span>
              </div>
            </template>
          </n-card>
        </n-grid-item>
      </n-grid>
    </n-spin>

    <n-alert class="mt-8" type="info" :bordered="false">
      {{ $t("page.help.visibilityNote") }}
    </n-alert>
  </main>
</template>

<script setup lang="ts">
import type { DocumentationSection } from "@airalogy/shared/utils"
import { LabRole } from "@/enum"
import { fetchUserLabs } from "@/service/api/users"
import { useAppStore } from "@/store/modules/app"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { $t } from "@airalogy/shared/locales"
import { configuredLinkUrl, documentationSectionUrl } from "@airalogy/shared/utils"

defineOptions({ name: "HelpCenter" })

const appStore = useAppStore()
const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const labsLoading = ref(false)
const managesAnyLab = ref(false)

const isGlobalAdministrator = computed(
  () => authStore.userInfo.roles?.some(role => role === "R_ADMIN" || role === "R_SUPER") ?? false,
)
const canViewLabAdministration = computed(() => isGlobalAdministrator.value || managesAnyLab.value)
const canViewSelfHosting = computed(
  () => isGlobalAdministrator.value && instanceStore.documentationProfile !== "vendor_managed",
)
const canViewManagedSupport = computed(
  () =>
    instanceStore.documentationProfile === "vendor_managed" && Boolean(instanceStore.supportUrl),
)

function openInNewTab(url: string) {
  window.open(url, "_blank", "noopener,noreferrer")
}

function openDocumentation(section: DocumentationSection) {
  openInNewTab(documentationSectionUrl(instanceStore.documentationUrl, appStore.locale, section))
}

function openSupport() {
  if (instanceStore.supportUrl)
    openInNewTab(configuredLinkUrl(instanceStore.supportUrl))
}

async function loadLabManagementRole() {
  if (isGlobalAdministrator.value || !authStore.userInfo.id)
    return

  labsLoading.value = true
  try {
    const result = await fetchUserLabs(authStore.userInfo.id, { page: 1, pageSize: 9999 })
    managesAnyLab.value = result?.labs.some(
      lab => lab.user_role === LabRole.OWNER || lab.user_role === LabRole.MANAGER,
    ) ?? false
  }
  catch {
    managesAnyLab.value = false
  }
  finally {
    labsLoading.value = false
  }
}

onMounted(async () => {
  if (!instanceStore.loaded)
    await instanceStore.load()
  await loadLabManagementRole()
})
</script>

<style scoped lang="sass">
.help-card
  cursor: pointer
  transition: transform 160ms ease, box-shadow 160ms ease

  &:hover
    transform: translateY(-2px)

.help-card__icon
  @apply h-11 w-11 flex shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600

.help-card__icon--admin
  @apply bg-emerald-50 text-emerald-600

.help-card__icon--operations
  @apply bg-amber-50 text-amber-600

.help-card__icon--support
  @apply bg-rose-50 text-rose-600

.help-card__description
  @apply m-0 min-h-12 text-sm text-gray-600 leading-6

.help-card__footer
  @apply flex items-center justify-between text-sm text-primary font-medium
</style>
