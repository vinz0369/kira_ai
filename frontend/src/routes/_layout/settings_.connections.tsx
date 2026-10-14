import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import { RefreshCw, ShieldCheck, Tv, Unplug } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { liveApi } from "@/lib/liveApi"
import { friendlyLiveError } from "@/lib/liveUi"

export const Route = createFileRoute("/_layout/settings_/connections")({
  component: YouTubeConnections,
})

const callbackMessages: Record<string, string> = {
  access_denied:
    "Google chưa cấp quyền. Hãy chọn tài khoản trong danh sách Test users.",
  token_exchange_failed:
    "Không đổi được mã Google thành token. Kiểm tra OAuth client và redirect URI trên Google Cloud.",
  channel_lookup_failed:
    "Đã nhận token nhưng chưa đọc được kênh YouTube. Kiểm tra YouTube Data API v3 và quyền của tài khoản.",
  youtube_api_disabled:
    "Bật YouTube Data API v3 trong đúng Google Cloud project.",
  quota_exceeded:
    "YouTube API đã hết quota; thử lại sau khi quota được cấp lại.",
  insufficient_scope:
    "Google không cấp quyền youtube.readonly; hãy kết nối lại.",
  connection_store_failed:
    "Không lưu được kết nối trên server; kiểm tra cấu hình backend.",
}

function YouTubeConnections() {
  const queryClient = useQueryClient()
  const connection = useQuery({
    queryKey: ["youtube-connection"],
    queryFn: liveApi.youtubeConnection,
    retry: false,
  })
  const connect = useMutation({
    mutationFn: liveApi.youtubeAuthorize,
    onSuccess: ({ authorization_url }) =>
      window.location.assign(authorization_url),
  })
  const disconnect = useMutation({
    mutationFn: liveApi.youtubeDisconnect,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["youtube-connection"] })
      queryClient.removeQueries({ queryKey: ["youtube-broadcasts"] })
    },
  })
  const callbackParams = new URLSearchParams(window.location.search)
  const callbackStatus = callbackParams.get("youtube")
  const callbackReason = callbackParams.get("reason")
  const data = connection.data

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-3xl font-semibold">Kết nối YouTube</h1>
        <p className="text-muted-foreground">
          Quyền chỉ đọc livestream và chat. Token Google chỉ được lưu mã hóa ở
          backend.
        </p>
      </div>
      {callbackStatus && (
        <p role="status" className="rounded-lg border p-3 text-sm">
          {callbackStatus === "connected"
            ? "Đã kết nối Google với YouTube."
            : callbackReason && callbackMessages[callbackReason]
              ? callbackMessages[callbackReason]
              : "Chưa kết nối được YouTube. Hãy thử lại hoặc kiểm tra cấu hình Google Cloud."}
        </p>
      )}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Tv className="size-5 text-red-600" /> YouTube Live
          </CardTitle>
          <CardDescription>
            Scope duy nhất: youtube.readonly. Ứng dụng không gửi hoặc xóa chat.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {connection.isLoading ? (
            <p>Đang kiểm tra cấu hình…</p>
          ) : connection.isError ? (
            <Alert variant="destructive">
              <AlertTitle>Không kiểm tra được kết nối YouTube</AlertTitle>
              <AlertDescription>
                {friendlyLiveError(connection.error)} Kết nối Google đã lưu
                không bị xóa vì lỗi tải trang này.
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="mt-2"
                  onClick={() => void connection.refetch()}
                >
                  <RefreshCw /> Thử lại
                </Button>
              </AlertDescription>
            </Alert>
          ) : !data?.configured ? (
            <div className="space-y-2">
              <Badge variant="secondary">Chưa cấu hình server</Badge>
              <p className="text-sm text-muted-foreground">
                Thêm GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET và
                DATA_ENCRYPTION_KEY vào môi trường backend.
              </p>
            </div>
          ) : data.connected ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge>Đã kết nối</Badge>
                <strong>{data.channel_name ?? data.channel_id}</strong>
              </div>
              <p className="text-sm text-muted-foreground">
                Token truy cập tự làm mới bằng refresh token được mã hóa.
              </p>
              {data.last_error_code && (
                <Alert variant="destructive">
                  <AlertTitle>YouTube API tạm lỗi</AlertTitle>
                  <AlertDescription>
                    {friendlyLiveError(new Error(data.last_error_code))} Kết nối
                    Google vẫn còn hiệu lực. Mã hỗ trợ: {data.last_error_code}.
                  </AlertDescription>
                </Alert>
              )}
              <div className="flex flex-wrap gap-2">
                <Button asChild>
                  <Link to="/live">Đến phiên live</Link>
                </Button>
                <Button variant="outline" onClick={() => connect.mutate()}>
                  <RefreshCw /> Cấp quyền lại
                </Button>
                <Button
                  variant="destructive"
                  onClick={() => disconnect.mutate()}
                >
                  <Unplug /> Thu hồi và ngắt kết nối
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <Badge
                variant={data?.needs_reconnect ? "destructive" : "secondary"}
              >
                {data?.needs_reconnect ? "Cần kết nối lại" : "Chưa kết nối"}
              </Badge>
              {data?.last_error_code && (
                <p className="text-sm text-destructive">
                  {friendlyLiveError(new Error(data.last_error_code))}
                </p>
              )}
              <Button
                onClick={() => connect.mutate()}
                disabled={connect.isPending}
              >
                <ShieldCheck /> Kết nối Google an toàn
              </Button>
            </div>
          )}
          {(connect.error || disconnect.error) && (
            <p className="text-sm text-destructive">
              {friendlyLiveError(connect.error ?? disconnect.error)}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
