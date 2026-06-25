import type { CheckboxProps, DatePickerProps, FormItemProps, InputNumberProps, InputProps, TimePickerProps } from "naive-ui"
import type { SelectProps } from "naive-ui/lib"
import { BuiltInType } from "@airalogy/shared/enum/airalogy"

// AIMD 边框颜色常量 - 与 aimd.css 中的 CSS 变量保持一致
const AIMD_BORDER_COLOR = "#90caf9"
const AIMD_BORDER_COLOR_FOCUS = "#4181fd"

export const commonOverrides = {
  paddingMedium: "0 0",
  heightMedium: "fit-content",
  borderRadius: "0 0 6px 6px",
  fontSizeMedium: "14px",
  textColorDisabled: "#333",
  border: `1px solid ${AIMD_BORDER_COLOR}`,
  borderHover: `1px solid ${AIMD_BORDER_COLOR}`,
  borderFocus: `1px solid ${AIMD_BORDER_COLOR_FOCUS}`,
} satisfies InputProps["themeOverrides"]

// Table cell specific overrides - full border radius for standalone inputs
export const tableCellOverrides = {
  ...commonOverrides,
  borderRadius: "6px", // Full border radius for table cells (no label above)
} satisfies InputProps["themeOverrides"]

export const themeOverridesRecord = {
  formItem: {
    labelHeightSmall: "12px",
    labelHeightMedium: "12px",
    labelPaddingVertical: "0",
  } satisfies FormItemProps["themeOverrides"],
  input: commonOverrides,
  inputNumber: {
    peers: {
      Input: commonOverrides,
    },
  } satisfies InputNumberProps["themeOverrides"],
  datePicker: {
    peers: {
      Input: commonOverrides,
    },
  } satisfies DatePickerProps["themeOverrides"],
  timePicker: {
    peers: {
      Input: { ...commonOverrides, borderRadius: "0px 0 6px 6px" },
    },
  } satisfies TimePickerProps["themeOverrides"],
  checkbox: {
    init: {
      border: "2px solid rgb(224, 224, 230)",
      borderDisabled: "2px solid rgb(224, 224, 230)",
      borderRadius: "6px",
      borderFocus: "2px solid #18a058",
      boxShadowFocus: "0 0 0 2px rgba(24, 160, 88, 0.3)",
      borderChecked: "2px solid #18a058",
      borderDisabledChecked: "2px solid rgba(224, 224, 230)",
      labelPadding: "0 0",
    } satisfies CheckboxProps["themeOverrides"],
    checked: {
      border: "2px solid rgba(24, 160, 88, 0.6)",
      borderDisabled: "2px solid rgba(24, 160, 88, 0.6)",
      borderRadius: "6px",
      borderFocus: "2px solid rgba(24, 160, 88, 1)",
      boxShadowFocus: "0 0 0 2px rgba(24, 160, 88, 0.6)",
      borderChecked: "2px solid rgba(24, 160, 88, 1)",
      borderDisabledChecked: "2px solid rgba(24, 160, 88, 1)",
      colorChecked: "rgba(24, 160, 88, 1)",
      colorDisabledChecked: "rgba(24, 160, 88, 1)",
      labelPadding: "0 0",
    } satisfies CheckboxProps["themeOverrides"],
    unchecked: {
      border: "2px solid rgba(255, 80, 83, 0.6)",
      borderDisabled: "2px solid rgba(255, 80, 83, 0.6)",
      borderRadius: "6px",
      borderFocus: "2px solid rgba(255, 80, 83, 1)",
      boxShadowFocus: "0 0 0 2px rgba(255, 80, 83, 0.6)",
      borderChecked: "2px solid rgba(255, 80, 83, 1)",
      borderDisabledChecked: "2px solid rgba(255, 80, 83, 1)",
      colorChecked: "rgba(255, 80, 83, 1)",
      colorDisabledChecked: "rgba(255, 80, 83, 1)",
      labelPadding: "0 0",
    } satisfies CheckboxProps["themeOverrides"],
  },
  // dynamicInput: {
  //   peers: {
  //     Input: commonOverrides,
  //     Button: {
  //       heightMedium: "32px",
  //       borderRadiusMedium: "6px",
  //     },
  //   },
  //   actionMargin: "0 4px",
  // } satisfies DynamicInputProps["themeOverrides"],
  dynamicInput: { ...commonOverrides, borderRadius: "0 0 6px 6px" },
  select: {
    peers: {
      InternalSelection: {
        heightMedium: "33px",
        fontSizeMedium: "14px",
        borderRadius: "0 0 6px 6px",
        textColorDisabled: commonOverrides.textColorDisabled,
      },
    },

  } satisfies SelectProps["themeOverrides"],
}

export function createCommonThemeOverrides(type: string) {
  switch (type) {
    case "text":
    case "textarea":
    case "password":
    case BuiltInType.UserName:
      return themeOverridesRecord.input
    case "number":
    case "integer":
    case "float":
      return themeOverridesRecord.inputNumber
    case "time":
    case "duration":
      return themeOverridesRecord.timePicker
    case "date":
    case "datetime":
    case BuiltInType.CurrentTime:
      return themeOverridesRecord.datePicker
    default:
      return commonOverrides
  }
}

/**
 * Create theme overrides for table cell inputs
 * Table cells have full border radius since there's no label above them
 */
export function createTableCellThemeOverrides(type: string) {
  switch (type) {
    case "text":
    case "textarea":
    case "password":
    case BuiltInType.UserName:
      return tableCellOverrides
    case "number":
    case "integer":
    case "float":
      return {
        peers: {
          Input: tableCellOverrides,
        },
      }
    case "time":
    case "duration":
      return {
        peers: {
          Input: tableCellOverrides,
        },
      }
    case "date":
    case "datetime":
    case BuiltInType.CurrentTime:
      return {
        peers: {
          Input: tableCellOverrides,
        },
      }
    default:
      return tableCellOverrides
  }
}
