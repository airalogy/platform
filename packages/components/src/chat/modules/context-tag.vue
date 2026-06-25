<template>
  <n-tooltip>
    <template #trigger>
      <n-tag :closable="props.closeable" class="relative max-w-full" @close="handleClose">
        <n-icon v-if="!props.closeable" class="absolute z-99 rotate-45 opacity-80 -right-1 -top-1" :size="14">
          <icon-tabler-pinned />
        </n-icon>
        <router-link
          v-if="navigateTo" :to="navigateTo" class="flex items-center gap-1 px-1 hover:router-link"
          target="_blank" rel="noopener noreferrer"
        >
          <n-icon :size="14">
            <icon-shared-record-outline v-if="props.context.type === 'record'" />
            <icon-shared-protocol-outline v-else-if="props.context.type === 'protocol'" />
          </n-icon>
          <n-ellipsis v-if="props.context.type === 'protocol'">
            {{ props.context.item.name }}
            <n-tag v-if="props.context.item.latest_version" type="info" size="tiny" class="cursor-pointer">
              v{{ props.context.item.latest_version }}
            </n-tag>
          </n-ellipsis>
          <span v-else class="max-w-[4em] overflow-hidden text-ellipsis" style="direction: rtl">#{{ props.context.id }}</span>
          <n-icon :size="14">
            <icon-ion-open-outline />
          </n-icon>
        </router-link>
        <span v-else> {{ props.context.id }} </span>
      </n-tag>
    </template>
    <div>
      <div class="capitalize">
        {{ props.context.type }}
      </div>
      <div class="tooltip-row">
        <n-icon size="14">
          <icon-shared-protocol-outline v-if="props.context.type === 'protocol' || props.context.type === 'record'" />
          <icon-ion-chevron-forward-circle-outline v-else />
        </n-icon>
        <div v-if="props.context.lab && props.context.project && props.context.protocol" class="tooltip-breadcrumb">
          <router-link
            :to="{ name: 'lab-projects', params: { labUid: props.context.lab.uid } }" class="hover:router-link"
            target="_blank" rel="noopener noreferrer"
          >
            {{ props.context.lab.name }}
          </router-link>
          <n-icon size="12">
            <icon-ion-chevron-forward />
          </n-icon>
          <router-link
            :to="{ name: 'project-protocols', params: { labUid: props.context.lab.uid, projectUid: props.context.project.uid } }"
            class="hover:router-link" target="_blank" rel="noopener noreferrer"
          >
            {{ props.context.project.name }}
          </router-link>
          <n-icon size="12">
            <icon-ion-chevron-forward />
          </n-icon>
          <router-link
            :to="{ name: 'protocol-info', params: { labUid: props.context.lab.uid, projectUid: props.context.project.uid, protocolUid: props.context.protocol.uid } }"
            class="hover:router-link" target="_blank" rel="noopener noreferrer"
          >
            {{ props.context.protocol.name }}
            <n-tag v-if="props.context.type === 'protocol'" size="tiny" class="ml-1">
              v{{ props.context.item.latest_version }}
            </n-tag>
            <n-tag v-else-if="props.context.type === 'record'" size="tiny" class="ml-1">
              v{{ props.context.item.metadata.protocol_version }}
            </n-tag>
          </router-link>
        </div>
      </div>

      <div v-if="props.context.type === 'record'" class="tooltip-row">
        <n-icon size="14">
          <icon-shared-record-outline />
        </n-icon>
        <span class="tooltip-value">{{ formatDate(props.context.item.metadata.record_current_version_submission_time, "date-time") }}</span>
      </div>

      <div v-if="props.context.type === 'record'" class="tooltip-row">
        <n-icon size="14">
          <icon-ion-person-outline />
        </n-icon>
        <router-link
          :to="`/users/${props.context.item.metadata.record_current_version_submission_user_id}`" class="tooltip-value hover:router-link" target="_blank"
          rel="noopener noreferrer"
        >
          {{ props.context.item.metadata.record_current_version_submission_user_id }}
        </router-link>
      </div>
    </div>
  </n-tooltip>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from "vue-router"
import { formatDate } from "@airalogy/shared/utils"

interface IProps {
  context: Chat.ChatContext
  closeable?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  closeable: true,
})

const emit = defineEmits<IEmit>()

interface IEmit {
  (e: "close", value: string): void
}

function handleClose() {
  emit("close", String(props.context.id))
}

const navigateTo = computed<RouteLocationRaw | null>(() => {
  const { lab, project, protocol, id } = props.context

  if (!lab || !project || !protocol) {
    return null
  }

  if (props.context.type === "record") {
    return {
      name: "protocol-record-report",
      params: {
        labUid: lab.uid,
        projectUid: project.uid,
        protocolUid: protocol.uid,
        protocolVersion: props.context.item.metadata?.protocol_version,
        recordId: id,
        recordVersion: props.context.item.record_version,
      },
    }
  }
  if (props.context.type === "protocol") {
    return { name: "protocol-detail", params: { labUid: lab.uid, projectUid: project.uid, protocolUid: protocol.uid } }
  }

  return null
})
</script>

<style scoped lang="sass">
.tooltip
  @apply min-w-[240px] p-2

.tooltip-breadcrumb
  @apply flex items-center gap-2 text-sm

.tooltip-row
  @apply flex items-center gap-2.5 text-sm py-1

.tooltip-value
  @apply font-medium

.tooltip-divider
  @apply h-[1px] bg-gray-800 mx-2

:deep(.n-tag__content)
  max-width: 100%
</style>
