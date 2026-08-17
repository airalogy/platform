import type { FileImporter } from "sass"
import type { Plugin } from "vite"
import { existsSync, readFileSync } from "node:fs"
import { extname, resolve, sep } from "node:path"
import { pathToFileURL } from "node:url"
import importMetaUrlPlugin from "@codingame/esbuild-import-meta-url-plugin"
import { defineConfig, loadEnv } from "vite"
import { createViteProxy } from "./build/config"
import { setupVitePlugins } from "./build/plugins"

const BUILD_TIME = new Date().toISOString()
const base = pathToFileURL(resolve("./src/styles"))
const documentationRoute = "/docs"

function setupEmbeddedDocumentation(): Plugin {
  return {
    name: "airalogy:embedded-documentation",
    apply: "serve",
    configureServer(server) {
      const documentationRoot = resolve(server.config.publicDir, "docs")
      server.middlewares.use((request, response, next) => {
        if (!request.url)
          return next()

        const url = new URL(request.url, "http://localhost")
        if (url.pathname === documentationRoute) {
          response.statusCode = 308
          response.setHeader("Location", `${documentationRoute}/${url.search}`)
          response.end()
          return
        }

        if (!url.pathname.startsWith(`${documentationRoute}/`))
          return next()

        const relativePath = decodeURIComponent(
          url.pathname.slice(`${documentationRoute}/`.length),
        )
        const candidates = !relativePath || relativePath.endsWith("/")
          ? [`${relativePath}index.html`]
          : extname(relativePath)
            ? []
            : [`${relativePath}.html`, `${relativePath}/index.html`]

        for (const candidate of candidates) {
          const absolutePath = resolve(documentationRoot, candidate)
          if (
            !absolutePath.startsWith(`${documentationRoot}${sep}`)
            || !existsSync(absolutePath)
          ) {
            continue
          }

          response.statusCode = 200
          response.setHeader("Content-Type", "text/html; charset=utf-8")
          response.end(readFileSync(absolutePath))
          return
        }

        next()
      })
    },
  }
}

const sassFileImporter: FileImporter<"sync"> = {
  findFileUrl(url) {
    if (url.startsWith("@styles/")) {
      return new URL(url.slice(1), base)
    }
    else if (url.startsWith("@airalogy/components/")) {
      return new URL(url.replace("@airalogy/components/", "./src/"), pathToFileURL(resolve("../../packages/components/src")))
    }

    return null
  },
}

// https://vitejs.dev/config/
export default defineConfig((configEnv) => {
  const loadedEnv = loadEnv(configEnv.mode, process.cwd(), "")
  const viteEnv = {
    ...loadedEnv,
    ...process.env,
    VITE_SERVICE_ENV: (process.env.VITE_SERVICE_ENV as Env.ServiceEnv) || "dev",
    VITE_HTTP_PROXY: (process.env.VITE_HTTP_PROXY as CommonType.YesOrNo) || "N",
  } as Env.ImportMeta

  console.log(`[Vite Config] Mode: ${configEnv.mode}`)
  console.log(`[Vite Config] VITE_SERVICE_ENV: ${viteEnv.VITE_SERVICE_ENV}`)
  console.log(`[Vite Config] VITE_HTTP_PROXY: ${viteEnv.VITE_HTTP_PROXY}`)

  return {
    worker: { format: "es" },
    build: {
      rollupOptions: {
        external: [/^vscode-jsonrpc/, "langium"],
      },
    },
    base: "/",
    // resolve: {
    //   alias: {
    //     "~": pathResolve("."),
    //     "@": pathResolve("./src"),
    //     "#": pathResolve("./types"),
    //     "@styles": pathResolve("./src/styles"),
    //     "@img": pathResolve("./src/assets/img"),
    //     "@icons": pathResolve("./src/assets/icons"),
    //     "@fonts": pathResolve("./src/assets/fonts"),
    //   },
    // },
    plugins: [setupEmbeddedDocumentation(), ...setupVitePlugins(viteEnv)],
    define: { BUILD_TIME: JSON.stringify(BUILD_TIME, null, 0) },
    server: {
      host: "0.0.0.0",
      port: 3000,
      open: !process.env.CI,
      proxy: createViteProxy(viteEnv),
      strictPort: true,
      // Remove CORS restrictions in development for external images
      ...(configEnv.mode === "production"
        ? {
            headers: {
              "Cross-Origin-Embedder-Policy": "require-corp",
              "Cross-Origin-Opener-Policy": "same-origin",
            },
          }
        : {}),
    },
    esbuild: configEnv.mode === "production"
      ? {
          drop: ["console", "debugger"],
        }
      : undefined,
    css: {
      preprocessorOptions: {
        sass: {
          additionalData: "@use \"@styles/sass/variable.sass\" as *\n",
          api: "modern-compiler",
          importers: [sassFileImporter],
        },
      },
    },
    resolve: {
      alias: {
        debug: resolve(__dirname, "src/shims/debug.ts"),
        extend: resolve(__dirname, "src/shims/extend.ts"),
      },
      dedupe: ["monaco-editor"],
    },
    optimizeDeps: {
      include: ["monaco-editor", "monaco-editor/esm/vs/editor/editor.worker"],
      exclude: ["@airalogy/shared", "langium"],
      esbuildOptions: {
        tsconfig: "./tsconfig.json",
        plugins: [importMetaUrlPlugin],
      },
    },
  }
})
