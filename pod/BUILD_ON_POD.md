# Build the Zeus MetaHuman Avatar on a RunPod GPU Pod — Master Runbook

> **Reality check (verified 2026-06-13):** there is **no built Unreal project**
> anywhere — not local, not on the VPS (`5.78.121.13`), not on the Mac mini, and
> the old VPS (`178.156.254.59`) is purged/dead. `ue/ZeusMetaHuman/` is a *kit*:
> the `ZeusAnimReceiver` C++ plugin source + `SETUP.md`. The MetaHuman and the
> packaged build have to be **created from scratch on the pod**. This runbook
> automates everything that can be automated and flags the steps only a human can do.

## What we're building
```
meeting audio ─▶ STT(:8001) ─▶ zeus-gateway(:8000) ─▶ TTS ─▶ a2f-bridge(:8003)
                                                              │ ARKit 52 blendshapes
                                                              ▼  ws://…/ws_anim
                ZeusAnimReceiver plugin ─▶ LiveLink "ZeusAvatar" ─▶ MetaHuman Face_AnimBP
                                                              │
                                              UE5 + Pixel Streaming (WebRTC, headless)
                                                              ▼
                                              browser / OBS / Zoom-Teams-Meet
```

## Engine strategy — Epic's official container (recommended)
We base the build on **`ghcr.io/epicgames/unreal-engine:dev-5.4`** (the official
UE5.4 Linux *dev* image: full editor + `RunUAT` + automation tools). This skips a
multi-hour source build. It is gated:
- Link your GitHub account to Epic: https://www.unrealengine.com/en-US/ue-on-github
- Accept the EULA, then `docker login ghcr.io` with a GitHub PAT (`read:packages`).
- (Fallback if you don't want the container: build UE5.4 from source —
  `01_install_ue5.sh --source` — adds ~2–3 h and ~150 GB.)

## Cost (pod bills for UPTIME — stop it when idle)
| GPU | ~$/hr | Build (one-time, ~2–4 h) | Live use 1 h |
|---|---|---|---|
| RTX 4090 (24 GB) | ~0.44 | ~$0.9–1.8 | ~$0.44 |
| A6000 / L40S (48 GB) | ~0.79 | ~$1.6–3.2 | ~$0.79 |
| Volume 100 GB | ~$5–7 / mo standing | | |

**Use A6000 (48 GB)** for the build+package (UE editor + cooking is memory-hungry);
you can run the live stream on a 4090 afterward. **Stop the pod between sessions.**

## Order of operations
| # | Step | Script | Who | GPU billing? |
|---|------|--------|-----|---|
| 0 | Epic↔GitHub link + EULA + `ghcr.io` login | — | **Daniel** | no |
| 1 | Provision pod (A6000, 100 GB vol, ports) | `provision_pod.sh` | auto | starts here |
| 2 | Install UE5.4 (pull dev image) on pod | `01_install_ue5.sh` | auto | yes |
| 3 | Bootstrap project (.uproject + plugin + map) | `02_bootstrap_project.sh` | auto | yes |
| 4 | **Create + import MetaHuman** (GUI, Quixel Bridge) | `INTERACTIVE_STEPS.md` | **Daniel** | yes |
| 5 | Wire Face_AnimBP LiveLink + level BP connect | `INTERACTIVE_STEPS.md` | **Daniel** | yes |
| 6 | Package Linux + Pixel Streaming (headless) | `03_package_pixelstreaming.sh` | auto | yes |
| 7 | Run signaling + packaged build + services | `04_run_stream.sh` | auto | yes |
| 8 | Verify in browser, then point OBS/Zoom at it | `RUNBOOK.md` (parent) | Daniel | yes |
| 9 | **Stop the pod** | `runpodctl stop pod <id>` | Daniel | stops |

Steps 4–5 are the only hard-manual ones, and they need a **GUI on the pod**
(RunPod "Desktop"/noVNC template, or run the editor once via the pod's web VNC).
Everything in 1–3 and 6–7 is scripted.

## The interactive bottleneck (read this before provisioning)
MetaHuman assets come from **Quixel Bridge inside the editor**, which needs an
interactive **Epic login** and a **GUI**. On a headless cloud pod that means one
of:
- **(A) Desktop pod** — provision with a desktop/VNC image, RDP/noVNC in, do the
  Bridge import + AnimBP wiring once, save to `Content/MetaHumans/Zeus/`. ← simplest
- **(B) Pre-bake the asset** — create the MetaHuman on any machine with the editor,
  export the `Content/MetaHumans/...` folder, and we upload it to the pod volume so
  packaging is fully headless. Avoids GUI on the pod entirely.

`INTERACTIVE_STEPS.md` covers both. **(B) is cheapest** (no GUI pod-hours) if you
have, or can get, editor access anywhere for ~30 min.

## Files in this kit
- `provision_pod.sh` — create the RunPod GPU pod + volume + ports via API
- `01_install_ue5.sh` — pull UE5.4 dev image (or `--source` build)
- `02_bootstrap_project.sh` — generate `ZeusMetaHuman.uproject`, copy the plugin, enable plugins, make a minimal map
- `03_package_pixelstreaming.sh` — `RunUAT BuildCookRun` Linux + Pixel Streaming
- `04_run_stream.sh` — signaling server + headless `-RenderOffscreen` build + connect a2f-bridge
- `INTERACTIVE_STEPS.md` — Epic login, MetaHuman create/import, AnimBP wiring (the human steps)
- `project/` — generated project scaffolding templates (`.uproject`, configs)

## IP rule (carried from the 2D work)
The avatar must be an **original** synthetic MetaHuman we own — not a real
person's likeness and not the copyrighted Matrix "Agent Smith." Build an original
suited-presenter MetaHuman.
