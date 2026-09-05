<template>
  <section
    data-testid="app-shell-header"
    class="mx-auto h-[70px] min-w-0 w-full flex items-center"
    :class="isContainer ? 'container' : ''"
    :style="containerStyle"
  >
    <global-logo class="mr-3 shrink-0 text-white lg:mr-5" monochrome :compact="isMobile" />
    <template v-if="authStore.isLogin">
      <global-menu />
      <global-add-new />
      <n-button
        v-if="!isMobile && instanceStore.aiEnabled"
        :theme-overrides="buttonThemeOverrides"
        class="ml-2 h-[36px] rounded-2 px-3"
        @click="routerPushByKey('global-chat')"
      >
        {{ $t("common.chat") }}
      </n-button>
      <n-dropdown v-if="!isMobile" trigger="click" :options="discoveryOptions" @select="handleSelect">
        <n-button :theme-overrides="buttonThemeOverrides" class="ml-2 h-9 rounded-2 px-3">
          {{ $t("common.more") }}
        </n-button>
      </n-dropdown>
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
      <n-dropdown trigger="click" :options="localeDropdownOptions" @select="handleLocaleSelect">
        <n-button
          :theme-overrides="buttonThemeOverrides"
          class="ml-auto mr-2 h-[36px] rounded-2 px-3"
          :aria-label="currentLocaleLabel"
        >
          <template #icon>
            <n-icon>
              <icon-ion-language />
            </n-icon>
          </template>
          <span v-if="!compactHeader">{{ currentLocaleLabel }}</span>
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
import { useMediaQuery } from "@vueuse/core"
import UserAvatar from "./components/user-avatar.vue"
import { buttonThemeOverrides } from "./constants"

defineOptions({ name: "GlobalHeader" })

const props = withDefaults(defineProps<IProps>(), {
  showLogo: true,
  showMenu: false,
  showMenuToggler: false,
})

const { isMobile } = useBasicLayout()
const compactHeader = useMediaQuery("(max-width: 1535px)")
interface IProps {
  showLogo?: boolean
  showMenu?: boolean
  showMenuToggler?: boolean
  isContainer?: boolean
  maxWidth?: number
}

const containerStyle = computed(() =>
  props.isContainer && props.maxWidth
    ? { maxWidth: `${props.maxWidth}px` }
    : undefined,
)

const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const appStore = useAppStore()
const { routerPushByKey } = useRouterPush()

async function handleToHelp() {
  await routerPushByKey("help-center")
}
const discoveryOptions = computed<DropdownOption[]>(() => [
  ...(!instanceStore.isSingleLab ? [{ label: $t("common.hub"), key: "hub" }] : []),
  { label: $t("page.help.title"), key: "help" },
])
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
    ...(instanceStore.aiEnabled ? [{ label: $t("common.chat"), key: "chat" }] : []),
    ...discoveryOptions.value,
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
    case "hub":
      await routerPushByKey("hub")
      break
    case "chat":
      await routerPushByKey("global-chat")
      break
    case "help":
      await handleToHelp()
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
