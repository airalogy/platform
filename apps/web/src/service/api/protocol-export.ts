import { request } from "../request"

export type ProtocolExportFormat = "aira" | "zip"

export async function downloadProtocolExport(id: string | number, version: string, format: ProtocolExportFormat = "aira") {
  const { data, error } = await request<Blob, "blob">({
    url: `/protocols/${id}/export`,
    params: { version, format },
    responseType: "blob",
    timeout: 5 * 60 * 1000,
    metadata: { showError: false },
  })
  if (error || !data)
    throw error || new Error("Protocol export failed")
  const url = URL.createObjectURL(data)
  const link = document.createElement("a")
  link.href = url
  link.download = `protocol-${String(id).replace(/[^\w-]/g, "_")}-v${version.replace(/[^\w.-]/g, "_")}.${format}`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
