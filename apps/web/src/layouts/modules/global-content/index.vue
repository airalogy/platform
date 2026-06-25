<template>
  <router-view v-slot="{ Component, route }">
    <Transition
      name="fade" mode="out-in" @before-leave="appStore.setContentXScrollable(true)"
      @after-enter="appStore.setContentXScrollable(false)"
    >
      <n-spin v-if="props.showSpin" :show="appStore.loading || !appStore.reloadFlag" class="max-w-full min-h-90 flex-1" :class="props.containerClass" :content-class="props.containerContentClass">
        <keep-alive
          v-if="route.meta.keepAlive"
          :include="routeStore.cacheRoutes.length === 0 ? undefined : routeStore.cacheRoutes"
        >
          <component
            :is="Component" v-if="appStore.reloadFlag" :key="route.path" :class="{ 'p-8': props.showPadding }"
            class="transition-300"
          />
        </keep-alive>
        <component
          :is="Component" v-else-if="appStore.reloadFlag" :key="route.path" :class="{ 'p-8': props.showPadding }"
          class="transition-300"
        />
      </n-spin>

      <template v-else>
        <keep-alive
          v-if="route.meta.keepAlive"
          :include="routeStore.cacheRoutes.length === 0 ? undefined : routeStore.cacheRoutes"
        >
          <component
            :is="Component" v-if="appStore.reloadFlag" :key="route.path" :class="{ 'p-8': props.showPadding }"
            class="transition-300"
          />
        </keep-alive>
        <component
          :is="Component" v-else-if="appStore.reloadFlag" :key="route.path" :class="{ 'p-8': props.showPadding }"
          class="transition-300"
        />
      </template>
    </Transition>
  </router-view>
</template>

<script setup lang="ts">
import { memoizedGetLabInfo } from "@/service/api/labs"
import { useAppStore } from "@/store/modules/app/"
import { useRouteStore } from "@/store/modules/route"

defineOptions({
  name: "GlobalContent",
})

const props = withDefaults(defineProps<Props>(), {
  showPadding: false,
  containerContentClass: "w-full h-full",
  showSpin: false,
})

interface Props {
  /** Show padding for content */
  showPadding?: boolean
  /** Container class */
  containerClass?: string
  /** Container content class */
  containerContentClass?: string
  /** Show spin */
  showSpin?: boolean
}

const appStore = useAppStore()
const routeStore = useRouteStore()

watch(() => appStore.reloadFlag, (val) => {
  if (!val) {
    memoizedGetLabInfo.clear()
  }
})
</script>

<style></style>
