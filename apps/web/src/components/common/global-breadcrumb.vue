<template>
  <n-breadcrumb class="global-breadcrumb">
    <!-- define component: BreadcrumbContent -->
    <define-breadcrumb-content v-slot="{ breadcrumb }">
      <div class="size-full">
        <n-ellipsis class="align-middle">
          {{ breadcrumb.breadcrumbLabel || breadcrumb.label }}
        </n-ellipsis>
      </div>
    </define-breadcrumb-content>
    <!-- define component: BreadcrumbContent -->

    <n-breadcrumb-item v-for="item in currentBreadcrumb" :key="item.key" class="flex-shrink-1 ellipsis-text overflow-hidden">
      <template #separator>
        <icon-local-breadcrumb-separator />
      </template>
      <router-link v-if="item.to" :to="item.to">
        <breadcrumb-content :breadcrumb="item" />
      </router-link>
      <n-dropdown
        v-else-if="item.options?.length"
        :options="item.options"
        placement="bottom-start"
        @select="handleClickMenu"
      >
        <breadcrumb-content :breadcrumb="item" />
      </n-dropdown>
      <breadcrumb-content v-else :breadcrumb="item" />
    </n-breadcrumb-item>
  </n-breadcrumb>
</template>

<script setup lang="ts">
import type { RouteNameKey } from "@/types/page-route"
import { useRouterPush } from "@/composables/useRouterPush"
import { useRouteStore } from "@/store/modules/route"
import { createReusableTemplate } from "@vueuse/core"

defineOptions({ name: "GlobalBreadcrumb" })

const routeStore = useRouteStore()
const route = useRoute()
const { routerPushByKey } = useRouterPush()

interface BreadcrumbContentProps {
  breadcrumb: App.Global.Breadcrumb
}

const [DefineBreadcrumbContent, BreadcrumbContent]
  = createReusableTemplate<BreadcrumbContentProps>()

async function handleClickMenu(key: RouteNameKey) {
  if (key === "project-protocols" || key === "project-members") {
    const { projectUid, labUid } = route.params
    if (projectUid && labUid) {
      await routerPushByKey(key, {
        params: { projectUid: projectUid as string, labUid: labUid as string },
      })
    }
  }
  else {
    await routerPushByKey(key)
    routeStore.clearDynamicBreadcrumbs()
  }
}

const currentBreadcrumb = computed((): App.Global.Breadcrumb[] => {
  const { breadcrumbs, dynamicBreadcrumbs } = routeStore

  if (dynamicBreadcrumbs.length > 0) {
    return [...breadcrumbs, ...dynamicBreadcrumbs]
  }

  return breadcrumbs
})
</script>

<style scoped lang="sass">
:deep(.n-breadcrumb-item__separator)
  margin: 0 6px!important
:deep(.n-breadcrumb-item__link)
  max-width: 100%
</style>

<style lang="sass">
.global-breadcrumb > ul
  display: flex!important
</style>
