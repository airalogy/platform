<template>
  <div class="h-full min-w-0" :class="[props.isCompact ? 'max-w-30' : 'min-w-20']">
    <div class="relative min-w-0">
      <n-ellipsis class="aira-type-item-title block">
        <router-link v-if="researchRoute" :to="researchRoute.protocol" class="!hover:router-link">
          {{ display.name }}
        </router-link>
      </n-ellipsis>
      <div
        v-if="props.showContext && researchRoute"
        data-testid="protocol-ownership-path"
        class="aira-type-meta mt-1 flex min-w-0 flex-wrap items-center gap-x-1"
      >
        <span class="shrink-0">{{ $t("common.from") }}</span>
        <router-link :to="researchRoute.lab" class="break-all !hover:router-link">
          {{ display.lab }}
        </router-link>
        <span aria-hidden="true">/</span>
        <router-link :to="researchRoute.project" class="break-all !hover:router-link">
          {{ display.project }}
        </router-link>
      </div>
      <div class="aira-type-meta -mb-1 mt-0.5 flex min-w-0 flex-wrap items-baseline gap-x-2">
        <router-link
          v-if="props.item.user"
          class="align-top no-underline hover:router-link"
          :to="userRoute"
        >
          {{ props.item.user.name || props.item.user.username || $t("common.unknown") }}
        </router-link>
        <span class="inline-block align-top">{{ $t("common.createdAt", { time: timeAgo }) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import type { RouteLocationRaw } from "vue-router"
import { formatDate } from "@airalogy/shared/utils"
import { useI18n } from "vue-i18n"

export interface IProps {
  item: ProtocolModels.ProjectProtocolInfo
  isCompact?: boolean
  showContext?: boolean
}

interface IDisplay {
  name: string
  lab: string
  project: string
}

const props = withDefaults(defineProps<IProps>(), {
  isCompact: true,
  showContext: false,
})
const { t, locale } = useI18n()

const timeAgo = computed(() => {
  return formatDate(props.item.created_at, "date-short")
})

const userRoute = computed<RouteLocationRaw>(() => {
  const { user } = props.item

  if (user?.username) {
    return { name: "user-profile", params: { username: user.username } }
  }

  return { name: "root" }
})

const researchRoute = computed<Record<
  "lab" | "project" | "members" | "protocol",
  RouteLocationRaw
> | null>(() => {
  const { project, uid, lab } = props.item
  if (!lab.uid || !project.uid || !uid) {
    return null
  }

  return {
    lab: {
      name: "lab-projects",
      params: {
        labUid: lab.uid,
      },
    },
    members: {
      name: "lab-members",
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
    protocol: {
      name: "protocol-info",
      params: {
        protocolUid: uid,
        projectUid: project.uid,
        labUid: lab.uid,
      },
    },
  }
})

const display = computed<IDisplay>(() => {
  const { item } = props

  return {
    name: item.name,
    lab: item.lab.name || item.lab.uid || t("common.unknownLab"),
    project: item.project.name || item.project.uid || t("common.unknownProject"),
  }
})
</script>

<style scoped lang="sass"></style>
