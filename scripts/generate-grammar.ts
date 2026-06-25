import fs from "node:fs"
import path from "node:path"
import { aimdLang } from "../packages/shared/src/constants/aimd/aimdSyntax"
import { AimdToken } from "../packages/shared/src/constants/aimd/tokens"

const grammarPath = path.resolve(process.cwd(), "test/grammar")

const keywords = [
  "var",
  "var_table",
  "step",
  "check",
  "ref_step",
  "ref_var",
]
const keywordMap = {
  var: AimdToken.KEYWORD_VARIABLE_AIMD,
  var_table: AimdToken.KEYWORD_VARIABLE_TABLE_AIMD,
  step: AimdToken.KEYWORD_STEP_AIMD,
  check: AimdToken.KEYWORD_CHECKPOINT_AIMD,
  ref_step: AimdToken.KEYWORD_REFERENCE_STEP_AIMD,
  ref_var: AimdToken.KEYWORD_REFERENCE_VARIABLE_AIMD,
}

function generateTestBlock(keyword) {
  const paramName = `${keyword}_1`.replace(/_/g, "_")
  const paramName2 = `${keyword}_2`.replace(/_/g, "_")
  const description = keyword.replace(/_/g, " ")

  const keywordToken = keywordMap[keyword]

  // For var and var_table, use VARIABLE_OTHER_AIMD (new type syntax patterns)
  // For other keywords, use VARIABLE_PARAMETER_AIMD (legacy patterns)
  const paramToken = (keyword === "var" || keyword === "var_table")
    ? AimdToken.VARIABLE_OTHER_AIMD
    : AimdToken.VARIABLE_PARAMETER_AIMD

  return `// SYNTAX TEST "source.aimd" "aimd ${description}"
{{${keyword}|${paramName}}}
//<- ${AimdToken.PUNCTUATION_DEFINITION_BEGIN_AIMD}
//${"^".repeat(keyword.length)} ${keywordToken}
//${" ".repeat(keyword.length)}^ ${AimdToken.DELIMITER_PIPE_AIMD}
// ${" ".repeat(keyword.length)}${"^".repeat(paramName.length)} ${paramToken}
// ${" ".repeat(keyword.length + paramName2.length)}^^ ${AimdToken.PUNCTUATION_DEFINITION_END_AIMD}

{{  ${keyword}  |  ${paramName2}  }}
//<- ${AimdToken.PUNCTUATION_DEFINITION_BEGIN_AIMD}
//  ${"^".repeat(keyword.length)} ${keywordToken}
//    ${" ".repeat(keyword.length)}^ ${AimdToken.DELIMITER_PIPE_AIMD}
//     ${" ".repeat(keyword.length)}  ${"^".repeat(paramName2.length)} ${paramToken}
//     ${" ".repeat(keyword.length + paramName2.length)}    ^^ ${AimdToken.PUNCTUATION_DEFINITION_END_AIMD}`
}

/**
 * Generate test blocks for new type syntax
 * Syntax: {{var|<id>: <type> = <default>, **kwargs}}
 */
function generateTypeSyntaxTests() {
  return `
// SYNTAX TEST "source.aimd" "aimd var with type syntax"

// Simple type annotation
{{var|name: str}}
//<- ${AimdToken.PUNCTUATION_DEFINITION_BEGIN_AIMD}
//^^^ ${AimdToken.KEYWORD_VARIABLE_AIMD}
//   ^ ${AimdToken.DELIMITER_PIPE_AIMD}
//    ^^^^ ${AimdToken.VARIABLE_OTHER_AIMD}
//        ^ ${AimdToken.DELIMITER_COLON_AIMD}
//          ^^^ ${AimdToken.SUPPORT_TYPE_AIMD}
//             ^^ ${AimdToken.PUNCTUATION_DEFINITION_END_AIMD}

// Type with default value
{{var|age: int = 18}}
//<- ${AimdToken.PUNCTUATION_DEFINITION_BEGIN_AIMD}
//^^^ ${AimdToken.KEYWORD_VARIABLE_AIMD}
//   ^ ${AimdToken.DELIMITER_PIPE_AIMD}
//    ^^^ ${AimdToken.VARIABLE_OTHER_AIMD}
//       ^ ${AimdToken.DELIMITER_COLON_AIMD}
//         ^^^ ${AimdToken.SUPPORT_TYPE_AIMD}
//             ^ ${AimdToken.DELIMITER_PARAMETER_AIMD}
//               ^^ ${AimdToken.CONSTANT_NUMERIC_AIMD}
//                 ^^ ${AimdToken.PUNCTUATION_DEFINITION_END_AIMD}

// Type with string default and kwargs
{{var|name: str = "张三", title = "姓名", max_length = 50}}
//<- ${AimdToken.PUNCTUATION_DEFINITION_BEGIN_AIMD}
//^^^ ${AimdToken.KEYWORD_VARIABLE_AIMD}
//   ^ ${AimdToken.DELIMITER_PIPE_AIMD}
//    ^^^^ ${AimdToken.VARIABLE_OTHER_AIMD}
//        ^ ${AimdToken.DELIMITER_COLON_AIMD}
//          ^^^ ${AimdToken.SUPPORT_TYPE_AIMD}
//              ^ ${AimdToken.DELIMITER_PARAMETER_AIMD}
//                ^^^^ ${AimdToken.STRING_QUOTED_AIMD}
//                    ^ ${AimdToken.DELIMITER_PARAMETER_AIMD}
//                      ^^^^^ ${AimdToken.VARIABLE_OTHER_AIMD}
//                            ^ ${AimdToken.DELIMITER_PARAMETER_AIMD}
//                              ^^^^ ${AimdToken.STRING_QUOTED_AIMD}

// Boolean type with boolean default
{{var|active: bool = true}}
//<- ${AimdToken.PUNCTUATION_DEFINITION_BEGIN_AIMD}
//^^^ ${AimdToken.KEYWORD_VARIABLE_AIMD}
//   ^ ${AimdToken.DELIMITER_PIPE_AIMD}
//    ^^^^^^ ${AimdToken.VARIABLE_OTHER_AIMD}
//          ^ ${AimdToken.DELIMITER_COLON_AIMD}
//            ^^^^ ${AimdToken.SUPPORT_TYPE_AIMD}
//                 ^ ${AimdToken.DELIMITER_PARAMETER_AIMD}
//                   ^^^^ ${AimdToken.CONSTANT_LANGUAGE_AIMD}
//                       ^^ ${AimdToken.PUNCTUATION_DEFINITION_END_AIMD}

// List type with subvars
{{var|students: list[Student], subvars=[name: str, age: int]}}
//<- ${AimdToken.PUNCTUATION_DEFINITION_BEGIN_AIMD}
//^^^ ${AimdToken.KEYWORD_VARIABLE_AIMD}
//   ^ ${AimdToken.DELIMITER_PIPE_AIMD}
//    ^^^^^^^^ ${AimdToken.VARIABLE_OTHER_AIMD}
//            ^ ${AimdToken.DELIMITER_COLON_AIMD}
//              ^^^^^^^^^^^^^ ${AimdToken.SUPPORT_TYPE_AIMD}
//                           ^ ${AimdToken.DELIMITER_PARAMETER_AIMD}
//                             ^^^^^^^ ${AimdToken.KEYWORD_OTHER_SUBVARS_AIMD}
//                                    ^ ${AimdToken.DELIMITER_PARAMETER_AIMD}
//                                     ^ ${AimdToken.DELIMITER_BRACKET_AIMD}
//                                      ^^^^ ${AimdToken.VARIABLE_OTHER_AIMD}
//                                          ^ ${AimdToken.DELIMITER_COLON_AIMD}
//                                            ^^^ ${AimdToken.SUPPORT_TYPE_AIMD}

// SYNTAX TEST "source.aimd" "aimd var_table with type syntax"

// var_table with nested var() subvars
{{var_table|items: list[Item], subvars=[var(id: str), var(count: int = 0)]}}
//<- ${AimdToken.PUNCTUATION_DEFINITION_BEGIN_AIMD}
//^^^^^^^^^ ${AimdToken.KEYWORD_VARIABLE_TABLE_AIMD}
//         ^ ${AimdToken.DELIMITER_PIPE_AIMD}
//          ^^^^^ ${AimdToken.VARIABLE_OTHER_AIMD}
//               ^ ${AimdToken.DELIMITER_COLON_AIMD}
//                 ^^^^^^^^^^ ${AimdToken.SUPPORT_TYPE_AIMD}
//                           ^ ${AimdToken.DELIMITER_PARAMETER_AIMD}
//                             ^^^^^^^ ${AimdToken.KEYWORD_OTHER_SUBVARS_AIMD}
//                                    ^ ${AimdToken.DELIMITER_PARAMETER_AIMD}
//                                     ^ ${AimdToken.DELIMITER_BRACKET_AIMD}
//                                      ^^^ ${AimdToken.KEYWORD_VARIABLE_AIMD}`
}

if (!fs.existsSync(grammarPath)) {
  fs.mkdirSync(grammarPath, { recursive: true })
}

fs.writeFileSync(
  path.resolve(grammarPath, "aimd.tmLanguage.json"),
  JSON.stringify(aimdLang, null, 2),
)

// Combine basic keyword tests with type syntax tests
const testFileContent = `${keywords.map(generateTestBlock).join("\n\n")}\n${generateTypeSyntaxTests()}`

fs.writeFileSync(
  path.resolve(grammarPath, "aimd.test.aimd"),
  testFileContent,
)
