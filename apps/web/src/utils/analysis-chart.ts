import type { AnalysisResult } from "@/service/api/analysis"

export interface AnalysisChartPoint {
  groupIndex: number
  value: number | null
  count: number
  x: number
  y: number | null
  barY: number
  barHeight: number
}

export interface AnalysisChartLayout {
  field: string
  title: string
  unit: string
  width: number
  height: number
  left: number
  right: number
  top: number
  bottom: number
  zeroY: number
  barWidth: number
  hasValues: boolean
  points: AnalysisChartPoint[]
  segments: AnalysisChartPoint[][]
  ticks: Array<{ value: number, y: number }>
}

/** Plot only server-calculated means, on independent field/unit axes. */
export function createAnalysisChartLayouts(result: AnalysisResult): AnalysisChartLayout[] {
  if (result.chart.type === "none")
    return []
  if (!["bar", "line"].includes(result.chart.type) || result.chart.statistic !== "mean" || result.chart.series.length !== result.fields.length)
    throw new Error("unsupported_analysis_chart")
  const seenFields = new Set<string>()
  return result.chart.series.map((series) => {
    const field = result.fields.find(item => item.key === series.field)
    if (!field || seenFields.has(series.field) || (field.unit || "") !== (series.unit || "") || series.points.length !== result.groups.length)
      throw new Error("inconsistent_analysis_chart")
    seenFields.add(series.field)
    const byGroup = new Map(series.points.map(point => [point.group_index, point]))
    if (byGroup.size !== result.groups.length)
      throw new Error("inconsistent_analysis_chart")
    const sourcePoints = result.groups.map((group, groupIndex) => {
      const point = byGroup.get(groupIndex)
      const statistics = group.fields[series.field]
      if (!point || !statistics || point.value !== statistics.mean || point.count !== statistics.count
        || !Number.isSafeInteger(point.count) || point.count < 0
        || (point.value !== null && (!Number.isFinite(point.value) || point.count === 0))) {
        throw new Error("inconsistent_analysis_chart")
      }
      return point
    })
    const values = sourcePoints.flatMap(point => point.value === null ? [] : [point.value])
    // Normalization avoids overflow in max-min for valid values near ±1e308.
    const magnitude = Math.max(...values.map(value => Math.abs(value))) || 1
    const normalized = values.map(value => value / magnitude)
    const min = Math.min(0, ...normalized)
    const max = Math.max(0, ...normalized) || (min === 0 ? 1 : 0)
    const width = Math.max(440, 112 + result.groups.length * 72)
    const height = 290
    const left = 88
    const right = width - 24
    const top = 24
    const bottom = 214
    const y = (value: number) => top + ((max - value) / (max - min)) * (bottom - top)
    const zeroY = y(0)
    const slot = (right - left) / Math.max(1, result.groups.length)
    const points = sourcePoints.map((point, groupIndex): AnalysisChartPoint => {
      const pointY = point.value === null ? null : y(point.value / magnitude)
      return {
        groupIndex,
        value: point.value,
        count: point.count,
        x: left + slot * (groupIndex + 0.5),
        y: pointY,
        barY: pointY === null ? zeroY : Math.min(zeroY, pointY),
        barHeight: pointY === null ? 0 : Math.abs(zeroY - pointY),
      }
    })
    const segments: AnalysisChartPoint[][] = []
    let segment: AnalysisChartPoint[] = []
    for (const point of points) {
      // Missing means break a line. A missing grouping coordinate is an isolated
      // category: its real mean remains visible, but it cannot connect a trend.
      const missingGroup = result.groups[point.groupIndex].key.some(item => item.value === null)
      if (point.y === null || missingGroup) {
        if (segment.length)
          segments.push(segment)
        segment = []
      }
      else {
        segment.push(point)
      }
    }
    if (segment.length)
      segments.push(segment)
    return {
      field: field.key,
      title: field.title || field.key,
      unit: field.unit || "",
      width,
      height,
      left,
      right,
      top,
      bottom,
      zeroY,
      barWidth: Math.min(36, slot * 0.55),
      hasValues: values.length > 0,
      points,
      segments: segments.filter(item => item.length > 1),
      ticks: Array.from({ length: 5 }, (_, index) => {
        const normalizedValue = min + (max - min) * index / 4
        return { value: normalizedValue * magnitude, y: y(normalizedValue) }
      }),
    }
  })
}
