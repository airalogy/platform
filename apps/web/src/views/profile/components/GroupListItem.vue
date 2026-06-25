<template>
  <n-card class="group-item" :bordered="false">
    <div class="group-header">
      <div class="group-info">
        <n-avatar
          :src="group.avatar || ''"
          :fallback-src="defaultAvatar"
        />
        <div class="group-details">
          <h3>{{ group.name }}</h3>
          <div class="group-id">
            <span>Id:</span>
            <span>{{ group.id }}</span>
          </div>
        </div>
        <n-tag :type="getRoleType(group.role)">
          {{ group.role }}
        </n-tag>
      </div>

      <div v-if="group.role === 'Owner'" class="group-actions">
        <n-button-group>
          <n-button secondary @click="$emit('edit', group.id)">
            <template #icon>
              <n-icon><edit-outline /></n-icon>
            </template>
          </n-button>
          <n-button secondary @click="$emit('remove', group.id)">
            <template #icon>
              <n-icon><trash-outline /></n-icon>
            </template>
          </n-button>
        </n-button-group>
      </div>
    </div>

    <div class="group-footer">
      <div class="update-time">
        <span>Recently update:</span>
        <span>{{ group.updateTime }}</span>
      </div>
      <div class="stats">
        <n-space>
          <n-statistic
            v-for="(value, key) in group.stats"
            :key="key"
            :label="key"
            :value="value"
          />
        </n-space>
      </div>
    </div>
  </n-card>
</template>

<script lang="ts" setup>
import defaultAvatar from "@/assets/images/avatar_default.svg"
import EditOutline from "~icons/ion/edit-outline"
import TrashOutline from "~icons/ion/trash-outline"

interface GroupProps {
  id: string
  name: string
  role: "Owner" | "Member"
  updateTime: string
  stats: Record<string, number>
  avatar?: string
}

const props = defineProps<{
  group: GroupProps
}>()

defineEmits<{
  (e: "edit", id: string): void
  (e: "remove", id: string): void
}>()

function getRoleType(role: string) {
  return role === "Owner" ? "success" : "info"
}
</script>

<style lang="scss" scoped>
.group-item {
  margin-bottom: 16px;

  .group-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }

  .group-info {
    display: flex;
    align-items: center;
    gap: 16px;

    .group-details {
      h3 {
        margin: 0 0 4px;
      }

      .group-id {
        color: var(--n-text-color-2);
        font-size: 14px;
      }
    }
  }

  .group-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;

    .update-time {
      color: var(--n-text-color-2);
      font-size: 14px;
    }
  }
}
</style>
