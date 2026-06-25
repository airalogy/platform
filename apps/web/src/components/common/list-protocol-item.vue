<template>
  <div class="w-full item__wrapper">
    <div class="relative max-w-full w-fit ellipsis-text">
      <router-link
        :to="researchRoute.research"
        class="text-4 font-500 !text-[#333] !hover:router-link"
      >
        {{ props.item.name }}
      </router-link>
    </div>
    <div class="relative flex items-center text-3 color-text-secondary">
      <span class="relative inline-block min-w-5 w-fit ellipsis-text">
        <router-link :to="researchRoute.lab" class="!hover:router-link">
          {{ props.item.lab.name }}
        </router-link>
      </span>
      <span class="pointer-events-none mx-1 inline-block text-sm font-500">/</span>
      <span class="relative inline-block min-w-5 w-fit ellipsis-text">
        <router-link
          :to="researchRoute.project"
          class="!hover:router-link"
        >
          {{ props.item.project.name }}
        </router-link>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared"
import type { RouteLocationRaw } from "vue-router"

defineOptions({ name: "ListResearchItem" })

const props = withDefaults(defineProps<IProps>(), {
  isCompact: true,
})

export interface IProps {
  item: ProtocolModels.ProjectProtocolInfo
  isCompact?: boolean
}

// interface IDisplay {
//   name: string
//   lab: string
//   project: string
//   count: {
//     member: number
//     project: number
//   }
// }

const researchRoute = computed<Record<"research" | "lab" | "project", RouteLocationRaw>>(() => {
  const { lab, project, uid } = props.item

  return {
    research: {
      name: "protocol-info",
      params: {
        // labId,
        labUid: lab.uid,
        projectUid: project.uid,
        protocolUid: uid,
      },
    },
    lab: {
      name: "lab-projects",
      params: {
        labUid: lab.uid,
      },
    },
    project: {
      name: "project-protocols",
      params: {
        labUid: lab.uid,
        projectUid: project.uid,
      },
    },
  }
})

// async function handleAddResearch(e: MouseEvent) {
//   e.stopImmediatePropagation()
//   e.preventDefault()

//   await routerPushByKey("home")
// }
</script>

<style scoped lang="sass">
.item__wrapper
  --n-item-text-color: #666
  line-height: 1.25
  @apply overflow-hidden
</style>
