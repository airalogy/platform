import type { Html2PdfOptions, Html2PdfWorker } from "html2pdf.js"
import html2pdf from "html2pdf.js"
import { ref } from "vue"

interface UseHtmlToPdfOptions extends Html2PdfOptions {
  filename?: string
  pagebreak?: {
    mode?: "css" | "legacy" | "avoid-all"
    before?: string | string[]
    after?: string | string[]
    avoid?: string | string[]
  }
}

const defaultOptions: UseHtmlToPdfOptions = {
  margin: 10,
  filename: "document.pdf",
  image: { type: "jpeg", quality: 0.98 },
  html2canvas: { scale: 2, useCORS: true },
  jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
}

export function useHtmlToPdf() {
  const isGenerating = ref(false)
  const worker = shallowRef<Html2PdfWorker | null>(null)

  async function exportToPdf(
    element: HTMLElement | string,
    options: Partial<UseHtmlToPdfOptions> = {},
    asBlob = false,
  ) {
    try {
      isGenerating.value = true
      const mergedOptions = { ...defaultOptions, ...options }
      if (!worker.value) {
        worker.value = html2pdf()
      }
      const workerInstance = worker.value

      workerInstance
        .set(mergedOptions)
        .from(element)

      // Save/download as usual
      if (asBlob) {
        return await workerInstance.outputPdf("blob")
      }

      return await workerInstance.save()
    }
    catch (error) {
      console.error("Failed to generate PDF:", error)
      throw error
    }
    finally {
      isGenerating.value = false
    }
  }

  return {
    exportToPdf,
    isGenerating,
  }
}
