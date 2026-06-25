import { onMounted, ref } from "vue"

export function useTruncation(elementRef: any) {
  const truncated = ref<boolean | null>(null)

  onMounted(() => {
    if (truncated.value === null && elementRef.value?.clientHeight > 200) {
      truncated.value = true
    }
  })

  function setTruncated(value: boolean) {
    truncated.value = value
  }

  return {
    truncated,
    setTruncated,
  }
}
