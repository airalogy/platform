import { expect, test } from "@playwright/test"
import { selectVisibleOption } from "./fixtures"

test("synthetic selector contract ignores same-label options in a closing menu", async ({ page }) => {
  // Keep the departing menu mounted after the current one, as Naive UI does.
  // No API or product state is mocked by this isolated helper regression.
  await page.setContent(`
    <div class="n-base-select-menu">
      <button class="n-base-select-option" onclick="document.body.dataset.picked='current'">Synthetic response</button>
    </div>
    <div class="n-base-select-menu fade-in-scale-up-transition-leave-active">
      <button class="n-base-select-option" onclick="document.body.dataset.picked='departing'">Synthetic response</button>
    </div>
  `)
  await selectVisibleOption(page, "Synthetic response")
  await expect(page.locator("body")).toHaveAttribute("data-picked", "current")
})
