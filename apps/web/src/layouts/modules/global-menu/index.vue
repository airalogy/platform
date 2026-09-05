<template>
  <nav :aria-label="$t('common.workspaceNavigation')" class="workspace-nav" data-testid="workspace-navigation">
    <div v-if="wide" class="workspace-nav__links">
      <router-link
        v-for="item in items" :key="item.name" :to="destination(item.name)"
        class="workspace-nav__link" :class="{ 'workspace-nav__link--active': activeName === item.name }"
        :aria-current="activeName === item.name ? 'page' : undefined"
      >
        {{ item.label }}
      </router-link>
    </div>
    <n-popover v-else v-model:show="expanded" trigger="click" placement="bottom-start" :show-arrow="false">
      <template #trigger>
        <n-button
          :theme-overrides="props.buttonThemeOverrides ?? buttonThemeOverrides" class="h-9 rounded-2 px-3"
          :aria-expanded="expanded" :aria-label="$t('common.workspaceNavigation')" data-testid="workspace-menu-trigger"
        >
          {{ props.label || activeLabel }}
          <template #icon><dropdown-icon filled :expended="expanded" /></template>
        </n-button>
      </template>
      <div class="workspace-nav__menu">
        <router-link
          v-for="item in items" :key="item.name" :to="destination(item.name)"
          class="workspace-nav__menu-link" :aria-current="activeName === item.name ? 'page' : undefined"
          @click="expanded = false"
        >
          {{ item.label }}
        </router-link>
      </div>
    </n-popover>
  </nav>
</template>

<script setup lang="ts">
import type { ButtonProps } from "naive-ui"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { $t } from "@airalogy/shared/locales"
import { useMediaQuery } from "@vueuse/core"
import { buttonThemeOverrides } from "../global-header/constants"

const props = defineProps<{ compact?: boolean, label?: string, buttonThemeOverrides?: ButtonProps["themeOverrides"] }>()
const route = useRoute()
const auth = useAuthStore()
const instance = useInstanceStore()
const desktop = useMediaQuery("(min-width: 1280px)")
const wide = computed(() => desktop.value && !props.compact)
const expanded = ref(false)
const items = computed<Array<{ name: App.Global.RouteNameKey, label: string }>>(() => [
  { name: "home", label: $t("route.home") },
  { name: "project-dashboard", label: $t("common.projectsLabel") },
  { name: "protocols-my", label: $t("common.protocolsLabel") },
  { name: "knowledge-home", label: $t("page.knowledge.title") },
  { name: "research-tasks", label: $t("page.research.title") },
  { name: "profile-records", label: $t("page.recordDiary.tab") },
  ...(!instance.isSingleLab ? [{ name: "labs-my" as const, label: $t("common.labsLabel") }] : []),
])
const activeName = computed(() => {
  const name = String(route.name || "")
  if (name.includes("knowledge"))
    return "knowledge-home"
  if (name.includes("research"))
    return "research-tasks"
  if (["profile-records", "project-records", "lab-records"].includes(name))
    return "profile-records"
  if (name.includes("protocol"))
    return "protocols-my"
  if (name.startsWith("project"))
    return "project-dashboard"
  if (name.startsWith("lab"))
    return "labs-my"
  if (name === "home" || name === "root")
    return "home"
  return null
})
const activeLabel = computed(() => items.value.find(item => item.name === activeName.value)?.label || $t("common.workspace"))

function destination(name: App.Global.RouteNameKey) {
  return name === "profile-records"
    ? { name, params: { username: auth.userInfo.username } }
    : { name }
}
watch(() => route.fullPath, () => {
  expanded.value = false
})
</script>

<style scoped>
.workspace-nav { min-width: 0; }
.workspace-nav__links { display: flex; align-items: center; gap: 0.125rem; }
.workspace-nav__link {
  border-radius: 0.5rem;
  padding: 0.625rem 0.75rem;
  color: rgb(255 255 255 / 80%);
  white-space: nowrap;
  text-decoration: none;
}
.workspace-nav__link:hover, .workspace-nav__link--active { color: white; background: rgb(255 255 255 / 14%); }
.workspace-nav__link--active { box-shadow: inset 0 -2px #74b9ff; }
.workspace-nav__menu { display: grid; min-width: 12rem; gap: 0.25rem; }
.workspace-nav__menu-link { padding: 0.625rem 0.75rem; border-radius: 0.375rem; color: inherit; text-decoration: none; }
.workspace-nav__menu-link:hover, .workspace-nav__menu-link[aria-current] { background: #edf5ff; color: #0067b3; }
.workspace-nav a:focus-visible { outline: 2px solid #74b9ff; outline-offset: 2px; }
</style>
