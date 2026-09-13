/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

const source = readFileSync(new URL("../src/utils/analysis-chart.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  reportDiagnostics: true,
})
assert.deepEqual(compiled.diagnostics, [])
const { createAnalysisChartLayouts } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`)

function result(values, type = "bar") {
  return {
    fields: [{ key: "mass", title: "Mass", unit: "mg" }],
    groups: values.map((mean, index) => ({ key: [{ field: "group", type: "string", value: `group-${index}` }], fields: { mass: { mean, count: mean === null ? 0 : index + 1 } } })),
    chart: { type, statistic: "mean", series: [{ field: "mass", title: "Mass", unit: "mg", points: values.map((value, group_index) => ({ group_index, value, count: value === null ? 0 : group_index + 1 })) }] },
  }
}

test("charts preserve actual server means, valid n and separate null from real zero", () => {
  const input = result([20, null, 0, -10])
  const original = structuredClone(input)
  const [chart] = createAnalysisChartLayouts(input)
  assert.deepEqual(chart.points.map(point => [point.value, point.count]), [[20, 1], [null, 0], [0, 3], [-10, 4]])
  assert.equal(chart.points[1].y, null)
  assert.equal(chart.points[2].y, chart.zeroY)
  assert.ok(chart.points[3].y > chart.zeroY)
  assert.equal(chart.points[3].barY, chart.zeroY)
  assert.deepEqual(input, original)
})

test("a line never connects across missing means", () => {
  const [chart] = createAnalysisChartLayouts(result([1, 2, null, 4, 5, null, 6], "line"))
  assert.deepEqual(chart.segments.map(segment => segment.map(point => point.groupIndex)), [[0, 1], [3, 4]])
})

test("a missing grouping coordinate keeps its real mean but breaks neighboring lines", () => {
  const input = result([1, 2, 3, 4, 5], "line")
  input.groups[2].key[0].value = null
  const [chart] = createAnalysisChartLayouts(input)
  assert.equal(chart.points[2].value, 3)
  assert.deepEqual(chart.segments.map(segment => segment.map(point => point.groupIndex)), [[0, 1], [3, 4]])
})

test("different units use independent scales instead of a shared Y axis", () => {
  const input = result([1, 2])
  const other = result([1000, 2000])
  input.fields.push({ key: "volume", title: "Volume", unit: "mL" })
  for (const [index, group] of input.groups.entries())
    group.fields.volume = other.groups[index].fields.mass
  input.chart.series.push({ ...other.chart.series[0], field: "volume", title: "Volume", unit: "mL" })
  const charts = createAnalysisChartLayouts(input)
  assert.deepEqual(charts.map(chart => [chart.field, chart.unit]), [["mass", "mg"], ["volume", "mL"]])
  assert.equal(charts[0].points[1].y, charts[1].points[1].y)
  assert.equal(charts[0].ticks.at(-1).value, 2)
  assert.equal(charts[1].ticks.at(-1).value, 2000)
})

test("positive, negative, zero and extreme finite scales have finite geometry", () => {
  for (const values of [[0, 0], [-2, -1], [1, 2], [-1e308, 1e308], [5e-324, 1e-323]]) {
    const [chart] = createAnalysisChartLayouts(result(values))
    for (const point of chart.points) {
      for (const coordinate of [point.x, point.y, point.barY, point.barHeight])
        assert.ok(Number.isFinite(coordinate))
      assert.ok(point.y >= chart.top && point.y <= chart.bottom)
    }
    for (const tick of chart.ticks)
      assert.ok(Number.isFinite(tick.value) && Number.isFinite(tick.y))
  }
})

test("empty or entirely missing data has no invented bars or means", () => {
  for (const values of [[], [null, null]]) {
    const [chart] = createAnalysisChartLayouts(result(values))
    assert.equal(chart.hasValues, false)
    assert.deepEqual(chart.segments, [])
    assert.ok(chart.points.every(point => point.y === null))
  }
})

test("series points are mapped to report group indexes without reordering groups", () => {
  const input = result([10, 2, 30])
  input.chart.series[0].points.reverse()
  assert.deepEqual(createAnalysisChartLayouts(input)[0].points.map(point => point.value), [10, 2, 30])
})

test("large group sets get scrollable width and distinct sample-count slots", () => {
  const [chart] = createAnalysisChartLayouts(result(Array.from({ length: 200 }, (_, index) => index)))
  assert.ok(chart.width > 10000)
  assert.ok(chart.points[1].x - chart.points[0].x >= 70)
})

test("inconsistent values, sample counts, units, group indexes or series fail closed", () => {
  const mutations = [
    input => input.chart.series[0].points[0].value = 99,
    input => input.chart.series[0].points[0].count = 0,
    input => input.chart.series[0].unit = "g",
    input => input.chart.series[0].points[0].group_index = 1,
    input => input.chart.series[0].points.pop(),
    input => input.chart.series.pop(),
    input => input.chart.statistic = "median",
  ]
  for (const mutate of mutations) {
    const input = result([1, 2])
    mutate(input)
    assert.throws(() => createAnalysisChartLayouts(input))
  }
})

test("table-only reports never generate a replacement chart", () => {
  const input = result([1, 2], "none")
  input.chart.series = []
  assert.deepEqual(createAnalysisChartLayouts(input), [])
})
