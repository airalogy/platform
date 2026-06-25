<template>
  <div class="max-h-80 w-80">
    <div
      v-for="item in marketItems"
      :key="item.name"
      class="mb-4 flex items-center"
    >
      <!-- <n-avatar class="h-8 min-w-8 w-8" >
        <component :is="item.icon" />
      </n-avatar> -->
      <n-icon :component="item.icon" />
      <router-link
        :to="item.to"
        class="wrap ml-2 hover:router-link"
      >
        {{ item.name }}
      </router-link>
    </div>
    <n-divider class="!my-3" />
    <router-link
      :to="{ name: 'hub-list' }"
      class="menu__link"
    >
      Hub
    </router-link>
  </div>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from "vue-router"
import MarketIcon from "~icons/carbon/shopping-catalog"

const marketItems: { icon: Component, name: string, to: RouteLocationRaw }[] = [
  {
    icon: MarketIcon,
    name: "Browse Market",
    to: { name: "hub-list" },
  },

]
</script>

<style scoped lang="sass">
.menu__link
  @apply block h-8 leading-8 capitalize hover:router-link
</style>
