<template>
  <div class="w-full flex items-start">
    <div class="min-w-0 flex flex-1 items-start gap-2">
      <div
        class="h-full"
        :class="[props.isCompact ? (props.item.type === 1 ? 'max-w-29' : '') : 'min-w-20']"
      >
        <span class="relative">
          <n-ellipsis class="m-0 text-4 font-500">
            <router-link :to="labRoute.lab" class="!hover:router-link">
              {{ display.name }}
            </router-link>
          </n-ellipsis>
        </span>
        <div class="relative w-fit flex items-center text-3 color-text-secondary">
          <n-tooltip trigger="hover">
            <template #trigger>
              <project-icon-compact />
            </template>
            {{ $t("page.labs.projects") }}
          </n-tooltip>
          <span class="relative w-fit">
            <router-link :to="labRoute.projects" class="ml-4px mr-10px !hover:router-link">
              {{ display.count.project }}
            </router-link>
          </span>
          <n-tooltip trigger="hover">
            <template #trigger>
              <profile-icon-compact />
            </template>
            {{ $t("page.labs.members") }}
          </n-tooltip>
          <span class="relative w-fit">
            <router-link :to="labRoute.members" class="mx-4px !hover:router-link">
              {{ display.count.member }}
            </router-link>
          </span>
        </div>
      </div>
      <div v-if="props.isCompact" class="ml-2 flex items-center self-center gap-1">
        <global-role-tag :item="props.item" type="lab" class="shrink-0" />
        <lock-icon v-if="props.item.type === 1" class="shrink-0" />
      </div>
    </div>
    <template v-if="!props.isCompact">
      <global-role-tag :item="props.item" type="lab" class="ml-4 mr-auto" />
      <lock-icon
        v-if="props.item.type === 1"
        :class="{ 'ml-5': !props.isCompact, 'mr-auto': !props.isCompact }"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from "vue-router"

defineOptions({ name: "ListLabItem" })

const props = withDefaults(defineProps<IProps>(), {
  isCompact: true,
})

export interface IProps {
  item: Api.Lab.LabInfo | Api.Lab.UsersLabInfo
  isCompact?: boolean
}

interface IDisplay {
  name: string
  lab: string
  project: string
  count: {
    member: number
    project: number
  }
}
const display = computed<IDisplay>(() => {
  const { item } = props
  const info: IDisplay = {
    name: item.name || item.uid,
    lab: "",
    project: "",
    count: { member: item.users_count, project: item.projects_count },
  }

  return info
})

const labRoute = computed<Record<"lab" | "members" | "projects", RouteLocationRaw>>(() => {
  const { uid: labUid } = props.item

  return {
    lab: {
      name: "lab-projects",
      params: {
        labUid,
      },
    },
    members: {
      name: "lab-members",
      params: {
        labUid,
      },
    },
    projects: {
      name: "lab-projects",
      params: {
        labUid,
      },
    },
  }
})
</script>

<style scoped lang="sass"></style>
