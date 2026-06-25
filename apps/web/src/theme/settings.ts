/** Default theme settings */
export const themeSettings: Theme.ThemeSetting = {
  themeScheme: "light",
  themeColor: "#1A79FF",
  otherColor: {
    info: "#3BC6DF",
    success: "#1BA37B",
    warning: "#F99534",
    error: "#FF5053",
  },
  isInfoFollowPrimary: true,
  layout: {
    mode: "vertical",
    scrollMode: "wrapper",
    maxWidth: 1200,
  },
  page: {
    animate: true,
    animateMode: "fade-slide",
  },
  header: {
    height: 70,
    breadcrumb: {
      visible: true,
      showIcon: true,
    },
  },
  tab: {
    visible: true,
    cache: true,
    height: 44,
    mode: "chrome",
  },
  fixedHeaderAndTab: true,
  sider: {
    inverted: false,
    width: 220,
    collapsedWidth: 64,
    mixWidth: 90,
    mixCollapsedWidth: 64,
    mixChildMenuWidth: 200,
  },
  footer: {
    visible: true,
    fixed: false,
    height: 400,
    right: true,
  },
  tokens: {
    light: {
      colors: {
        "container": "rgb(255, 255, 255)",
        "layout": "rgb(255, 255, 255)",
        "inverted": "rgb(0, 20, 40)",
        "base-text": "rgb(31, 31, 31)",
        "text-secondary": "rgb(102, 102, 102)",
        "field-var-bg": "rgb(26, 121, 255)",
        "field-step-bg": "rgb(240, 160, 32)",
        "field-check-bg": "rgb(24, 160, 88)",
        "field-step-text": "rgb(240, 160, 32)",
        "field-check-text": "rgb(24, 160, 88)",
        "border": "rgb(224, 224, 230)",
        "border-hover": "rgb(224, 224, 230)",
        "border-focus": "rgb(224, 224, 230)",
      },
      boxShadow: {
        header: "0 1px 2px rgb(0, 21, 41, 0.08)",
        sider: "2px 0 8px 0 rgb(29, 35, 41, 0.05)",
        tab: "0 1px 2px rgb(0, 21, 41, 0.08)",
      },
    },
    // Dark theme has been completely removed
  },
  content: {
    containerContentClass: "",
    contentClass: "",
  },
}

/**
 * Override theme settings
 *
 * If publish new version, use `overrideThemeSettings` to override certain theme settings
 */
export const overrideThemeSettings: Partial<Theme.ThemeSetting> = {
  footer: { visible: true } as any,
}
