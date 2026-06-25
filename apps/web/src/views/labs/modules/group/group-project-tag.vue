<template>
  <n-tag
    size="large"
    class="my-1 rounded bg-white pl-4 pr-3.5 !h-10"
    closable
    @close="handleClose"
    @click.stop
  >
    <div class="flex items-center">
      <span class="mr-3">
        {{ props.name }}
      </span>
      <span
        v-if="visibilityLabel"
        class="mr-2 inline-flex items-center whitespace-nowrap rounded px-2 py-0.5 text-xs font-500"
        :class="visibilityClass"
      >
        {{ visibilityLabel }}
      </span>
      <n-select
        :value="roleRef"
        :options="(projectRoleOptions as any as SelectMixedOption[])"
        size="small"
        ghost
        :consistent-menu-width="false"
        :disabled="!props.changeRole"
        :bordered="false"
        class="mr-2 w-28"
        :theme-overrides="{
          peers: {
            InternalSelection: {
              heightMedium: '32px',
              fontSizeMedium: '14px',
              borderRadius: '4px',
              color: 'transparent',
              colorActive: 'transparent',
            },
          },
        }"
        @update:value="updateRoleRef"
      />
    </div>
  </n-tag>
</template>

<script setup lang="ts">
import type { SelectMixedOption } from "naive-ui/es/select/src/interface"
import { useRoleDescription } from "@/composables"
import { useProjectVisibility } from "@/composables/useProjectVisibility"
import { ProjectRole, ProjectType } from "@/enum"

defineOptions({ name: "GroupProjectTag" })
const props = withDefaults(defineProps<IProps>(), {
  changeRole: true,
  role: ProjectRole.VIEWER,
  type: ProjectType.PUBLIC,
})

const emits = defineEmits<IEmits>()

export interface IProps {
  name: string
  id: string
  topRole: ProjectRole
  type?: ProjectType
  changeRole?: boolean
  role?: ProjectRole
}

interface IEmits {
  (ev: "tag:close", val: string): void
  (ev: "select:role", val: { role: Api.Lab.LabRole, id: string }): void
}

const roleRef = ref<Api.Lab.LabRole>(props.role)

const { projectRoleOptions } = useRoleDescription(computed(() => props.topRole), "project", computed(() => props.type))

const { visibilityLabel, visibilityClass } = useProjectVisibility(() => props.type)

function handleClose(e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  emits("tag:close", props.id)
}

function updateRoleRef(role: Api.Lab.LabRole) {
  roleRef.value = role
  emits("select:role", { role, id: props.id })
}
</script>
