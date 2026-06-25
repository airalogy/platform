import { fileURLToPath } from "node:url"

export function pathResolve(dir: string, base: string) {
  return fileURLToPath(new URL(dir, base))
}
