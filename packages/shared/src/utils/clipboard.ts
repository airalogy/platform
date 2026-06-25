/**
 * Copy text to clipboard with fallback for older browsers
 * @param text - The text to copy to clipboard
 * @returns Promise that resolves with the copied text
 */
export async function copyToClip(text: string): Promise<string> {
  try {
    await navigator.clipboard.writeText(text)
  }
  catch (error) {
    const textArea = document.createElement("textarea")
    textArea.value = text
    textArea.style.position = "fixed"
    textArea.style.opacity = "0"
    document.body.appendChild(textArea)
    textArea.focus()
    textArea.select()
    document.execCommand("copy")
    document.body.removeChild(textArea)
  }

  return text
}
