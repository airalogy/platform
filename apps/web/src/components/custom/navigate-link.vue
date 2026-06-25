<template>
  <router-link :to="props.to" #="{ navigate, href }" custom>
    <n-a :href="href" v-bind="$attrs" @click="navigate">
      <slot />
    </n-a>
  </router-link>
</template>

<script lang="ts" setup>
import type { RouteLocationRaw } from "vue-router"

interface IProps {
  to: RouteLocationRaw
}

const props = defineProps<IProps>()
</script>
