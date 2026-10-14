import { expect, test } from "@playwright/test"

test("self-hosted Silero WASM module imports in Vite", async ({ page }) => {
  await page.goto("/login")
  const assets = await page.evaluate(async () => {
    const module = await import("/vad/ort-wasm-simd-threaded.mjs?import")
    const wasm = await fetch("/vad/ort-wasm-simd-threaded.wasm")
    const model = await fetch("/vad/silero_vad_v5.onnx")
    return {
      factory: typeof module.default,
      wasmStatus: wasm.status,
      wasmType: wasm.headers.get("content-type"),
      modelStatus: model.status,
    }
  })
  expect(assets).toEqual({
    factory: "function",
    wasmStatus: 200,
    wasmType: "application/wasm",
    modelStatus: 200,
  })
})

test("Phase 3 diagnostics labels preflight and never exposes provider secrets", async ({
  page,
}) => {
  const apiBase = process.env.PLAYWRIGHT_API_URL ?? "http://localhost:8000"
  await page.goto("/settings/diagnostics")

  await expect(
    page.getByRole("heading", { name: "Phase 3 Diagnostics" }),
  ).toBeVisible()
  await expect(page.getByText(/Preflight không gọi provider/)).toBeVisible()
  await expect(page.getByText("Pipeline Voice Real")).toBeVisible()
  await expect(page.getByText(/FPT Marketplace/)).toBeVisible()
  await expect(page.getByText(/gTTS miễn credential/)).toBeVisible()
  await expect(page.getByText(/Edge TTS thử nghiệm/)).toBeVisible()
  await expect(page.getByText("Chưa sẵn sàng").first()).toBeVisible()

  const diagnostics = await page.evaluate(async (base) => {
    const response = await fetch(`${base}/api/v1/diagnostics/phase3`, {
      headers: {
        Authorization: `Bearer ${localStorage.getItem("access_token")}`,
      },
    })
    return { status: response.status, text: await response.text() }
  }, apiBase)
  expect(diagnostics.status).toBe(200)
  expect(diagnostics.text).toContain('"measurement_scope":"PREFLIGHT_ONLY"')
  expect(diagnostics.text).not.toContain("API_KEY")
  expect(diagnostics.text).not.toContain("CREDENTIALS")
})
