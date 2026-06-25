<template>
  <div class="min-h-[200px] p-4">
    <template v-if="versions.length">
      <div class="space-y-4">
        <n-timeline>
          <n-timeline-item
            v-for="version in versions"
            :key="version.id"
            :title="version.version"
            :time="formatDate(version.createdAt)"
          >
            {{ version.description }}
          </n-timeline-item>
        </n-timeline>
      </div>
    </template>
    <n-empty v-else description="No version history available yet">
      <template #extra>
        <n-button secondary>
          View All Versions
        </n-button>
      </template>
    </n-empty>
  </div>
</template>

<script setup lang="ts">
import { formatDate } from "@airalogy/shared/utils"

interface Version {
  id: string
  version: string
  description: string
  createdAt: string
}

const versions = ref<Version[]>([])

// Add your version history loading logic here
</script>
