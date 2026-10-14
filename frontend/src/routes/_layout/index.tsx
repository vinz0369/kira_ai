import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowRight, Bot, Radio, ShieldCheck, Tv } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import useAuth from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [
      {
        title: "Tổng quan - Kira AI Live",
      },
    ],
  }),
})

function Dashboard() {
  const { user: currentUser } = useAuth()

  return (
    <div className="space-y-6" data-testid="dashboard-home">
      <div className="rounded-3xl border bg-gradient-to-br from-primary/10 via-background to-background p-6 md:p-8">
        <Badge variant="outline" className="mb-3">
          KIRA AI LIVE
        </Badge>
        <h1 className="max-w-2xl text-3xl font-semibold tracking-tight md:text-4xl">
          Chào {currentUser?.full_name || currentUser?.email}
        </h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          Quản lý nhân vật AI, kết nối YouTube và phát giọng qua OBS. Bạn có thể
          luyện tập bằng Demo trước, rồi chuyển sang YouTube và giọng AI thật
          khi đã sẵn sàng.
        </p>
        <Button asChild className="mt-5">
          <Link to="/live">
            Mở khu vực live <ArrowRight />
          </Link>
        </Button>
      </div>
      <div>
        <h2 className="text-xl font-semibold">Bắt đầu trong 3 bước</h2>
        <p className="text-sm text-muted-foreground">
          Không cần cấu hình mọi nhà cung cấp cùng lúc. Demo dùng được trước.
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex gap-2">
              <Bot className="text-primary" /> 1. Chuẩn bị nhân vật
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-4 text-sm text-muted-foreground">
              Chọn tính cách, giọng nói và xem trước Kira 3D.
            </p>
            <Button asChild>
              <Link to="/studio">Mở Studio</Link>
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex gap-2">
              <Tv className="text-primary" /> 2. Chọn nguồn live
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-4 text-sm text-muted-foreground">
              Dùng Demo để thử, hoặc kết nối YouTube để đọc chat và Super Chat
              thật. Quyền YouTube chỉ đọc.
            </p>
            <Button asChild variant="outline">
              <Link to="/settings/connections">Kết nối YouTube</Link>
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex gap-2">
              <Radio className="text-primary" /> 3. Tạo phiên & mở OBS
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Tạo phiên, nhấn Start rồi sao chép overlay URL riêng của phiên đó
              vào OBS Browser Source. Phiên mới cần URL mới.
            </p>
            <Button asChild variant="outline">
              <Link to="/live">Quản lý phiên</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
      <div className="flex items-start gap-3 rounded-xl border bg-muted/30 p-4 text-sm text-muted-foreground">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" />
        <p>
          Demo, YouTube thật, giọng mô phỏng và giọng AI thật luôn được gắn nhãn
          riêng. Dashboard không phát tiếng AI; OBS overlay là nơi phát duy
          nhất.
        </p>
      </div>
    </div>
  )
}
