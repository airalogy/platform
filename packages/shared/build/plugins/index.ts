import type { PluginOption } from "vite"
import vue from "@vitejs/plugin-vue"
import tsconfigPaths from "vite-tsconfig-paths"
import { setupUnplugin } from "./unplugin"

export function setupVitePlugins(viteEnv: Env.ImportMeta) {
  const plugins: PluginOption = [
    vue({
      script: {
        defineModel: true,
      },
    }),
    tsconfigPaths(),
    ...setupUnplugin(viteEnv),
  ]

  return plugins
}
