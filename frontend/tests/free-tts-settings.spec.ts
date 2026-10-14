import { expect, test } from "@playwright/test"

test("Character Studio selects credential-free Vietnamese TTS", async ({
  page,
}) => {
  const apiBase = process.env.PLAYWRIGHT_API_URL ?? "http://localhost:8000"
  await page.goto("/studio")
  const character = await page.evaluate(async (base) => {
    const response = await fetch(`${base}/api/v1/characters/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${localStorage.getItem("access_token")}`,
      },
      body: JSON.stringify({
        name: `Kira Free TTS ${Date.now()}`,
        llm_provider: "fake",
        llm_model: "mock-template",
        voice_provider: "fake",
        voice_id: "mock-sine",
      }),
    })
    return response.json()
  }, apiBase)

  await page.goto(`/studio/${character.id}`)
  const llmProvider = page.getByLabel("Nhà cung cấp LLM")
  await expect(llmProvider).toBeVisible()
  await expect(llmProvider.locator('option[value="fpt"]')).toContainText(
    "FPT AI Marketplace",
  )
  await llmProvider.selectOption("fpt")
  await expect(page.getByLabel("Model hội thoại")).toHaveValue(
    "Saola-Small-32B",
  )
  const provider = page.getByLabel("Nhà cung cấp TTS")
  await expect(provider).toBeVisible()
  await expect(provider.locator('option[value="gtts"]')).toContainText(
    "gTTS tiếng Việt",
  )
  await expect(provider.locator('option[value="edge"]')).toContainText(
    "thử nghiệm",
  )

  await provider.selectOption("gtts")
  await expect(page.getByLabel("Giọng tiếng Việt")).toHaveValue("vi")
  await page.getByRole("button", { name: "Lưu thay đổi" }).click()
  await expect(page.getByText("Đã lưu")).toBeVisible()

  const saved = await page.evaluate(
    async ({ id, base }) => {
      const response = await fetch(`${base}/api/v1/characters/${id}`, {
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
      })
      return response.json()
    },
    { id: character.id, base: apiBase },
  )
  expect(saved.voice_provider).toBe("gtts")
  expect(saved.voice_id).toBe("vi")
  expect(saved.llm_provider).toBe("fpt")
  expect(saved.llm_model).toBe("Saola-Small-32B")
})
