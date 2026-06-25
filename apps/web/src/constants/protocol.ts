import type { ProtocolMetaData } from "@airalogy/shared/types/models/protocol"

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

export const diaryProtocol: ProtocolData = {
  model: "",
  protocol: `# Diary

Recorder's Name: {{var|name: UserName}}

Recording Time: {{var|time: CurrentTime}}

Content:

{{var|content: AiralogyMarkdown}}`,
  assigner: "",
  toml_config: `
[airalogy_protocol]
id = "diary"
version = "0.0.2"
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
      version: "0.0.2",
    },
  },
}
