declare module "pdfjs-dist/legacy/build/pdf.min.mjs" {
  export * from "pdfjs-dist"
}

declare module "pdfjs-dist/legacy/build/pdf.worker.entry" {
  const entry: string
  export default entry
}

declare module "pdfjs-dist/legacy/web/pdf_viewer.component" {
  export * from "pdfjs-dist/types/web/event_utils"
}

declare module "pdfjs-dist/legacy/web/pdf_viewer" {
  export * from "pdfjs-dist/types/web/pdf_viewer"
}

declare module "pdfjs-dist/legacy/web/event_utils" {
  export * from "pdfjs-dist/types/web/pdf_viewer.component"
}
