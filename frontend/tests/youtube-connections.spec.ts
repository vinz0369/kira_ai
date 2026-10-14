import { expect, test } from "@playwright/test"

test("YouTube connection UI shows an honest disconnected state", async ({
  page,
}) => {
  await page.goto("/settings/connections")
  await expect(
    page.getByRole("heading", { name: "Kết nối YouTube" }),
  ).toBeVisible()
  // Local E2E may have OAuth client credentials configured, but no channel
  // consent. Both states must remain explicit instead of implying connection.
  await expect(
    page.getByText(/Chưa cấu hình server|Chưa kết nối/),
  ).toBeVisible()
  await expect(
    page.getByText("youtube.readonly", { exact: false }),
  ).toBeVisible()
  await expect(page.getByText("Đã kết nối")).toHaveCount(0)

  await page.goto("/live")
  await expect(page.getByRole("button", { name: "Demo / Mock" })).toBeEnabled()
  await expect(
    page.getByRole("button", { name: "YouTube thật" }),
  ).toBeDisabled()
  await expect(page.getByTestId("mock-badge").first()).toBeVisible()
})

test("OAuth callback shows a safe actionable error reason", async ({
  page,
}) => {
  await page.goto(
    "/settings/connections?youtube=error&reason=channel_lookup_failed",
  )
  await expect(page.getByRole("status")).toContainText(
    "chưa đọc được kênh YouTube",
  )
  await expect(page.getByRole("status")).not.toContainText("OAuth: error")
})

test("YouTube API failure does not label valid Google consent as reconnect", async ({
  page,
}) => {
  await page.route("**/api/v1/youtube/connection", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        configured: true,
        connected: true,
        status: "degraded",
        channel_id: "test-channel",
        channel_name: "Test Channel",
        granted_scopes: ["https://www.googleapis.com/auth/youtube.readonly"],
        expires_at: null,
        needs_reconnect: false,
        last_error_code: "quota_exceeded",
      }),
    })
  })
  await page.goto("/settings/connections")
  await expect(page.getByText("Đã kết nối")).toBeVisible()
  await expect(page.getByRole("alert")).toContainText("quota_exceeded")
  await expect(page.getByText("Cần kết nối lại")).toHaveCount(0)
})

test("connection request failure is not presented as missing server configuration", async ({
  page,
}) => {
  await page.route("**/api/v1/youtube/connection", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: "{}",
    })
  })
  await page.goto("/settings/connections")
  await expect(
    page.getByText("Không kiểm tra được kết nối YouTube"),
  ).toBeVisible()
  await expect(page.getByText("Chưa cấu hình server")).toHaveCount(0)
})

test("session conflict explains how to recover without exposing a raw API error", async ({
  page,
}) => {
  await page.route("**/api/v1/characters/", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: [
          {
            id: "00000000-0000-4000-8000-000000000097",
            name: "Kira",
            persona_description: "Bạn đồng hành",
          },
        ],
        count: 1,
      }),
    })
  })
  await page.route("**/api/v1/sessions/current", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "null",
    })
  })
  await page.route("**/api/v1/sessions/", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Another live session is active" }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "[]",
    })
  })
  await page.goto("/live")
  await page.getByRole("button", { name: "Kira" }).click()
  await page.getByRole("button", { name: "Tạo phiên Demo" }).click()
  await expect(page.getByText(/Mở phiên đó và chọn Stop/)).toBeVisible()
  await expect(page.getByText("Another live session is active")).toHaveCount(0)
})

test("ended YouTube chat offers verified in-place rebind without stopping OBS", async ({
  page,
}) => {
  const sessionId = "00000000-0000-4000-8000-000000000099"
  let bound = false
  const oldSession = {
    id: sessionId,
    character_id: "00000000-0000-4000-8000-000000000098",
    mode: "youtube",
    voice_mode: "mock",
    status: "active",
    ai_muted: true,
    mic_connected: false,
    session_epoch: 1,
    created_at: "2026-10-14T00:00:00Z",
    updated_at: "2026-10-14T00:00:00Z",
    overlay_url: null,
    youtube_broadcast_id: "old-broadcast",
    youtube_live_chat_id: "old-chat",
    youtube_ingest_status: "chat_disabled_or_ended",
    youtube_last_error: "chat_disabled_or_ended",
    real_voice_configured: false,
  }
  await page.route(`**/api/v1/sessions/${sessionId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        bound
          ? {
              ...oldSession,
              youtube_broadcast_id: "abcdefghijk",
              youtube_live_chat_id: "new-chat",
              youtube_ingest_status: "connecting",
              youtube_last_error: null,
            }
          : oldSession,
      ),
    })
  })
  await page.route("**/api/v1/youtube/broadcasts/resolve", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "abcdefghijk",
        title: "New Live",
        live_chat_id: "new-chat",
        actual_start_time: null,
        life_cycle_status: "live",
      }),
    })
  })
  await page.route("**/api/v1/youtube/broadcasts", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "abcdefghijk",
          title: "New Live",
          live_chat_id: "new-chat",
          actual_start_time: null,
          life_cycle_status: "live",
        },
      ]),
    })
  })
  await page.route(
    `**/api/v1/sessions/${sessionId}/youtube/bind`,
    async (route) => {
      bound = true
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...oldSession,
          youtube_broadcast_id: "abcdefghijk",
          youtube_live_chat_id: "new-chat",
          youtube_ingest_status: "connecting",
          youtube_last_error: null,
        }),
      })
    },
  )
  await page.goto(`/live/${sessionId}`)
  await expect(
    page.getByText(/gắn video đang live khác vào chính phiên này/),
  ).toBeVisible()
  await expect(page.getByText(/Không cần Stop hay thay URL OBS/)).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Kết nối ingest lại" }),
  ).toHaveCount(0)
  await page.getByRole("button", { name: "Chọn livestream này" }).click()
  await expect(page.getByText(/Đã xác minh: New Live/)).toBeVisible()
  await page
    .getByRole("button", { name: "Gắn chat của video này vào phiên" })
    .click()
  await expect(
    page.getByRole("link", { name: "Xem trên YouTube" }),
  ).toHaveAttribute("href", "https://www.youtube.com/watch?v=abcdefghijk")
  expect(bound).toBe(true)
})

test("live setup verifies a pasted video when automatic discovery is empty", async ({
  page,
}) => {
  await page.route("**/api/v1/youtube/connection", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        configured: true,
        connected: true,
        status: "connected",
        channel_id: "channel-1",
        channel_name: "Kira Channel",
        granted_scopes: ["https://www.googleapis.com/auth/youtube.readonly"],
        expires_at: null,
        needs_reconnect: false,
        last_error_code: null,
      }),
    })
  })
  await page.route("**/api/v1/youtube/broadcasts", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "[]",
    })
  })
  await page.route("**/api/v1/youtube/broadcasts/resolve", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "abcdefghijk",
        title: "Live được xác minh",
        live_chat_id: "new-chat",
        actual_start_time: null,
        life_cycle_status: "live",
      }),
    })
  })
  await page.goto("/live")
  await page.getByRole("button", { name: "YouTube thật" }).click()
  await expect(page.getByText("Chưa có livestream đang phát")).toBeVisible()
  await page
    .getByRole("textbox", { name: "Liên kết livestream YouTube" })
    .fill("https://youtube.com/live/abcdefghijk")
  await page.getByRole("button", { name: "Kiểm tra link" }).click()
  await expect(page.getByText(/Đã xác minh: Live được xác minh/)).toBeVisible()
})

test("old backend 404 explains why a pasted video cannot be checked", async ({
  page,
}) => {
  await page.route("**/api/v1/youtube/connection", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        configured: true,
        connected: true,
        status: "connected",
        channel_id: "channel-1",
        channel_name: "Kira Channel",
        granted_scopes: ["https://www.googleapis.com/auth/youtube.readonly"],
        expires_at: null,
        needs_reconnect: false,
        last_error_code: null,
      }),
    })
  })
  await page.route("**/api/v1/youtube/broadcasts/resolve", async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Not Found" }),
    })
  })
  await page.route("**/api/v1/youtube/broadcasts", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "[]",
    })
  })
  await page.goto("/live")
  await page.getByRole("button", { name: "YouTube thật" }).click()
  await page
    .getByRole("textbox", { name: "Liên kết livestream YouTube" })
    .fill("https://youtube.com/live/abcdefghijk")
  await page.getByRole("button", { name: "Kiểm tra link" }).click()
  await expect(
    page.getByRole("alert").filter({
      hasText: "Server đang chạy chưa có chức năng này",
    }),
  ).toBeVisible()
  await expect(page.getByText(/Không thể hoàn tất thao tác/)).toHaveCount(0)
})
