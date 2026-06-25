<template>
  <div class="flex items-center gap-2">
    <div class="flex flex-col">
      <span class="text-base font-medium">{{ item.name }}</span>
      <div class="flex items-center gap-1 text-xs text-gray-500">
        <span>Id:</span>
        <span>{{ item.id }}</span>
      </div>
    </div>
    <n-tag :type="getRoleType(item.user_role)">
      {{ item.user_role }}
    </n-tag>
  </div>
</template>

<script setup lang="ts">
import { LabRole } from "@/enum"

defineProps<{
  item: Api.Groups.GroupsInfo
  isCompact?: boolean
}>()

function getRoleType(role: number) {
  // return role === "Owner" ? "success" : "info"
  return role === LabRole.OWNER ? "success" : "info"
}
</script>
