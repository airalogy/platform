<template>
  <div class="research-action-impact">
    <div class="flex flex-wrap items-center gap-2">
      <n-tag size="small" round :type="kindTagType">
        {{ kindLabel }}
      </n-tag>
      <span v-if="action.tool_job" class="aira-type-meta">
        {{ action.tool_job.tool_key }} · v{{ action.tool_job.tool_version }}
      </span>
      <span v-else-if="action.wait_event" class="aira-type-meta">
        {{ action.wait_event.expected_event_type }}
      </span>
      <span v-else-if="action.resource_reservation" class="aira-type-meta">
        {{ resolvedResource.resource_name || action.resource_reservation.resource_id }}
        <template v-if="resolvedResource.resource_code">
          · {{ resolvedResource.resource_code }}
        </template>
      </span>
      <span v-else-if="action.protocol" class="aira-type-meta">
        {{ action.protocol.name }} · v{{ action.protocol.version }}
      </span>
    </div>

    <div v-if="action.tool_job" class="mt-2">
      <div class="aira-type-meta">{{ $t("page.research.toolArguments") }}</div>
      <pre>{{ formatted(action.tool_job.arguments) }}</pre>
    </div>
    <div v-else-if="action.wait_event" class="mt-2">
      <div class="aira-type-meta">{{ $t("page.research.expectedPayload") }}</div>
      <pre>{{ formatted(action.wait_event.payload_schema) }}</pre>
    </div>
    <div v-else-if="action.resource_reservation" class="mt-2">
      <div class="aira-type-meta">{{ $t("page.research.reservationImpact") }}</div>
      <div class="aira-type-body mt-1">
        <template v-if="action.resource_reservation.kind === 'inventory'">
          {{ action.resource_reservation.quantity }} {{ action.resource_reservation.unit }}
        </template>
        <template v-else>
          {{ formatDate(action.resource_reservation.starts_at) }} – {{ formatDate(action.resource_reservation.ends_at) }}
        </template>
      </div>
      <p class="aira-type-meta aira-text-muted mb-0 mt-1">
        {{ action.resource_reservation.purpose }}
      </p>
    </div>
    <div v-else-if="action.protocol_run && Object.keys(action.protocol_run.initial_values || {}).length" class="mt-2">
      <div class="aira-type-meta">{{ $t("page.research.initialValues") }}</div>
      <pre>{{ formatted(action.protocol_run.initial_values) }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ResearchAction } from "@/service/api/research-tasks"
import type { TagProps } from "naive-ui"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ action: ResearchAction }>()

const kindLabel = computed(() => {
  const known = ["protocol_run", "tool_job", "resource_reservation", "wait_event", "human_work_item"]
  return known.includes(props.action.kind)
    ? $t(`page.research.actionKind.${props.action.kind}` as I18n.I18nKey)
    : props.action.kind.replaceAll("_", " ")
})

const kindTagType = computed<TagProps["type"]>(() => {
  if (props.action.kind === "tool_job")
    return "info"
  if (props.action.kind === "wait_event")
    return "warning"
  if (props.action.kind === "resource_reservation")
    return "warning"
  return "default"
})

const resolvedResource = computed(() => (
  (props.action.input_data?.resolved || {}) as Record<string, string>
))

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : "—"
}

function formatted(value: Record<string, unknown>) {
  return JSON.stringify(value || {}, null, 2)
}
</script>

<style scoped>
.research-action-impact {
  margin-top: 0.75rem;
  border: 1px solid rgb(226 232 240);
  border-radius: 0.75rem;
  background: rgb(248 250 252 / 80%);
  padding: 0.75rem;
}

pre {
  max-height: 12rem;
  overflow: auto;
  margin: 0.35rem 0 0;
  border-radius: 0.5rem;
  background: rgb(255 255 255 / 85%);
  padding: 0.625rem;
  color: rgb(51 65 85);
  font-size: 0.75rem;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
