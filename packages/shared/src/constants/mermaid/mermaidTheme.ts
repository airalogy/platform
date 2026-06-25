import type { editor } from "monaco-editor"
import type { ThemeRegistration } from "shiki"

export const mermaidMonacoTheme: editor.IStandaloneThemeData = {
  base: "vs-dark",
  inherit: true,
  colors: {},
  rules: [
    { token: "typeKeyword", foreground: "9650c8", fontStyle: "bold" },
    { token: "transition", foreground: "008800", fontStyle: "bold" },
    { token: "identifier", foreground: "9cdcfe" },
  ],
}

export const mermaidShikiTheme: ThemeRegistration & Pick<editor.IStandaloneThemeData, "rules" | "base" | "inherit"> = {
  name: "mermaid-dark",
  ...mermaidMonacoTheme,
}
