<template>
  <header>
    <div class="mt-5 flex items-center">
      <n-icon :size="40">
        <icon-local-protocol />
      </n-icon>

      <template v-if="props.protocol">
        <router-link
          v-if="authStore.isLogin"
          :to="{ name: 'lab-projects', params: { labUid: props.protocol?.lab?.uid } }"
          class="ml-5 text-6 color-text-secondary"
        >
          {{ props.protocol?.lab?.name }}
        </router-link>
        <span v-else class="ml-5 text-6 color-text-secondary">
          {{ props.protocol?.lab?.name }}
        </span>
        <span class="mx-3 select-none text-5 color-text-secondary">/</span>
        <router-link
          :to="{ name: 'project-protocols', params: { labUid: props.protocol?.lab?.uid, projectUid: props.protocol?.project?.uid } }"
          class="text-6 color-text-secondary"
        >
          {{ props.protocol?.project?.name }}
        </router-link>
        <span class="mx-3 select-none text-5 color-text-secondary">/</span>
        <h2 class="!text-6">
          {{ props.protocol?.name }}
        </h2>
      </template>
      <n-skeleton v-else class="ml-5" width="20rem" />
    </div>
    <!-- <n-card class="mr-auto mt-3 max-w-[calc(75%-6px)]">
      {{ props.item.description }}
    </n-card> -->
  </header>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import { useAuthStore } from "@/store/modules/auth"

interface Props {
  protocol?: ProtocolModels.ProjectProtocolInfo | null
  isStarred: boolean
}

const props = defineProps<Props>()
const authStore = useAuthStore()
</script>
