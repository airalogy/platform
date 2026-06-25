<template>
  <n-tooltip trigger="hover">
    <div class="flex items-center">
      <template v-for="(segment, index) in pathSegments" :key="segment.uid">
        <router-link
          class="!hover:router-link"
          :to="segment.route"
        >
          {{ segment.uid }}
        </router-link>
        <span v-if="index < pathSegments.length - 1" class="mx-1">/</span>
      </template>
    </div>
    <template #trigger>
      <div class="inline-flex items-center font-semibold">
        <template v-for="(segment, index) in pathSegments" :key="segment.uid">
          <router-link
            class="!hover:router-link"
            :to="segment.route"
          >
            {{ segment.name }}
          </router-link>
          <span v-if="index < pathSegments.length - 1" class="mx-1">/</span>
        </template>
      </div>
    </template>
  </n-tooltip>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types/models"
import { useProtocolPath } from "@/composables/useProtocolPath"
import { NTooltip } from "naive-ui"

interface Props {
  protocolInfo: ProtocolModels.ProjectProtocolInfo
  showProtocolName?: boolean
}

const props = defineProps<Props>()
const { pathSegments } = useProtocolPath(props.protocolInfo, props.showProtocolName)
</script>
