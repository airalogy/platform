/* eslint-disable regexp/no-dupe-disjunctions */
/* eslint-disable regexp/no-super-linear-backtracking */
// https://github.com/mermaid-js/mermaid-live-editor/blob/develop/src/lib/util/monacoExtra.ts

import type { languages } from "monaco-editor"

const requirementDiagrams = [
  "requirement",
  "functionalRequirement",
  "interfaceRequirement",
  "performanceRequirement",
  "physicalRequirement",
  "designConstraint",
]

const keywords: Record< string, {
  typeKeywords: string[]
  blockKeywords: string[]
  keywords: string[]
}> = {
  flowchart: {
    typeKeywords: ["flowchart", "flowchart-v2", "graph"],
    blockKeywords: ["subgraph", "end"],
    keywords: [
      "TB",
      "TD",
      "BT",
      "RL",
      "LR",
      "click",
      "call",
      "href",
      "_self",
      "_blank",
      "_parent",
      "_top",
      "linkStyle",
      "style",
      "classDef",
      "class",
      "direction",
      "interpolate",
    ],
  },
  sequenceDiagram: {
    typeKeywords: ["sequenceDiagram"],
    blockKeywords: ["alt", "par", "and", "loop", "else", "end", "rect", "opt", "alt", "rect"],
    keywords: [
      "participant",
      "as",
      "Note",
      "note",
      "right of",
      "left of",
      "over",
      "activate",
      "deactivate",
      "autonumber",
      "title",
      "actor",
      "accDescription",
      "link",
      "links",
    ],
  },
  classDiagram: {
    typeKeywords: ["classDiagram", "classDiagram-v2"],
    blockKeywords: ["class"],
    keywords: [
      "link",
      "click",
      "callback",
      "call",
      "href",
      "cssClass",
      "direction",
      "TB",
      "BT",
      "RL",
      "LR",
      "title",
      "accDescription",
      "order",
    ],
  },
  stateDiagram: {
    typeKeywords: ["stateDiagram", "stateDiagram-v2"],
    blockKeywords: ["state", "note", "end"],
    keywords: ["state", "as", "hide empty description", "direction", "TB", "BT", "RL", "LR"],
  },
  erDiagram: {
    typeKeywords: ["erDiagram"],
    blockKeywords: [],
    keywords: ["title", "accDescription"],
  },
  journey: {
    typeKeywords: ["journey"],
    blockKeywords: ["section"],
    keywords: ["title"],
  },
  info: {
    typeKeywords: ["info"],
    blockKeywords: [],
    keywords: ["showInfo"],
  },
  gantt: {
    typeKeywords: ["gantt"],
    blockKeywords: [],
    keywords: [
      "title",
      "dateFormat",
      "axisFormat",
      "todayMarker",
      "section",
      "excludes",
      "inclusiveEndDates",
    ],
  },
  requirementDiagram: {
    typeKeywords: ["requirement", "requirementDiagram"],
    blockKeywords: [...requirementDiagrams, "element"],
    keywords: [],
  },
  gitGraph: {
    typeKeywords: ["gitGraph"],
    blockKeywords: [],
    keywords: [
      "accTitle",
      "accDescr",
      "commit",
      "cherry-pick",
      "branch",
      "merge",
      "reset",
      "checkout",
      "LR",
      "BT",
      "id",
      "msg",
      "type",
      "tag",
      "NORMAL",
      "REVERSE",
      "HIGHLIGHT",
    ],
  },
  pie: {
    typeKeywords: ["pie"],
    blockKeywords: [],
    keywords: ["showData", "title", "accDescr", "accTitle"],
  },
  c4Diagram: {
    typeKeywords: ["C4Context", "C4Container", "C4Component", "C4Dynamic", "C4Deployment"],
    blockKeywords: [
      "Boundary",
      "Enterprise_Boundary",
      "System_Boundary",
      "Container_Boundary",
      "Node",
      "Node_L",
      "Node_R",
    ],
    keywords: [
      "title",
      "accDescription",
      "direction",
      "TB",
      "BT",
      "RL",
      "LR",
      "Person_Ext",
      "Person",
      "SystemQueue_Ext",
      "SystemDb_Ext",
      "System_Ext",
      "SystemQueue",
      "SystemDb",
      "System",
      "ContainerQueue_Ext",
      "ContainerDb_Ext",
      "Container_Ext",
      "ContainerQueue",
      "ContainerDb",
      "Container",
      "ComponentQueue_Ext",
      "ComponentDb_Ext",
      "Component_Ext",
      "ComponentQueue",
      "ComponentDb",
      "Component",
      "Deployment_Node",
      "Rel",
      "BiRel",
      "Rel_Up",
      "Rel_U",
      "Rel_Down",
      "Rel_D",
      "Rel_Left",
      "Rel_L",
      "Rel_Right",
      "Rel_R",
      "Rel_Back",
      "RelIndex",
    ],
  },
  sankey: {
    typeKeywords: ["sankey-beta"],
    blockKeywords: [],
    keywords: [],
  },
}

const configDirectiveHandler = [
  /^\s*%%(?=\{)/,
  {
    token: "string",
    next: "@configDirective",
    nextEmbedded: "javascript",
  },
] as languages.IShortMonarchLanguageRule1

// Register a tokens provider for the mermaid language
export const language: languages.IMonarchLanguage = {
  ...Object.entries(keywords)
    .map(entry =>
      Object.fromEntries(
        Object.entries(entry[1]).map(deepEntry => [
          entry[0] + deepEntry[0][0].toUpperCase() + deepEntry[0].slice(1),
          deepEntry[1],
        ]),
      ),
    )
    .reduce(
      (overallKeywords, nextKeyword) => ({
        ...overallKeywords,
        ...nextKeyword,
      }),
      {},
    ),
  tokenizer: {
    root: [
      [/^\s*gitGraph/m, "typeKeyword", "gitGraph"],
      [/^\s*info/m, "typeKeyword", "info"],
      [/^\s*pie/m, "typeKeyword", "pie"],
      [/^\s*(flowchart|flowchart-v2|graph)/m, "typeKeyword", "flowchart"],
      [/^\s*sequenceDiagram/, "typeKeyword", "sequenceDiagram"],
      [/^\s*classDiagram(-v2)?/, "typeKeyword", "classDiagram"],
      [/^\s*journey/, "typeKeyword", "journey"],
      [/^\s*gantt/, "typeKeyword", "gantt"],
      [/^\s*stateDiagram(-v2)?/, "typeKeyword", "stateDiagram"],
      [/^\s*er(Diagram)?/, "typeKeyword", "erDiagram"],
      [/^\s*requirement(Diagram)?/, "typeKeyword", "requirementDiagram"],
      [/^\s*sankey-beta/m, "typeKeyword", "sankey"],
      [
        /^\s*(C4Context|C4Container|C4Component|C4Dynamic|C4Deployment)/m,
        "typeKeyword",
        "c4Diagram",
      ],
      configDirectiveHandler,
      [/%%[^${].*$/, "comment"],
    ],
    configDirective: [[/%%$/, { token: "string", next: "@pop", nextEmbedded: "@pop" }]],
    gitGraph: [
      configDirectiveHandler,
      [/option(?=s)/, { token: "typeKeyword", next: "optionsGitGraph" }],
      [/(accTitle|accDescr)(\s*:)(\s*(?:\S[^\n\r]*|[\t\v\f \xA0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000\uFEFF])$)/, ["keyword", "delimiter.bracket", "string"]],
      [
        /(^\s*branch)(.*?)(\s+order)(:\s*)(\d+\s*$)/,
        ["keyword", "variable", "keyword", "delimiter.bracket", "number"],
      ],
      [/".*?"/, "string"],
      [
        /(^\s*)(branch|reset|merge|checkout)(\s*\S+)/m,
        ["delimiter.bracket", "keyword", "variable"],
      ],
      [
        /[A-Z][\w$]*/i,
        {
          cases: {
            "@gitGraphBlockKeywords": "typeKeyword",
            "@gitGraphKeywords": "keyword",
          },
        },
      ],
      [/%%[^$]([^%]*(?!%%$)%?)*$/, "comment"],
      [/\^/, "delimiter.bracket"],
    ],
    optionsGitGraph: [
      [
        /s$/,
        {
          token: "typeKeyword",
          nextEmbedded: "json",
        },
      ],
      ["end", { token: "typeKeyword", next: "@pop", nextEmbedded: "@pop" }],
    ],
    info: [
      [
        /[A-Z][\w$]*/i,
        {
          cases: {
            "@infoBlockKeywords": "typeKeyword",
            "@infoKeywords": "keyword",
          },
        },
      ],
    ],
    pie: [
      configDirectiveHandler,
      [/(title|accDescription)(.*$)/, ["keyword", "string"]],
      [
        /[A-Z][\w$]*/i,
        {
          cases: {
            "@pieBlockKeywords": "typeKeyword",
            "@pieKeywords": "keyword",
          },
        },
      ],
      [/".*?"/, "string"],
      [/\s*\d+/, "number"],
      [/:/, "delimiter.bracket"],
      [/%%[^$]([^%]*(?!%%$)%?)*$/, "comment"],
    ],
    flowchart: [
      configDirectiveHandler,
      [/[ox]?(-{2,}|={2,})[ox]/, "transition"],
      [
        /[A-Z][\w$]*/i,
        {
          cases: {
            "@flowchartBlockKeywords": "typeKeyword",
            "@flowchartKeywords": "keyword",
            "@default": "variable",
          },
        },
      ],
      [/\|+.+?\|+/, "string"],
      [/\[+(\\.+?[/\\]|\/.+?[/\\])\]+/, "string"],
      [/[>[]+(?:[^>[\]|][^[\]|]*|>)\]+/, "string"],
      [/\{.+?\}+/, "string"],
      [/\(.+?\)+/, "string"],
      [/-\.+->?/, "transition"],
      [/(-[.-])([^>-][^-]+?)(-{3,}|-{2,}>|\.-+>)/, ["transition", "string", "transition"]],
      [/(={2,})([^=]+)(={3,}|={2,}>)/, ["transition", "string", "transition"]],
      [/<?(-{2,}|={2,})>|={3,}|-{3,}/, "transition"],
      [/:::/, "transition"],
      [/[&;]/, "delimiter.bracket"],
      [/".*?"/, "string"],
      [/%%[^$]([^%]*(?!%%$)%?)*$/, "comment"],
    ],
    sequenceDiagram: [
      configDirectiveHandler,
      [/(title:?|accDescription)([^\n\r;]*$)/, ["keyword", "string"]],
      [/(autonumber)([^\S\n\r]+off[^\S\n\r]*$)/, ["keyword", "keyword"]],
      [/(autonumber)((?:[^\S\n\r]+\d+){2}[^\S\n\r]*$)/, ["keyword", "number"]],
      [/(autonumber)([^\S\n\r]+\d+[^\S\n\r]*$)/, ["keyword", "number"]],
      [
        /(link\s+)(.*?)(:)(\s*(?:\S.*?)??)(\s*@)(\s*[^\n\r;]+)/,
        ["keyword", "variable", "delimiter.bracket", "string", "delimiter.bracket", "string"],
      ],
      [
        /((?:links|properties)\s+)([^\n\r:]*)(:\s+)/,
        [
          { token: "keyword" },
          { token: "variable" },
          {
            token: "delimiter.bracket",
            nextEmbedded: "javascript",
            next: "@sequenceDiagramLinksProps",
          },
        ],
      ],
      [
        /[A-Z][\w$]*/i,
        {
          cases: {
            "@sequenceDiagramBlockKeywords": "typeKeyword",
            "@sequenceDiagramKeywords": "keyword",
            "@default": "variable",
          },
        },
      ],
      [/(--?>?>|--?[)x])[+-]?/, "transition"],
      [/(:)([^\n:]*$)/, ["delimiter.bracket", "string"]],
      [/%%[^$]([^%]*(?!%%$)%?)*$/, "comment"],
    ],
    sequenceDiagramLinksProps: [
      // [/^:/, { token: 'delimiter.bracket', nextEmbedded: 'json' }],
      [/$|;/, { nextEmbedded: "@pop", next: "@pop", token: "delimiter.bracket" }],
    ],
    classDiagram: [
      configDirectiveHandler,
      [/(^\s*(?:title|accDescription))(\s+(?:\S.*)?$)/, ["keyword", "string"]],
      [
        /(\*|<\|?|o|)(--|\.\.)(\*|\|?>|o|)([\t ]*[A-Za-z]+[\t ]*)(:)(.*$)/,
        ["transition", "transition", "transition", "variable", "delimiter.bracket", "string"],
      ],
      [/(?!class\s)([A-Za-z]+)(\s+[A-Za-z]+)/, ["type", "variable"]],
      [/(\*|<\|?|o)?(--|\.\.)(\*|\|?>|o)?/, "transition"],
      [/^\s*class\s(?!.*\{)/, "keyword"],
      [
        /[A-Z][\w$]*/i,
        {
          cases: {
            "@classDiagramBlockKeywords": "typeKeyword",
            "@classDiagramKeywords": "keyword",
            "@default": "variable",
          },
        },
      ],
      [/%%[^$]([^%]*(?!%%$)%?)*$/, "comment"],
      [/(<<)(.+?)(>>)/, ["delimiter.bracket", "annotation", "delimiter.bracket"]],
      [/".*?"/, "string"],
      [/:::/, "transition"],
      [/[:+\-#~(){}]|\*\s*$|\$\s*$/, "delimiter.bracket"],
    ],
    journey: [
      configDirectiveHandler,
      [/(title)(.*)/, ["keyword", "string"]],
      [/(section)(.*)/, ["typeKeyword", "string"]],
      [
        /[A-Z][\w$]*/i,
        {
          cases: {
            "@journeyBlockKeywords": "typeKeyword",
            "@journeyKeywords": "keyword",
            "@default": "variable",
          },
        },
      ],
      [
        /(^\s*(?:\S.*?|[\t\v\f \xA0\u1680\u2000-\u200A\u202F\u205F\u3000\uFEFF]))(:)(.*?)(:)(.*?)([$,])/,
        [
          "string",
          "delimiter.bracket",
          "number",
          "delimiter.bracket",
          "variable",
          "delimiter.bracket",
        ],
      ],
      [/,/, "delimiter.bracket"],
      [/(^\s*(?:\S.*?|[\t\v\f \xA0\u1680\u2000-\u200A\u202F\u205F\u3000\uFEFF]))(:)([^:]*)$/, ["string", "delimiter.bracket", "variable"]],
      [/%%[^$]([^%]*(?!%%$)%?)*$/, "comment"],
    ],
    gantt: [
      configDirectiveHandler,
      [/(title)(.*)/, ["keyword", "string"]],
      [/(section)(.*)/, ["typeKeyword", "string"]],
      [/^\s*([^\n:]*)(:)/, ["string", "delimiter.bracket"]],
      [
        /[A-Z][\w$]*/i,
        {
          cases: {
            "@ganttBlockKeywords": "typeKeyword",
            "@ganttKeywords": "keyword",
          },
        },
      ],
      [/%%[^$]([^%]*(?!%%$)%?)*$/, "comment"],
      [/:/, "delimiter.bracket"],
    ],
    stateDiagram: [
      configDirectiveHandler,
      [/note[^:]*$/, { token: "typeKeyword", next: "stateDiagramNote" }],
      ["hide empty description", "keyword"],
      [/^\s*state\s(?!.*\{)/, "keyword"],
      [/(<<)(fork|join|choice)(>>)/, "annotation"],
      [/(\[\[)(fork|join|choice)(\]\])/, ["delimiter.bracket", "annotation", "delimiter.bracket"]],
      [
        /[A-Z][\w$]*/i,
        {
          cases: {
            "@stateDiagramBlockKeywords": "typeKeyword",
            "@stateDiagramKeywords": "keyword",
            "@default": "variable",
          },
        },
      ],
      [/".*?"/, "string"],
      [/(:)([^\n:]*$)/, ["delimiter.bracket", "string"]],
      [/\{|\}/, "delimiter.bracket"],
      [/%%[^$]([^%]*(?!%%$)%?)*$/, "comment"],
      [/-->/, "transition"],
      [/\[.*?\]/, "string"],
    ],
    stateDiagramNote: [
      [/^\s*end note$/, { token: "typeKeyword", next: "@pop" }],
      [/.*/, "string"],
    ],
    erDiagram: [
      configDirectiveHandler,
      [/(title|accDescription)(.*$)/, ["keyword", "string"]],
      [/[|}][o|](--|\.\.)[o|][{|]/, "transition"],
      [/".*?"/, "string"],
      [/(:)(.*$)/, ["delimiter.bracket", "string"]],
      [/[:{}]/, "delimiter.bracket"],
      [/([A-Z]+)(\s+[A-Z]+)/i, ["type", "variable"]],
      [/%%[^$]([^%]*(?!%%$)%?)*$/, "comment"],
      [/[A-Z_-][\w$]*/i, "variable"],
    ],
    requirementDiagram: [
      configDirectiveHandler,
      [/->|<-|-/, "transition"],
      [/(\d+\.)*\d+/, "number"],
      [
        /[A-Z_-][\w$]*/i,
        {
          cases: {
            "@requirementDiagramBlockKeywords": "typeKeyword",
            "@default": "variable",
          },
        },
      ],
      [/[/:{}]/, "delimiter.bracket"],
      [/%%[^$]([^%]*(?!%%$)%?)*$/, "comment"],
      [/".*?"/, "string"],
    ],
    c4Diagram: [
      configDirectiveHandler,
      [/(title|accDescription)(.*$)/, ["keyword", "string"]],
      [/\(/, { token: "delimiter.bracket", next: "c4DiagramParenthesis" }],
      [
        /[A-Z_-][\w$]*/i,
        {
          cases: {
            "@c4DiagramBlockKeywords": "typeKeyword",
            "@c4DiagramKeywords": "keyword",
            "@default": "variable",
          },
        },
      ],
      [/%%[^$]([^%]*(?!%%$)%?)*$/, "comment"],
    ],
    c4DiagramParenthesis: [
      [/,/, "delimiter.bracket"],
      [/\)/, { next: "@pop", token: "delimiter.bracket" }],
      [/[^),]/, "string"],
    ],
    sankey: [
      configDirectiveHandler,
      [/(title)(.*)/, ["keyword", "string"]],
      [/(accTitle|accDescr)(\s*:)(\s*(?:\S[^\n\r]*|[\t\v\f \xA0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000\uFEFF])$)/, ["keyword", "delimiter.bracket", "string"]],
      [/".*?"/, "string"],
      [/[A-Z]+/i, "string"],
      [/\s*\d+/, "number"],
      [/,/, "delimiter.bracket"],
      [/%%[^$]([^%]*(?!%%$)%?)*$/, "comment"],
    ],
  },
}

export const conf: languages.LanguageConfiguration = {
  autoClosingPairs: [
    {
      open: "(",
      close: ")",
    },
    {
      open: "{",
      close: "}",
    },
    {
      open: "[",
      close: "]",
    },
  ],
  brackets: [
    ["(", ")"],
    ["{", "}"],
    ["[", "]"],
  ],
  comments: {
    lineComment: "%%",
  },
}
