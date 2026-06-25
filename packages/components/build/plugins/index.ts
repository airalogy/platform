import type { PluginOption } from "vite"
import vue from "@vitejs/plugin-vue"
import vueJsx from "@vitejs/plugin-vue-jsx"
import tsconfigPaths from "vite-tsconfig-paths"
import { setupUnocss } from "./unocss"
import { setupUnplugin } from "./unplugin"

export function setupVitePlugins(viteEnv: Env.ImportMeta) {
  const plugins: PluginOption = [
    tsconfigPaths({ loose: true }),
    vue({
      script: {
        defineModel: true,
      },
    }),
    vueJsx(),
    setupUnocss(viteEnv) as unknown as PluginOption,
    ...setupUnplugin(viteEnv),
  ]

  return plugins
}
