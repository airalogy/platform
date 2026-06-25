import type { PluginOption } from "vite"
import { createSiteOrigin } from "../../env.config"

function createRobotsTxt(siteOrigin: string) {
  return [
    "User-agent: *",
    "Allow: /",
    "Allow: /api/sitemap.xml",
    "Disallow: /admin/",
    "Disallow: /login",
    "Disallow: /sign-up",
    "Disallow: /forget-password",
    `Sitemap: ${siteOrigin}/sitemap.xml`,
    "",
  ].join("\n")
}

function createSitemapIndex(siteOrigin: string) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>${siteOrigin}/api/sitemap.xml</loc>
  </sitemap>
</sitemapindex>
`
}

export function setupSeoArtifacts(viteEnv: Env.ImportMeta): PluginOption {
  const siteOrigin = createSiteOrigin(viteEnv)

  return {
    name: "airalogy-seo-artifacts",
    apply: "build",
    generateBundle() {
      this.emitFile({
        type: "asset",
        fileName: "robots.txt",
        source: createRobotsTxt(siteOrigin),
      })
      this.emitFile({
        type: "asset",
        fileName: "sitemap.xml",
        source: createSitemapIndex(siteOrigin),
      })
    },
  }
}
