import { Badge } from "@/components/ui/badge"

export function MockBadge({ label = "DEMO · MOCK" }: { label?: string }) {
  return (
    <Badge
      className="bg-amber-500 text-black hover:bg-amber-500"
      data-testid="mock-badge"
    >
      {label}
    </Badge>
  )
}
