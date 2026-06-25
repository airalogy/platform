<template>
  <n-tooltip v-if="roleLabel" trigger="hover">
    <template #trigger>
      <n-tag :color="color" class="cursor-pointer" :bordered="false" v-bind="$attrs">
        {{ roleLabel }}
        <span v-if="isMyself" class="ml-1 inline-block">({{ $t("common.me") }})</span>
      </n-tag>
    </template>

    <div v-if="roleOptions.length">
      <div>
        <span>{{ roleOptions[0].label }}</span>
        {{ $t("common.can") }}
        <span>{{ uncapitalize(roleOptions[0].description) }}</span>
      </div>
      <ol class="list-decimal pl-4">
        <li v-for="(permission, index) in permissionList" :key="index">
          {{ permission }}
        </li>
      </ol>
    </div>
    <div v-else>
      {{ $t("common.noDescriptionFor", { name: roleLabel }) }}
    </div>
  </n-tooltip>
</template>

<script setup lang="ts">
import { useRoleDescription } from "@/composables/useRoleDescription"
import { ProjectType } from "@/enum"
import { useAuthStore } from "@/store/modules/auth"
import { $t } from "@airalogy/shared/locales"
import { uncapitalize } from "@airalogy/shared/utils"
import { NTooltip } from "naive-ui"

export interface IProps {
  item: Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem | Api.Profile.User | { name: string, username: string, avatar_url: string, alias?: string, id: string } | Api.Groups.GroupProjectItem | Api.Project.MyProjectInfo | Api.Lab.LabInfo | Api.Lab.UsersLabInfo
  type: "lab" | "group" | "project"
  isOwner?: boolean
  projectType?: ProjectType
}

const props = withDefaults(defineProps<IProps>(), {
  isCompact: true,
  showAtSymbol: false,
  projectType: ProjectType.PUBLIC,
})

const role = computed(() => {
  const { type, item } = props
  if (type === "lab") {
    return (item as Api.Lab.MemberListItem).lab_role || (item as Api.Lab.UsersLabInfo).user_role
  }
  if (type === "group") {
    return (item as Api.Groups.GroupProjectItem).group_role
  }

  return (item as Api.Project.MemberListItem).project_role
})

const { projectRoleOptions, labRoleOptions, roleLabel, color } = useRoleDescription(role, computed(() => props.type), computed(() => props.projectType), false)

const roleOptions = computed(() => {
  if (props.type === "lab") {
    return labRoleOptions.value
  }
  return projectRoleOptions.value
})
const permissionList = computed(() => roleOptions.value.flatMap(({ permissions }) => permissions))

const { userInfo } = useAuthStore()

const isMyself = computed(() => {
  return props.item.id === userInfo.id
})
</script>

<style scoped>

</style>
