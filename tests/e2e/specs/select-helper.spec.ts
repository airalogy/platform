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

for (const inputClass of ["n-base-selection-input", "n-base-selection-input-tag__input"]) {
  test(`synthetic selector searches virtualized options through ${inputClass}`, async ({ page }) => {
    await page.setContent(`
      <input class="${inputClass}" oninput="document.querySelector('button').hidden = this.value !== 'Synthetic distant option'">
      <div class="n-base-select-menu">
        <button hidden class="n-base-select-option" onclick="document.body.dataset.picked='searched'">Synthetic distant option</button>
      </div>
    `)
    await page.locator("input").focus()
    await selectVisibleOption(page, "Synthetic distant option")
    await expect(page.locator("input")).toHaveValue("Synthetic distant option")
    await expect(page.locator("body")).toHaveAttribute("data-picked", "searched")
  })
}
