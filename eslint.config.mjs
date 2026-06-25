// @ts-check
import antfu from "@antfu/eslint-config"

export default antfu(
  {
    unocss: true,
    ignores: [
      // eslint ignore globs here
      ".history/*",
    ],
  },
  {
    settings: {
      "import/resolver": {
        typescript: true,
        node: true,
      },
    },
    rules: {
      // overrides
      "node/prefer-global/process": ["off"],
      "prefer-promise-reject-errors": ["off"],
      "no-console": ["off"],
      "vue/component-tags-order": ["error", { order: [["template", "script"], "style"] }],
      "vue/block-order": ["error", { order: [["template", "script"], "style"] }],
      "vue/component-name-in-template-casing": ["warn", "kebab-case"],
      "style/quotes": ["warn", "double"],
      "unused-imports/no-unused-vars": ["warn", { varsIgnorePattern: "^_", argsIgnorePattern: "^_", caughtErrors: "none", destructuredArrayIgnorePattern: "^_" }],
      "vue/no-unused-vars": ["warn", { ignorePattern: "^_" }],
      "vue/custom-event-name-casing": ["error", "camelCase", { ignores: ["/^[a-z]+(?:-[a-z]+)*:[a-z]+(?:-[a-z]+)*$/u"] }],
      "no-debugger": ["warn"],
      "no-useless-return": ["warn"],
    },
  },
  {
    files: ["**/*.vue"],
    rules: {
      "unused-imports/no-unused-imports": ["off"],
      "unused-imports/no-unused-vars": ["off"],
    },
  },
)
