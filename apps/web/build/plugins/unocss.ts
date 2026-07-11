import path from "node:path"
import process from "node:process"
import { FileSystemIconLoader } from "@iconify/utils/lib/loader/node-loaders"
import presetIcons from "@unocss/preset-icons"
import unocss from "@unocss/vite"
import baseUnoConfig from "../../../../uno.config"

/** Icon prefix */
const ICON_PREFIX = "icon"
/** Local icon prefix */
const ICON_LOCAL_PREFIX = "icon-local"

export function setupUnocss(_viteEnv: Env.ImportMeta) {
  const localIconPath = path.join(process.cwd(), "src/assets/svg-icon")

  /** The name of the local icon collection */
  const collectionName = ICON_LOCAL_PREFIX.replace(`${ICON_PREFIX}-`, "")

  return unocss({
    ...baseUnoConfig,
    presets: [
      ...(baseUnoConfig.presets ?? []),
      presetIcons({
        prefix: `${ICON_PREFIX}-`,
        scale: 1,
        extraProperties: {
          display: "inline-block",
        },
        collections: {
          [collectionName]: FileSystemIconLoader(localIconPath, svg =>
            svg.replace(/^<svg\s/, "<svg width=\"1em\" height=\"1em\" ")),
        },
        warn: true,
      }),
    ],
  })
}
