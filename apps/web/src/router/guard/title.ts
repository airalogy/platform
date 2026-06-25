import type { Router } from "vue-router"
import { applyRouteSeo } from "@/utils/seo"
import { $t } from "@airalogy/shared/locales"

export function createDocumentTitleGuard(router: Router) {
  router.afterEach((to) => {
    const { meta, name } = to
    const { i18nKey, title, i18nTitle } = meta

    const key = i18nTitle || i18nKey
    const documentTitle = (key ? $t(key) : title) || "Airalogy"
    let finalTitle = `${documentTitle} · Airalogy`

    if (name === "root") {
      finalTitle = documentTitle
    }
    else if (name === "project-protocols" || name === "group-projects" || name === "protocol-info") {
      const { projectName, groupName, experimentName } = to.params
      const serialized = [experimentName, projectName, groupName].filter(Boolean).join(" / ")
      if (serialized) {
        finalTitle = `${serialized} · ${documentTitle}`
      }
    }

    applyRouteSeo(to, finalTitle)
  })
}
