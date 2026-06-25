<template>
  <n-tag
    size="large"
    class="my-1 rounded bg-white pl-2 pr-3.5 !h-10"
    closable
    @close="handleClose"
    @click.stop
  >
    <div class="flex items-center">
      <n-avatar
        :src="avatarSrc"
        size="small"
        class="shrink-0"
        fallback-src="/images/avatar_default.svg"
        color="transparent"
        object-fit="cover"
      />
      <span class="mx-3">{{ props.name }}</span>
      <div v-if="props.changeRole" class="flex items-center text-gray-400 transition-colors hover:text-primary">
        <template v-if="isEditingAlias">
          <n-input
            v-model:value="aliasRef"
            size="tiny"
            :placeholder="`Add alias for ${props.name}`"
            class="!w-32"
            autofocus
            @blur="handleAliasBlur"
            @keyup.enter="handleAliasBlur"
          />
        </template>
        <template v-else>
          <span v-if="aliasRef" class="text-sm text-gray-500">({{ aliasRef }})</span>
          <tooltip-button
            :tooltip="aliasRef ? 'Edit alias' : 'Add alias'"
            button-class="!h-6 !p-0.5"
            :button-props="{ quaternary: true, size: 'tiny' }"
            @click="toggleAliasEdit"
          >
            <template #icon>
              <n-icon size="16">
                <icon-ion-pencil-outline v-if="aliasRef" />
                <icon-ion-add-outline v-else />
              </n-icon>
            </template>
          </tooltip-button>
        </template>
      </div>
      <n-text v-if="props.username" depth="3" class="mr-3">
        (@{{ props.username }})
      </n-text>
      <n-select
        v-if="props.changeRole"
        :value="roleRef"
        :options="(memberRoles as SelectMixedOption[])"
        size="small"
        ghost
        :disabled="!props.changeRole"
        :bordered="false"
        class="mr-2 w-28"
        :consistent-menu-width="false"
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
import { useProjectPermissions } from "@/composables"
import { LabRole, ProjectRole } from "@/enum"
import TooltipButton from "@airalogy/components/tooltip-button.vue"
import { useOrProvideProjectInfoStore } from "../../project-protocols/hooks/useProjectInfoStore"

defineOptions({ name: "LabMemberTag" })

const props = withDefaults(defineProps<IProps>(), {
  changeRole: true,
  avatar: "/images/avatar_default.svg",
  username: undefined,
})

const emits = defineEmits<IEmits>()

export interface IProps {
  name: string
  username?: string
  id: string
  avatar?: string | null
  role?: LabRole | ProjectRole
  changeRole?: boolean
  type?: "lab" | "project" | "group"
  isPrivate?: boolean
}

interface IEmits {
  (ev: "tag:close", val: string): void
  (ev: "select:role", val: { role: Api.Lab.LabRole, id: string }): void
  (ev: "update:alias", val: { alias: string, id: string }): void
}

const roleRef = ref<Api.Lab.LabRole>(
  props.role
  || (props.type === "group" || props.type === "project"
    ? (props.isPrivate ? ProjectRole.RECORDER : ProjectRole.COLLABORATOR)
    : LabRole.MEMBER),
)

const aliasRef = ref("")
const isEditingAlias = ref(false)
const { projectInfo } = useOrProvideProjectInfoStore(null)

const {
  isOwner: isProjectOwner,
  isManager: isProjectManager,
} = useProjectPermissions(projectInfo)

const projectRoleOptions = Object.entries(ProjectRole)
  .filter(([_, value]) => typeof value === "number")
  .map(([key, value]) => ({
    label: key.charAt(0).toUpperCase() + key.slice(1).toLowerCase(),
    value: Number(value),
  }))

const memberRoles = computed<SelectMixedOption[]>(() => {
  if (props.type === "group" || props.type === "project") {
    const baseRoleOptions = props.isPrivate ? projectRoleOptions.filter(({ value }) => value <= ProjectRole.RECORDER) : projectRoleOptions

    if (isProjectOwner.value) {
      return baseRoleOptions
    }
    if (isProjectManager.value) {
      return baseRoleOptions.filter(option => option.value > ProjectRole.MANAGER)
    }

    return props.isPrivate ? baseRoleOptions : projectRoleOptions.filter(({ value }) => value >= ProjectRole.EXPLORER)
  }

  return [
    { label: "Manager", value: LabRole.MANAGER },
    { label: "Member", value: LabRole.MEMBER },
  ]
})

const avatarSrc = computed(() => {
  const { avatar } = props
  return avatar || "/images/avatar_default.svg"
})

function handleClose(e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  emits("tag:close", props.id)
}

function updateRoleRef(role: Api.Lab.LabRole) {
  roleRef.value = role
  emits("select:role", { role, id: props.id })
}

function toggleAliasEdit() {
  if (!props.changeRole)
    return
  isEditingAlias.value = !isEditingAlias.value
}

function handleAliasBlur() {
  isEditingAlias.value = false
  if (aliasRef.value !== "") {
    emits("update:alias", { alias: aliasRef.value, id: props.id })
  }
}

onMounted(() => {
  // Initialize role correctly based on type
  if (!props.role) {
    if (props.type === "group" || props.type === "project") {
      roleRef.value = props.isPrivate ? ProjectRole.RECORDER : ProjectRole.COLLABORATOR
    }
    else {
      roleRef.value = LabRole.MEMBER
    }
  }
})
</script>
