<template>
  <div>
    <div class="h-full" :class="[props.isCompact ? 'max-w-22' : 'min-w-20 max-w-full']">
      <span class="relative">
        <n-ellipsis class="m-0 font-500">
          <router-link :to="groupRoute.group" class="!hover:router-link">
            {{ display.name }}
          </router-link>
        </n-ellipsis>
      </span>
      <div class="relative w-fit flex items-center">
        <project-icon-compact />
        <span class="relative w-fit">
          <router-link :to="groupRoute.group" class="ml-4px mr-10px !hover:router-link">
            {{ display.count.projects }}
          </router-link>
        </span>
        <profile-icon-compact />
        <span class="relative w-fit">
          <router-link :to="groupRoute.members" class="mx-4px !hover:router-link">
            {{ display.count.members }}
          </router-link>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from "vue-router"

export interface IProps {
  item: Api.Groups.MyGroupsInfo
  isCompact?: boolean
}

interface IDisplay {
  name: string
  lab: string
  project: string
  count: {
    members: number
    projects: number
  }
}
const props = withDefaults(defineProps<IProps>(), {
  isCompact: true,
})

const display = computed<IDisplay>(() => {
  if (!props.item) {
    return {
      name: "",
      lab: "",
      project: "",
      count: { members: 0, projects: 0 },
    }
  }

  const { name, users_count, projects_count, lab_name } = props.item
  return {
    name,
    lab: lab_name,
    project: name,
    count: { members: users_count, projects: projects_count },
  }
})

const groupRoute = computed<Record<"lab" | "group" | "members", RouteLocationRaw>>(() => {
  const { lab_id, lab_uid: labUid, id } = props.item

  return {
    lab: {
      name: "lab-group-projects",
      params: {
        labUid,
        groupId: id,
      },
    },
    members: {
      name: "lab-group-members",
      params: {
        labUid,
        groupId: id,
      },
    },
    group: {
      name: "lab-group-projects",
      params: {
        labUid,
        groupId: id,
      },
    },
  }
})

// const fetchProjectCount = async () => {
//   const groupId = props.item.id
//   const result = await Promise.allSettled([
//     fetchResearches(groupId, { page: 1, pageSize: 0 }),
//     fetchGroupsMemberList(groupId, { page: 1, pageSize: 0 }),
//   ])
//   result.forEach((res, idx) => {
//     if (res.status === "rejected" || !res.value) {
//       return
//     }

//     const count = res.value.data?.total_count ?? 0
//     if (idx === 0) {
//       display.value.count.researches = count
//     }
//     if (idx === 1) {
//       display.value.count.members = count || 1
//     }
//   })
// }
// onMounted(async () => {
//   await fetchProjectCount()
// })
</script>

<style scoped lang="sass"></style>
