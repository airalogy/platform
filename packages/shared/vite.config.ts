import { defineConfig, loadEnv } from "vite"
import { setupVitePlugins } from "./build/plugins"

import "./src/types/env.d.ts"

const BUILD_TIME = new Date().toISOString()

// https://vitejs.dev/config/
export default defineConfig((configEnv) => {
  const viteEnv = loadEnv(configEnv.mode, process.cwd()) as unknown as Env.ImportMeta
  console.log("configEnv", configEnv)
  console.log("viteEnv", viteEnv)

  return {
    build: {
      lib: {
        entry: {
          index: "src/index.ts",
          constants: "src/constants/index.ts",
          enum: "src/enum/index.ts",
          utils: "src/utils/index.ts",
          unified: "src/unified/index.ts",
        },
        formats: ["es"],
      },
      rollupOptions: {
        external: ["naive-ui", "@vueuse/core", "vue"],
        output: {
          format: "es",
          dir: "dist",
          entryFileNames: "[name].js",
          chunkFileNames: "[name].js",
        },
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
