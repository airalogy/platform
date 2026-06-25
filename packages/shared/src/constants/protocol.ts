import type { ProtocolMetaData } from "../types/models/protocol"

export type ProtocolPackageFileId = Exclude<keyof typeof DEFAULT_FILE_ID_MAP, "version">
export type ProtocolData = Record<ProtocolPackageFileId, string> & {
  metadata: {
    airalogy_protocol?: Partial<ProtocolMetaData>
  }
}

export const DEFAULT_FILE_ID_MAP = {
  model: "airalogy_model",
  protocol: "airalogy_protocol",
  version: "airalogy_version",
  toml_config: "airalogy_toml_config",
  assigner: "airalogy_assigner",
} as const
export const DEFAULT_FILE_ID_NAME_MAP = {
  [DEFAULT_FILE_ID_MAP.model]: "model.py",
  [DEFAULT_FILE_ID_MAP.protocol]: "protocol.aimd",
  [DEFAULT_FILE_ID_MAP.version]: "version.py",
  [DEFAULT_FILE_ID_MAP.toml_config]: "protocol.toml",
  [DEFAULT_FILE_ID_MAP.assigner]: "assigner.py",

} as const

export const diaryProtocol: ProtocolData = {
  model: `from pydantic import BaseModel

from airalogy.built_in_types import UserName, CurrentTime, AiralogyMarkdown


class VarModel(BaseModel):
    name: UserName
    time: CurrentTime
    content: AiralogyMarkdown`,
  protocol: `# Diary

Recorder's Name: {{var|name}}

Recording Time: {{var|time}}

Content:

{{var|content}}`,
  assigner: "",
  toml_config: `
[airalogy_protocol]
id = "diary"
version = "0.0.1"
name = "Diary"
description = "A protocol for keeping a diary."
authors = [
    {name = "Airalogy"}
]
maintainers = [
    {name = "Airalogy"}
]
keywords = ["diary"]
license = "Apache-2.0"`,
  metadata: {
    airalogy_protocol: {
      name: "Diary",
      version: "0.0.1",
    },
  },
}
