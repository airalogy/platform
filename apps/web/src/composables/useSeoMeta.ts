import type { SeoMetaInput } from "@/utils/seo"
import type { MaybeRefOrGetter } from "vue"
import { applySeoMeta } from "@/utils/seo"
import { toValue, watchEffect } from "vue"

export function useSeoMeta(source: MaybeRefOrGetter<SeoMetaInput | null | undefined>) {
  watchEffect(() => {
    const value = toValue(source)
    if (!value) {
      return
    }

    applySeoMeta(value)
  })
}
