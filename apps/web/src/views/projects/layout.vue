<template>
  <global-layout>
    <content-layout title="Projects" :tabs="tabs" :title-icon="ProjectIcon">
      <template #suffix>
        <create-project-modal v-if="route.name === 'project-dashboard'" @modal:new-project="handleAddProject" />
      </template>
    </content-layout>
  </global-layout>
</template>

<script setup lang="ts">
import type { TabPaneProps } from "naive-ui/es/tabs"
import ProjectIcon from "@/components/icon/project-icon.vue"
import { useRouterPush } from "@/composables/useRouterPush"

import ContentLayout from "@/layouts/content-layout/index.vue"
import GlobalLayout from "@/layouts/global-layout/index.vue"
import { $t } from "@airalogy/shared/locales"
import CreateProjectModal from "./modules/create-project-modal.vue"

defineOptions({
  name: "ProjectLayout",
})

withDefaults(defineProps<Props>(), {
  showPadding: false,
})

interface Props {
  /** Show padding for content */
  showPadding?: boolean
}

const tabs: TabPaneProps[] = [
  { name: "project-dashboard", tab: $t("page.project.tab.my") },
  { name: "project-starred", tab: $t("page.project.tab.star") },
]

const route = useRoute()
const { routerPushByKey } = useRouterPush()
async function handleAddProject(val: Api.Project.MyProjectInfo) {
  const { lab_uid, uid } = val

  if (!lab_uid || !uid) {
    return
  }

  await routerPushByKey("project-protocols", { params: { labUid: lab_uid, projectUid: uid } })
}
</script>

<style></style>
