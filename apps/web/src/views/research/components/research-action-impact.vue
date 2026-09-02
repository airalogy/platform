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
  const known = ["protocol_run", "tool_job", "wait_event", "human_work_item"]
  return known.includes(props.action.kind)
    ? $t(`page.research.actionKind.${props.action.kind}` as I18n.I18nKey)
    : props.action.kind.replaceAll("_", " ")
})

const kindTagType = computed<TagProps["type"]>(() => {
  if (props.action.kind === "tool_job")
    return "info"
  if (props.action.kind === "wait_event")
    return "warning"
  return "default"
})

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
