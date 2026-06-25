/**
 * AIMD Variable Type Syntax Parser
 *
 * Parses the new AIMD type syntax sugar:
 * {{var|<var_id>: <var_type> = <default_value>, **kwargs}}
 *
 * Examples:
 * - {{var|name: str}}
 * - {{var|age: int = 18}}
 * - {{var|name: str = "张三", title = "姓名", max_length = 50}}
 * - {{var|students: list[Student], subvars=[name: str, age: int]}}
 */

export interface VarFieldDefinition {
  /** Variable ID/name */
  id: string
  /** Variable type (e.g., str, int, bool, list[Student]) */
  type?: string
  /** Default value */
  default?: string | number | boolean | null
  /** Additional kwargs */
  kwargs: Record<string, string | number | boolean | null>
  /** Sub variables for nested types */
  subvars?: VarFieldDefinition[]
}

/**
 * Token types for the parser
 */
enum TokenType {
  IDENTIFIER = "IDENTIFIER",
  COLON = "COLON",
  EQUALS = "EQUALS",
  COMMA = "COMMA",
  STRING = "STRING",
  NUMBER = "NUMBER",
  BOOLEAN = "BOOLEAN",
  LBRACKET = "LBRACKET",
  RBRACKET = "RBRACKET",
  LPAREN = "LPAREN",
  RPAREN = "RPAREN",
  VAR = "VAR",
  EOF = "EOF",
}

interface Token {
  type: TokenType
  value: string
  raw?: string
}

/**
 * Tokenizer for AIMD type syntax
 */
class Tokenizer {
  private pos = 0
  private input: string

  constructor(input: string) {
    this.input = input.trim()
  }

  private skipWhitespace(): void {
    while (this.pos < this.input.length && /\s/.test(this.input[this.pos])) {
      this.pos++
    }
  }

  private readString(quote: string): Token {
    const start = this.pos
    this.pos++ // skip opening quote
    let value = ""

    while (this.pos < this.input.length && this.input[this.pos] !== quote) {
      if (this.input[this.pos] === "\\" && this.pos + 1 < this.input.length) {
        // Handle escape sequences
        this.pos++
        const escaped = this.input[this.pos]
        switch (escaped) {
          case "n":
            value += "\n"
            break
          case "t":
            value += "\t"
            break
          case "r":
            value += "\r"
            break
          case "\\":
            value += "\\"
            break
          case "\"":
            value += "\""
            break
          case "'":
            value += "'"
            break
          default:
            value += escaped
        }
      }
      else {
        value += this.input[this.pos]
      }
      this.pos++
    }

    if (this.pos < this.input.length) {
      this.pos++ // skip closing quote
    }

    return { type: TokenType.STRING, value, raw: this.input.slice(start, this.pos) }
  }

  private readNumber(): Token {
    const start = this.pos
    let hasDecimal = false

    if (this.input[this.pos] === "-" || this.input[this.pos] === "+") {
      this.pos++
    }

    while (this.pos < this.input.length) {
      const char = this.input[this.pos]
      if (/\d/.test(char)) {
        this.pos++
      }
      else if (char === "." && !hasDecimal) {
        hasDecimal = true
        this.pos++
      }
      else {
        break
      }
    }

    const value = this.input.slice(start, this.pos)
    return { type: TokenType.NUMBER, value }
  }

  private readIdentifier(): Token {
    const start = this.pos

    // Allow type syntax like list[Student], Optional[str], etc.
    let bracketDepth = 0
    while (this.pos < this.input.length) {
      const char = this.input[this.pos]
      if (char === "[") {
        bracketDepth++
        this.pos++
      }
      else if (char === "]") {
        if (bracketDepth > 0) {
          bracketDepth--
          this.pos++
        }
        else {
          break
        }
      }
      else if (bracketDepth > 0) {
        // Inside brackets, allow more characters
        this.pos++
      }
      else if (/\w/.test(char)) {
        this.pos++
      }
      else {
        break
      }
    }

    const value = this.input.slice(start, this.pos)

    // Check for special keywords
    if (value === "true" || value === "True") {
      return { type: TokenType.BOOLEAN, value: "true" }
    }
    if (value === "false" || value === "False") {
      return { type: TokenType.BOOLEAN, value: "false" }
    }
    if (value === "null" || value === "None") {
      return { type: TokenType.BOOLEAN, value: "null" }
    }
    if (value === "var") {
      return { type: TokenType.VAR, value }
    }

    return { type: TokenType.IDENTIFIER, value }
  }

  nextToken(): Token {
    this.skipWhitespace()

    if (this.pos >= this.input.length) {
      return { type: TokenType.EOF, value: "" }
    }

    const char = this.input[this.pos]

    // Single character tokens
    switch (char) {
      case ":":
        this.pos++
        return { type: TokenType.COLON, value: ":" }
      case "=":
        this.pos++
        return { type: TokenType.EQUALS, value: "=" }
      case ",":
        this.pos++
        return { type: TokenType.COMMA, value: "," }
      case "[":
        this.pos++
        return { type: TokenType.LBRACKET, value: "[" }
      case "]":
        this.pos++
        return { type: TokenType.RBRACKET, value: "]" }
      case "(":
        this.pos++
        return { type: TokenType.LPAREN, value: "(" }
      case ")":
        this.pos++
        return { type: TokenType.RPAREN, value: ")" }
      case "\"":
      case "'":
        return this.readString(char)
    }

    // Numbers (including negative)
    if (/\d/.test(char) || ((char === "-" || char === "+") && /\d/.test(this.input[this.pos + 1] || ""))) {
      return this.readNumber()
    }

    // Identifiers and keywords
    if (/\w/.test(char)) {
      return this.readIdentifier()
    }

    // Unknown character, skip it
    this.pos++
    return this.nextToken()
  }

  peek(): Token {
    const savedPos = this.pos
    const token = this.nextToken()
    this.pos = savedPos
    return token
  }
}

/**
 * Parser for AIMD type syntax
 */
class VarTypeParser {
  private tokenizer: Tokenizer
  private currentToken: Token

  constructor(input: string) {
    this.tokenizer = new Tokenizer(input)
    this.currentToken = this.tokenizer.nextToken()
  }

  private advance(): Token {
    const token = this.currentToken
    this.currentToken = this.tokenizer.nextToken()
    return token
  }

  private expect(type: TokenType): Token {
    if (this.currentToken.type !== type) {
      throw new Error(`Expected ${type}, got ${this.currentToken.type} (${this.currentToken.value})`)
    }
    return this.advance()
  }

  private isEndOfContent(): boolean {
    return this.currentToken.type === TokenType.EOF || this.currentToken.type === TokenType.RPAREN
  }

  private parseValue(): string | number | boolean | null {
    const token = this.currentToken

    switch (token.type) {
      case TokenType.STRING:
        this.advance()
        return token.value
      case TokenType.NUMBER:
        this.advance()
        return token.value.includes(".") ? Number.parseFloat(token.value) : Number.parseInt(token.value, 10)
      case TokenType.BOOLEAN:
        this.advance()
        if (token.value === "null")
          return null
        return token.value === "true"
      case TokenType.IDENTIFIER:
        // For unquoted values, treat as string
        this.advance()
        return token.value
      default:
        throw new Error(`Unexpected token for value: ${token.type}`)
    }
  }

  private parseSubvar(): VarFieldDefinition {
    // subvar can be:
    // 1. Simple: name
    // 2. With type: name: str
    // 3. With default: name: str = "张三"
    // 4. Full: var(name: str = "张三", title = "姓名")

    if (this.currentToken.type === TokenType.VAR) {
      // var(...) syntax
      this.advance() // consume 'var'
      this.expect(TokenType.LPAREN)
      const def = this.parseVarDefinition()
      this.expect(TokenType.RPAREN)
      return def
    }

    // Simple syntax: name or name: type or name: type = default
    const id = this.expect(TokenType.IDENTIFIER).value
    const def: VarFieldDefinition = { id, kwargs: {} }

    if (this.currentToken.type === TokenType.COLON) {
      this.advance()
      def.type = this.expect(TokenType.IDENTIFIER).value
    }

    if (this.currentToken.type === TokenType.EQUALS) {
      this.advance()
      def.default = this.parseValue()
    }

    return def
  }

  private parseSubvars(): VarFieldDefinition[] {
    const subvars: VarFieldDefinition[] = []

    this.expect(TokenType.LBRACKET)

    while (this.currentToken.type !== TokenType.RBRACKET && this.currentToken.type !== TokenType.EOF) {
      subvars.push(this.parseSubvar())

      if (this.currentToken.type === TokenType.COMMA) {
        this.advance()
      }
    }

    this.expect(TokenType.RBRACKET)

    return subvars
  }

  private parseVarDefinition(): VarFieldDefinition {
    // Parse: <id>: <type> = <default>, key1 = val1, key2 = val2, subvars=[...]
    const id = this.expect(TokenType.IDENTIFIER).value
    const def: VarFieldDefinition = { id, kwargs: {} }

    // Optional type annotation
    if (this.currentToken.type === TokenType.COLON) {
      this.advance()
      def.type = this.expect(TokenType.IDENTIFIER).value
    }

    // Optional default value
    if (this.currentToken.type === TokenType.EQUALS) {
      this.advance()
      def.default = this.parseValue()
    }

    // Parse remaining kwargs
    while (this.currentToken.type === TokenType.COMMA) {
      this.advance() // consume comma

      // Check for end tokens after advance
      if (this.isEndOfContent()) {
        break
      }

      const key = this.expect(TokenType.IDENTIFIER).value

      if (key === "subvars") {
        this.expect(TokenType.EQUALS)
        def.subvars = this.parseSubvars()
      }
      else {
        this.expect(TokenType.EQUALS)
        const value = this.parseValue()
        def.kwargs[key] = value
      }
    }

    return def
  }

  parse(): VarFieldDefinition {
    return this.parseVarDefinition()
  }
}

/**
 * Parse AIMD variable type syntax
 *
 * @param input - The content inside {{var|...}}
 * @returns Parsed variable definition
 *
 * @example
 * parseVarTypeDefinition("name: str")
 * // => { id: "name", type: "str", kwargs: {} }
 *
 * @example
 * parseVarTypeDefinition("age: int = 18, title = \"年龄\"")
 * // => { id: "age", type: "int", default: 18, kwargs: { title: "年龄" } }
 */
export function parseVarTypeDefinition(input: string): VarFieldDefinition {
  const parser = new VarTypeParser(input.trim())
  return parser.parse()
}

/**
 * Check if the input contains new type syntax (has colon for type annotation)
 */
export function hasTypeSyntax(input: string): boolean {
  // Simple check: has colon that's not inside quotes
  const trimmed = input.trim()
  let inQuotes = false
  let quoteChar = ""

  for (let i = 0; i < trimmed.length; i++) {
    const char = trimmed[i]

    if (!inQuotes && (char === "\"" || char === "'")) {
      inQuotes = true
      quoteChar = char
    }
    else if (inQuotes && char === quoteChar && trimmed[i - 1] !== "\\") {
      inQuotes = false
    }
    else if (!inQuotes && char === ":") {
      return true
    }
  }

  return false
}

/**
 * Convert VarFieldDefinition to JSON Schema compatible format
 */
export function varDefToJsonSchema(def: VarFieldDefinition): Record<string, any> {
  const schema: Record<string, any> = {}

  // Map AIMD types to JSON Schema types
  const typeMapping: Record<string, string> = {
    str: "string",
    string: "string",
    int: "integer",
    integer: "integer",
    float: "number",
    number: "number",
    bool: "boolean",
    boolean: "boolean",
  }

  if (def.type) {
    // Handle list types like list[Student]
    const listMatch = def.type.match(/^list\[(\w+)\]$/i)
    if (listMatch) {
      schema.type = "array"
      schema.items = { type: "object", title: listMatch[1] }
    }
    else {
      schema.type = typeMapping[def.type.toLowerCase()] || def.type
    }
  }

  if (def.default !== undefined) {
    schema.default = def.default
  }

  // Map kwargs to schema properties
  const kwargMapping: Record<string, string> = {
    title: "title",
    description: "description",
    max_length: "maxLength",
    min_length: "minLength",
    maximum: "maximum",
    minimum: "minimum",
    ge: "minimum",
    le: "maximum",
    gt: "exclusiveMinimum",
    lt: "exclusiveMaximum",
    pattern: "pattern",
    enum: "enum",
  }

  for (const [key, value] of Object.entries(def.kwargs)) {
    const schemaKey = kwargMapping[key] || key
    schema[schemaKey] = value
  }

  // Handle subvars
  if (def.subvars && def.subvars.length > 0) {
    schema.type = "array"
    schema.items = {
      type: "object",
      properties: {},
      required: [],
    }

    for (const subvar of def.subvars) {
      schema.items.properties[subvar.id] = varDefToJsonSchema(subvar)
      // Add to required if no default
      if (subvar.default === undefined) {
        schema.items.required.push(subvar.id)
      }
    }
  }

  return schema
}

/**
 * Extract just the variable name from type syntax
 * Handles both old syntax (just name) and new syntax (name: type = default, ...)
 */
export function extractVarName(input: string): string {
  const trimmed = input.trim()

  // Find the first delimiter (colon, comma, or equals)
  let endIndex = trimmed.length
  for (let i = 0; i < trimmed.length; i++) {
    const char = trimmed[i]
    if (char === ":" || char === "," || char === "=") {
      endIndex = i
      break
    }
  }

  return trimmed.slice(0, endIndex).trim()
}
