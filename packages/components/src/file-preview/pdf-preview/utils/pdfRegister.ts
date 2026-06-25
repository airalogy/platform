import type {
  DocumentInitParameters,
  PDFDataRangeTransport,
  PDFDocumentLoadingTask,
} from "pdfjs-dist/types/src/display/api"

import * as pdfjsLib from "pdfjs-dist/legacy/build/pdf.min.mjs"

export const PIXEL_RATIO = window.devicePixelRatio || 1
export const VIEWPORT_RATIO = 0.98

export function createLoadingTask(src: string | URL | Uint8Array | PDFDataRangeTransport | DocumentInitParameters): PDFDocumentLoadingTask {
  if (!pdfjsLib.GlobalWorkerOptions.workerSrc) {
    pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
      "pdfjs-dist/legacy/build/pdf.worker.min.mjs",
      import.meta.url,
    ).toString()
  }

  const loadingTask = pdfjsLib.getDocument(src)
  return loadingTask
}
