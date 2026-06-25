<template>
  <defs>
    <marker
      :id="`arrow-${id}`" class="vue-flow__arrowhead" viewBox="-10 -10 20 20" refX="0" refY="0" markerWidth="12.5"
      markerHeight="12.5" marker-protocols="strokeWidth" orient="auto-start-reverse"
    >
      <polyline
        stroke-linecap="round" stroke-linejoin="round" fill="none" points="-5,-4 0,0 -5,4"
        :style="{ 'stroke': props.style?.stroke || 'rgb(177, 177, 183)', 'stroke-width': '1' }"
      />
    </marker>
  </defs>
  <template v-if="parallelPaths.length > 0">
    <path
      v-for="(item, idx) in parallelPaths" :id="(id || '') + idx" :key="idx" :d="item.path" :style="props.style"
      class="vue-flow__edge-path" :marker-end="item.markerEnd" :marker-start="item.markerStart"
    />

    <!-- <template>
    <path
      :id="id"
      ref="pathEl"
      :d="pathVal.path"
      :style="attrs.style"
      class="vue-flow__edge-path"
      :class="attrs.class"
      :marker-end="markerEnd"
      :marker-start="markerStart"
    />
    <path
      v-if="interactionWidth"
      ref="interactionEl"
      fill="none"
      :d="pathVal.path"
      :stroke-width="interactionWidth"
      :stroke-opacity="0"
      class="vue-flow__edge-interaction"
    />
  </template> -->
    <edge-text
      v-if="label && pathVal.centerX && pathVal.centerY" ref="labelEl" :x="pathVal.centerX"
      :y="pathVal.centerY" :label="label" :label-show-bg="labelShowBg" :label-bg-style="labelBgStyle"
      :label-bg-padding="labelBgPadding" :label-bg-border-radius="labelBgBorderRadius" :label-style="labelStyle"
    />
  </template>
  <template v-else>
    <path
      :id="id" :d="pathVal.path" :style="props.style" class="vue-flow__edge-path" :class="$attrs.class"
      :marker-end="markerEnd" :marker-start="markerStart"
    />

    <path
      v-if="interactionWidth" ref="interactionEl" fill="none" :d="pathVal.path"
      :stroke-width="props.interactionWidth" :stroke-opacity="0" class="vue-flow__edge-interaction"
    />

    <edge-text
      v-if="label && pathVal.labelX && pathVal.labelY" ref="labelEl" :x="pathVal.labelX" :y="pathVal.labelY"
      :label="label" :label-show-bg="labelShowBg" :label-bg-style="labelBgStyle" :label-bg-padding="labelBgPadding"
      :label-bg-border-radius="labelBgBorderRadius" :label-style="labelStyle"
    />
  </template>
</template>

<script lang="ts" setup>
import type { BaseEdgeProps, EdgePositions } from "@vue-flow/core"

import { EdgeText, getSmoothStepPath, getStraightPath, Position } from "@vue-flow/core"

defineOptions({
  name: "BidirectionalEdge",
  inheritAttrs: false,
})

const props = withDefaults(
  defineProps<
    EdgePositions &
    Omit<BaseEdgeProps, "labelX" | "labelY" | "path"> & {
      parallel?: boolean
      mode?: "edit" | "preview" | "report"
      pathProps?: any
      sourceNode: Node & { rank: number, data: { raw: { width: number, height: number, x: number } } }
      targetNode: Node & { rank: number, data: { raw: { width: number, height: number, y: number } } }
    }
  >(),
  { interactionWidth: 20, labelShowBg: true, mode: undefined, pathProps: () => ({}) },
)

function createParallelPaths(
  sourceX: number,
  sourceY: number,
  targetX: number,
  targetY: number,
  offset = 5,
  lengthRatio = 0.3,
) {
  // 计算原始路径的长度
  const dx = targetX - sourceX
  const dy = targetY - sourceY
  const length = Math.sqrt(dx * dx + dy * dy)

  // 计算缩短后的路径长度
  const shortenedLength = length * lengthRatio

  // 计算原始路径的角度
  const angle = Math.atan2(dy, dx)

  const halfShortenedLength = shortenedLength / 2
  const startX = sourceX + halfShortenedLength * Math.cos(angle)
  const startY = sourceY + halfShortenedLength * Math.sin(angle)
  const endX = targetX - halfShortenedLength * Math.cos(angle)
  const endY = targetY - halfShortenedLength * Math.sin(angle)

  // 生成两个平行路径

  if (props.parallel) {
    // 计算缩短后的路径的起点和终点
    const offsetX = offset * Math.cos(angle + Math.PI / 2) // 垂直于直线的偏移量
    const offsetY = offset * Math.sin(angle + Math.PI / 2) // 垂直于直线的偏移量

    return [
      {
        path: `M ${startX + offsetX},${startY + offsetY}L ${endX + offsetX},${endY + offsetY}`,
        markerStart: `url(#arrow-${props.id})`,
      },
      {
        path: `M ${startX - offsetX},${startY - offsetY}L ${endX - offsetX},${endY - offsetY}`,
        markerEnd: `url(#arrow-${props.id})`,
      },
    ]
  }

  return [
    {
      path: `M ${startX},${startY}L ${endX},${endY}`,
      markerEnd: `url(#arrow-${props.id})`,
    },
  ]
}

const isStraight = computed(() => {
  const { sourceNode, targetNode } = props

  return Math.abs(sourceNode.rank - targetNode.rank) === 2
})

const pathVal = computed(() => {
  if (isStraight.value) {
    const [path, centerX, centerY, offsetX, offsetY] = getStraightPath(props)

    return { path, centerX, centerY, offsetX, offsetY }
  }

  const [path, labelX, labelY, offsetX, offsetY] = getSmoothStepPath({
    ...props,
    sourceX: props.sourceNode.data.raw ? props.sourceX - props.sourceNode.data.raw.width / 2 : props.sourceX,
    sourceY: props.sourceNode.data.raw ? props.sourceY + props.sourceNode.data.raw.height / 2 : props.sourceY,
    targetX: props.targetNode.data.raw ? props.targetX + props.targetNode.data.raw.width / 2 : props.targetX,
    targetY: props.targetNode.data.raw ? props.targetY + props.targetNode.data.raw.height / 2 : props.targetY,
    sourcePosition: Position.Bottom,
    targetPosition: Position.Bottom,
  })

  return { path, labelX, labelY, offsetX, offsetY }
})

const parallelPaths = computed(() => {
  if (isStraight.value) {
    return createParallelPaths(props.sourceX, props.sourceY, props.targetX, props.targetY)
  }

  return []
})

const interactionEl = ref<SVGPathElement | null>(null)

const labelEl = ref<SVGGElement | null>(null)

defineExpose({
  interactionEl,
  labelEl,
})
</script>
