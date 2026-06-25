<template>
  <span>
    <template v-for="(node, index) in processedNodes" :key="index">
      <component :is="node" />
    </template>
  </span>
</template>

<script lang="ts" setup>
interface Props {
  text: string
  tag?: "span" | "div"
}

const props = withDefaults(
  defineProps<Props>(),
  {
    tag: "span",
  },
)

function insertWbr(str: string = "") {
  const { tag } = props

  const splitAry = str.split("_")
  const boundary = splitAry.length - 1

  return splitAry
    .map((segment, index) => {
      const segmentNode = h(tag, null, segment)
      if (index < boundary) {
        // Add <wbr> only if it's not the last element
        return [segmentNode, h("wbr"), h("span", "_")]
      }

      return segmentNode
    })
    .flat()
}

const processedNodes = computed(() => {
  return insertWbr(props.text)
})
</script>
