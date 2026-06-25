<template>
  <n-card
    content-style="padding-bottom: 0"
    header-style="padding-bottom: 0"
    footer-style="padding-bottom: 14px"
    class="mb-5 rounded-2.5"
    hoverable
  >
    <template #header>
      <div class="flex items-center">
        <n-avatar
          round
          :size="40"
          :src="props.user.avatar_url || '/images/avatar_default.svg'"
          fallback-src="/images/logo.png"
          color="transparent"
        />
        <n-skeleton v-if="loading" text style="width: 30em" />
        <div v-else class="ml-4 text-4">
          <div class="-mb-1">
            <router-link class="align-middle no-underline hover:router-link" :to="userRoute">
              {{ props.user.name || props.user.username }}
            </router-link>
            <span class="ml-3 inline-block align-middle font-400">{{ props.activity }}</span>
          </div>
          <span class="text-3 font-400">
            <n-time :time="new Date(props.time)" type="relative" />
          </span>
        </div>
      </div>
    </template>
    <template v-if="loading">
      <n-skeleton text style="width: 20em" />
    </template>
    <div v-else class="my-2 w-fit font-medium">
      <router-link v-if="activityRoute.lab" :to="activityRoute.lab" class="hover:router-link">
        {{ props.lab.name }}
      </router-link>
      <template v-if="activityRoute.project">
        <span class="pointer-events-none mx-1 inline-block text-sm font-500 -mt-1">/</span>
        <router-link :to="activityRoute.project" class="hover:router-link">
          {{ props.project?.name }}
        </router-link>
      </template>
      <template v-if="activityRoute.protocol">
        <span class="pointer-events-none mx-1 inline-block text-sm font-500 -mt-1">/</span>
        <router-link :to="activityRoute.protocol" class="hover:router-link">
          {{ props.protocol?.name || "" }}
        </router-link>
      </template>
      <template v-if="activityRoute.record">
        <span class="pointer-events-none mx-1 inline-block text-sm font-500 -mt-1">/</span>
        <router-link :to="activityRoute.record" class="hover:router-link">
          {{ props.record?.record_id || "" }}
        </router-link>
      </template>
    </div>
    <template #footer>
      <template v-if="loading">
        <n-skeleton text :repeat="3" style="width: 60%" />
        <n-skeleton text style="width: 60%" />
      </template>
      <n-ellipsis v-else-if="props.description" :line-clamp="2" :tooltip="{ width: 900 }">
        {{ props.description }}
      </n-ellipsis>
      <div v-else />
    </template>
  </n-card>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import type { RouteLocationRaw } from "vue-router"

export interface IProps {
  id: string
  user: Partial<Api.Auth.UserInfo>
  project?: Partial<Api.Project.ProjectItem>
  group?: Partial<Api.Groups.GroupsInfo>
  protocol?: Partial<ProtocolModels.ProjectProtocolInfo>
  record?: Partial<ProtocolModels.RecordInfo>
  node?: any
  lab: Partial<Api.Lab.LabItem>
  description?: string
  activity: string
  loading?: boolean
  time: string
}

const props = withDefaults(defineProps<IProps>(), { loading: false })

const userRoute = computed<RouteLocationRaw>(() => {
  const { username } = props.user
  if (username) {
    return { name: "user-profile", params: { username } }
  }

  return { name: "root" }
})

const activityRoute = computed<Record<"project" | "lab" | "protocol" | "record", RouteLocationRaw | null>>(
  () => {
    const { project, lab, protocol, record } = props

    return {
      project:
        lab?.uid && project?.id
          ? { name: "project-protocols", params: { labUid: lab.uid, projectUid: project.uid } }
          : null,
      lab: lab?.uid ? { name: "lab-projects", params: { labUid: lab.uid } } : null,
      protocol: protocol?.id && lab?.uid && project?.uid ? { name: "protocol-info", params: { labUid: lab.uid, projectUid: project.uid, protocolUid: protocol.uid } } : null,
      record: record?.record_id && lab?.uid && project?.uid ? { name: "protocol-record-report", params: { labUid: lab.uid, projectUid: project.uid, protocolUid: record.metadata?.airalogy_protocol_id, recordId: record.record_id, recordVersion: record.record_version } } : null,
    } as any
  },
)
</script>

<style scoped lang="sass"></style>
