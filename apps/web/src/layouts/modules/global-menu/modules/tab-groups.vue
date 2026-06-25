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
    <router-link to="/Labs" class="menu__link">
      My Labs
    </router-link>
    <!-- <router-link to="/labs/public" class="menu__link">
      Public Labs
    </router-link> -->
  </div>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from "vue-router"
import GlobalSearch from "@/layouts/modules/global-search/index.vue"

interface IEmits {
  (e: "modal:open"): void
  (e: "modal:close"): void
  (e: "search:start-loading"): void
  (e: "search:end-loading"): void
}

const emits = defineEmits<IEmits>()
const recentlyVisited = ref<{ avatar: string, to: RouteLocationRaw, name: string }[]>([])
</script>

<style scoped lang="sass">
.menu__link
  @apply block h-8 leading-8 capitalize hover:router-link
</style>
