<template>
  <n-radio-group v-model:value="selectedRole" name="role-selection">
    <n-space vertical>
      <div>{{ $t("common.selectNewRole") }}</div>
      <n-radio
        v-for="roleOption in props.availableRoles"
        :key="roleOption.value"
        :value="roleOption.value"
      >
        <div class="font-semibold">
          {{ roleOption.label }}
          <span v-if="roleOption.value === props.currentRole" class="text-sm text-text-secondary font-normal">({{ $t("common.current") }})</span>
        </div>
        <div class="text-sm text-gray-500">
          {{ roleOption.description }}
        </div>
      </n-radio>
    </n-space>
  </n-radio-group>
</template>

<script setup lang="ts">
import type { RoleInfo } from "@/composables"
import type { ProjectRole } from "@/enum"

const props = defineProps<{
  availableRoles: RoleInfo[]
  currentRole: number
  role: number
}>()

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "update:role", val: ProjectRole): void
}

const selectedRole = useVModel(props, "role", emit)
</script>
