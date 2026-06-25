import { defineConfig, loadEnv } from "vite"
import { setupVitePlugins } from "./build/plugins"

const BUILD_TIME = new Date().toISOString()

// https://vitejs.dev/config/
export default defineConfig((configEnv) => {
  const viteEnv = loadEnv(configEnv.mode, process.cwd()) as unknown as Env.ImportMeta
  console.log("configEnv", configEnv)
  console.log("viteEnv", viteEnv)

  return {
    build: {
      lib: {
        entry: "src/index.ts",
        name: "AiralogyComponents",
        fileName: "index",
        formats: ["es"],
        external: ["vue", "vue-router", "naive-ui", "@vueuse/core"],
      },
    },
    plugins: setupVitePlugins(viteEnv),
    define: { BUILD_TIME: JSON.stringify(BUILD_TIME, null, 0) },
    esbuild: viteEnv.VITE_SERVICE_ENV === "dev"
      ? undefined
      : {
        drop: ["console", "debugger"],
      },
    // css: {
    //   preprocessorOptions: {
    //     sass: {
    //       additionalData: "@import \"@/styles/sass/variable\"\n",
    //     },
    //   },
    // },
  }
})
