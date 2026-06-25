import type { PDFDocumentProxy } from "pdfjs-dist"
import type { MaybeRef } from "vue"
import { useLoading } from "@airalogy/composables"
import { ref, shallowRef, unref, watch } from "vue"
import { createLoadingTask } from "../utils/pdfRegister"

export function usePdfDocument(options: MaybeRef<{ loading?: boolean, error?: string }>) {
  const { loading, startLoading, endLoading } = useLoading(false)
  const error = ref<string>("")
  const pdfDocument = shallowRef<PDFDocumentProxy | null>(null)
  const totalPages = ref(0)

  watch(options, (value) => {
    const val = unref(value)
    if (!val) {
      return
    }

    loading.value = val.loading ?? false
    error.value = val.error ?? ""
  }, { immediate: true, deep: true })

  async function loadPdf(pdfUrl: string) {
    if (!pdfUrl)
      return

    startLoading()
    error.value = ""

    try {
      const loadingTask = createLoadingTask(pdfUrl)
      pdfDocument.value = await loadingTask.promise
      totalPages.value = pdfDocument.value.numPages
      endLoading()
      return pdfDocument.value
    }
    catch (err) {
      console.error("Error loading PDF:", err)
      error.value = err instanceof Error ? err.message : "Failed to load PDF document"
      endLoading()
      throw err
    }
  }

  function cleanup() {
    pdfDocument.value = null
    totalPages.value = 0
    error.value = ""
  }

  return {
    loading,
    error,
    pdfDocument,
    totalPages,
    loadPdf,
    cleanup,
  }
}
