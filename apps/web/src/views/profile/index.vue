<template>
  <section class="py-8 pl-20 pr-14">
    <n-tabs
      v-model:value="activeTab"
      placement="left"
      :theme-overrides="themOverrides"
      tab-class="rounded"
    >
      <n-tab-pane name="edit" :tab="$t('page.profile.info')">
        <edit-profile />
      </n-tab-pane>
      <n-tab-pane name="settings" :tab="$t('page.profile.setting')">
        <change-settings />
      </n-tab-pane>
      <n-tab-pane name="api-key-settings" :tab="$t('page.profile.apiKeySetting')">
        <api-key-settings />
      </n-tab-pane>
    </n-tabs>
  </section>
</template>

<script setup lang="ts">
import type { TabsProps } from "naive-ui/es/tabs"
import { $t } from "@airalogy/shared/locales"
import { useRouteParams } from "@vueuse/router"
import ApiKeySettings from "./modules/api-key-settings.vue"
import ChangeSettings from "./modules/change-settings.vue"
import EditProfile from "./modules/edit-profile.vue"

defineOptions({ name: "ProfileSettings" })

// const activeTab = ref<string>("edit")
const activeTab = useRouteParams("tab", "edit")
const themOverrides: TabsProps["themeOverrides"] = {
  tabBorderRadius: "6px",
  panePaddingMedium: "4rem 0 0 0",
}
</script>

<style scoped lang="sass">
@use "@styles/sass/tab.sass" as *
:deep(.n-tabs-nav--left.n-tabs-nav)
  width: 20rem
  border-radius: 8px
  border: 1px solid #EFEFF5
  height: fit-content
</style>
