import { $t } from "@airalogy/shared/locales"

export function getHomeBreadcrumb(): App.Global.Breadcrumb {
  return {
    key: "home",
    label: $t("route.home").toUpperCase(),
    routeKey: "home",
    routePath: "/home",
    i18nKey: "route.home",
    to: { name: "home" },
    options: [],
  }
}
