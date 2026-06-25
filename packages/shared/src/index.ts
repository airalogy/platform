// Constants (AIMD constants moved to @airalogy/aimd-core)
export * from "./constants/content-layout"
export * from "./constants/country-code"
export * from "./constants/editor"
export * from "./constants/eventKey"
export * from "./constants/mermaid"
export * from "./constants/protocol"

export * from "./constants/reg"

export * from "./enum"


export * from "./theme"

export type * from "./types"

// Field types (migrated from markdown-it)
export type {
  ExtractResult,
  FieldKey,
  FieldRecord,
  FieldResponseKey,
  FiledName,
  IAnnotationDataItem,
  IFieldItem,
  IFileDataItem,
  IRecordData,
  IRecordDataItem,
  IRecordDataKey,
  ScopeFieldKey,
} from "./types/fields"

// Utils - export all utilities (excluding schema constants to avoid re-export)
export * from "./utils/assert"
export * from "./utils/changeCase"
export * from "./utils/clipboard"
export * from "./utils/date"
export * from "./utils/download"
// Editor/file utilities (migrated from markdown-it)
export { base64ToBuffer, blobUrlToBase64, blobUrlToFile, bufferToBlob, createFullUrl, fileToBase64, fileToBlob, filterFiles, isBase64, isUrl, randomId, sanitizeUrl } from "./utils/editor-utils"
export * from "./utils/errorFormatter"
export * from "./utils/file"
export * from "./utils/formatNumbers"
export * from "./utils/isoDuration"
export * from "./utils/jsonSchema"
export * from "./utils/parseAiralogyId"
export * from "./utils/request"
// Schema constants - explicitly export to avoid conflicts
export {
  getRecordDataKey,
  getSchemaKey,
  scopeColorRecord,
  scopeKeyRecord,
  scopeNameRecord,
} from "./utils/schema/constants"
export * from "./utils/storage"

export * from "./utils/storageMonitor"

export * from "./utils/uri"

export * from "./utils/varTypeParser"
