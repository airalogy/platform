import type { CheckboxProps, DatePickerProps, DynamicInputProps, FormItemProps, InputNumberProps, InputProps, SelectProps, TimePickerProps } from "naive-ui"
import { BuiltInType } from "@airalogy/shared/enum/airalogy"

export const commonOverrides = {
  textColorDisabled: "#333",
  heightMedium: "40px",
} satisfies InputProps["themeOverrides"]

export const themeOverridesRecord = {
  formItem: {
    labelHeightSmall: "12px",
    labelHeightMedium: "12px",
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
  dynamicInput: {
    peers: {
      Input: commonOverrides,
      Button: {
        heightMedium: "32px",
        borderRadiusMedium: "6px",
      },
    },
    actionMargin: "0 4px",
  } satisfies DynamicInputProps["themeOverrides"],
  select: {
    peers: {
      InternalSelection: commonOverrides,
    },
  } satisfies SelectProps["themeOverrides"],
}
export const formThemeOverrides = {
  datePicker: {
    peers: {
      Input: {
        ...commonOverrides,
        borderRadius: "6px 6px 6px 6px",
      },
    },
  },
  dynamicInput: {
    peers: {
      Input: commonOverrides,
      Button: {
        heightMedium: "32px",
        borderRadiusMedium: "6px",
      },
    },
    actionMargin: "auto 4px",
  } satisfies DynamicInputProps["themeOverrides"],
}

export function createCommonThemeOverrides(type: string, source: "preview" | "form" = "preview") {
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
      return source === "form" ? formThemeOverrides.datePicker : themeOverridesRecord.datePicker
    case "enum":
      return themeOverridesRecord.select
    case "array":

      return source === "form" ? formThemeOverrides.dynamicInput : themeOverridesRecord.dynamicInput
    default:
      return commonOverrides
  }
}
