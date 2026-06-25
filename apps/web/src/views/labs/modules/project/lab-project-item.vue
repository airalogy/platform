<template>
  <div class="flex items-center">
    <div class="h-full" :class="[props.isCompact ? 'max-w-22' : 'min-w-20 max-w-full']">
      <span class="relative">
        <n-ellipsis class="m-0 font-500">
          <router-link :to="projectRoute.project" class="!hover:router-link">
            {{ display.name }}
          </router-link>
        </n-ellipsis>
      </span>
      <div v-if="props.type === 'lab'" class="relative w-fit flex items-center">
        <project-icon-compact />
        <span class="relative w-fit">
          <router-link :to="projectRoute.project" class="ml-4px mr-10px !hover:router-link">
            {{ display.count.protocols }}
          </router-link>
        </span>
        <profile-icon-compact />
        <span class="relative w-fit">
          <router-link :to="projectRoute.members" class="mx-4px !hover:router-link">
            {{ display.count.members }}
          </router-link>
        </span>
      </div>
      <div v-if="hierarchyHint" class="mt-1 text-xs text-gray-500">
        {{ hierarchyHint }}
      </div>
      <div v-else-if="props.item.description" class="whitespace-pre-wrap text-sm text-gray-500">
        <n-ellipsis>
          {{ props.item.description }}
        </n-ellipsis>
      </div>
    </div>
    <span
      v-if="visibilityLabel"
      class="inline-flex items-center whitespace-nowrap rounded px-2 py-0.5 text-xs font-500"
      :class="[visibilityClass, { 'ml-5': !props.isCompact, 'mr-auto': !props.isCompact, 'ml-2': props.isCompact }]"
    >
      {{ visibilityLabel }}
    </span>
    <slot />
  </div>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from "vue-router"
import { useProjectVisibility } from "@/composables/useProjectVisibility"
import { $t } from "@airalogy/shared/locales"

export interface IProps {
  item: Api.Project.MyProjectInfo
  type: "lab" | "group" | "project"
  isCompact?: boolean
  fetchCount?: boolean
}

interface IDisplay {
  name: string
  count: {
    members: number
    protocols: number
  }
}
const props = withDefaults(defineProps<IProps>(), {
  isCompact: true,
  fetchCount: true,
})

const display = ref<IDisplay>({
  name: props.item.name,
  count: { members: props.item.users_count || 0, protocols: props.item.protocols_count || 0 },
},
)

const projectRoute = computed<Record<"lab" | "project" | "members", RouteLocationRaw>>(() => {
  const { lab_uid: labUid, uid } = props.item

  return {
    lab: {
      name: "lab-projects",
      params: {
        labUid,
      },
    },
    members: {
      name: "project-members",
      params: {
        labUid,
        projectUid: uid,
      },
    },
    project: {
      name: "project-protocols",
      params: {
        labUid,
        projectUid: uid,
      },
    },
  }
})

const { visibilityLabel, visibilityClass } = useProjectVisibility(() => props.item.type)
const hierarchyHint = computed(() => {
  if (props.item.parent_project_name) {
    return $t("page.project.settingsPage.subprojectOf", { name: props.item.parent_project_name })
  }
  if ((props.item.children_count || 0) > 0) {
    return props.item.children_count === 1
      ? $t("page.project.settingsPage.subprojectCountSingle", { count: props.item.children_count })
      : $t("page.project.settingsPage.subprojectCountPlural", { count: props.item.children_count })
  }
  return ""
})
</script>

<style scoped lang="sass"></style>
