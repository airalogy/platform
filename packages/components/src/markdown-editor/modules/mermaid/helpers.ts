import type { MermaidConfig, RenderResult } from "mermaid"
import mermaid from "mermaid"

export async function render(config: MermaidConfig, code: string, id: string): Promise<RenderResult> {
  // Should be able to call this multiple times without any issues.
  mermaid.initialize(config)
  return await mermaid.render(id, code)
}

export async function parse(code: string) {
  return await mermaid.parse(code)
}
