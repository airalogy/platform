<template>
  <section v-if="result.chart.type !== 'none'" class="analysis-charts mb-5" data-testid="analysis-result-charts" :aria-label="t('page.analysis.charts.title')">
    <h3 class="aira-type-label mb-2">
      {{ t("page.analysis.charts.title") }}
    </h3>
    <p class="aira-type-meta mb-3">
      {{ t("page.analysis.charts.explanation") }}
    </p>
    <p v-if="result.chart.type === 'line'" class="aira-type-meta mb-3">
      {{ t("page.analysis.charts.lineHint") }}
    </p>
    <n-alert v-if="layout.error" type="warning">
      {{ t("page.analysis.charts.unavailable") }}
    </n-alert>
    <figure v-for="(chart, index) in layout.charts" :key="chart.field" class="analysis-chart" :data-field="chart.field" :data-chart-type="result.chart.type">
      <figcaption :id="`${id}-caption-${index}`" class="analysis-chart-caption">
        <strong class="aira-type-label">{{ chart.title }}</strong>
        <span class="aira-type-meta">{{ t("page.analysis.statistics.mean") }} · {{ chart.unit ? t("page.analysis.charts.unit", { unit: chart.unit }) : t("page.analysis.charts.noUnit") }}</span>
      </figcaption>
      <p v-if="!chart.hasValues" class="aira-type-body px-3">
        {{ t("page.analysis.charts.noValues") }}
      </p>
      <div v-else class="analysis-chart-scroll" tabindex="0" :aria-labelledby="`${id}-caption-${index}`" :aria-describedby="`${id}-description-${index}`">
        <svg :viewBox="`0 0 ${chart.width} ${chart.height}`" :style="{ minWidth: `${chart.width}px` }" role="img" :aria-labelledby="`${id}-caption-${index} ${id}-description-${index}`">
          <desc :id="`${id}-description-${index}`">{{ t("page.analysis.charts.accessibleSummary", { field: chart.title, count: chart.points.length }) }}</desc>
          <g v-for="(tick, tickIndex) in chart.ticks" :key="tickIndex" class="analysis-chart-axis" aria-hidden="true">
            <line :x1="chart.left" :x2="chart.right" :y1="tick.y" :y2="tick.y" class="analysis-chart-grid" />
            <text :x="chart.left - 10" :y="tick.y + 4" text-anchor="end">{{ tickLabel(tick.value) }}</text>
          </g>
          <line :x1="chart.left" :x2="chart.right" :y1="chart.zeroY" :y2="chart.zeroY" class="analysis-chart-baseline" aria-hidden="true" />
          <g v-if="result.chart.type === 'line'" class="analysis-chart-line" aria-hidden="true">
            <polyline v-for="(segment, segmentIndex) in chart.segments" :key="segmentIndex" :points="segment.map(point => `${point.x},${point.y}`).join(' ')" />
          </g>
          <g v-for="point in chart.points" :key="point.groupIndex" :data-group-index="point.groupIndex" :data-count="point.count" :data-mean="point.value ?? 'missing'">
            <title>{{ pointDescription(point) }}</title>
            <template v-if="point.y !== null">
              <rect v-if="result.chart.type === 'bar' && point.barHeight > 0" :x="point.x - chart.barWidth / 2" :y="point.barY" :width="chart.barWidth" :height="point.barHeight" class="analysis-chart-bar" />
              <circle v-else :cx="point.x" :cy="point.y" r="4" class="analysis-chart-point" />
            </template>
            <text v-else :x="point.x" :y="chart.bottom - 6" text-anchor="middle" class="analysis-chart-missing">—</text>
            <text :x="point.x" :y="chart.bottom + 22" text-anchor="middle" class="analysis-chart-axis">{{ t("page.analysis.charts.groupNumber", { number: point.groupIndex + 1 }) }}</text>
            <text :x="point.x" :y="chart.bottom + 42" text-anchor="middle" class="analysis-chart-axis">n = {{ point.count }}</text>
          </g>
        </svg>
      </div>
    </figure>
    <details v-if="layout.charts.length" class="analysis-chart-key">
      <summary class="aira-type-meta">
        {{ t("page.analysis.charts.groupKey") }}
      </summary>
      <ol class="aira-type-meta">
        <li v-for="(group, index) in result.groups" :key="index">
          {{ groupLabel(group) }}
        </li>
      </ol>
    </details>
  </section>
</template>

<script setup lang="ts">
import type { AnalysisGroup, AnalysisResult } from "@/service/api/analysis"
import type { AnalysisChartPoint } from "@/utils/analysis-chart"
import { createAnalysisChartLayouts } from "@/utils/analysis-chart"
import { useId } from "vue"
import { useI18n } from "vue-i18n"

const props = defineProps<{ result: AnalysisResult }>()
const { t, locale } = useI18n()
const id = useId()
const layout = computed(() => {
  try {
    return { charts: createAnalysisChartLayouts(props.result), error: false }
  }
  catch {
    return { charts: [], error: true }
  }
})
function tickLabel(value: number) {
  return value.toLocaleString(locale.value, { maximumSignificantDigits: 3, notation: Math.abs(value) >= 1e5 || (value !== 0 && Math.abs(value) < 0.001) ? "scientific" : "standard" })
}
function groupLabel(group: AnalysisGroup) {
  return group.key.length ? group.key.map(item => `${item.field}: ${item.value === null ? t("page.analysis.missingGroup") : String(item.value)}`).join(" · ") : t("page.analysis.allRecords")
}
function pointDescription(point: AnalysisChartPoint) {
  return `${groupLabel(props.result.groups[point.groupIndex])} · ${t("page.analysis.statistics.mean")}: ${point.value === null ? t("page.analysis.charts.missingMean") : point.value.toLocaleString(locale.value, { maximumSignificantDigits: 8 })} · n = ${point.count}`
}
</script>

<style scoped>
.analysis-charts { min-width: 0; }
.analysis-chart { min-width: 0; margin: .75rem 0; border: 1px solid #e5e7eb; border-radius: .75rem; }
.analysis-chart-caption { display: flex; flex-wrap: wrap; justify-content: space-between; gap: .4rem 1rem; padding: .75rem; overflow-wrap: anywhere; }
.analysis-chart-scroll { max-width: 100%; overflow-x: auto; border-radius: 0 0 .75rem .75rem; }
.analysis-chart-scroll:focus-visible, .analysis-chart-key summary:focus-visible { outline: 2px solid #0084e2; outline-offset: 2px; }
.analysis-chart-scroll svg { display: block; width: 100%; height: auto; max-height: 21rem; font-family: inherit; }
.analysis-chart-axis { font-size: 12px; fill: #596174; }
.analysis-chart-grid { stroke: #e5e7eb; stroke-width: 1; }
.analysis-chart-baseline { stroke: #8791a3; stroke-width: 1; }
.analysis-chart-bar, .analysis-chart-point { fill: #0079c9; }
.analysis-chart-line polyline { fill: none; stroke: #0079c9; stroke-width: 2; stroke-linejoin: round; }
.analysis-chart-missing { font-size: 16px; fill: #596174; }
.analysis-chart-key summary { cursor: pointer; padding: .25rem 0; }
.analysis-chart-key ol { max-height: 14rem; overflow: auto; padding-left: 2rem; overflow-wrap: anywhere; }
.analysis-chart-key li { padding: .25rem .25rem .25rem 0; }
@media (prefers-reduced-motion: reduce) { .analysis-chart-scroll { scroll-behavior: auto; } }
</style>
