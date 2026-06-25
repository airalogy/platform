import type { PluginOption } from "vite"
import AutoImport from "unplugin-auto-import/vite"
import { FileSystemIconLoader } from "unplugin-icons/loaders"
import IconsResolver from "unplugin-icons/resolver"
import Icons from "unplugin-icons/vite"
import { NaiveUiResolver } from "unplugin-vue-components/resolvers"
import Components from "unplugin-vue-components/vite"
import { pathResolve } from "./utils"

/** Icon prefix */
const ICON_PREFIX = "icon"
/** Local icon prefix */
const ICON_LOCAL_PREFIX = "icon-local"
/** Shared icon prefix */
const ICON_SHARED_PREFIX = "icon-shared"

export function setupUnplugin(_viteEnv: Env.ImportMeta) {
  const localIconPath = pathResolve("../../src/assets/svg-icon", import.meta.url)
  const sharedIconPath = pathResolve("../../../../packages/shared/src/assets/icons", import.meta.url)
  console.log(localIconPath, sharedIconPath)

  /** The name of the local icon collection */
  const collectionName = ICON_LOCAL_PREFIX.replace(`${ICON_PREFIX}-`, "")
  const sharedCollectionName = ICON_SHARED_PREFIX.replace(`${ICON_PREFIX}-`, "")

  const plugins: PluginOption[] = [
    AutoImport({
      include: [
        /\.[tj]sx?$/, // .ts, .tsx, .js, .jsx
        /\.vue$/,
        /\.vue\?vue/, // .vue
      ],
      dts: "src/types/auto-imports.d.ts",
      imports: ["vue", "vue-router", "vuex", "@vueuse/core"],
    }),
    Icons({
      compiler: "vue3",
      customCollections: {
        [collectionName]: FileSystemIconLoader(localIconPath, svg =>
          svg.replace(/^<svg\s/, "<svg width=\"1em\" height=\"1em\" ")),
        [sharedCollectionName]: FileSystemIconLoader(sharedIconPath, svg =>
          svg.replace(/^<svg\s/, "<svg width=\"1em\" height=\"1em\" ")),
      },
      scale: 1,
      // defaultClass: "inline-block",
    }),
    Components({
      dts: "src/types/components.d.ts",
      resolvers: [
        NaiveUiResolver(),
        IconsResolver({ customCollections: [collectionName, sharedCollectionName], componentPrefix: ICON_PREFIX }),
      ],
    }),
  ]
  return plugins
}
