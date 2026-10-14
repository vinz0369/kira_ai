import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import { Bot, Plus, Sparkles } from "lucide-react"
import { useState } from "react"

import { MockBadge } from "@/components/Live/MockBadge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { liveApi } from "@/lib/liveApi"

export const Route = createFileRoute("/_layout/studio")({ component: Studio })

const presets = [
  [
    "balanced-friend",
    "Bạn thân lém lỉnh",
    "Ấm áp, cà khịa nhẹ và luôn nhường lời streamer.",
  ],
  [
    "gentle-assistant",
    "Trợ lý tinh tế",
    "Điềm tĩnh, súc tích và chú ý nhịp buổi live.",
  ],
  [
    "friendly-rival",
    "Đối thủ hiếu thắng",
    "Năng lượng cao, trêu vui nhưng không lấn át.",
  ],
] as const

function Studio() {
  const queryClient = useQueryClient()
  const [name, setName] = useState("Kira")
  const [preset, setPreset] =
    useState<(typeof presets)[number][0]>("balanced-friend")
  const characters = useQuery({
    queryKey: ["characters"],
    queryFn: liveApi.listCharacters,
  })
  const create = useMutation({
    mutationFn: () => {
      const selected = presets.find(([id]) => id === preset) ?? presets[0]
      return liveApi.createCharacter({
        name,
        template_id: selected[0],
        persona_description: selected[2],
        address_streamer_as: "bạn",
        viewer_style: "thân thiện",
        humor_level: "balanced",
        proactivity: "balanced",
        llm_provider: "fpt",
        llm_model: "Saola-Small-32B",
        voice_provider: "gtts",
        voice_id: "vi",
        memory_opt_in: false,
      })
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["characters"] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold">Character Studio</h1>
          <p className="text-muted-foreground">
            Tạo nhân vật từ preset rồi chỉnh thành chất riêng của bạn.
          </p>
        </div>
        <MockBadge />
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="size-5" /> Tạo nhân vật
          </CardTitle>
          <CardDescription>
            Ba preset là điểm bắt đầu; mọi mô tả đều có thể sửa sau.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            {presets.map(([id, label, description]) => (
              <button
                type="button"
                key={id}
                onClick={() => setPreset(id)}
                className={`rounded-xl border p-4 text-left transition ${preset === id ? "border-primary bg-primary/10" : "hover:bg-muted"}`}
              >
                <strong>{label}</strong>
                <p className="mt-1 text-sm text-muted-foreground">
                  {description}
                </p>
              </button>
            ))}
          </div>
          <div className="grid gap-2 md:max-w-md">
            <Label htmlFor="character-name">Tên nhân vật</Label>
            <Input
              id="character-name"
              value={name}
              maxLength={80}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <Button
            onClick={() => create.mutate()}
            disabled={!name.trim() || create.isPending}
          >
            <Plus /> {create.isPending ? "Đang tạo…" : "Tạo nhân vật"}
          </Button>
          {create.error && (
            <p className="text-sm text-destructive">{create.error.message}</p>
          )}
        </CardContent>
      </Card>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {characters.data?.data.map((character) => (
          <Card key={character.id}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bot className="size-5 text-primary" /> {character.name}
              </CardTitle>
              <CardDescription>{character.persona_description}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link
                  to="/studio/$characterId"
                  params={{ characterId: character.id }}
                >
                  Chỉnh sửa & preview
                </Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
