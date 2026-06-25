<template>
  <div class="relative flex flex-col gap-18px border border-[#EAECF0] rounded-8px border-solid bg-white p-19px shadow-[0px_3px_12px_rgba(43,54,94,0.06)]">
    <div class="inline-flex">
      <div class="inline-flex items-center justify-center rounded-34px bg-[#1DC3E1] px-17px py-6px text-14px text-white font-400">
        <span>{{ props.badgeText }}</span>
      </div>
    </div>

    <div v-for="(item, index) in props.labs" :key="index" class="w-full flex items-center justify-between">
      <div class="flex items-center gap-2">
        <div class="h-8 w-8 overflow-hidden rounded-4px bg-[#D9D9D9]">
          <div v-if="!item.logoSrc" class="h-full w-full bg-[#FDBF46] opacity-16" />
          <img v-else :src="item.logoSrc" class="h-full w-full object-cover">
        </div>
        <div class="flex flex-col">
          <div class="text-14px text-[#333333] font-500">
            {{ item.name }}
          </div>
          <div class="flex items-center gap-2">
            <project-icon-compact color="#9A9A9A" />
            <div class="text-14px text-[#666666] font-500">
              {{ item.projectCount }}
            </div>
            <profile-icon-compact color="#9A9A9A" />
            <div class="text-14px text-[#666666] font-500">
              {{ item.memberCount }}
            </div>
          </div>
        </div>
      </div>
      <n-tag :color="getRoleColor(item.role)" :bordered="false">
        {{ item.role }}
      </n-tag>
    </div>
  </div>
</template>

<script setup lang="ts">
import ProfileIconCompact from "@/components/icon/profile-icon-compact.vue"
import ProjectIconCompact from "@/components/icon/project-icon-compact.vue"
import { NTag } from "naive-ui"

defineOptions({ name: "OrganizationCard" })

const props = withDefaults(defineProps<IProps>(), {
  badgeText: "Labs",
  labs: () => [],
})

export interface IProps {
  badgeText?: string
  labs: {
    name: string
    memberCount: number
    projectCount: number
    role: "owner" | "manager" | "member"
    logoSrc?: string
  }[]
}

function getRoleColor(role: "owner" | "manager" | "member") {
  if (role === "owner") {
    return { color: "#EDF4FF", textColor: "#1A79FF" }
  }
  if (role === "manager") {
    return { color: "#FFF7EF", textColor: "#F99534" }
  }
  if (role === "member") {
    return { color: "#EDF8F4", textColor: "#1BA37B" }
  }

  return { color: "#E7EFFF", textColor: "#1A79FF" }
}
</script>

<style scoped lang="sass">
// Remove all styles as they're now inline in the template using UnoCSS
</style>
