import type { PluginOption } from "vite"
import { fileURLToPath } from "node:url"
import AutoImport from "unplugin-auto-import/vite"
import { FileSystemIconLoader } from "unplugin-icons/loaders"
import IconsResolver from "unplugin-icons/resolver"
import Icons from "unplugin-icons/vite"
import { NaiveUiResolver } from "unplugin-vue-components/resolvers"
import Components from "unplugin-vue-components/vite"

function pathResolve(dir: string) {
  return fileURLToPath(new URL(dir, import.meta.url))
}

export function setupUnplugin(viteEnv: Env.ImportMeta) {
  const { VITE_ICON_PREFIX, VITE_ICON_SHARED_PREFIX } = viteEnv

  const sharedIconPath = pathResolve("../../src/assets/icons")

  /** The name of the shared icon collection */
  const sharedCollectionName = VITE_ICON_SHARED_PREFIX.replace(`${VITE_ICON_PREFIX}-`, "")

  const plugins: PluginOption[] = [
    AutoImport({
      include: [
        /\.[tj]sx?$/, // .ts, .tsx, .js, .jsx
        /\.vue$/,
        /\.vue\?vue/, // .vue
      ],
      dts: "src/types/auto-imports.d.ts",
      imports: ["vue", "@vueuse/core"],
    }),
    Icons({
      compiler: "vue3",
      customCollections: {
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
        IconsResolver({ customCollections: [sharedCollectionName], componentPrefix: VITE_ICON_PREFIX }),
      ],
    }),
  ]
  return plugins
}
