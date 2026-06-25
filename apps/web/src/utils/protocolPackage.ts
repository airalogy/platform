import type { Zippable } from "@airalogy/shared/utils"
import { fileMap } from "@airalogy/components/monaco-editor/composables/useFileUpload"
import { zipToPromise } from "@airalogy/shared/utils"
import { DEFAULT_FILE_ID_MAP, type ProtocolData } from "../constants/protocol"

// export async function unPackageProtocol(file: File): Promise<ProtocolData | null> {
//   if (!file) {
//     return null
//   }

//   try {
//     const buffer = await file.arrayBuffer()

//     const massiveFile = new Uint8Array(buffer)

//     let root = ""
//     const decompressed = await unzipToPromise(massiveFile, {
//       filter(file) {
//         const { name } = file
//         const isMACOSX = name.startsWith("__MACOSX") || name.endsWith(".DS_Store")
//         if (isMACOSX) {
//           return false
//         }

//         if (!root && /[^/]+\/$/.test(file.name)) {
//           root = file.name
//           return false
//         }

//         return true
//       },
//     })

//     if (!decompressed) {
//       return null
//     }

//     const result = Object.entries(decompressed).reduce((acc, [k, v]) => {
//       convertContentToProtocol(acc, k, v, root)

//       return acc
//     }, { model: "", assigner: "", protocol: "", metadata: {} } as ProtocolData)

//     return result
//   }
//   catch (e) {
//     // NOPE

//     return null
//   }
// }

// export async function convertContentToProtocol(acc: ProtocolData, path: string, v: Uint8Array, root: string) {
//   const content = arrayBufferToString(v)
//   try {
//     if (path === `${root}model.py`) {
//       acc.model = content
//     }
//     else if (path === `${root}protocol.aimd`) {
//       acc.protocol = content
//     }
//     else if (path === `${root}assigner.py`) {
//       acc.assigner = content
//     }
//     else if (path === `${root}protocol.toml`) {
//       try {
//         acc.toml_config = content
//         acc.metadata = parse(content)
//       }
//       catch (e) {
//         //
//       }
//     }
//     // else if (k === `${root}version.py`) {
//     //   acc.metadata.version = parseVersion(arrayBufferToString(v))
//     // }
//   }
//   catch (e) {
//     //
//   }
//   finally {
//     // eslint-disable-next-line no-unsafe-finally
//     return acc
//   }
// }

const encoder = new TextEncoder()
export async function convertProtocolToZip(data: ProtocolData, name: string) {
  if (!data || !name) {
    throw new Error("Protocol data and name are required")
  }

  const zipData: Zippable = {
    // Add root directory entry with trailing slash
    [`${name}/`]: new Uint8Array(0),
  }

  Object.entries(data).forEach(([key, value]) => {
    if (!value || typeof value !== "string")
      return

    const fileName = fileMap[DEFAULT_FILE_ID_MAP[key as keyof typeof DEFAULT_FILE_ID_MAP]]
    if (!fileName)
      return

    // Add files under the root directory
    zipData[`${name}/${fileName}`] = encoder.encode(value)
  })

  try {
    const zip = await zipToPromise(zipData, { level: 0 })
    return new File([zip], `${name}.zip`, { type: "application/zip" })
  }
  catch (error) {
    throw new Error(`Failed to create protocol package: ${(error as Error).message}`)
  }
}
