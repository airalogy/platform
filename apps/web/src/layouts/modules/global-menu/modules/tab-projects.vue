<template>
  <div class="max-h-80 w-80">
    <global-search />
    <!-- <h4 class="text- my-2 font-300">
      Recently visited
    </h4> -->
    <div v-for="item in recentlyVisited" :key="item.name" class="mb-4 flex items-center">
      <n-avatar :src="item.avatar" class="h-8 min-w-8 w-8" />
      <router-link :to="item.to" class="wrap ml-2 hover:router-link">
        {{ item.name }}
      </router-link>
    </div>
    <n-divider class="!my-3" />
    <router-link :to="{ name: 'project-dashboard' }" class="menu__link">
      My Projects
    </router-link>
    <router-link to="/projects/starred" class="menu__link">
      Stared Projects
    </router-link>
    <!-- <n-divider class="!my-2" />
    <create-project-modal
      trigger="Create New Project"
      :show-icon="false"
      :button-props="{
        class: 'justify-start m-0 p-0 h-8',
        bordered: false,
        block: true,
      }"
      @modal:close="emits('modal:close')"
      @modal:open="emits('modal:open')"
      @modal:new-project="handleAddProject"
    /> -->
  </div>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from "vue-router"
import { useRouterPush } from "@/composables/useRouterPush"
import GlobalSearch from "@/layouts/modules/global-search/index.vue"

interface IEmits {
  (e: "modal:open"): void
  (e: "modal:close"): void
  (e: "search:start-loading"): void
  (e: "search:end-loading"): void
}

const emits = defineEmits<IEmits>()

const { routerPushByKey } = useRouterPush()
async function handleAddProject(val: Api.Project.MyProjectInfo) {
  const { lab_uid, uid } = val

  if (!lab_uid || !uid) {
    return
  }

  await routerPushByKey("project-protocols", { params: { labUid: lab_uid, projectUid: uid } })
}

const recentlyVisited = ref<{ avatar: string, to: RouteLocationRaw, name: string }[]>([])
</script>

<style scoped lang="sass">
.menu__link
  @apply block h-8 leading-8 capitalize hover:router-link
</style>
