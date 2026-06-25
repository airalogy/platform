import type { Component, Ref, VNode } from "vue"
import { cloneDeep } from "lodash-es"
import { onMounted, onUnmounted, ref } from "vue"

/**
 * Type of answer, thinking or answer
 */
export enum AnswerType {
  ANSWER = "answer",
  THINKING = "thinking",
}

// export type Theme = "light" | "dark"
export enum Theme {
  LIGHT = "light",
  DARK = "dark",
}

export enum TimerType {
  SET_TIMEOUT,
  REQUEST_ANIMATION_FRAME,
}

/**
 * Character interface
 */
export interface IChar {
  content: string
  answerType: AnswerType
  tokenId: number
  /** Character index */
  index: number
}

export interface ITokensReference {
  startIndex: number
  raw: string
}

export interface IOnTypedCharData {
  currentIndex: number
  currentChar: string
  answerType: AnswerType
  prevStr: string
}

export interface IStartData extends IOnTypedCharData {}

export interface ITypedChar extends IOnTypedCharData {
  percent: number
  currentStr: string
}

export interface IBeforeTypedChar extends IOnTypedCharData {
  percent: number
}

export interface IMarkdownThemeProps {
  /** Theme */
  theme?: Theme
  /** Math formula configuration */
  math?: IMarkdownMath
  /** Code block configuration */
  codeBlock?: IMarkdownCode
  /** Plugin configuration */
  plugins?: IMarkdownPlugin[]
  /** Answer type */
  answerType?: AnswerType
}

export interface IMarkdownCode {
  /**
   * Whether to display the header operation buttons
   * If true, the header operation buttons are displayed
   * If it is a VNode, the custom header operation buttons are displayed
   */
  headerActions?: boolean | VNode
}

export interface IMarkdownPlugin {
  type: "buildIn" | "custom"
  id?: string
  components?: Record<string, Component>
}

export interface IMarkdownMath {
  /** Whether to use parentheses or $ as a separator, default is $ */
  splitSymbol: "bracket" | "dollar"
  /** Math formula replacement function */
  replaceMathBracket?: (value: string) => string
}

export interface IWholeContent {
  [AnswerType.THINKING]: {
    content: string
    length: number
    prevLength: number
  }
  [AnswerType.ANSWER]: {
    content: string
    length: number
    prevLength: number
  }
  allLength: number
}

export interface MarkdownBaseRef {
  stop: () => void
  resume: () => void
  start: () => void
  restart: () => void
}

/** Ref type for Markdown component */
export type MarkdownRef = MarkdownBaseRef

/** Ref type for MarkdownCMD component */
export interface MarkdownCMDRef extends MarkdownBaseRef {
  push: (content: string, answerType?: AnswerType) => void
  clear: () => void
  triggerWholeEnd: () => void
}

export interface IEndData {
  manual: boolean
  /** Answer string */
  answerStr: string
  /** Thinking string */
  thinkingStr: string
  /** Typed string, same as answerStr */
  str: string
}

interface UseTypingOptions {
  step?: number
  /** Timer type: supports setTimeout and requestAnimationFrame */
  timerType?: TimerType
  /** Typewriter effect interval time */
  interval?: number
  /** Callback after typing is completed */
  onEnd?: (data?: IEndData) => void
  /** Callback when starting to type */
  onStart?: (data?: { currentIndex: number, currentChar: string, answerType: AnswerType, prevStr: string }) => void
  /** Callback before typing a character */
  onBeforeTypedChar?: (data?: IBeforeTypedChar) => Promise<void>
  /**
   * Callback after a character is typed
   * @param char character
   * @param index character index
   */
  onTypedChar?: (data?: ITypedChar) => void
  /** Whether to disable the typewriter effect */
  disableTyping?: boolean
  initContent?: IWholeContent
}

export interface TypingState {
  start: () => void
  stop: () => void
  clear: () => void
  isTyping: Ref<boolean>
  /** Whether the stop method was actively called */
  isManualStop: Ref<boolean>
  wholeContentRef: Ref<IWholeContent>
  resume: () => void
  restart: () => void
  push: (content: string, answerType?: AnswerType) => void
  processCharDisplay: (char: IChar) => void
  triggerWholeEnd: () => void
  resetWholeContent: () => void
  chars: Ref<IChar[]>
  disableTyping: Ref<boolean>
  step: Ref<number>
}

const DEFAULT_WHOLE_CONTENT: Readonly<IWholeContent> = Object.freeze({
  thinking: {
    content: "",
    length: 0,
    prevLength: 0,
  },
  answer: {
    content: "",
    length: 0,
    prevLength: 0,
  },
  allLength: 0,
})

export function useTypewriterEffect(options?: UseTypingOptions): TypingState {
  const {
    timerType = TimerType.SET_TIMEOUT,
    step = 1,
    interval = 10,
    onEnd,
    onStart,
    onBeforeTypedChar,
    onTypedChar,
    disableTyping = false,
    initContent = cloneDeep(DEFAULT_WHOLE_CONTENT),
    // triggerUpdate,
  } = options || {}

  const wholeContentRef = ref<IWholeContent>(initContent)
  const isStartedTypingRef = ref(false)
  const isWholeTypedEndRef = ref(false)
  const charIndexRef = ref(0)
  const stepRef = ref(step)

  /** Input chars */
  const charsRef = ref<IChar[]>([])
  /** Whether it is unmounted */
  const isUnmountRef = ref(false)
  /** Whether it is typing */
  const isTypingRef = ref(false)
  /** Animation frame ID */
  const animationFrameRef = ref<number | null>(null)
  /** Traditional timer (compatibility mode) */
  const timerRef = ref<ReturnType<typeof setTimeout> | null>(null)
  // Record of typed characters
  const typedCharsRef = ref<{ typedContent: string, answerType: AnswerType, prevStr: string } | undefined>(undefined)
  // Whether the stop method was actively called
  const typedIsManualStopRef = ref(false)

  const disableTypingRef = ref(disableTyping)

  const intervalRef = ref(interval)

  const processCharDisplay = (chars: IChar | IChar[]) => {
    const { [AnswerType.ANSWER]: answer, [AnswerType.THINKING]: thinking } = wholeContentRef.value

    if (!isStartedTypingRef.value) {
      isStartedTypingRef.value = true
    }
    if (Array.isArray(chars)) {
      let thinkingContent = ""
      let answerContent = ""
      chars.forEach(({ answerType, content }) => {
        if (answerContent === AnswerType.THINKING) {
          thinkingContent += content
        }
        else if (answerType === AnswerType.ANSWER) {
          answerContent += content
        }
      })

      thinking.content += thinkingContent
      thinking.length += thinkingContent.length
      answer.content += answerContent
      answer.length += answerContent.length
    }
    else {
      if (chars.answerType === AnswerType.THINKING) {
        thinking.content += chars.content
        thinking.length += 1
      }
      else {
        answer.content += chars.content
        answer.length += 1
      }
    }
  }

  /**
   * Trigger the onStart callback
   * @param char current character
   */
  const triggerOnStart = (char: IChar) => {
    if (!onStart) {
      return
    }
    const prevStr = wholeContentRef.value[char.answerType].content
    onStart({
      currentIndex: prevStr.length,
      currentChar: char.content,
      answerType: char.answerType,
      prevStr,
    })
  }

  /**
   * Trigger the onEnd callback
   */
  const triggerOnEnd = (data?: { manual?: boolean }) => {
    if (!onEnd) {
      return
    }

    const { [AnswerType.ANSWER]: answer, [AnswerType.THINKING]: thinking } = wholeContentRef.value

    onEnd({
      str: answer.content,
      answerStr: answer.content,
      thinkingStr: thinking.content,
      manual: data?.manual ?? false,
    })
  }

  /**
   * Trigger the onBeforeTypedChar callback
   * @param char current character
   */
  const triggerOnBeforeTypedChar = async (char: IChar) => {
    if (!onBeforeTypedChar) {
      return
    }

    const { answerType, content, index } = char

    const allLength = wholeContentRef.value.allLength

    // Calculate the percentage of previous characters
    const percent = (char.index / allLength) * 100

    await onBeforeTypedChar({
      currentIndex: index,
      currentChar: content,
      answerType,
      prevStr: wholeContentRef.value[answerType].content,
      percent,
    })
  }

  /** Callback after typing is completed */
  const triggerOnTypedChar = async (char: IChar) => {
    if (!onTypedChar) {
      return
    }
    const { answerType, content, index } = char
    const allLength = wholeContentRef.value.allLength
    const percent = ((char.index + 1) / allLength) * 100

    onTypedChar({
      currentIndex: index,
      currentChar: content,
      answerType,
      prevStr: wholeContentRef.value[answerType].content.slice(0, index),
      currentStr: wholeContentRef.value[answerType].content,
      percent,
    })
  }

  /** Clear the timer */
  function clearTimer() {
    // Clear requestAnimationFrame
    if (animationFrameRef.value) {
      cancelAnimationFrame(animationFrameRef.value)
      animationFrameRef.value = null
    }

    // Clear setTimeout (may be used by timestamp mode)
    if (timerRef.value) {
      clearTimeout(timerRef.value)
      timerRef.value = null
    }

    isTypingRef.value = false
    typedCharsRef.value = undefined
  }

  /** Start the typing task */
  const startTypedTask = () => {
    /** If the stop method is called manually, do not restart typing */
    if (typedIsManualStopRef.value) {
      return
    }

    if (isTypingRef.value) {
      return
    }

    if (timerType === TimerType.REQUEST_ANIMATION_FRAME) {
      startAnimationFrameMode()
    }
    else {
      startTimeoutMode()
    }
  }

  /** Type all remaining characters */
  async function typingRemainAll() {
    const chars = toValue(charsRef)
    const thinkingCharsStr = chars
      .filter(char => char.answerType === AnswerType.THINKING)
      .map(char => char.content)
      .join("")
    const answerCharsStr = chars
      .filter(char => char.answerType === AnswerType.ANSWER)
      .map(char => char.content)
      .join("")

    const { [AnswerType.ANSWER]: answer, [AnswerType.THINKING]: thinking } = wholeContentRef.value

    if (thinkingCharsStr && onBeforeTypedChar) {
      await onBeforeTypedChar({
        currentIndex: thinking.length,
        currentChar: thinkingCharsStr,
        answerType: AnswerType.THINKING,
        prevStr: thinking.content,
        percent: 100,
      })
    }

    if (answerCharsStr && onBeforeTypedChar) {
      await onBeforeTypedChar({
        currentIndex: answer.length,
        currentChar: answerCharsStr,
        answerType: AnswerType.ANSWER,
        prevStr: answer.content,
        percent: 100,
      })
    }

    thinking.content += thinkingCharsStr
    thinking.length += thinkingCharsStr.length
    answer.content += answerCharsStr
    answer.length += answerCharsStr.length

    wholeContentRef.value.allLength += thinkingCharsStr.length + answerCharsStr.length

    charsRef.value = []
    isTypingRef.value = false

    triggerOnEnd()
  }

  /** requestAnimationFrame mode */
  function startAnimationFrameMode() {
    let lastFrameTime = performance.now()

    async function frameLoop(currentTime: number) {
      // If the typewriter effect is disabled, type all characters
      if (disableTypingRef.value) {
        await typingRemainAll()
        return
      }
      const chars = toValue(charsRef)

      if (isUnmountRef.value)
        return

      if (chars.length === 0) {
        stopAnimationFrame()
        return
      }

      const deltaTime = currentTime - lastFrameTime
      const needToTypingCharsLength = Math.min(Math.max(0, Math.floor(deltaTime / intervalRef.value)), chars.length, stepRef.value)

      if (needToTypingCharsLength > 0) {
        // Process characters
        let i = 0
        for (; i < needToTypingCharsLength; i++) {
          const char = chars[i]
          if (char === undefined)
            break

          if (!isTypingRef.value) {
            isTypingRef.value = true
            triggerOnStart(char)
          }
          /** Callback before typing */
          await triggerOnBeforeTypedChar(char)
          processCharDisplay(char)
          /** Callback after typing */
          triggerOnTypedChar(char)
        }

        charsRef.value = chars.slice(i)
        lastFrameTime = performance.now()

        // Continue to the next frame
        if (chars.length > 0) {
          animationFrameRef.value = requestAnimationFrame(frameLoop)
        }
        else {
          isTypingRef.value = false
          triggerOnEnd()
        }
      }
      else {
        // You don't need to type this time, continue to the next frame
        animationFrameRef.value = requestAnimationFrame(frameLoop)
      }
    }

    animationFrameRef.value = requestAnimationFrame(frameLoop)
  }

  /** Stop animation frame mode */
  function stopAnimationFrame(manual = false) {
    isTypingRef.value = false
    if (animationFrameRef.value) {
      cancelAnimationFrame(animationFrameRef.value)
      animationFrameRef.value = null
    }
    if (!manual) {
      triggerOnEnd({ manual })
    }
  }

  /** setTimeout mode */
  function startTimeoutMode() {
    const nextTyped = () => {
      const chars = toValue(charsRef)
      if (chars.length === 0) {
        stopTimeout()
        return
      }
      timerRef.value = setTimeout(startTyped, intervalRef.value)
    }

    async function startTyped(isStartPoint = false) {
      // If the typewriter effect is disabled, type all characters
      if (disableTypingRef.value) {
        typingRemainAll()
        return
      }

      const chars = toValue(charsRef)
      if (isUnmountRef.value)
        return

      isTypingRef.value = true

      const needToTypingCharsLength = Math.min(chars.length, stepRef.value)

      if (needToTypingCharsLength > 0) {
        // Process characters
        let i = 0
        for (; i < needToTypingCharsLength; i++) {
          const char = chars[i]
          if (typeof char === "undefined") {
            stopTimeout()
            break
          }

          if (!isTypingRef.value || isStartPoint) {
            isTypingRef.value = true
            triggerOnStart(char)
          }
          /** Callback before typing */
          await triggerOnBeforeTypedChar(char)
          processCharDisplay(char)
          /** Callback after typing */
          triggerOnTypedChar(char)
        }

        charsRef.value = chars.slice(i)

        // Continue to the next frame
        if (charsRef.value.length > 0) {
          nextTyped()
        }
        else {
          isTypingRef.value = false
          triggerOnEnd()
        }
      }
      else {
        stopTimeout()
      }

      // const char = chars.shift()

      // if (char === undefined) {
      //   stopTimeout()
      //   return
      // }

      // if (isStartPoint) {
      //   triggerOnStart(char)
      // }
      // /** Callback before typing */
      // await triggerOnBeforeTypedChar(char)
      // processCharDisplay(char)
      // /** Callback after typing */
      // triggerOnTypedChar(char)
      // nextTyped()
    }

    startTyped(true)
  }

  /** Stop timeout mode */
  function stopTimeout() {
    isTypingRef.value = false
    if (timerRef.value) {
      clearTimeout(timerRef.value)
      timerRef.value = null
    }
    triggerOnEnd()
  }

  const cancelTask = () => {
    if (timerType === TimerType.REQUEST_ANIMATION_FRAME) {
      stopAnimationFrame()
    }
    else {
      stopTimeout()
    }
  }

  /** Pause temporarily */
  const stopTask = () => {
    typedIsManualStopRef.value = true
    cancelTask()
  }

  /** Stop the typing task */
  const endTask = () => {
    cancelTask()
  }

  function restartTypedTask() {
    endTask()
    const { [AnswerType.ANSWER]: answer, [AnswerType.THINKING]: thinking } = wholeContentRef.value

    // Put the content of wholeContentRef into charsRef
    charsRef.value.unshift(
      ...thinking.content.split("").map((charUnit) => {
        const char: IChar = {
          content: charUnit,
          answerType: AnswerType.THINKING,
          tokenId: 0,
          index: 0,
        }
        return char
      }),
    )
    charsRef.value.unshift(
      ...answer.content.split("").map((charUnit) => {
        const char: IChar = {
          content: charUnit,
          answerType: AnswerType.ANSWER,
          tokenId: 0,
          index: 0,
        }
        return char
      }),
    )
    resetWholeContent()
    startTypedTask()
  }

  function clear() {
    stopTask()

    typedIsManualStopRef.value = false
    charsRef.value = []
    resetWholeContent()
    isWholeTypedEndRef.value = false
    charIndexRef.value = 0
    isStartedTypingRef.value = false

    clearTimer()
  }

  function resume() {
    typedIsManualStopRef.value = false
    startTypedTask()
  }

  const processNoTypingPush = (content: string, answerType: AnswerType) => {
    const { [AnswerType.ANSWER]: answer, [AnswerType.THINKING]: thinking } = wholeContentRef.value
    const target = answerType === AnswerType.ANSWER ? answer : thinking

    target.content += content
    // 记录打字前的长度
    target.prevLength = target.length
    target.length += content.length

    if (onEnd) {
      onEnd({
        str: content,
        answerStr: answer.content,
        thinkingStr: thinking.content,
        manual: false,
      })
    }
  }
  function push(content: string, answerType: AnswerType = AnswerType.ANSWER) {
    if (disableTypingRef.value) {
      processNoTypingPush(content, answerType)
      return
    }
    processHasTypingPush(content, answerType)
  }

  function processHasTypingPush(content: string, answerType: AnswerType) {
    if (content.length === 0) {
      return
    }
    const prevCharIndex = charIndexRef.value
    const newContent = content.split("").map((chatStr, idx) => {
      const index = prevCharIndex + idx + 1
      return {
        content: chatStr,
        answerType,
        tokenId: 0,
        index,
      }
    })

    charIndexRef.value = prevCharIndex + newContent.length

    charsRef.value.push(...newContent)

    wholeContentRef.value.allLength += content.length

    if (!isTypingRef.value) {
      startTypedTask()
    }
  }

  function triggerWholeEnd() {
    isWholeTypedEndRef.value = true
    if (isTypingRef.value) {
      return
    }
    if (onEnd) {
      const { [AnswerType.ANSWER]: answer, [AnswerType.THINKING]: thinking } = wholeContentRef.value

      return onEnd({
        str: answer.content,
        answerStr: answer.content,
        thinkingStr: thinking.content,
        manual: true,
      })
    }
  }

  function resetWholeContent() {
    wholeContentRef.value = cloneDeep(DEFAULT_WHOLE_CONTENT)
  }

  onMounted(() => {
    isUnmountRef.value = false
  })

  onUnmounted(() => {
    isUnmountRef.value = true
    clearTimer()
  })

  return {
    start: startTypedTask,
    restart: restartTypedTask,
    stop: stopTask,
    resume,
    clear,
    isTyping: isTypingRef,
    isManualStop: typedIsManualStopRef,
    wholeContentRef,
    push,
    processCharDisplay,
    triggerWholeEnd,
    resetWholeContent,
    chars: charsRef,
    disableTyping: disableTypingRef,
    step: stepRef,
  }
}
