<template>
  <div class="organization-card">
    <div class="inline-flex">
      <div class="organization-card__badge aira-type-label">
        <span>{{ props.badgeText }}</span>
      </div>
    </div>

    <div v-for="(item, index) in props.labs" :key="index" class="organization-card__item">
      <div class="organization-card__main">
        <div class="organization-card__logo">
          <div v-if="!item.logoSrc" class="h-full w-full bg-[#FDBF46] opacity-16" />
          <img v-else :src="item.logoSrc" class="h-full w-full object-cover">
        </div>
        <div class="min-w-0 flex flex-col">
          <div class="aira-type-item-title truncate">
            {{ item.name }}
          </div>
          <div class="organization-card__metrics aira-type-metric">
            <project-icon-compact color="#9A9A9A" />
            <span>
              {{ item.projectCount }}
            </span>
            <profile-icon-compact color="#9A9A9A" />
            <span>
              {{ item.memberCount }}
            </span>
          </div>
        </div>
      </div>
      <n-tag class="shrink-0" size="small" :color="getRoleColor(item.role)" :bordered="false">
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
.organization-card
  @apply relative flex min-w-0 flex-col gap-4 border border-[#EAECF0] rounded-8px border-solid bg-white p-4 shadow-[0px_3px_12px_rgba(43,54,94,0.06)] sm:p-5

.organization-card__badge
  @apply inline-flex items-center justify-center rounded-full bg-[#1DC3E1] px-4 py-1.5 text-white

.organization-card__item
  @apply flex min-w-0 w-full items-center justify-between gap-3

.organization-card__main
  @apply flex min-w-0 flex-1 items-center gap-3

.organization-card__logo
  @apply h-10 w-10 shrink-0 overflow-hidden rounded-4px bg-[#D9D9D9]

.organization-card__metrics
  @apply flex flex-wrap items-center gap-x-2 gap-y-0
</style>
