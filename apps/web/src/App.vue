<template>
  <n-config-provider
    :theme-overrides="themeStore.naiveTheme"
    :locale="naiveLocale"
    :date-locale="naiveDateLocale"
    inline-theme-disabled
    class="h-full"
  >
    <app-provider>
      <router-view />
    </app-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { DEFAULT_LOCALE } from "@/locales"
import { naiveDateLocales, naiveLocales } from "@/locales/naive"
import { useAppStore } from "@/store/modules/app"
import { useAuthStore } from "@/store/modules/auth"
import { useThemeStore } from "@airalogy/composables/theme"

defineOptions({
  name: "App",
})

const themeStore = useThemeStore()
const authStore = useAuthStore()
const appStore = useAppStore()

const naiveLocale = computed(() => naiveLocales[appStore.locale] || naiveLocales[DEFAULT_LOCALE])
const naiveDateLocale = computed(() => naiveDateLocales[appStore.locale] || naiveDateLocales[DEFAULT_LOCALE])

onMounted(async () => {
  await authStore.getUserAvatar()
})
</script>

<style lang="sass">
.n-message .n-message__content
  max-height: 80vh
  word-break: break-all
  overflow-y: auto
</style>
