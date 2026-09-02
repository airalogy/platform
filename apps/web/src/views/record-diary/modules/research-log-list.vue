<template>
  <n-timeline size="large" class="research-log-timeline">
    <n-timeline-item
      v-for="item in items"
      :key="item.id"
      :type="timelineType(item)"
      :time="formatDate(item.occurred_at, 'date-time')"
    >
      <article class="research-log-card">
        <header class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="mb-2 flex flex-wrap items-center gap-2">
              <n-tag size="small" :type="tagType(item)">
                {{ eventLabel(item) }}
              </n-tag>
              <span v-if="item.entry_type === 'manual'" class="aira-type-meta">
                {{ scopeLabel(item) }} · r{{ item.revision }}
              </span>
              <span v-else class="aira-type-meta">
                {{ contextLabel(item) }}
              </span>
            </div>
            <h3 class="aira-type-card-title m-0 break-words">
              {{ item.title }}
            </h3>
          </div>
          <div v-if="item.author" class="aira-type-meta flex shrink-0 items-center gap-2">
            <router-link :to="{ name: 'user-profile', params: { username: item.author.username } }" class="record-diary-link">
              {{ item.author.name || item.author.username }}
            </router-link>
            <n-time :time="new Date(item.occurred_at)" type="relative" />
          </div>
        </header>

        <template v-if="item.entry_type === 'manual'">
          <p v-if="item.body" class="aira-type-body aira-text-secondary mb-0 mt-3 whitespace-pre-wrap">
            {{ item.body }}
          </p>
          <div v-if="item.goal" class="research-log-field mt-4">
            <span>{{ $t("page.recordDiary.logGoal") }}</span>
            <p>{{ item.goal }}</p>
          </div>
          <div class="research-log-field-grid mt-4">
            <research-log-field :label="$t('page.recordDiary.completedItems')" :items="item.completed_items" />
            <research-log-field :label="$t('page.recordDiary.evidence')" :items="item.evidence" />
            <research-log-field :label="$t('page.recordDiary.risks')" :items="item.risks" />
            <research-log-field :label="$t('page.recordDiary.nextSteps')" :items="item.next_steps" />
          </div>
          <div v-if="item.asset_links.length" class="mt-4 flex flex-wrap gap-2">
            <n-tag v-for="asset in item.asset_links" :key="`${asset.asset_type}:${asset.asset_id}`" size="small" round>
              {{ asset.label || asset.asset_type }}
            </n-tag>
          </div>
          <footer v-if="item.can_edit" class="mt-4 flex justify-end">
            <n-button quaternary size="small" @click="emit('edit', item)">
              <template #icon><n-icon><icon-tabler-edit /></n-icon></template>
              {{ $t("common.edit") }}
            </n-button>
          </footer>
        </template>
        <template v-else>
          <p class="aira-type-body aira-text-secondary mb-0 mt-3">
            {{ item.summary }}
          </p>
          <footer v-if="assetRoute(item)" class="mt-4 flex justify-end">
            <router-link :to="assetRoute(item)!">
              <n-button type="primary" quaternary size="small">
                <template #icon><n-icon><icon-tabler-external-link /></n-icon></template>
                {{ $t("page.recordDiary.viewAsset") }}
              </n-button>
            </router-link>
          </footer>
        </template>
      </article>
    </n-timeline-item>
  </n-timeline>
</template>

<script setup lang="ts">
import type {
  ResearchLogManualEntry,
  ResearchLogSystemEvent,
  ResearchLogTimelineItem,
} from "@/service/api/research-log"
import type { RouteLocationRaw } from "vue-router"
import { $t } from "@airalogy/shared/locales"
import { formatDate } from "@airalogy/shared/utils"
import ResearchLogField from "./research-log-field.vue"

const props = defineProps<{ items: ResearchLogTimelineItem[] }>()
const emit = defineEmits<{ edit: [entry: ResearchLogManualEntry] }>()

function eventLabel(item: ResearchLogTimelineItem) {
  if (item.entry_type === "manual") {
    const suffix = item.kind.charAt(0).toUpperCase() + item.kind.slice(1)
    return $t(`page.recordDiary.kind${suffix}` as I18n.I18nKey)
  }
  const eventKey = item.event_type.replaceAll(".", "_")
  const key = (item.event_type.includes(".")
    ? `page.recordDiary.event.${eventKey}`
    : `page.research.event.${eventKey}`) as I18n.I18nKey
  return $t(key)
}

function timelineType(item: ResearchLogTimelineItem): "default" | "success" | "info" | "warning" | "error" {
  if (item.entry_type === "system")
    return item.event_type.includes("failed") || item.event_type.includes("rejected") ? "error" : "info"
  if (item.kind === "blocker")
    return "warning"
  if (item.kind === "milestone")
    return "success"
  return "default"
}

function tagType(item: ResearchLogTimelineItem): "default" | "success" | "info" | "warning" | "error" {
  return timelineType(item)
}

function scopeLabel(item: ResearchLogManualEntry) {
  return $t(`page.recordDiary.scope.${item.scope_type}` as I18n.I18nKey)
}

function contextLabel(item: ResearchLogSystemEvent) {
  return [item.lab?.name, item.project?.name].filter(Boolean).join(" / ")
}

function assetRoute(item: ResearchLogSystemEvent): RouteLocationRaw | null {
  const asset = item.asset
  if (!asset)
    return null
  if (asset.type === "research_task")
    return { name: "research-task-detail", params: { taskId: asset.id } }
  if (asset.type === "knowledge")
    return { name: "knowledge-home", query: { item: asset.id } }
  if (!item.lab || !item.project)
    return null
  if (asset.type === "protocol") {
    return {
      name: "protocol-info",
      params: { labUid: item.lab.uid, projectUid: item.project.uid, protocolUid: asset.uid },
    }
  }
  if (asset.type === "record") {
    return {
      name: "protocol-record-report",
      params: {
        labUid: item.lab.uid,
        projectUid: item.project.uid,
        protocolUid: asset.protocol_uid,
        protocolVersion: asset.protocol_version,
        recordId: asset.id,
        recordVersion: asset.version,
      },
    }
  }
  return null
}
</script>

<style scoped lang="sass">
.research-log-timeline
  min-width: 0
  padding-left: 8px

  :deep(.n-timeline-item-content)
    min-width: 0

.research-log-card
  min-width: 0
  border: 1px solid #E5E7EB
  border-radius: 10px
  background: #FFFFFF
  padding: 18px
  transition: border-color 0.2s ease, box-shadow 0.2s ease

  &:hover
    border-color: #BED7FF
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06)

.research-log-field
  span
    color: #64748B
    font-size: 12px
    font-weight: 600
    letter-spacing: 0.04em
    text-transform: uppercase

  p
    margin: 6px 0 0
    white-space: pre-wrap

.research-log-field-grid
  display: grid
  grid-template-columns: repeat(2, minmax(0, 1fr))
  gap: 14px

@media (max-width: 640px)
  .research-log-card
    padding: 14px

  .research-log-field-grid
    grid-template-columns: minmax(0, 1fr)
</style>
