import type * as Monaco from "monaco-editor"
import { useLoading } from "@airalogy/composables"

// Monaco Editor workers
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker"
import cssWorker from "monaco-editor/esm/vs/language/css/css.worker?worker"
import htmlWorker from "monaco-editor/esm/vs/language/html/html.worker?worker"
import jsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker"
import tsWorker from "monaco-editor/esm/vs/language/typescript/ts.worker?worker"

export function useLanguageClient() {
  const monaco = shallowRef<typeof Monaco | null>(null)
  const loadingState = useLoading()
  const { startTargetLoading, endTargetLoading } = loadingState

  async function init() {
    try {
      startTargetLoading("loader")

      // Setup Monaco Environment - Worker Configuration
      // @ts-expect-error - MonacoEnvironment is not defined in the global scope
      globalThis.MonacoEnvironment = {
        /* eslint-disable new-cap */
        getWorker(_: string, label: string) {
          if (label === "json")
            return new jsonWorker()
          if (label === "css" || label === "scss" || label === "less")
            return new cssWorker()
          if (label === "html" || label === "handlebars" || label === "razor")
            return new htmlWorker()
          if (label === "typescript" || label === "javascript")
            return new tsWorker()
          return new editorWorker()
        },
        /* eslint-enable new-cap */
      }

      // Import Monaco Editor
      const monacoInstance: typeof Monaco = await import("monaco-editor")
      monaco.value = markRaw(monacoInstance)

      // Register AIMD Language
      registerAimdLanguage(monacoInstance)

      // Register TOML Language
      registerTomlLanguage(monacoInstance)
    }
    catch (error: any) {
      console.error("Monaco initialization error:", error)
    }
    finally {
      endTargetLoading("loader")
    }
  }

  return { monaco, init, loadingState }
}

/**
 * Register AIMD Language (Based on Markdown + AIMD Field Syntax)
 */
function registerAimdLanguage(monaco: typeof Monaco) {
  // Register Language
  monaco.languages.register({
    id: "aimd",
    extensions: [".aimd"],
    aliases: ["AIMD", "aimd"],
    mimetypes: ["text/x-aimd"],
  })

  // Set Language Configuration
  monaco.languages.setLanguageConfiguration("aimd", {
    brackets: [
      ["{", "}"],
      ["[", "]"],
      ["(", ")"],
    ],
    autoClosingPairs: [
      { open: "{", close: "}" },
      { open: "[", close: "]" },
      { open: "(", close: ")" },
      { open: "\"", close: "\"" },
      { open: "'", close: "'" },
      { open: "`", close: "`" },
      { open: "{{", close: "}}" },
    ],
    surroundingPairs: [
      { open: "{", close: "}" },
      { open: "[", close: "]" },
      { open: "(", close: ")" },
      { open: "\"", close: "\"" },
      { open: "'", close: "'" },
      { open: "`", close: "`" },
    ],
  })

  // Set Monarch Syntax
  monaco.languages.setMonarchTokensProvider("aimd", {
    defaultToken: "",
    tokenPostfix: ".aimd",

    // AIMD Field Keywords
    aimdKeywords: ["var", "var_table", "step", "check", "ref_step", "ref_var"],
    aimdTypes: ["str", "int", "float", "bool", "list", "dict", "any"],

    tokenizer: {
      root: [
        // AIMD Field: {{type|content}}
        [/\{\{/, { token: "delimiter.bracket.aimd", next: "@aimdField" }],

        // Markdown Headers
        [/^#{1,6}\s.*$/, "keyword.md"],

        // Markdown Code Blocks
        [/^```\w*$/, { token: "string.code", next: "@codeblock" }],
        [/^~~~\w*$/, { token: "string.code", next: "@codeblock" }],

        // Markdown Inline Code
        [/`[^`]+`/, "string.code"],

        // Markdown Bold
        [/\*\*[^*]+\*\*/, "strong"],
        [/__[^_]+__/, "strong"],

        // Markdown Italic
        [/\*[^*]+\*/, "emphasis"],
        [/_[^_]+_/, "emphasis"],

        // Markdown Links
        [/\[[^\]]+\]\([^)]+\)/, "string.link"],

        // Markdown Images
        [/!\[[^\]]*\]\([^)]+\)/, "string.link"],

        // Markdown Blockquotes
        [/^>.*$/, "comment.quote"],

        // Markdown Lists
        [/^\s*[-*+]\s/, "keyword.list"],
        [/^\s*\d+\.\s/, "keyword.list"],

        // Markdown Horizontal Rules
        [/^[-*_]{3,}\s*$/, "keyword.hr"],

        // HTML Tags
        [/<\/?[\w-][^>]*>/, "tag"],
      ],

      // AIMD Field Content
      aimdField: [
        [/\}\}/, { token: "delimiter.bracket.aimd", next: "@pop" }],
        // Field Type Keywords
        [/\b(var_table|var|step|check|ref_step|ref_var)\b/, "keyword.aimd"],
        // Delimiters
        [/\|/, "delimiter.aimd"],
        // Type Annotations
        [/:/, "delimiter"],
        [/\b(str|int|float|bool|list|dict|any)\b/, "type.aimd"],
        // Brackets
        [/[[\]()]/, "delimiter.bracket"],
        // Equals Sign
        [/=/, "delimiter"],
        // Strings
        [/"[^"]*"/, "string"],
        [/'[^']*'/, "string"],
        // Numbers
        [/-?\d+\.?\d*/, "number"],
        // Booleans/null
        [/\b(true|false|True|False|null|None)\b/, "constant"],
        // subvars Keyword
        [/\bsubvars\b/, "keyword"],
        // Comma
        [/,/, "delimiter"],
        // Identifiers (Variable Names)
        [/[a-z_]\w*/i, "variable.aimd"],
        // Whitespace
        [/\s+/, ""],
      ],

      // Markdown Code Blocks
      codeblock: [
        [/^```\s*$/, { token: "string.code", next: "@pop" }],
        [/^~~~\s*$/, { token: "string.code", next: "@pop" }],
        [/.*$/, "string.code"],
      ],
    },
  })

  // Register Completion Provider
  monaco.languages.registerCompletionItemProvider("aimd", {
    provideCompletionItems: (model, position) => {
      const keywords = ["var", "var_table", "step", "check", "ref_step", "ref_var"]
      const word = model.getWordUntilPosition(position)
      const range = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endColumn: word.endColumn,
      }
      const suggestions = keywords.map(keyword => ({
        label: `{{${keyword}|}}`,
        kind: monaco.languages.CompletionItemKind.Snippet,
        insertText: `{{${keyword}|\${1:name}}}`,
        insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
        documentation: `Insert AIMD ${keyword} field`,
        range,
      }))
      return { suggestions }
    },
  })

  // Define AIMD Theme Colors
  monaco.editor.defineTheme("aimd-light", {
    base: "vs",
    inherit: true,
    rules: [
      { token: "delimiter.bracket.aimd", foreground: "2563eb" },
      { token: "keyword.aimd", foreground: "2563eb", fontStyle: "bold" },
      { token: "delimiter.aimd", foreground: "6b7280" },
      { token: "type.aimd", foreground: "7c3aed" },
      { token: "variable.aimd", foreground: "059669" },
      { token: "keyword.md", foreground: "1e40af" },
      { token: "string.code", foreground: "be185d" },
      { token: "strong", fontStyle: "bold" },
      { token: "emphasis", fontStyle: "italic" },
      { token: "string.link", foreground: "2563eb" },
      { token: "comment.quote", foreground: "6b7280", fontStyle: "italic" },
    ],
    colors: {},
  })

  monaco.editor.defineTheme("aimd-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "delimiter.bracket.aimd", foreground: "60a5fa" },
      { token: "keyword.aimd", foreground: "60a5fa", fontStyle: "bold" },
      { token: "delimiter.aimd", foreground: "9ca3af" },
      { token: "type.aimd", foreground: "a78bfa" },
      { token: "variable.aimd", foreground: "34d399" },
      { token: "keyword.md", foreground: "93c5fd" },
      { token: "string.code", foreground: "f472b6" },
      { token: "strong", fontStyle: "bold" },
      { token: "emphasis", fontStyle: "italic" },
      { token: "string.link", foreground: "60a5fa" },
      { token: "comment.quote", foreground: "9ca3af", fontStyle: "italic" },
    ],
    colors: {},
  })
}

/**
 * Register TOML Language
 */
function registerTomlLanguage(monaco: typeof Monaco) {
  // Register Language
  monaco.languages.register({
    id: "toml",
    extensions: [".toml"],
    aliases: ["TOML", "toml"],
    mimetypes: ["application/toml", "text/toml"],
  })

  // Set Language Configuration
  monaco.languages.setLanguageConfiguration("toml", {
    brackets: [
      ["{", "}"],
      ["[", "]"],
    ],
    autoClosingPairs: [
      { open: "{", close: "}" },
      { open: "[", close: "]" },
      { open: "\"", close: "\"" },
      { open: "'", close: "'" },
    ],
    comments: {
      lineComment: "#",
    },
  })

  // Set Monarch Syntax
  monaco.languages.setMonarchTokensProvider("toml", {
    defaultToken: "",
    tokenPostfix: ".toml",

    tokenizer: {
      root: [
        // Comments
        [/#.*$/, "comment"],
        // Table Headers
        [/\[[^\]]+\]\]?/, "keyword"],
        // Key-Value Pairs
        [/[a-z_][\w-]*(?=\s*=)/i, "variable"],
        // Equals Sign
        [/=/, "delimiter"],
        // Strings
        [/"""/, { token: "string", next: "@multilineString" }],
        [/"[^"]*"/, "string"],
        [/'[^']*'/, "string"],
        // Numbers
        [/-?\d+\.?\d*/, "number"],
        // Booleans
        [/\b(true|false)\b/, "constant"],
        // Date Time
        [/\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?/, "number"],
      ],
      multilineString: [
        [/"""/, { token: "string", next: "@pop" }],
        [/./, "string"],
      ],
    },
  })
}
