import type { PluginOption } from "vite"
import { VitePluginWatchWorkspace } from "@prosopo/vite-plugin-watch-workspace"
import vue from "@vitejs/plugin-vue"
import vueJsx from "@vitejs/plugin-vue-jsx"
import mkcert from "vite-plugin-mkcert"
import progress from "vite-plugin-progress"
// import { VitePWA } from "vite-plugin-pwa"
import VueDevtools from "vite-plugin-vue-devtools"
import tsconfigPaths from "vite-tsconfig-paths"
import { setupSeoArtifacts } from "./seo"
import { setupUnocss } from "./unocss"
import { setupUnplugin } from "./unplugin"
import { pathResolve } from "./utils"

export function setupVitePlugins(viteEnv: Env.ImportMeta) {
  const enableWorkspaceWatch = process.env.VITE_WATCH_WORKSPACE !== "N"
  const enableDevtools = process.env.VITE_DEVTOOLS !== "N"
  const enableMkcert = process.env.VITE_MKCERT === "Y"

  const plugins: PluginOption = [
    tsconfigPaths({ loose: true }),
    ...(enableWorkspaceWatch
      ? [VitePluginWatchWorkspace({
          workspaceRoot: pathResolve("../../../../", import.meta.url),
          currentPackage: "apps/web",
          format: "esm", // or 'cjs'
          fileTypes: ["ts", "tsx", "js", "jsx", "vue"], // optional - file types to watch. default is ['ts', 'tsx']
          ignorePaths: ["node_modules", "dist"], // optional - globs to ignore
        })]
      : []),
    vue({
      script: {
        defineModel: true,
      },
    }),
    vueJsx(),
    ...(enableDevtools ? [VueDevtools()] : []),
    setupUnocss(viteEnv),
    setupSeoArtifacts(viteEnv),
    ...(enableMkcert
      ? [mkcert({
          hosts: [
            "localhost",
            "127.0.0.1",
          ],
          savePath: "./certs",
          autoUpgrade: false,
        })]
      : []),
    ...setupUnplugin(viteEnv),
    progress(),
    // VitePWA(),
  ]

  return plugins
}
