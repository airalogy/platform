<template>
  <n-avatar v-if="props.isUser" :size="32" round :src="avatar" fallback-src="defaultAvatar" color="transparent" />
  <n-icon v-else :size="32">
    <icon-shared-airalogy-chat />
  </n-icon>
</template>

<script lang="ts" setup>
import { NAvatar } from "naive-ui"

interface Props {
  isUser?: boolean
  image?: string
}

const props = defineProps<Props>()

const avatar = computed(() => props.image || "/images/avatar_default.svg")
</script>
