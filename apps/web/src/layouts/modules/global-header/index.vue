<template>
  <section class="mx-auto h-[70px] min-w-0 w-full flex items-center" :class="isContainer ? 'container' : ''">
    <global-logo class="shrink-0 text-white" :class="isMobile ? 'mx-4' : 'mr-18'" monochrome :compact="isMobile" />
    <template v-if="authStore.isLogin">
      <global-menu />
      <global-add-new />
      <n-button
        v-if="!isMobile && !instanceStore.isSingleLab"
        :theme-overrides="buttonThemeOverrides"
        class="ml-4 h-[36px] rounded-2 px-3"
        @click="routerPushByKey('hub')"
      >
        {{ $t("common.hub") }}
      </n-button>
      <n-button
        v-if="!isMobile"
        :theme-overrides="buttonThemeOverrides"
        class="ml-4 h-[36px] rounded-2 px-3"
        @click="routerPushByKey('global-chat')"
      >
        {{ $t("common.chat") }}
      </n-button>
      <n-button
        v-if="!isMobile"
        :theme-overrides="buttonThemeOverrides"
        class="ml-4 h-[36px] rounded-2 px-3"
        @click="handleToDocs"
      >
        <span class="flex items-center gap-1">
          {{ $t("common.docs") }}
          <n-icon :size="14">
            <icon-ion-open-outline />
          </n-icon>
        </span>
      </n-button>
    </template>
    <!-- <global-search
      class="my-5 ml-auto w-full border-0 sm:max-w-[400px]"
      :input-props="{
        inputClass: 'border-0',
        showBorder: false,
      }"
    /> -->
    <!-- <div class="ml-auto h-4 w-1px rounded bg-white opacity-40" :class="authStore.isLogin ? 'mr-5' : 'mr-2'" /> -->
    <!-- <n-dropdown v-if="isMobile" :options="options" @select="handleSelect" /> -->
    <n-dropdown v-if="isMobile" trigger="click" :options="localeDropdownOptions" @select="handleLocaleSelect">
      <n-button
        quaternary
        color="white"
        class="ml-auto mr-2"
        :aria-label="currentLocaleLabel"
        :title="currentLocaleLabel"
      >
        <template #icon>
          <n-icon>
            <icon-ion-language />
          </n-icon>
        </template>
      </n-button>
    </n-dropdown>
    <n-dropdown v-if="isMobile" trigger="click" :options="menuOptions" @select="handleSelect">
      <n-button quaternary color="white" :aria-label="$t('common.more')" :title="$t('common.more')">
        <template #icon>
          <n-icon>
            <icon-tabler-menu-2 />
          </n-icon>
        </template>
      </n-button>
    </n-dropdown>
    <template v-else>
      <n-dropdown :options="localeDropdownOptions" @select="handleLocaleSelect">
        <n-button
          :theme-overrides="buttonThemeOverrides"
          class="ml-auto mr-2 h-[36px] rounded-2 px-3"
        >
          <template #icon>
            <n-icon>
              <icon-ion-language />
            </n-icon>
          </template>
          <span v-if="!isMobile">{{ currentLocaleLabel }}</span>
        </n-button>
      </n-dropdown>
      <template v-if="authStore.isLogin">
        <!-- <global-notification /> -->
        <user-avatar />
      </template>
      <template v-else>
        <n-button
          style="
          --n-text-color-hover: rgba(255, 255, 255, 0.8);
          --n-text-color-pressed: rgba(255, 255, 255, 0.4);
        "
          class="mr-4 text-white"
          quaternary
          @click="routerPushByKey('login')"
        >
          {{ $t("common.login") }}
        </n-button>
        <n-button v-if="instanceStore.signupMode === 'open'" type="primary" @click="routerPushByKey('sign-up')">
          {{ $t("common.signup") }}
        </n-button>
      </template>
    </template>
  </section>
</template>

<script setup lang="ts">
import type { DropdownOption } from "naive-ui"

import { useBasicLayout } from "@/composables"
import { useRouterPush } from "@/composables/useRouterPush"
import GlobalAddNew from "@/layouts/modules/global-add-new/index.vue"
import GlobalMenu from "@/layouts/modules/global-menu/index.vue"
import { useAppStore } from "@/store/modules/app"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { $t } from "@airalogy/shared/locales"
import UserAvatar from "./components/user-avatar.vue"
import { buttonThemeOverrides } from "./constants"

defineOptions({ name: "GlobalHeader" })

const props = withDefaults(defineProps<IProps>(), {
  showLogo: true,
  showMenu: false,
  showMenuToggler: false,
})

const { isMobile } = useBasicLayout()
interface IProps {
  showLogo?: boolean
  showMenu?: boolean
  showMenuToggler?: boolean
  isContainer?: boolean
}

const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const appStore = useAppStore()
const { routerPushByKey } = useRouterPush()

function handleToDocs() {
  window.open(import.meta.env.VITE_DOCS_URL || "https://github.com/airalogy/platform/tree/main/docs", "_blank")
}
const menuOptions = computed<DropdownOption[]>(() => {
  if (!authStore.isLogin) {
    return [
      { label: $t("common.login"), key: "login" },
      ...(instanceStore.signupMode === "open"
        ? [{ label: $t("common.signup"), key: "sign-up" }]
        : []),
    ]
  }

  return [
    { label: $t("common.chat"), key: "chat" },
    { label: $t("common.docs"), key: "docs" },
    { label: $t("common.profile"), key: "profile" },
    ...(authStore.userInfo.roles?.some(role => role === "R_ADMIN" || role === "R_SUPER")
      ? [{ label: $t("common.adminDashboard"), key: "admin-dashboard" }]
      : []),
    { type: "divider", key: "account-divider" },
    { label: $t("common.logout"), key: "logout" },
  ]
})

async function handleSelect(key: string | number) {
  switch (key) {
    case "login":
    case "sign-up":
      await routerPushByKey(key)
      break
    case "chat":
      await routerPushByKey("global-chat")
      break
    case "docs":
      handleToDocs()
      break
    case "profile":
      await routerPushByKey("user-profile", {
        params: { username: authStore.userInfo.username, tab: "summary" },
      })
      break
    case "admin-dashboard":
      await routerPushByKey("admin-dashboard")
      break
    case "logout":
      authStore.logout()
      break
  }
}

const localeDropdownOptions = computed<DropdownOption[]>(() => {
  return appStore.localeOptions.map(option => ({
    label: option.label,
    key: option.key,
  }))
})

const currentLocaleLabel = computed(() => {
  return appStore.localeOptions.find(option => option.key === appStore.locale)?.label || appStore.locale
})

function handleLocaleSelect(key: string | number) {
  appStore.changeLocale(key as I18n.LangType)
}
</script>

<style scoped lang="sass"></style>
