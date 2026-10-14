import { type VRM, VRMLoaderPlugin } from "@pixiv/three-vrm"
import { Float } from "@react-three/drei"
import { Canvas, useFrame, useLoader, useThree } from "@react-three/fiber"
import type { ReactNode } from "react"
import {
  Component,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react"
import type { Group, Mesh, Object3D } from "three"
import {
  AnimationMixer,
  Bone,
  BufferGeometry,
  LoopRepeat,
  MeshBasicMaterial,
  Quaternion,
  Skeleton,
  SkinnedMesh,
  Vector3,
} from "three"
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js"
import { MMDLoader } from "three-stdlib"

type AvatarSceneProps = {
  speaking: boolean
  amplitude?: number
  mood?:
    | "neutral"
    | "happy"
    | "annoyed"
    | "surprised"
    | "sad"
    | "relaxed"
    | "wink"
  vrmUrl?: string
  motion?: "idle" | "greet" | "heart" | "dance"
  cameraFraming?: "chest-up" | "full-body"
  cameraZoom?: number
  danceVmdUrl?: string
  danceVmdState?: "loading" | "available" | "unavailable"
  className?: string
}

function FrameDriver({
  speaking,
  motion,
}: {
  speaking: boolean
  motion: AvatarSceneProps["motion"]
}) {
  const invalidate = useThree((state) => state.invalidate)
  useEffect(() => {
    const timer = setInterval(
      invalidate,
      speaking || (motion && motion !== "idle") ? 50 : 100,
    )
    return () => clearInterval(timer)
  }, [invalidate, motion, speaking])
  return null
}

function CameraDriver({
  vrm,
  framing,
  zoom,
}: {
  vrm: boolean
  framing: "chest-up" | "full-body"
  zoom: number
}) {
  const camera = useThree((state) => state.camera)
  const invalidate = useThree((state) => state.invalidate)
  useEffect(() => {
    const fullBody = framing === "full-body"
    const targetY = vrm ? (fullBody ? 0.85 : 1.28) : 0
    const distance = vrm ? (fullBody ? 4.2 : 2.45) : fullBody ? 4.2 : 3.2
    camera.position.set(
      0,
      targetY,
      distance / Math.min(1.5, Math.max(0.7, zoom)),
    )
    camera.lookAt(0, targetY, 0)
    camera.updateProjectionMatrix()
    invalidate()
  }, [camera, framing, invalidate, vrm, zoom])
  return null
}

function ProceduralMascot({
  speaking,
  amplitude = 0.7,
  mood = "neutral",
  motion = "idle",
}: AvatarSceneProps) {
  const group = useRef<Group>(null)
  const mouth = useRef<Mesh>(null)
  useFrame(({ clock }) => {
    if (group.current) {
      group.current.rotation.y =
        Math.sin(clock.elapsedTime * (motion === "dance" ? 4 : 0.6)) *
        (motion === "dance" ? 0.18 : 0.08)
      group.current.rotation.z =
        motion === "dance"
          ? Math.sin(clock.elapsedTime * 5) * 0.09
          : motion === "greet"
            ? Math.sin(clock.elapsedTime * 8) * 0.08
            : motion === "heart"
              ? Math.sin(clock.elapsedTime * 3) * 0.03
              : 0
    }
    if (mouth.current) {
      const open = speaking
        ? 0.3 + Math.abs(Math.sin(clock.elapsedTime * 15)) * amplitude
        : 0.12
      mouth.current.scale.y = open
    }
  })
  const bodyColor =
    mood === "happy"
      ? "#35d6aa"
      : mood === "annoyed"
        ? "#ff758f"
        : mood === "surprised"
          ? "#ffd166"
          : "#7c8cff"
  return (
    <Float speed={1.5} rotationIntensity={0.08} floatIntensity={0.25}>
      <group
        ref={group}
        position={[0, -0.25, 0]}
        data-testid="procedural-avatar"
      >
        <mesh position={[0, -1.05, 0]} scale={[1.05, 1.2, 0.72]}>
          <capsuleGeometry args={[0.72, 0.9, 12, 24]} />
          <meshStandardMaterial color={bodyColor} roughness={0.55} />
        </mesh>
        <mesh position={[0, 0.35, 0]}>
          <sphereGeometry args={[0.88, 32, 24]} />
          <meshStandardMaterial color="#f8d9c4" roughness={0.75} />
        </mesh>
        <mesh
          position={[-0.3, 0.48, 0.76]}
          scale={[1, mood === "surprised" ? 1.4 : 1, 1]}
        >
          <sphereGeometry args={[0.09, 18, 18]} />
          <meshStandardMaterial color="#17213b" />
        </mesh>
        <mesh
          position={[0.3, 0.48, 0.76]}
          scale={[1, mood === "surprised" ? 1.4 : 1, 1]}
        >
          <sphereGeometry args={[0.09, 18, 18]} />
          <meshStandardMaterial color="#17213b" />
        </mesh>
        <mesh ref={mouth} position={[0, 0.12, 0.82]} scale={[0.24, 0.12, 0.08]}>
          <sphereGeometry args={[1, 18, 12]} />
          <meshStandardMaterial color="#b92f5d" />
        </mesh>
        <mesh position={[-0.55, 1.05, -0.05]} rotation={[0, 0, -0.35]}>
          <coneGeometry args={[0.28, 0.8, 18]} />
          <meshStandardMaterial color={bodyColor} />
        </mesh>
        <mesh position={[0.55, 1.05, -0.05]} rotation={[0, 0, 0.35]}>
          <coneGeometry args={[0.28, 0.8, 18]} />
          <meshStandardMaterial color={bodyColor} />
        </mesh>
      </group>
    </Float>
  )
}

type BonePose = { node: Object3D; x: number; y: number; z: number }

type DanceRig = {
  mixer: AnimationMixer
  reset: () => void
  source: "2-phut-hon-vmd" | "cc0-fallback"
  bones: Array<{
    source: Object3D
    target: Object3D
    sourceRest: Quaternion
    targetRest: Quaternion
    danceRotation: Quaternion
  }>
  rootMotion?: {
    source: Object3D
    target: Object3D
    sourceRest: Vector3
    targetRest: Vector3
    scale: number
    dancePosition: Vector3
  }
  footIk: Array<{
    source: Object3D
    sourceRest: Vector3
    upperLeg: Object3D
    lowerLeg: Object3D
    foot: Object3D
    targetRest: Vector3
    target: Vector3
    danceTarget: Vector3
    scale: number
  }>
}

type RestTransform = { rotation: Quaternion; position: Vector3 }

const VMD_CENTER_BONE = "\u30bb\u30f3\u30bf\u30fc"
const VMD_FOOT_IK_BONES = {
  "\u5de6\u8db3\uff29\uff2b": {
    upperLeg: "leftUpperLeg",
    lowerLeg: "leftLowerLeg",
    foot: "leftFoot",
  },
  "\u53f3\u8db3\uff29\uff2b": {
    upperLeg: "rightUpperLeg",
    lowerLeg: "rightLowerLeg",
    foot: "rightFoot",
  },
} as const

const VMD_TO_VRM_BONES: Record<string, string> = {
  下半身: "hips",
  上半身: "spine",
  上半身2: "chest",
  首: "neck",
  頭: "head",
  左肩: "leftShoulder",
  左腕: "leftUpperArm",
  左ひじ: "leftLowerArm",
  左手首: "leftHand",
  右肩: "rightShoulder",
  右腕: "rightUpperArm",
  右ひじ: "rightLowerArm",
  右手首: "rightHand",
  左足: "leftUpperLeg",
  左ひざ: "leftLowerLeg",
  左足首: "leftFoot",
  左つま先: "leftToes",
  右足: "rightUpperLeg",
  右ひざ: "rightLowerLeg",
  右足首: "rightFoot",
  右つま先: "rightToes",
}

function createVmdProxy() {
  const mesh = new SkinnedMesh(new BufferGeometry(), new MeshBasicMaterial())
  const bones = [
    VMD_CENTER_BONE,
    ...Object.keys(VMD_FOOT_IK_BONES),
    ...Object.keys(VMD_TO_VRM_BONES),
  ].map((name) => {
    const bone = new Bone()
    bone.name = name
    mesh.add(bone)
    return bone
  })
  mesh.bind(new Skeleton(bones))
  return mesh
}

const IK_JOINT = new Vector3()
const IK_EFFECTOR = new Vector3()
const IK_TO_EFFECTOR = new Vector3()
const IK_TO_TARGET = new Vector3()
const IK_PARENT_WORLD = new Quaternion()
const IK_JOINT_WORLD = new Quaternion()
const IK_DELTA = new Quaternion()
const IK_LIMITED_DELTA = new Quaternion()
const IK_WORLD_RESULT = new Quaternion()
const IK_IDENTITY = new Quaternion()
const IK_SCENE_WORLD = new Quaternion()

function solveFootIk(
  normalizedRigRoot: Object3D,
  chain: DanceRig["footIk"][number],
) {
  // Start from the authored leg rotations, then make small CCD corrections so
  // the animated MMD foot target is actually followed. Limiting each step
  // avoids knee flips when source and avatar proportions differ.
  for (let iteration = 0; iteration < 3; iteration += 1) {
    for (const joint of [chain.lowerLeg, chain.upperLeg]) {
      // Only the normalized skeleton is needed here. Traversing the complete
      // VRM scene six times per frame stalls UI/audio events on large models.
      normalizedRigRoot.updateMatrixWorld(true)
      chain.foot.getWorldPosition(IK_EFFECTOR)
      joint.getWorldPosition(IK_JOINT)
      IK_TO_EFFECTOR.copy(IK_EFFECTOR).sub(IK_JOINT)
      IK_TO_TARGET.copy(chain.target).sub(IK_JOINT)
      if (
        IK_TO_EFFECTOR.lengthSq() < 0.000001 ||
        IK_TO_TARGET.lengthSq() < 0.000001
      )
        continue
      IK_TO_EFFECTOR.normalize()
      IK_TO_TARGET.normalize()
      IK_DELTA.setFromUnitVectors(IK_TO_EFFECTOR, IK_TO_TARGET)
      const angle = 2 * Math.acos(Math.min(1, Math.abs(IK_DELTA.w)))
      IK_LIMITED_DELTA.copy(IK_IDENTITY).slerp(
        IK_DELTA,
        angle > 0.45 ? 0.45 / angle : 1,
      )
      joint.getWorldQuaternion(IK_JOINT_WORLD)
      IK_WORLD_RESULT.copy(IK_LIMITED_DELTA).multiply(IK_JOINT_WORLD)
      joint.parent?.getWorldQuaternion(IK_PARENT_WORLD)
      joint.quaternion.copy(IK_PARENT_WORLD.invert()).multiply(IK_WORLD_RESULT)
    }
  }
}

function LicensedVrm({
  url,
  speaking,
  amplitude = 0,
  mood = "neutral",
  motion = "idle",
  danceVmdUrl,
  danceVmdState = "unavailable",
  onReady,
  onMissingVrm,
  onDanceReady,
}: AvatarSceneProps & {
  url: string
  onReady: () => void
  onMissingVrm: () => void
  onDanceReady: (source: DanceRig["source"]) => void
}) {
  const gltf = useLoader(GLTFLoader, url, (loader) => {
    loader.register((parser) => new VRMLoaderPlugin(parser))
  })
  const vrm = gltf.userData.vrm as VRM | undefined
  const bones = useRef<Record<string, BonePose>>({})
  const mouth = useRef(0)
  const emotion = useRef(0)
  const nextBlink = useRef(2.4)
  const blinkStart = useRef(-10)
  const danceBlend = useRef(0)
  const gestureBlend = useRef(0)
  const danceRig = useRef<DanceRig | null>(null)
  const restTransforms = useRef<Record<string, RestTransform>>({})
  const wasDancing = useRef(false)
  useEffect(() => {
    if (!vrm || motion !== "dance" || danceRig.current) return
    let cancelled = false
    const configureDance = (
      sourceRoot: Object3D,
      clip: NonNullable<Parameters<AnimationMixer["clipAction"]>[0]>,
      map: Record<string, string>,
      source: DanceRig["source"],
    ) => {
      const mapped = Object.entries(map).flatMap(([sourceName, targetName]) => {
        const sourceNode = sourceRoot.getObjectByName(sourceName)
        const target = vrm.humanoid.getNormalizedBoneNode(targetName as never)
        return sourceNode && target
          ? [
              {
                source: sourceNode,
                target,
                sourceRest: sourceNode.quaternion.clone(),
                targetRest:
                  restTransforms.current[targetName]?.rotation.clone() ??
                  target.quaternion.clone(),
                danceRotation: new Quaternion(),
              },
            ]
          : []
      })
      if (mapped.length === 0 || cancelled) return false
      const mixer = new AnimationMixer(sourceRoot)
      const action = mixer.clipAction(clip)
      if (!action) return false
      action.setLoop(LoopRepeat, Infinity)
      action.play()
      mixer.setTime(0)
      const sourceCenter = sourceRoot.getObjectByName(VMD_CENTER_BONE)
      const targetHips = vrm.humanoid.getNormalizedBoneNode("hips")
      const hipsRest = restTransforms.current.hips
      // MMD motions use model units (a typical character is about 20 units
      // tall), while VRM uses metres. Scaling from the target hip height keeps
      // lateral sway and jumps proportional without letting the avatar drift.
      const centerScale = hipsRest
        ? Math.min(0.11, Math.max(0.055, hipsRest.position.y / 10))
        : 0.08
      vrm.scene.updateWorldMatrix(true, false)
      vrm.humanoid.normalizedHumanBonesRoot.updateMatrixWorld(true)
      const footIk =
        source === "2-phut-hon-vmd"
          ? Object.entries(VMD_FOOT_IK_BONES).flatMap(
              ([sourceName, targetNames]) => {
                const sourceNode = sourceRoot.getObjectByName(sourceName)
                const upperLeg = vrm.humanoid.getNormalizedBoneNode(
                  targetNames.upperLeg,
                )
                const lowerLeg = vrm.humanoid.getNormalizedBoneNode(
                  targetNames.lowerLeg,
                )
                const foot = vrm.humanoid.getNormalizedBoneNode(
                  targetNames.foot,
                )
                return sourceNode && upperLeg && lowerLeg && foot
                  ? [
                      {
                        source: sourceNode,
                        sourceRest: sourceNode.position.clone(),
                        upperLeg,
                        lowerLeg,
                        foot,
                        targetRest: foot.getWorldPosition(new Vector3()),
                        target: new Vector3(),
                        danceTarget: new Vector3(),
                        scale: centerScale,
                      },
                    ]
                  : []
              },
            )
          : []
      danceRig.current = {
        mixer,
        bones: mapped,
        source,
        footIk,
        rootMotion:
          source === "2-phut-hon-vmd" && sourceCenter && targetHips && hipsRest
            ? {
                source: sourceCenter,
                target: targetHips,
                sourceRest: sourceCenter.position.clone(),
                targetRest: hipsRest.position.clone(),
                scale: centerScale,
                dancePosition: new Vector3(),
              }
            : undefined,
        reset: () => action.reset().play(),
      }
      onDanceReady(source)
      return true
    }
    const loadCc0Fallback = () => {
      const loader = new GLTFLoader()
      loader.load(
        `${import.meta.env.BASE_URL}motions/UAL1_Standard.glb`,
        (gltf) => {
          if (cancelled) return
          const clip = gltf.animations.find(
            (item) => item.name === "Dance_Loop",
          )
          if (!clip) return
          configureDance(
            gltf.scene,
            clip,
            {
              pelvis: "hips",
              spine_01: "spine",
              spine_02: "chest",
              spine_03: "upperChest",
              neck_01: "neck",
              Head: "head",
              clavicle_l: "leftShoulder",
              upperarm_l: "leftUpperArm",
              lowerarm_l: "leftLowerArm",
              hand_l: "leftHand",
              clavicle_r: "rightShoulder",
              upperarm_r: "rightUpperArm",
              lowerarm_r: "rightLowerArm",
              hand_r: "rightHand",
              thigh_l: "leftUpperLeg",
              calf_l: "leftLowerLeg",
              foot_l: "leftFoot",
              thigh_r: "rightUpperLeg",
              calf_r: "rightLowerLeg",
              foot_r: "rightFoot",
            },
            "cc0-fallback",
          )
        },
      )
    }
    if (danceVmdState === "loading")
      return () => {
        cancelled = true
      }
    if (danceVmdState === "available" && danceVmdUrl) {
      const proxy = createVmdProxy()
      new MMDLoader().loadAnimation(
        danceVmdUrl,
        proxy,
        (animation) => {
          if (cancelled || !("tracks" in animation)) return
          configureDance(proxy, animation, VMD_TO_VRM_BONES, "2-phut-hon-vmd")
        },
        undefined,
        () => loadCc0Fallback(),
      )
    } else loadCc0Fallback()
    return () => {
      cancelled = true
    }
  }, [danceVmdState, danceVmdUrl, motion, onDanceReady, vrm])
  useEffect(() => {
    if (motion === "dance" && !wasDancing.current) danceRig.current?.reset()
    wasDancing.current = motion === "dance"
  }, [motion])
  useEffect(() => {
    if (!vrm) {
      onMissingVrm()
      return
    }
    vrm.scene.rotation.y = Math.PI
    const poses: Record<string, BonePose> = {}
    const rest: Record<string, RestTransform> = {}
    for (const name of new Set([
      ...Object.values(VMD_TO_VRM_BONES),
      "upperChest",
    ])) {
      const node = vrm.humanoid.getNormalizedBoneNode(name as never)
      if (node)
        rest[name] = {
          rotation: node.quaternion.clone(),
          position: node.position.clone(),
        }
    }
    restTransforms.current = rest
    for (const name of [
      "spine",
      "chest",
      "head",
      "leftUpperArm",
      "rightUpperArm",
      "leftLowerArm",
      "rightLowerArm",
      "leftHand",
      "rightHand",
    ] as const) {
      const node = vrm.humanoid.getNormalizedBoneNode(name)
      if (node)
        poses[name] = {
          node,
          x: node.rotation.x,
          y: node.rotation.y,
          z: node.rotation.z,
        }
    }
    bones.current = poses
    onReady()
  }, [vrm, onMissingVrm, onReady])
  useFrame(({ clock }, delta) => {
    if (!vrm) return
    const t = clock.elapsedTime
    const smoothing = Math.min(1, delta * 16)
    const mouthTarget = speaking
      ? Math.min(1, Math.max(0.12, amplitude * 1.45))
      : 0
    mouth.current += (mouthTarget - mouth.current) * smoothing
    emotion.current +=
      ((mood === "neutral" ? 0 : 0.85) - emotion.current) *
      Math.min(1, delta * 5)
    if (t >= nextBlink.current) {
      blinkStart.current = t
      nextBlink.current = t + 3.2 + (Math.sin(t * 5.13) + 1) * 1.5
    }
    const blink = Math.max(0, 1 - Math.abs(t - blinkStart.current - 0.1) / 0.1)
    const expressions = vrm.expressionManager
    if (expressions) {
      if (expressions.getExpression("aa"))
        expressions.setValue("aa", mouth.current)
      if (expressions.getExpression("blink"))
        expressions.setValue("blink", blink)
      const options: Record<NonNullable<AvatarSceneProps["mood"]>, string[]> = {
        neutral: ["neutral"],
        happy: ["happy", "joy", "Joy"],
        annoyed: ["angry", "Angry"],
        surprised: ["surprised", "Surprised"],
        sad: ["sad", "sorrow", "Sorrow"],
        relaxed: ["relaxed", "Relaxed"],
        wink: ["wink", "Wink", "blinkRight"],
      }
      for (const [state, names] of Object.entries(options)) {
        const supported = names.find((name) => expressions.getExpression(name))
        if (supported)
          expressions.setValue(supported, state === mood ? emotion.current : 0)
      }
    }
    const rig = danceRig.current
    // Always start from the normalized VRM rest pose. Previously these values
    // were captured after the idle arm pose had already been applied, so every
    // VMD shoulder/arm rotation inherited a large and incorrect offset.
    if (rig) {
      for (const bone of rig.bones) bone.target.quaternion.copy(bone.targetRest)
      if (rig.rootMotion)
        rig.rootMotion.target.position.copy(rig.rootMotion.targetRest)
    }
    const gesture = speaking ? Math.min(1, amplitude) : 0
    const spine = bones.current.spine
    if (spine) {
      spine.node.rotation.x = spine.x + Math.sin(t * 1.45) * 0.014
      spine.node.rotation.z = spine.z + Math.sin(t * 0.7) * 0.012
    }
    const chest = bones.current.chest
    if (chest) chest.node.rotation.x = chest.x + Math.sin(t * 1.45) * 0.012
    const head = bones.current.head
    if (head) {
      head.node.rotation.x = head.x + Math.sin(t * 3.1) * 0.025 * gesture
      head.node.rotation.y = head.y + Math.sin(t * 0.8) * 0.018
    }
    for (const [side, sign] of [
      ["leftUpperArm", 1],
      ["rightUpperArm", -1],
    ] as const) {
      const arm = bones.current[side]
      if (arm)
        arm.node.rotation.z =
          arm.z + sign * (1.05 + Math.sin(t * 2.5) * 0.045 * gesture)
    }
    for (const name of [
      "leftLowerArm",
      "rightLowerArm",
      "leftHand",
      "rightHand",
    ] as const) {
      const bone = bones.current[name]
      if (bone) bone.node.rotation.set(bone.x, bone.y, bone.z)
    }
    const actionBlend = motion === "greet" || motion === "heart" ? 1 : 0
    gestureBlend.current += (actionBlend - gestureBlend.current) * smoothing
    if (motion === "greet") {
      const upper = bones.current.rightUpperArm
      const lower = bones.current.rightLowerArm
      const hand = bones.current.rightHand
      const wave = Math.sin(t * 12) * 0.24
      if (upper)
        upper.node.rotation.z +=
          (1.05 - gestureBlend.current * 0.65) * gestureBlend.current
      if (lower) lower.node.rotation.z += (0.85 + wave) * gestureBlend.current
      if (hand) hand.node.rotation.x += 0.16 * gestureBlend.current
    } else if (motion === "heart") {
      const left = bones.current.leftUpperArm
      const right = bones.current.rightUpperArm
      const leftLower = bones.current.leftLowerArm
      const rightLower = bones.current.rightLowerArm
      if (left) left.node.rotation.z += -0.45 * gestureBlend.current
      if (right) right.node.rotation.z += 0.45 * gestureBlend.current
      if (leftLower) leftLower.node.rotation.z += 0.9 * gestureBlend.current
      if (rightLower) rightLower.node.rotation.z += -0.9 * gestureBlend.current
    }
    danceBlend.current +=
      ((motion === "dance" && danceRig.current ? 0.92 : 0) -
        danceBlend.current) *
      Math.min(1, delta * 5)
    if (rig && danceBlend.current > 0.001)
      rig.mixer.update(Math.min(delta, 0.05))
    if (rig && danceBlend.current > 0.001) {
      for (const bone of rig.bones) {
        const deltaRotation = bone.sourceRest
          .clone()
          .invert()
          .multiply(bone.source.quaternion)
        bone.danceRotation.copy(bone.targetRest).multiply(deltaRotation)
        bone.target.quaternion.slerp(bone.danceRotation, danceBlend.current)
      }
      const rootMotion = rig.rootMotion
      if (rootMotion) {
        rootMotion.dancePosition
          .copy(rootMotion.source.position)
          .sub(rootMotion.sourceRest)
          .multiplyScalar(rootMotion.scale)
          .add(rootMotion.targetRest)
        rootMotion.target.position.lerp(
          rootMotion.dancePosition,
          danceBlend.current,
        )
      }
      if (rig.footIk.length > 0) {
        vrm.scene.updateWorldMatrix(true, false)
        const normalizedRigRoot = vrm.humanoid.normalizedHumanBonesRoot
        const sceneRotation = vrm.scene.getWorldQuaternion(IK_SCENE_WORLD)
        for (const chain of rig.footIk) {
          chain.danceTarget
            .copy(chain.source.position)
            .sub(chain.sourceRest)
            .multiplyScalar(chain.scale)
            .applyQuaternion(sceneRotation)
            .add(chain.targetRest)
          chain.target
            .copy(chain.targetRest)
            .lerp(chain.danceTarget, danceBlend.current)
          solveFootIk(normalizedRigRoot, chain)
        }
      }
    }
    vrm.scene.position.y = Math.sin(t * 1.45) * 0.009
    vrm.update(Math.min(delta, 0.05))
  })
  return vrm ? (
    <primitive object={vrm.scene} />
  ) : (
    <ProceduralMascot
      speaking={speaking}
      amplitude={amplitude}
      mood={mood}
      motion={motion}
    />
  )
}

class VrmErrorBoundary extends Component<
  { children: ReactNode; fallback: ReactNode; onError: () => void },
  { failed: boolean }
> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch() {
    this.props.onError()
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

export function AvatarScene(props: AvatarSceneProps) {
  const [readyUrl, setReadyUrl] = useState<string | null>(null)
  const [failedUrl, setFailedUrl] = useState<string | null>(null)
  const [danceReadyUrl, setDanceReadyUrl] = useState<string | null>(null)
  const [danceSource, setDanceSource] = useState<DanceRig["source"] | null>(
    null,
  )
  const markReady = useCallback(
    () => setReadyUrl(props.vrmUrl ?? null),
    [props.vrmUrl],
  )
  const markFailed = useCallback(
    () => setFailedUrl(props.vrmUrl ?? null),
    [props.vrmUrl],
  )
  const markDanceReady = useCallback(
    (source: DanceRig["source"]) => {
      setDanceReadyUrl(props.vrmUrl ?? null)
      setDanceSource(source)
    },
    [props.vrmUrl],
  )
  const avatarStatus = !props.vrmUrl
    ? "fallback"
    : failedUrl === props.vrmUrl
      ? "fallback"
      : readyUrl === props.vrmUrl
        ? "vrm"
        : "loading"
  return (
    <div
      className={props.className ?? "h-full w-full"}
      data-testid="avatar-canvas"
      data-avatar-status={avatarStatus}
      data-avatar-motion={props.motion ?? (props.speaking ? "talking" : "idle")}
      data-camera-framing={props.cameraFraming ?? "chest-up"}
      data-camera-zoom={props.cameraZoom ?? 1}
      data-dance-ready={danceReadyUrl === props.vrmUrl ? "true" : "false"}
      data-dance-source={
        danceReadyUrl === props.vrmUrl ? (danceSource ?? "unknown") : "pending"
      }
      data-dance-retarget={
        danceSource === "2-phut-hon-vmd"
          ? "normalized-rest+center+foot-ik"
          : "rotation-only"
      }
    >
      <Canvas
        gl={{ alpha: true, antialias: true }}
        dpr={1}
        frameloop="demand"
        camera={{ position: [0, 0, 4.2], fov: 38 }}
      >
        <FrameDriver speaking={props.speaking} motion={props.motion} />
        <CameraDriver
          vrm={avatarStatus === "vrm"}
          framing={props.cameraFraming ?? "chest-up"}
          zoom={props.cameraZoom ?? 1}
        />
        <ambientLight intensity={1.3} />
        <directionalLight position={[2, 3, 4]} intensity={1.8} />
        <directionalLight position={[-2, 2, -2]} intensity={0.55} />
        <Suspense fallback={<ProceduralMascot {...props} />}>
          {props.vrmUrl ? (
            <VrmErrorBoundary
              key={props.vrmUrl}
              fallback={<ProceduralMascot {...props} />}
              onError={markFailed}
            >
              <LicensedVrm
                {...props}
                url={props.vrmUrl}
                onReady={markReady}
                onMissingVrm={markFailed}
                onDanceReady={markDanceReady}
              />
            </VrmErrorBoundary>
          ) : (
            <ProceduralMascot {...props} />
          )}
        </Suspense>
      </Canvas>
    </div>
  )
}
