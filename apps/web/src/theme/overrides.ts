import type { ConfigProviderProps } from "naive-ui"

export const themeOverrides: ConfigProviderProps["themeOverrides"] = {
  common: {
    primaryColor: "#1A79FF",
    primaryColorHover: "#4181FD",
    primaryColorPressed: "#1454D4",
  },
  // Cascader: {
  //   optionTextColorActive: "#007bffFF",
  //   optionCheckMarkColor: "#007bffFF",
  //   loadingColor: "#007bffFF",
  // },

  Button: {
    /** Large */
    fontSizeLarge: "16px",
    heightLarge: "48px",
    borderRadiusLarge: "8px",
    paddingLarge: "14px",
    iconMarginLarge: "8px",

    /** Medium */
    fontSizeMedium: "14px",
    heightMedium: "40px",
    borderRadiusMedium: "6px",
    paddingMedium: "12px",
    iconMarginMedium: "6px",

    /** Small */
    fontSizeSmall: "12px",
  },
  Tabs: {
    tabFontWeightActive: 500,
    tabFontSizeMedium: "1.125rem",
    tabPaddingMediumLine: "1.125rem 0",
  },
  // Menu: {
  //   itemHeight: "60px",
  //   borderRadius: "12px",
  // },
  Tag: {
    borderRadius: "6px",
  },
  Popover: {
    borderRadius: "8px",
  },
  Dropdown: {
    borderRadius: "8px",
  },
  Input: {
    heightMedium: "3rem",
    fontSizeMedium: "1rem",
    borderRadius: "8px",
  },
  Select: {
    peers: {
      InternalSelection: {
        heightMedium: "3rem",
        fontSizeMedium: "1rem",
        borderRadius: "8px",
      },
      InternalSelectMenu: {
        borderRadius: "6px",
        height: "14rem",
      },
    },
  },
  Message: {
    borderRadius: "6px",
  },
  List: {
    borderRadius: "6px",
  },
  Dialog: {
    borderRadius: "20px",
    padding: "20px 24px 24px 24px",
    iconSize: "24px",
    contentMargin: "20px 0",
    iconMargin: "0 8px 0 0",
    closeSize: "24px",
    closeIconSize: "20px",
    fontSize: "16px",
  },
  Notification: {
    borderRadius: "8px",
  },
  Card: {
    borderRadius: "10px",
  },

  DataTable: {
    thColor: "#F3F5F9",
  },

  Form: {
    labelFontSizeTopLarge: "16px",
    feedbackPadding: "2px 0",
    feedbackHeightLarge: "22px",
  },

  Upload: {
    borderRadius: "6px",
  },

  Cascader: {
    menuBorderRadius: "0 0 12px 12px",
    peers: {
      InternalSelection: {
        heightMedium: "3rem",
        fontSizeMedium: "1rem",
        borderRadius: "8px",
      },
    },
  },
}

export const lightThemeOverrides: ConfigProviderProps["themeOverrides"] = {
  common: {
    textColorBase: "#333333",
    textColor1: "#333333",
    textColor2: "#333333",
    textColor3: "#666666",
  },
  Button: {
    colorPressed: "#FFFFFF",
    itemTextColorActive: "#1A79FF",
    textColorFocus: "#1A79FF",
    textColorHover: "#1A79FF",
    textColorPressed: "#1A79FF",
    borderFocus: "#4181FD",

    /** Primary */
    textColorPrimary: "#FFFFFF",
    textColorFocusPrimary: "#FFFFFF",
    textColorPressedPrimary: "#FFFFFF",

    colorPrimary: "#1A79FF",
    colorHoverPrimary: "#4181FD",
    colorPressedPrimary: "#1454D4",
    colorDisabledPrimary: "#A0C0FE",

    borderPrimary: "#1A79FF",
    borderHoverPrimary: "1px solid #4181FD",
    borderPressedPrimary: "#1454D4",

    /** Secondary */
    colorSecondary: "#1A79FF",
    colorSecondaryHover: "#F1F6FF",
    colorSecondaryPressed: "#DBE7FF",

    /** Tertiary */

    /** Quaternary */
    textColorQuaternary: "#1A79FF",
    textColorQuaternaryHover: "#4181FD",
    textColorQuaternaryPressed: "#1454D4",
    textColorQuaternaryFocus: "#1A79FF",

    /** Ghost */
    textColorGhost: "#666666",
    textColorGhostHover: "#4181FD",
    textColorGhostPressed: "#1454D4",
    textColorGhostDisabled: "#BCBCBC",

    /** Text */
    textColorText: "#1A79FF",
    textColorTextHover: "#4181FD",
    textColorTextPressed: "#1454D4",
    textColorTextDisabled: "#BCBCBC",

    /** Disabled */
    // colorDisabled: "#A0C0FE",
    textColorDisabledPrimary: "#FFFFFF",
    borderDisabled: "#E5E6EB",
  },
  Tabs: {
    tabTextColorActiveBar: "#333333",
    tabTextColorActiveLine: "#333333",
    tabTextColorHoverBar: "#666666",
    tabTextColorHoverLine: "#666666",
  },
  Pagination: {
    itemTextColorHover: "#1A79FF",
    itemColorActive: "#1A79FF",
    itemTextColorActive: "#FFFFFF",
    itemColorActiveHover: "#1A79FF",
  },
  Input: {
    color: "#F7F8F9",
    colorFocus: "#FFFFFF",
  },
  Modal: {
    peers: { Card: { borderRadius: "20px", actionColor: "#FFFFFF" } },
  },
  Select: {
    peers: {
      InternalSelection: {
        color: "#F7F8F9",
      },
    },
  },
  Form: {
    labelTextColor: "#333333",
  },
  Steps: {
    indicatorTextColorProcess: "#333333",
  },
  Upload: {
    draggerBorder: "1px dashed #EAECF0",
    draggerBorderHover: "1px solid #EAECF0",
  },
  Timeline: {
    lineColor: "rgba(26, 121, 255, 0.6)",
  },
}

export const darkThemeOverrides: ConfigProviderProps["themeOverrides"] = {
  common: {
    textColorBase: "#FFFFFF",
    textColor1: "#FFFFFF",
    textColor2: "#FFFFFF",
    textColor3: "#FFFFFF",
  },
  Button: {
    colorPressed: "#FFFFFF",
    itemTextColorActive: "#1A79FF",
    textColorFocus: "#1A79FF",
    textColorHover: "#1A79FF",
    textColorPressed: "#1A79FF",
  },
  Upload: {
    draggerBorder: "1px dashed #EAECF0",
    draggerBorderHover: "1px solid #EAECF0",
  },
  Tabs: {
    tabTextColorBar: "#FFFFFF66",
    tabTextColorHoverBar: "#FFFFFF88",
    tabTextColorActiveBar: "#FFFFFF",
  },
  Tree: {
    nodeTextColor: "#FFFFFF",
    nodeColorHover: "#3C445399",
    nodeColorActive: "#3c4453",
  },
}
