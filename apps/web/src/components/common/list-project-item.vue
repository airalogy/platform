<template>
  <div class="flex items-center">
    <template v-if="display && labName">
      <div v-if="props.isCompact" class="ml-2 min-w-0 flex flex-1 flex-col gap-1">
        <div class="min-w-0 flex items-center gap-2">
          <router-link
            :to="{
              name: 'project-protocols',
              params: { projectUid: display.project.uid, labUid: display.lab.uid },
            }"
            class="min-w-0 truncate text-4 font-500 leading-5 !text-[#333] hover:router-link"
            @click.stop
          >
            {{ item.name || item.uid }}
          </router-link>
          <span
            v-if="visibilityLabel"
            class="inline-flex items-center whitespace-nowrap rounded px-2 py-0.5 text-xs font-500"
            :class="visibilityClass"
          >
            {{ visibilityLabel }}
          </span>
        </div>
        <div class="min-w-0 text-3 color-text-secondary leading-5">
          <router-link
            v-if="display.lab.uid"
            :to="{ name: 'lab-projects', params: { labUid: display.lab.uid } }"
            class="block truncate hover:router-link"
            @click.stop
          >
            {{ labName }}
          </router-link>
          <span v-else class="block truncate">
            {{ labName }}
          </span>
        </div>
      </div>
      <div v-else class="lab-project-line ml-2 min-w-0 flex flex-wrap items-start gap-x-2 gap-y-1">
        <div class="lab-project-text min-w-0 flex-1 break-words text-4 color-text-secondary leading-5">
          <router-link
            v-if="display.lab.uid" :to="{ name: 'lab-projects', params: { labUid: display.lab.uid } }"
            class="break-words hover:router-link"
            @click.stop
          >
            {{ labName }}
          </router-link>
          <span v-else class="break-words">
            {{ labName }}
          </span>
          <span class="mx-1 select-none text-3">/</span>
          <router-link
            :to="{
              name: 'project-protocols',
              params: { projectUid: display.project.uid, labUid: display.lab.uid },
            }"
            class="break-words hover:router-link"
            @click.stop
          >
            {{ item.name || item.uid }}
          </router-link>
        </div>
        <span
          v-if="visibilityLabel"
          class="inline-flex items-center self-center whitespace-nowrap rounded px-2 py-0.5 text-xs font-500"
          :class="[
            visibilityClass,
            { 'ml-2': props.isCompact, 'ml-5': !props.isCompact, 'mr-auto': !props.isCompact },
          ]"
        >
          {{ visibilityLabel }}
        </span>
      </div>
    </template>
    <n-skeleton v-else width="20rem" />
  </div>
</template>

<script setup lang="ts">
import { useLoading } from "@/composables"
import { useProjectVisibility } from "@/composables/useProjectVisibility"
import { memoizedGetLabInfo } from "@/service/api/labs"

defineOptions({ name: "ListProjectItem" })

const props = withDefaults(defineProps<IProps>(), {
  isCompact: true,
})

export interface IProps {
  item: Api.Project.MyProjectInfo
  isCompact?: boolean
}

interface IDisplay {
  lab: { name: string, id: string, uid: string }
  project: { name: string, id: string, uid: string }
  count: {
    member: number
    project: number
  }
}
const display = computed<IDisplay | null>(() => {
  const { item } = props
  if (!item) {
    return null
  }

  const { lab_id, lab_name, id, name, lab_uid, uid } = item
  const info: IDisplay = {
    lab: { name: lab_name, id: lab_id, uid: lab_uid },
    project: { name, id, uid },
    count: { member: 0, project: 0 },
  }

  return info
})

const labName = ref<string | null>(null)

const { startLoading, endLoading } = useLoading()

const { visibilityLabel, visibilityClass } = useProjectVisibility(() => props.item.type)

onMounted(async () => {
  startLoading()
  const labId = props.item.lab_id
  if (!labId) {
    return
  }

  const info = await memoizedGetLabInfo(labId)
  endLoading()

  if (info) {
    labName.value = info.name || info.uid
  }
  else {
    labName.value = ""
  }
})

onUnmounted(() => {
  memoizedGetLabInfo.clear()
})
</script>

<style scoped lang="sass"></style>
