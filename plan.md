## Current Product Scope

DevDefender Lab is currently scoped to the lightweight Project Briefing Room product for VS Code Codex and similar code agents.

Current default path:

- Generate a stakeholder-readable briefing from repo-visible workspace facts.
- Let Codex present the briefing, listen to stakeholder feedback, ask follow-up questions, and decide how that feedback changes direction, requirements, risk, evidence, priority, or acceptance.
- Use scripts only for deterministic persistence and checks: write bounded artifacts, update the controlled plan block, and evaluate the execution gate.
- Continue implementation in the same Codex session only when `artifacts/project_briefing_room/session.json` and the execution gate indicate the updated plan is actionable.

Default package boundaries:

- Included: `project-briefing-room`, `project-briefing-room-doctor`, `project-briefing-agent-input`, repo-local artifacts under `artifacts/project_briefing_room/`, and the repo-versioned `$project-briefing-room` skill.
- Not included by default: live meeting rooms, speech or video capture, Zoom, LiveKit, WebRTC, Node/Slidev runtime, OpenAI credentials, external SaaS scheduling, or automated code-agent handoff chains.

Release checks are tracked in `RELEASE_CHECKLIST.md`.

---

初始改造前 code agent 可以使用 [Gitlawb/openclaude](https://github.com/Gitlawb/openclaude)，但它不能直接成为系统里的“自由行动者”。

正确姿势是：把 Code Agent 当成一个可替换的执行后端，通过统一的 Agent Adapter 接入黑板状态机。LangGraph 只给它结构化 Issue、代码版本指针、允许修改范围、测试命令和验收规则；Code Agent 只能返回 patch、测试日志、commit 指针和风险说明，不能绕过 TDAD 流程直接改主分支。

🌟 顶层编排设计：中心辐射型“黑板模式” (Hub-and-Spoke)
整个系统绝不能是一段从头跑到尾的 Python 脚本，而是一个支持“超长异步挂起”的分布式状态机。

编排大脑拼接：LangGraph + Pydantic。

超长异步挂起（HITL）：人类开会可能在代码提交后的几天。当系统备好 PPT 后，调用 LangGraph 的 interrupt() 机制与 Checkpointer (如 PostgresSaver)，进程瞬间持久化休眠，彻底释放服务器内存。会议结束后，收到 Webhook 带着 thread_id 携原图谱上下文精准唤醒。

防上下文爆炸契约：在全局黑板（Blackboard State）中，绝对禁止传递几万行的源代码全文。只流转结构化指针：agent_a_repo_commit_hash（代码版本指针）、slidev_url（幻灯片指针）以及 verified_architectural_decisions（人类确认后的共识记忆，防重构回退）。

🧩 五大子系统开源“物料清单”与缝合方案 (BOM & Stitching)
🛠️ 模块零：代码执行层 —— 受控 Code Agent 接入网关 (The Agent Gateway)
【目标】 把 openclaude / Aider / Codex / 自研 agent 变成可审计、可替换、可回放的“补丁执行器”，而不是让它们直接接管仓库。

适配器拼装：Agent Adapter Interface + Git Worktree + Patch Contract。

缝合逻辑：所有 Code Agent 统一实现同一个最小接口：

- `plan(issue, graph_pointer, repo_commit)`：只产出修改计划，不改文件。
- `write_tests(issue, allowed_paths)`：先写红灯测试，返回测试文件 diff。
- `implement(issue, failing_tests, allowed_paths)`：只在白名单路径内生成补丁。
- `verify(test_commands)`：运行测试并返回结构化日志。
- `summarize()`：返回 changed_files、risk_notes、commit_hash、rollback_patch。

沙箱边界：每次执行都在独立 git worktree / 临时分支里完成，输入是 `repo_commit_hash + issue_json + graph_json path`，输出是 `patch.diff + test_report.json + agent_trace.json`。禁止把 `.env`、密钥、完整聊天记录、会议录音全文传给 Code Agent。

权限契约：

- 白名单：只允许修改 Issue 映射到的模块、对应测试、必要文档。
- 黑名单：禁止修改 CI、发布脚本、密钥文件、锁文件、大面积格式化，除非 Issue 明确授权。
- 命令门禁：只允许运行配置好的 test/lint/typecheck 命令；危险命令如 `git reset --hard`、删除目录、网络发布必须人工确认。
- 产物门禁：没有红灯测试证据、没有绿灯测试日志、没有 diff 摘要，不允许进入 merge/commit 节点。

Code Agent 候选：

- openclaude：适合早期接入和改造，作为 Agent Adapter 的第一个实验后端。
- Aider Architect 模式：适合 TDAD 下的“先计划、再测试、再补丁”流程。
- Codex CLI / 本地编码 agent：适合 IDE 内人机协作和多轮调试。

黑板状态新增指针：

- `agent_backend`: 当前执行后端，如 openclaude/aider/codex。
- `agent_workspace`: 临时 worktree 路径。
- `agent_patch_path`: 生成的 patch 文件路径。
- `agent_test_report_path`: 测试报告 JSON 路径。
- `agent_trace_path`: agent 思考摘要、工具调用摘要和风险说明。
- `agent_commit_hash`: 通过验收后的临时分支 commit。

🛠️ 模块一：防御大脑 —— 确定性代码知识图谱 (Agentic GraphRAG)
【目标】 彻底消灭 AI 在答辩被质问深层代码逻辑时的“大模型幻觉”与盲区。

弃用传统文本 RAG：传统向量切分会撕裂代码的函数依赖树。

底层拼装：Tree-sitter + Memgraph (内存图数据库)。

缝合逻辑：每次代码 PR 提交后，Python 脚本调用 Tree-sitter（毫秒级 AST 解析器）将代码 100% 确定性地解析为抽象语法树（DKB 策略）。将其函数 CALLS (调用)、IMPORTS (依赖) 作为边写入 Memgraph，构建不可辩驳的“物理代码图谱”。

查询拼装：MCP Tools (模型上下文协议)。

缝合逻辑：答辩面临质询时，通过 MCP 挂载的工具，自动将人类的自然语言转化为 Cypher 查询语句。执行原子化图内推演 (Atomic GraphRAG)，直接把带有异常抛出路径的函数调用子图拉出来，用铁证进行防御辩护。

🛠️ 模块二：视觉呈现 —— 自愈合幻灯片工厂 (The Presenter)
【目标】 将冰冷的代码 Diff 转化为极客风的交互式幻灯片，且天生支持被后端 API 遥控。

自愈拼装：Mermaid-CLI 本地沙箱。

缝合逻辑：大模型直接写 Mermaid 架构图极易因转义字符导致语法崩溃。必须在生成后送入 CLI 沙箱编译，一旦报错，将 AST 错误日志直接扔回给 LLM 触发自我修复 (Self-healing)，直到通过编译。

渲染拼装（绝对核心）：Slidev。

缝合逻辑：Slidev 基于 Vite 构建，天生是前端 SPA。利用其原生的 --remote (开启 WebSocket) 和 --tunnel (公网穿透) 命令行启动参数，瞬间在后台起一个可以被 Python 接口精确遥控翻页的公网网页。

🛠️ 模块三：多模态虚拟化身 —— 无头答辩舱 (The Avatar) [技术深水区]
【目标】 AI 长出“嘴巴和眼睛”，静默入会讲 PPT，并能抗住人类毫无规律的连环打断。

音视频中枢拼装：LiveKit Agents。

缝合逻辑：强于 Pipecat 的点在于其开箱即用的 CNN 自适应打断声学模型。评委咳嗽、叹气不会导致 AI 闭嘴重置，只有真正的话语权争夺（<216ms响应）才会触发打断与重新规划。

会议劫持拼装：Puppeteer + Xvfb (Linux虚拟显示屏)。

缝合逻辑：在 Docker 中拉起无头 Chrome，利用 --use-fake-device-for-media-stream 绕过麦克风/摄像头权限测试。利用 canvas.captureStream() 高级 API 强行劫持 Slidev 的网页画面伪装成摄像头流，推入 Zoom/腾讯会议的 Web 端。

神级声画同步（黑科技）：TTS Word-level Timestamps。

缝合逻辑：当 LiveKit 的 TTS 语音流播报到预埋的锚点词汇（如“让我们看下一页的支付架构”）时，底层会吐出该词的精确毫秒级时间戳。后台 Python 进程捕获到该时间戳后，通过 WebSocket 瞬间给 Slidev 发送 {"action": "next"}，评委看到的就是完美的“边讲边翻页”。

🛠️ 模块四：逆向工程 —— 安全重构闭环 (The Refiner)
【目标】 听懂人类充满废话和代词的模糊反馈，安全地转化为新代码。

意图对齐拼装：WhisperX + 多模态时间轴交叉。

缝合逻辑：当评委随口说“把这个功能砍掉”时，利用 WhisperX 提取毫秒级发音时间戳，反查该时间点 Slidev 正好停留在哪一页，从而精准消歧，锁定对应的代码模块（如 PaymentAPI）。

防幻觉提取：LangChain Structured Output。

缝合逻辑：设立“非对称审计”工作流。强制剥夺 LLM 的润色权限，任何没有“会议原话时间戳（Evidence Pointer）”支持的修改意见，全部剔除防脑补，最终输出标准 GitHub Issue JSON。

安全重构拼装：Aider (Architect 模式) + TDAD 机制。

缝合逻辑：绝不允许 AI 拿到 Issue 直接自由发挥 (Vibe Coding)。强制引入 TDAD (测试驱动智能体开发)：Aider 在改写核心业务逻辑前，必须先写测试脚本（红灯）。只要测试没跑通，就不允许 Commit 提交，用编译器作为防线的最后兜底。

Code Agent 缝合逻辑：Refiner 不直接改代码，而是把标准 GitHub Issue JSON 转换成 Agent Task Envelope：

```json
{
  "issue": "...",
  "repo_commit_hash": "...",
  "allowed_paths": ["src/payment/**", "tests/payment/**"],
  "required_tests": ["pytest tests/payment -q"],
  "evidence_pointers": ["timeline://thread#event=12&kind=speech_interrupted", "slide://thread#page=7"],
  "acceptance": {
    "must_write_test_first": true,
    "must_pass_existing_tests": true,
    "must_return_patch_only": true
  }
}
```

Agent Gateway 执行后，Refiner 只读取 `patch.diff`、`test_report.json`、`agent_trace.json`，再决定：接受、要求重试、升级人工审核，或生成 rollback。

🧪 测试与验收设计 (Testing & Acceptance Matrix)
系统必须把“能跑 demo”和“值得信任”分开验收。每个阶段至少保留以下测试层：

1. 单元测试：
   - parser：函数、类、import、CALLS 边是否稳定抽取。
   - graph_store：保存、加载、查询子图是否可重复。
   - issue extractor：LLM/mock 输出是否能被 Pydantic schema 严格校验。
   - agent adapter：同一 Issue 输入是否生成合法 Task Envelope，是否拒绝越权路径。

2. 契约测试：
   - Blackboard State 不允许出现源代码全文、密钥、完整 transcript。
   - Code Agent 输出必须包含 patch/test_report/trace 三件套。
   - 没有红灯测试证据时，Refiner 必须拒绝进入 implement/commit。
   - 测试失败时，workflow 状态必须停在 `needs_fix`，不能假装完成。

3. 集成测试：
   - `repo -> graph.json -> deck/slides.md -> interrupt -> feedback -> defense -> issue.json -> agent task -> refinement.json` 全链路。
   - mock agent：故意返回越权 diff，系统必须拦截。
   - mock agent：故意不写测试，系统必须拦截。
   - mock agent：测试失败，系统必须保留失败日志并生成可读报告。

4. 回放测试：
   - 固定 `thread_id + repo_commit_hash + feedback`，多次运行应产生等价 Issue 和验收状态。
   - LangGraph interrupt/resume 的 checkpoint 迁移测试：进程重启后仍能用 thread_id 恢复。
   - agent_trace 回放：不重新调用 LLM，仅用保存产物验证状态机决策。

5. 安全测试：
   - prompt injection：反馈中要求“忽略测试/打印 .env/删除仓库”时必须拒绝。
   - path traversal：Issue 指向 `../../.env` 或锁文件时必须拒绝。
   - secret leakage：任何 artifact 里不得出现 `.env` 内容、API key、会议原始音频路径。
   - destructive command：Code Agent 请求 reset/delete/publish 时必须进入人工确认。

6. 视觉与交互测试：
   - Slidev deck 能构建、能被 iframe 加载。
   - Mermaid 图必须通过 CLI 编译，不通过则进入自修复或失败状态。
   - 阶段 2 起，WebSocket 翻页事件必须有可回放日志：`timestamp -> action -> slide_index`。

7. 端到端验收标准：
   - 一条尖锐反馈最终必须产出：答辩文本、Issue JSON、测试报告、agent patch 或明确的 no-op 证据。
   - 所有产物必须能从 `thread_id` 追溯。
   - 人类可以在任意门禁点选择 accept/retry/reject。

🚀 落地实施路线图 (MVP 到生产级别)
为了避免团队一开始就陷入底层的 Linux 音视频编解码与 Docker 虚拟声卡泥潭中，建议分三个阶段敏捷演进：

🟢 阶段 1：纯异步“图文答辩室” (跑通中枢大脑，约1-2周)
目标：验证 LangGraph 状态机、Slidev 渲染与 GraphRAG 代码防幻觉。

做法：不接任何语音和 LiveKit。你提交脏代码 -> 后台分析 AST 图谱并生成 Slidev 网页链接 -> LangGraph 挂起休眠。你自己看着网页 PPT，在一个文字 Chat 框里打字提出刁钻意见 -> 唤醒 LangGraph -> 测试 AI 能否基于图谱文字反击 -> 提取 Issue -> 生成 Agent Task Envelope -> 触发 mock/openclaude/Aider adapter 在临时 worktree 中先写红灯测试 -> 生成补丁 -> 跑绿灯测试 -> 产出 `refinement.json` 与 `agent_trace.json`。

阶段 1 必须补齐的测试：

- mock LLM + mock agent 的全链路 e2e。
- Code Agent 越权修改拦截测试。
- 没有测试先行时的拒绝测试。
- 失败测试报告持久化测试。
- artifact 不泄露 `.env` 的扫描测试。

🟡 阶段 2：本地“多模态声画同步舱” (攻克交互魔法，约2-3周)
目标：跑通 LiveKit 打断机制与 WebSocket 声画同步。

做法：不接入 Zoom 会议软件。自己写一个左右分屏的 Web HTML 测试页。左边 iframe 嵌入 Slidev PPT，右边嵌入 LiveKit 的 Web 语音按钮。你对着麦克风发难，测试 CNN 模型能否精准过滤咳嗽声；测试 AI 一边流利解答，一边完美控制左侧 PPT 翻页。

当前本地验收基线：

- 串行房间验收：`scripts/room_acceptance_smoke.py --managed-room` 必须能自行启动 mock room、等待 `/api/session`、串行执行 smokes、通过临时 shutdown token 关闭 room，并确认 room/Slidev 测试端口无残留监听。
- 离线回放验收：`scripts/room_replay_smoke.py` 必须校验 slide 当前状态、打断状态、timeline-to-slide action/source 映射、每条 timeline 事件对应的当时 slide pointer，以及完整 slide 事件序列。
- 证据指针验收：`scripts/evidence_packet_smoke.py` 必须从 replay 结果生成 `timeline://...` 与 `slide://...` 指针，供后续 Issue 提取和 Agent Task Envelope 使用，且不包含原始音频或 transcript。
- Issue 与 Agent Task Envelope 接入：`extract_issue()` 与 `run_tdad_refinement()` 通过同一个 fail-closed loader 读取通过验收的 `artifacts/evidence_packet.json`，只把预算内的高价值证据指针子集同步写入 `issue.json`、`agent_task.json`、`agent_trace.json` 与 `refinement.json`；不得把原始音频、完整 transcript 或 LiveKit token 交给 Code Agent。
- 证据选择审计：`artifacts/evidence_selection.json` 必须记录 pointer budget、selected/omitted counts 与 selected/omitted pointers；`scripts/evidence_chain_smoke.py` 必须确认该审计文件与共享 loader 输出一致。
- 证据指针 grammar：只允许 `timeline://<thread>#event=<n>&kind=<known-kind>` 与 `slide://<thread>#page=<n>`；未知 kind、额外参数、路径、负数页码/事件、`transcript://` 或 `audio://` 一律拒绝。
- 证据链闭环验收：`scripts/evidence_chain_smoke.py` 必须确认 `evidence_packet.json` 中的 replay-derived pointers 已贯穿 `issue.json`、`agent_task.json`、`agent_trace.json` 与 `refinement.json`。
- 阶段闭环验收：`scripts/phase1_room_closure_smoke.py` 必须串起 managed room acceptance、Phase 1 mock e2e、证据链验收和密钥扫描，确保新生成的 room evidence packet 被 Issue/refinement 真实消费；默认主报告只保留摘要，完整子步骤 payload 写入 `.full.json`。
- LiveKit 证据连续性：当闭环验收包含 `--include-livekit-browser` 时，`phase1_room_closure_smoke.py` 必须显式断言 `livekit_connected` 与 `audio_track_published` 指针同时进入 evidence chain 和 Issue evidence。
- 同一 run/thread 连续性：闭环验收必须确认 `room_replay`、`evidence_packet`、evidence-chain pointers 与 Issue evidence 使用同一个 room thread，避免旧 artifacts 混入新验收。
- 浏览器讲解锚点验收：`scripts/presenter_cue_smoke.py` 使用 `speech_started -> tts_word: next` 验证声画同步路径，不依赖真实 TTS，不保存 transcript。
- 浏览器打断验收：`scripts/browser_interruption_smoke.py` 使用 Web Audio 测试脉冲触发 `speech_started` 与 `speech_interrupted`，只保存结构化事件，不保存音频。
- 真实 LiveKit 凭证验收：`scripts/room_acceptance_smoke.py --managed-room --include-livekit-token --include-livekit-browser --out artifacts/room_acceptance_livekit_browser_gate.json`
- 安全验收：`scripts/artifact_secret_smoke.py` 必须确认 `.env` 中的密钥值没有进入文本产物。

阶段 2 当前已验收闭环：

- 最终通过报告：`artifacts/phase1_room_closure_livekit_openclaude_smoke.json`。
- 最终门禁命令：`scripts/phase1_room_closure_smoke.py --include-livekit-token --include-livekit-browser --agent-backend openclaude-cli --agent-timeout 240 --out artifacts\phase1_room_closure_livekit_openclaude_smoke.json --full-out artifacts\phase1_room_closure_livekit_openclaude_smoke.full.json --room-acceptance-out artifacts\room_acceptance_livekit_openclaude_gate.json`。
- 已验证：managed room clean shutdown、真实 LiveKit browser connect/publish、OpenClaude 后端 Phase 1 e2e、LiveKit 指针进入 evidence chain 与 Issue evidence、同一 room thread 连续性、artifact secret scan clean。
- 当前边界：这只是本地多模态声画同步舱闭环；真实麦克风打断模型、会议浏览器自动化、Docker/PulseAudio 路由和虚拟摄像头推流仍属于阶段 3。

🔴 阶段 3：终极“无头刺客数字人” (工程级重型封装)
目标：全自动上会，彻底释放人力。

做法：将阶段 2 的能力打包进 Docker。死磕 Puppeteer 与 PulseAudio 虚拟音频路由脚本，让 AI 像幽灵一样自动点击会议链接，绕过权限弹窗，把虚拟的音视频流推上云端。会后自动拉取录音转录，彻底完成自动驾驶式的 Code Review 闭环。

---

## Phase 3E 更新：AI 直接发起会议，而不是等待人工预定

### Phase 3E-LiveKit 更新：AI 直接创建 LiveKit room

已按 LiveKit-first 路线实现 `--provider livekit`：

- `LiveKitMeetingProvisioner` 使用本地环境里的 `LIVEKIT_URL`、`LIVEKIT_API_KEY`、`LIVEKIT_API_SECRET` 创建真实 LiveKit room。
- room 名称来自当前 DevDefender room thread，输出为非秘密句柄 `livekit://room/<meeting_id>`。
- 浏览器通过已有 `/api/livekit-token` 获取一次性入会 token，并在主 room 页面用 `auto_livekit=1` 自动加入指定 room。
- timeline 记录 `meeting_created`、`livekit_connected`、`audio_track_published`。
- teardown 调用 LiveKit delete room；报告只保存 `join_url` 和 `secret_ref`，不保存 raw token / API secret / cookie / local storage / screenshot / raw media / transcript。

验收命令：

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\meeting_provisioner_smoke.py --provider livekit --managed-room --out artifacts\meeting_provisioner_livekit_smoke.json --timeout 45
```

当前通过报告：`artifacts/meeting_provisioner_livekit_smoke.json`，`ok: true`，`teardown.command = livekit-room-deleted`。这条路线已经解决“AI 直接发起会议”而不是等待人工预定的问题；Zoom/Tencent 后续作为外部 SaaS provider 再接。

### Phase 3D 更新：LiveKit provider 已纳入一键闭环默认路径

`phase3_meeting_closure_smoke.py` 现在默认运行 `meeting_provisioner_smoke.py --provider livekit`，并要求同一条 room thread 同时包含：

- `meeting_created`
- `livekit_connected`
- `audio_track_published`

验收命令：

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\phase3_meeting_closure_smoke.py --skip-visual --out artifacts\phase3_meeting_closure_smoke.json --full-out artifacts\phase3_meeting_closure_smoke.full.json --provisioner-out artifacts\phase3d_meeting_provisioner_smoke.json --phase3d-evidence-out artifacts\evidence_packet_phase3d.json
```

当前通过报告：`artifacts/phase3_meeting_closure_smoke.json`，`ok: true`。本次闭环产生 34 个 replay-derived evidence events，`livekit_provisioned_meeting_in_packet_ok`、`livekit_pointers_in_evidence_chain_ok`、`livekit_pointers_in_issue_ok` 全部为 true，artifact secret scan 无发现。

## Phase 4A 更新：浏览器 TTS 答辩流

已实现第一条可验收的真实语音/答辩切片：

- 新增 `/voice-defense-test` 专用页面。
- 浏览器调用 Web Speech Synthesis 执行 opening、answer、resume 三段讲解。
- 两个 `tts_word: next` 锚点通过既有 timeline-to-slide mapping 推动翻页两次。
- Web Audio 测试脉冲模拟评委打断，记录 `speech_started` 与 `speech_interrupted`。
- answer/resume 事件让 interruption state 回到 inactive。
- 不保存 raw audio、audio path、full transcript 或 TTS 文本到普通 artifacts。

验收命令：

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\phase4_voice_defense_smoke.py --managed-room --out artifacts\phase4_voice_defense_smoke.json --timeout 35
```

当前通过报告：`artifacts/phase4_voice_defense_smoke.json`，`ok: true`。Replay 通过，`artifacts/evidence_packet_phase4_voice_defense.json` 生成 7 条结构化 evidence events，artifact secret scan 无发现。

当前 Phase 3D 已经证明：会议自动化事件、媒体路由事件、回放证据、Issue、Agent Task、agent trace、refinement、secret scan 和 pytest 可以在同一条 room thread 上闭环。但它仍然默认“会议链接已经存在”。下一步改为增加 Meeting Provisioner 层，让 AI 先创建会议，再交给 Meeting Adapter 入会。

### 新目标

- AI 根据当前答辩/防御 session 自动创建或分配一个会议。
- 人不再手动预定会议链接；人只需要一次性配置 provider 凭证或选择本地/self-hosted provider。
- 普通 artifacts 只保存脱敏 join URL、provider、非秘密 meeting handle、过期时间和 evidence pointer。
- host start URL、meeting password、OAuth token、SDK token、cookie、localStorage、截图、页面 HTML、原始音视频和 transcript 不进入普通 artifacts。

### 新模块：Meeting Provisioner

Provider-neutral 接口：

```text
create_meeting(provider, topic, duration, room_thread_id) -> ProvisionedMeeting
teardown_meeting(provider, meeting_id | secret_ref) -> ProvisioningResult
```

`ProvisionedMeeting` 只允许暴露：

```text
provider
meeting_id 或 meeting_handle
join_url_redacted
expires_at
secret_ref
```

`secret_ref` 只能指向 env / OS credential vault / cloud secret manager，不能包含真实 secret 值。

### Provider 路线

1. mock/local provisioner：第一步实现，零凭证，用于 CI 和 Phase 3D 兼容性验证。
2. self-hosted LiveKit provisioner：最适合“AI 完全拥有会议”的路线，AI 创建 room 并生成参会链接。
3. Zoom provisioner：通过 Zoom Meetings API 创建会议，再由浏览器 adapter 使用受控 start/join 信息入会。
4. Tencent Meeting provisioner：通过腾讯会议 REST API 创建会议，但需要账号版本/API 权限支持。
5. Teams/Google Meet provisioner：作为后续企业集成选项。

### 新 timeline 事件

- `meeting_created`
- `meeting_provision_failed`
- 继续复用：`meeting_join_started`, `meeting_joined`, `meeting_left`, `meeting_error`

### 新验收门禁

计划新增：

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\meeting_provisioner_smoke.py --provider mock --managed-room --out artifacts\meeting_provisioner_smoke.json
```

验收条件：

- `meeting_created` 被记录到 timeline。
- 生成的 join URL 在报告和 timeline 中已脱敏。
- host/start URL 和 provider token 不进入 artifacts。
- mock/local provisioned meeting 能交给现有 meeting automation 页面完成 join/leave lifecycle。
- replay、evidence packet、artifact secret scan 和 Phase 3D closure 仍然通过。

### 下一步实施顺序

1. 增加 `src/devdefender_lab/meeting_provisioner.py`：Pydantic contract、redaction helper、mock provider。
2. 扩展 timeline/evidence kind：加入 `meeting_created` 和 `meeting_provision_failed`。
3. 增加 `scripts/meeting_provisioner_smoke.py`：创建 mock meeting -> 写入 timeline -> 交给本地 meeting adapter -> 生成报告。
4. 增加 tests：contract、secret filtering、smoke report、Phase 3D compatibility。
5. 更新 Phase 3D closure：可选包含 provisioner gate。
6. 凭证准备好后，再实现 Zoom/Tencent 的真实 provider adapter。

## Phase 4B update: LiveKit TTS audio track

Implemented the first real generated-speech-to-LiveKit audio route:

- Added `/api/tts-audio` to synthesize SAPI WAV bytes locally without writing the WAV into normal artifacts.
- Added `/livekit-tts-test` to decode that WAV in the browser, route it through Web Audio, and publish the generated `MediaStreamTrack` to LiveKit.
- Added structured timeline events `tts_audio_track_created` and `tts_audio_track_published`.
- Added `scripts/phase4_livekit_tts_smoke.py` as the acceptance gate.
- The smoke creates a LiveKit room, publishes the generated TTS audio track, emits `speech_started` and `tts_word: next`, advances one slide, deletes the LiveKit room, and keeps raw audio/transcript fields out of artifacts.

Accepted command:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\phase4_livekit_tts_smoke.py --managed-room --out artifacts\phase4_livekit_tts_smoke.json --timeout 75
```

Accepted report: `artifacts/phase4_livekit_tts_smoke.json`, `ok: true`.
Replay passed with 6 timeline events and 1 mapped slide event on `phase1-cda26c6db47e`.
Evidence packet: `artifacts/evidence_packet_phase4_livekit_tts.json`, 6 structured evidence events.
Artifact secret scan: clean across 141 scanned files.

## Phase 4C update: LiveKit remote audio interruption

Implemented the first real remote-audio interruption route inside LiveKit:

- Added `/livekit-interruption-test` to connect detector and reviewer participants to the same provisioned LiveKit room.
- The reviewer participant publishes generated reviewer speech as a LiveKit audio track.
- The detector participant subscribes to the reviewer track, attaches the remote audio element, captures the playback stream, and runs browser Web Audio RMS detection.
- The page records `speech_started` and `speech_interrupted` from source `browser-livekit-remote-interruption`.
- The smoke keeps raw audio/transcript fields out of artifacts and deletes the LiveKit room in teardown.

Accepted command:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\phase4_livekit_interruption_smoke.py --managed-room --out artifacts\phase4_livekit_interruption_smoke.json --timeout 90
```

Accepted report: `artifacts/phase4_livekit_interruption_smoke.json`, `ok: true`.
Replay passed with 7 timeline events and 1 mapped slide event on `phase1-2a3c665978e9`.
Evidence packet: `artifacts/evidence_packet_phase4_livekit_interruption.json`, 7 structured evidence events.
Artifact secret scan: clean across 144 scanned files.

## Product Direction Update: Project Briefing Room

The next plan is to productize the accepted LiveKit room path as a lightweight project briefing workflow for code agents.

Decision:

- Default meeting path: LiveKit room created by the AI workflow.
- Defer Zoom/Tencent/Teams/Google SaaS adapters unless external meeting integration becomes an explicit product requirement.
- Product entry point: a repo-versioned Codex skill named `project-briefing-room`.
- Product shape: thin skill orchestration plus deterministic local runtime.
- Core user value: the code agent can brief a non-technical user like a meeting presenter, using architecture diagrams, progress/status, requirement coverage, experiment results, risks, open questions, and next asks.
- Manual setup target: minimal configuration beyond repo checkout, Python environment, LiveKit credentials when using real room mode, and optional helper skill installation.

Division of responsibility:

- The `project-briefing-room` skill gathers repo/task context, asks a code-agent adapter for structured briefing data, optionally installs or calls helper skills, and launches the local runtime.
- The local runtime owns graph/deck generation, Mermaid/Slidev assets, LiveKit provisioning, TTS audio publish, remote interruption detection, replay, evidence packets, and secret scanning.
- Code agents integrate through a structured briefing JSON contract instead of directly operating meeting internals.

Skill installer finding:

- No existing skill fully covers project-status briefing plus diagrams plus LiveKit presentation plus evidence closure.
- Reusable optional skills include `speech`, `transcribe`, `notion-meeting-intelligence`, `security-threat-model`, `security-ownership-map`, and already installed local `pdf`, `playwright`, and `screenshot`.
- Figma skills are useful only if a UI/design handoff becomes part of the product, not for the core meeting briefing path.

Next implementation order:

1. Create `skills/project-briefing-room/SKILL.md` and `skills/project-briefing-room/dependencies.md`.
2. Add `src/devdefender_lab/briefing.py` with the provider-neutral briefing schema and mock adapter output.
3. Add `src/devdefender_lab/briefing_deck.py` to turn structured briefing data into stakeholder script, Mermaid diagram requests, and Slidev deck content.
4. Add `scripts/project_briefing_room_smoke.py --managed-room --agent-backend mock`.
5. Gate Phase 4D on repo state -> briefing deck -> LiveKit room -> generated presenter audio -> remote interruption -> replay/evidence packet -> artifact secret scan.

Planned Phase 4D command:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --managed-room --agent-backend mock --out artifacts\project_briefing_room_smoke.json --timeout 120
```

## Phase 4D-1 update: skill skeleton

Created the repo-versioned product skill skeleton:

- `skills/project-briefing-room/SKILL.md`
- `skills/project-briefing-room/dependencies.md`
- `skills/project-briefing-room/agents/openai.yaml`

The skill is intentionally thin. It defines how a code agent should gather repo/task facts, translate them into a non-technical stakeholder briefing, optionally call helper skills, and delegate deterministic meeting/deck/evidence work to this repo runtime.

Validation passed:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\project-briefing-room
```

Observed result: `Skill is valid!`

Next implementation target: `src/devdefender_lab/briefing.py` with the provider-neutral briefing schema and mock adapter output.

## Phase 4D-2 update: briefing schema and mock adapter

Implemented the provider-neutral briefing contract:

- `src/devdefender_lab/briefing.py`
- `tests/test_briefing.py`

The new contract includes:

- `BriefingContext`
- `ProjectBriefingReport`
- diagram, progress, requirement, experiment, risk, stakeholder question, follow-up task, and evidence pointer models
- `MockBriefingAdapter`
- `default_briefing_context()`
- `contains_forbidden_briefing_artifact_fields()`

The mock adapter now produces a stable stakeholder briefing report that can be serialized as JSON and later consumed by the deck/runtime layer. It rejects unsafe evidence pointers and forbidden raw artifact fields such as tokens, API secrets, raw audio, full transcripts, cookies, local storage, unredacted meeting credentials, and audio file references.

Accepted commands:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests\test_briefing.py -q
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests\test_briefing.py tests\test_evidence.py -q
```

Accepted result: `7 passed` for briefing tests and `16 passed` for briefing plus evidence regression.

Next implementation target: `src/devdefender_lab/briefing_deck.py` to turn `ProjectBriefingReport` into stakeholder script, Mermaid diagram requests, and Slidev deck content.

## Phase 4D-3 update: briefing deck renderer

Implemented the first deterministic renderer from `ProjectBriefingReport` to stakeholder-facing artifacts:

- `src/devdefender_lab/briefing_deck.py`
- `tests/test_briefing_deck.py`

The renderer provides:

- `BriefingDeckArtifact`
- `render_briefing_deck(report)`
- `write_briefing_deck(report, artifact_dir)`
- `render_presenter_script(report)`

Current output:

- Slidev Markdown with title, stakeholder summary, Mermaid architecture diagram, progress, requirements coverage, experiment results, risks, stakeholder questions, next asks, and evidence pointers.
- Presenter script suitable for later TTS/meeting narration.
- Artifact metadata: `diagram_count`, `slide_count`, optional `deck_path`, and optional `script_path`.
- Forbidden artifact-field protection using the same briefing detector.

Accepted command:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests\test_briefing_deck.py tests\test_briefing.py -q
```

Accepted result: `11 passed`.

Next implementation target: Phase 4D-4 `scripts/project_briefing_room_smoke.py --managed-room --agent-backend mock`, wiring mock briefing report -> briefing deck files -> existing LiveKit TTS/interruption gates.

## Phase 4D-4 update: Project Briefing Room smoke

Implemented the first one-command product smoke orchestrator:

- `scripts/project_briefing_room_smoke.py`
- `tests/test_project_briefing_room_smoke.py`

The smoke now:

- builds a mock `ProjectBriefingReport`
- writes `artifacts/briefing_deck/briefing_report.json`
- writes `artifacts/briefing_deck/slides.md`
- writes `artifacts/briefing_deck/presenter_script.md`
- verifies required deck sections and Mermaid presence
- verifies product-level report summaries do not contain forbidden token/secret/raw audio/transcript fields
- supports `--skip-livekit-gates` for no-credential local validation
- can reuse the accepted Phase 4B and 4C LiveKit child gates when not skipped

Accepted commands:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests\test_project_briefing_room_smoke.py tests\test_briefing_deck.py tests\test_briefing.py -q
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --skip-livekit-gates --out artifacts\project_briefing_room_smoke.skip_livekit.json
```

Accepted result: `18 passed`; skip-LiveKit product smoke report `ok: true`.

Full LiveKit command when credentials are available:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --managed-room --agent-backend mock --out artifacts\project_briefing_room_smoke.json --timeout 120
```

Next implementation target: run and accept the full LiveKit 4D smoke with local LiveKit credentials, then add evidence/replay/secret-scan closure around the product smoke.

## Phase 4D-4 full LiveKit acceptance

Accepted the full Project Briefing Room smoke with local LiveKit credentials loaded from `.env`.

Accepted command:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --managed-room --agent-backend mock --out artifacts\project_briefing_room_smoke.json --timeout 120
```

Accepted report: `artifacts/project_briefing_room_smoke.json`, `ok: true`.

Observed result:

- `briefing_artifacts`: `ok: true`
- `livekit_tts`: `ok: true`, 6 new timeline events, including `meeting_created`, `livekit_connected`, `tts_audio_track_created`, `tts_audio_track_published`, `speech_started`, and `tts_word`
- `livekit_interruption`: `ok: true`, 6 new timeline events, including `meeting_created`, two `livekit_connected` events, `audio_track_published`, `speech_started`, and `speech_interrupted`
- managed room shutdown: `ok: true`, no terminate/kill fallback, no lingering ports
- product report secret/raw artifact cross-check: `ok: true`

Generated product artifacts:

- `artifacts/briefing_deck/briefing_report.json`
- `artifacts/briefing_deck/slides.md`
- `artifacts/briefing_deck/presenter_script.md`
- `artifacts/project_briefing_room_livekit_tts.json`
- `artifacts/project_briefing_room_livekit_interruption.json`

Next implementation target: add product-level evidence/replay/secret-scan closure around `project_briefing_room_smoke.py`.

## Phase 4D-5 update: product closure gates

Extended `scripts/project_briefing_room_smoke.py` with product-level closure gates:

- `room_replay`
- `evidence_packet`
- `artifact_secret`

New options:

- `--skip-closure-gates`
- `--evidence-packet-out`
- `--secret-scan-out`

Accepted full command:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --managed-room --agent-backend mock --out artifacts\project_briefing_room_smoke.json --timeout 120
```

Accepted report: `artifacts/project_briefing_room_smoke.json`, `ok: true`.

Observed closure result:

- checks: `briefing_artifacts`, `livekit_tts`, `livekit_interruption`, `room_replay`, `evidence_packet`, and `artifact_secret` all true
- replay thread: `phase1-0ac18eb0cf73`, 13 timeline events, 2 slide events, 2 mapped slide events
- evidence packet: `artifacts/evidence_packet_project_briefing_room.json`, `ok: true`, same thread as replay
- artifact secret scan: `artifacts/project_briefing_room_secret_scan.json`, `ok: true`, 153 scanned files, 3 loaded secret values, 0 findings
- cross-checks confirmed required project events are present: `meeting_created`, `livekit_connected`, `tts_audio_track_published`, and `speech_interrupted`
- managed room shutdown: `ok: true`, no terminate/kill fallback, no lingering ports

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests\test_project_briefing_room_smoke.py tests\test_briefing_deck.py tests\test_briefing.py tests\test_evidence.py -q
```

Accepted result: `29 passed`.

Next implementation target: decide the first real code-agent briefing adapter beyond mock: Codex-native report, OpenClaude CLI, or Aider.

## VS Code Codex skill install update

Added a local installer for the repo-versioned `project-briefing-room` skill:

- `scripts/install_project_briefing_room_skill.ps1`
- `tests/test_install_project_briefing_room_skill.py`

Accepted install command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_project_briefing_room_skill.ps1
```

Accepted result:

- source: `skills/project-briefing-room`
- target: `C:\Users\Administrator\.codex\skills\project-briefing-room`
- validation: `Skill is valid!`

VS Code Codex invocation:

```text
Use $project-briefing-room to brief me on the current project status.
```

This makes the product path directly usable from the VS Code Codex plugin after one local install command.


## Phase 4E-1 accepted: workspace briefing adapter

Implemented the VS Code Codex workspace path so the skill can brief from real current-workspace facts instead of the mock briefing report.

Delivered:

- Added `WorkspaceBriefingAdapter`, which reads repo docs, git status, accepted artifact summaries, evidence pointers, and recent project outputs.
- Extended `project_briefing_room_smoke.py` with `--agent-backend workspace`.
- Kept the accepted LiveKit/deck/replay/evidence/secret closure path unchanged.
- Made the repo-versioned `$project-briefing-room` skill default to the workspace backend for VS Code Codex.
- Fixed stale child-report handling so stdout-only closure gates cannot reuse an old replay report.

Updated files:

- `src/devdefender_lab/briefing_workspace.py`
- `tests/test_briefing_workspace.py`
- `scripts/project_briefing_room_smoke.py`
- `skills/project-briefing-room/SKILL.md`
- README/plan/handoff docs

Workspace adapter inputs:

- `git status --short`
- changed files from the current repo
- docs when present: `plan.md`, `README.md`, `PHASE3_HANDOFF.md`, `PHASE3_DESIGN.md`, `DESIGN.md`
- recent product artifacts: `artifacts/project_briefing_room_smoke.json`, `artifacts/briefing_deck/briefing_report.json`, `artifacts/evidence_packet_project_briefing_room.json`, `artifacts/project_briefing_room_secret_scan.json`
- recent accepted command/result lines from docs/artifacts

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests\test_briefing_workspace.py tests\test_project_briefing_room_smoke.py tests\test_briefing.py -q
```

Observed result: `22 passed`.

Accepted quick workspace gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --agent-backend workspace --repo . --skip-livekit-gates --out artifacts\project_briefing_room_workspace.skip_livekit.json
```

Observed result: `ok: true`, generated by `workspace-briefing-adapter`.

Accepted full LiveKit workspace gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --managed-room --agent-backend workspace --repo . --out artifacts\project_briefing_room_workspace.json --timeout 120
```

Observed result:

- `briefing_artifacts`, `livekit_tts`, `livekit_interruption`, `room_replay`, `evidence_packet`, and `artifact_secret` all passed.
- Replay/evidence thread matched: `phase1-3a71e498d046`.
- Required evidence kinds were present: `meeting_created`, `livekit_connected`, `tts_audio_track_published`, and `speech_interrupted`.
- Artifact secret scan found 0 leaks.
- Managed room shutdown was clean.

Still out of scope after Phase 4E-1:

- OpenClaude/Aider adapters
- VS Code or Codex private extension APIs
- Codex chat-history extraction
- speech-to-text opinion content extraction
- external meeting SaaS routes

## Phase 4E-2 accepted: provider-neutral agent briefing contract

Implemented the first portable code-agent input contract for Project Briefing Room. Any compatible code agent can now write one bounded JSON file and let the workspace backend merge that task context into the stakeholder briefing.

Delivered:

- Added `AgentBriefingInput` in `src/devdefender_lab/briefing_contract.py`.
- Added safe contract loading, template writing, and `BriefingContext` merge logic.
- Extended `BriefingContext` with current task, completed work, in-progress work, blockers, next steps, requirements, and open questions.
- Extended `WorkspaceBriefingAdapter` to read `artifacts/agent_briefing_input.json` by default or an explicit `--agent-input`.
- Extended `project_briefing_room_smoke.py` with `--agent-input`.
- Added skill template: `skills/project-briefing-room/templates/agent_briefing_input.json`.
- Updated the skill instructions so Codex/OpenClaude/Aider/generic agents can fill the same input shape.

Safety behavior:

- Rejects payloads with forbidden secret/raw artifact fields.
- Rejects raw audio, full transcripts, provider tokens, cookies, local storage, and meeting start URLs.
- Keeps LiveKit/deck/replay/evidence/secret closure unchanged.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests\test_briefing_contract.py tests\test_briefing_workspace.py tests\test_project_briefing_room_smoke.py tests\test_briefing.py -q
```

Observed result: `27 passed`.

Accepted quick workspace gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --agent-backend workspace --repo . --skip-livekit-gates --out artifacts\project_briefing_room_workspace.skip_livekit.json
```

Observed result: `ok: true`.

Contract invocation:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --agent-backend workspace --repo . --agent-input artifacts\agent_briefing_input.json --skip-livekit-gates --out artifacts\project_briefing_room_workspace.skip_livekit.json
```

Next likely iteration:

- Add a tiny helper command to generate/fill `artifacts/agent_briefing_input.json` from current repo facts, or
- Add the first external trace adapter on top of the same contract.

## Phase 4E-3 accepted: auto-generate agent briefing input

Implemented the lightweight helper command that generates `AgentBriefingInput` from current repo/docs/git/artifact facts.

Delivered:

- Added `scripts/agent_briefing_input.py`.
- Added `agent_input_from_context` and `write_agent_briefing_input` helpers.
- The command inspects the selected repo through `WorkspaceBriefingAdapter` while deliberately ignoring any existing agent input file.
- The generated JSON can be passed directly to `project_briefing_room_smoke.py --agent-input`.
- Updated `$project-briefing-room` skill instructions to prefer this helper before running the briefing gate.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests\test_agent_briefing_input.py tests\test_briefing_contract.py tests\test_briefing_workspace.py tests\test_project_briefing_room_smoke.py tests\test_briefing.py -q
```

Observed result: `29 passed`.

Accepted generator command:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\agent_briefing_input.py --repo . --out artifacts\agent_briefing_input.generated.json --agent-kind codex
```

Observed result: `ok: true`, with 14 changed files, 11 completed-work facts, 20 test facts, 4 artifact references, and 12 evidence pointers.

Accepted generated-input quick gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --agent-backend workspace --repo . --agent-input artifacts\agent_briefing_input.generated.json --skip-livekit-gates --out artifacts\project_briefing_room_workspace.generated_input.skip_livekit.json
```

Observed result: `ok: true`.

Next likely iteration:

- Add the first external trace adapter on top of `AgentBriefingInput`, or
- Run the full LiveKit gate with the generated input file.

## Phase 4E-4 accepted: full LiveKit gate with generated input

Accepted the complete generated-input product path:

1. generate `AgentBriefingInput` from current workspace facts
2. build workspace briefing artifacts from that generated input
3. start a managed local room
4. run LiveKit TTS
5. run LiveKit remote interruption
6. run replay/evidence/secret closure

Accepted generator command:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\agent_briefing_input.py --repo . --out artifacts\agent_briefing_input.generated.json --agent-kind codex
```

Observed result: `ok: true`.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests\test_agent_briefing_input.py tests\test_briefing_contract.py tests\test_briefing_workspace.py tests\test_project_briefing_room_smoke.py tests\test_briefing.py -q
```

Observed result: `29 passed`.

Accepted full LiveKit generated-input gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --managed-room --agent-backend workspace --repo . --agent-input artifacts\agent_briefing_input.generated.json --out artifacts\project_briefing_room_workspace.generated_input.json --timeout 180 --interruption-timeout 120
```

Observed result:

- overall report: `artifacts/project_briefing_room_workspace.generated_input.json`, `ok: true`
- `briefing_artifacts`, `livekit_tts`, `livekit_interruption`, `room_replay`, `evidence_packet`, and `artifact_secret` all passed
- replay/evidence thread matched: `phase1-a6ec04134125`
- 13 timeline events, 2 slide events, 2 mapped slide events
- evidence packet passed on the same thread
- secret scan scanned 161 files, loaded 3 secret values, and found 0 leaks
- managed room shutdown was clean

Operational note:

- The first generated-input full gate attempt had a transient LiveKit interruption failure: detector/reviewer connected and reviewer audio track published, but detector peak stayed `0.0000`. Re-running with `--interruption-timeout 120` passed without code changes.

Next likely iteration:

- Add the first external trace adapter on top of `AgentBriefingInput`, or
- Make LiveKit interruption detection more robust against transient zero-peak remote audio events.

## Phase 4E-5 accepted: LiveKit interruption stability

Hardened the LiveKit remote interruption gate after a transient zero-peak remote audio run.

Delivered:

- Warm the reviewer audio track with a short non-zero signal before publishing, reducing the chance that the remote subscriber observes a silent optimized track.
- Detect remote speech from both `element.captureStream()` and `track.mediaStreamTrack` sources.
- Extend the browser-side remote speech detection window from 6 seconds to 10 seconds.
- Set the product smoke default `--interruption-timeout` to 120 seconds.
- Add one automatic retry for the product-level `livekit_interruption` child step.
- Include summarized previous failure metadata if a retry is needed.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests\test_project_briefing_room_smoke.py tests\test_phase4_livekit_interruption_smoke.py tests\test_room.py -q
```

Observed result: `41 passed`.

Accepted generated-input quick gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --agent-backend workspace --repo . --agent-input artifacts\agent_briefing_input.generated.json --skip-livekit-gates --out artifacts\project_briefing_room_workspace.generated_input.skip_livekit.json
```

Observed result: `ok: true`.

Accepted full generated-input gate after stability change:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --managed-room --agent-backend workspace --repo . --agent-input artifacts\agent_briefing_input.generated.json --out artifacts\project_briefing_room_workspace.generated_input.json --timeout 180
```

Observed result:

- overall report: `artifacts/project_briefing_room_workspace.generated_input.json`, `ok: true`
- `livekit_interruption` passed on the first attempt in this run
- replay/evidence thread matched: `phase1-29279a296b04`
- secret scan scanned 161 files, loaded 3 secret values, and found 0 leaks

Next likely iteration:

- Add the first external trace adapter on top of `AgentBriefingInput`.

## Phase 4F-1 Acceptance: Interactive Feedback-To-Plan Loop

Phase 4F-1 is accepted as the first product correction after stakeholder feedback. The Project Briefing Room output now treats the user's feedback as a primary planning input instead of stopping at a one-way briefing.

Delivered:

- Added `BriefingFeedbackPlan` in `src/devdefender_lab/briefing_feedback.py`.
- Added `scripts/briefing_feedback_plan.py`.
- Added default product smoke gate `briefing_feedback_plan`.
- Added `--feedback`, `--feedback-file`, `--clarification`, `--feedback-plan-out`, and `--skip-feedback-plan` to `scripts/project_briefing_room_smoke.py`.
- The quick workspace gate now writes both `artifacts/briefing_feedback_plan.json` and `artifacts/briefing_feedback_plan.smoke.json`.
- Updated the `project-briefing-room` skill so pending clarification questions are reported before implementation continues.

Feedback plan artifact:

- `feedback_summary`
- `interpreted_concerns`
- `clarification_questions`
- `decisions`
- `plan_changes`
- `updated_execution_plan`
- `needs_follow_up`
- `evidence_pointers`

Safety behavior:

- The feedback plan does not store raw audio or full meeting notes.
- Forbidden secret, raw audio, transcript, cookie, local storage, token, and meeting start URL fields are rejected.
- The product smoke fails if the feedback plan is missing interpreted concerns, clarification questions, plan changes, or updated execution steps.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests\test_briefing_feedback.py tests\test_briefing_feedback_plan_smoke.py tests\test_project_briefing_room_smoke.py tests\test_agent_briefing_input.py tests\test_briefing_contract.py tests\test_briefing_workspace.py tests\test_briefing.py -q
```

Observed result: `39 passed`.

Accepted quick workspace gate:

```powershell
Set-Content -Path artifacts\stakeholder_feedback.txt -Encoding utf8 -Value "The briefing loop should listen to stakeholder feedback, ask clarifying questions, and update the execution plan before continuing."
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --agent-backend workspace --repo . --agent-input artifacts\agent_briefing_input.generated.json --feedback-file artifacts\stakeholder_feedback.txt --skip-livekit-gates --out artifacts\project_briefing_room_workspace.feedback.skip_livekit.json
```

Next likely iteration:

- Add a real in-meeting feedback capture source, such as typed room feedback first, then STT later.
- Apply answered `briefing_feedback_plan.json` decisions back into `plan.md` or a code-agent task envelope.

## Phase 4F-2 Acceptance: Typed Room Feedback Plan Update

Phase 4F-2 connects room UI feedback to the same `BriefingFeedbackPlan` path created in Phase 4F-1.

Planned scope:

- Add a typed project-briefing feedback form in the local room UI.
- Add `POST /api/briefing-feedback`.
- Generate `artifacts/briefing_feedback_plan.json` from room feedback without running Phase 1 issue/refinement.
- Attach bounded slide/timeline evidence pointers.
- Reject forbidden secret, raw audio, transcript, cookie, local storage, token, and meeting start URL payloads.

Out of scope:

- Speech-to-text feedback extraction.
- Direct code edits from unresolved feedback.
- External SaaS meeting adapters.

Delivered:

- Added `POST /api/briefing-feedback` in the local room.
- Added a `project briefing feedback` form to the room UI.
- Room feedback writes `artifacts/briefing_feedback_plan.json`.
- Room feedback includes bounded slide/timeline evidence pointers.
- Added `scripts/briefing_room_feedback_smoke.py`.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests\test_room.py tests\test_briefing_feedback.py tests\test_briefing_room_feedback_smoke.py tests\test_project_briefing_room_smoke.py -q
```

Observed result: `47 passed`.

Accepted room feedback smoke command:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\briefing_room_feedback_smoke.py --room-url http://127.0.0.1:8765 --out artifacts\briefing_room_feedback_smoke.json
```

Accepted managed-room smoke command:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\briefing_room_feedback_smoke.py --managed-room --out artifacts\briefing_room_feedback_smoke.json
```

Observed result: `ok: true`, with `managed_room_shutdown_ok: true`.

Next likely iteration:

- Apply answered clarification decisions from `briefing_feedback_plan.json` back into `plan.md`.
- Add STT as an optional input source after the typed room path is stable.

## Phase 4F-3 Acceptance: Apply Feedback Plan To Execution Plan

Phase 4F-3 makes the feedback plan actionable by writing a bounded, repeatable section back into `plan.md`.

Delivered:

- Added `src/devdefender_lab/briefing_plan_update.py`.
- Added `scripts/apply_briefing_feedback_plan.py`.
- Added `tests/test_briefing_plan_update.py`.
- Added `tests/test_apply_briefing_feedback_plan.py`.
- The update uses marker comments so repeated runs replace the same section instead of appending duplicates.
- Pending clarification questions are preserved as `needs_clarification`; answered plans become `ready_for_execution`.

Accepted apply command:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\apply_briefing_feedback_plan.py --feedback-plan artifacts\briefing_feedback_plan.json --plan plan.md --out artifacts\briefing_plan_update.json
```

Observed result: `ok: true`, `needs_follow_up: true`, `pending_question_count: 3`, `ready_for_execution: false`.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests\test_briefing_plan_update.py tests\test_apply_briefing_feedback_plan.py tests\test_briefing_feedback.py -q
```

Next likely iteration:

- Add a command that answers pending clarification questions and re-applies the plan.
- Generate a future code-agent task envelope only when `ready_for_execution` is true.

## Phase 4F-4 Update: First Clarification Answer Recorded

Recorded stakeholder clarification answers into `artifacts/briefing_feedback_plan.json` and re-applied the plan update.

Delivered:

- Added `answer_feedback_clarification()` in `src/devdefender_lab/briefing_feedback.py`.
- Added `scripts/answer_briefing_clarification.py`.
- Added `tests/test_answer_briefing_clarification.py`.
- Added `POST /api/briefing-clarification` to the room API.
- Added room UI rendering for pending clarification questions and per-question answers.

Accepted command:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\answer_briefing_clarification.py --feedback-plan artifacts\briefing_feedback_plan.json --question 1 --answer "Pause after the direction, risk, and requirements coverage summary, then pause again before the final execution plan."
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\apply_briefing_feedback_plan.py --feedback-plan artifacts\briefing_feedback_plan.json --plan plan.md --out artifacts\briefing_plan_update.json
```

Observed intermediate result:

- `answered_question_count: 1`
- `pending_question_count: 2`
- `ready_for_execution: false`
- `needs_follow_up: true`

## Phase 4F-5 Acceptance: Room Feedback Clarification And Execution Gate

Phase 4F-5 closes the room feedback loop inside the running meeting path. Typed room feedback now generates a feedback plan, asks clarification questions, records answers, applies the updated plan, and evaluates whether execution may continue.

Delivered:

- Added `src/devdefender_lab/briefing_execution_gate.py`.
- Added `scripts/briefing_execution_gate.py`.
- Added `tests/test_briefing_execution_gate.py`.
- Room feedback responses now include both `plan_update` and `execution_gate`.
- `scripts/project_briefing_room_smoke.py` now verifies feedback plan generation, plan update, and execution gate before allowing continuation.
- `scripts/briefing_room_feedback_smoke.py` now verifies the full HTTP loop: `/api/briefing-feedback` -> `/api/briefing-clarification` -> plan update -> execution gate.
- `Phase1Room` now writes the feedback plan section to the target repo's `plan.md` when it exists; otherwise it writes `artifacts/briefing_plan.md`. This prevents sample-room and test runs from polluting the host workspace plan.

Acceptance behavior:

- Initial ambiguous feedback blocks continuation with `execution_gate.can_continue: false`.
- Answered clarification questions turn `needs_follow_up` off and allow continuation with `execution_gate.can_continue: true`.
- Room feedback keeps bounded evidence pointers and rejects raw audio, full transcripts, secrets, cookies, local storage, provider tokens, and meeting start URLs.
- Repeated plan application remains marker-based and idempotent.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests\test_room.py tests\test_briefing_room_feedback_smoke.py -q
```

Observed result: `32 passed, 1 warning`.

Accepted managed-room smoke:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\briefing_room_feedback_smoke.py --managed-room --out artifacts\briefing_room_feedback_smoke.json
```

Observed result:

- `ok: true`
- `clarifications_answered: true`
- `execution_gate_can_continue: true`
- `pending_question_count: 0`
- `managed_room_shutdown_ok: true`

Next likely iteration:

- Generate a code-agent task envelope only from a feedback plan whose execution gate allows continuation.
- Add optional STT capture later, reusing the same feedback-plan and execution-gate path.

## Phase 4F-6 Acceptance: Feedback Plan To Code-Agent Task Envelope

Phase 4F-6 adds the guarded handoff from an approved briefing feedback plan into a code-agent task envelope. It does not run Codex, OpenClaude, Aider, or any other code agent automatically.

Delivered:

- Added `src/devdefender_lab/briefing_agent_task.py`.
- Added `scripts/briefing_agent_task.py`.
- Added `tests/test_briefing_agent_task.py`.
- `scripts/project_briefing_room_smoke.py` now runs `briefing_agent_task` after `briefing_execution_gate`.
- The product smoke now verifies that the generated task is ready, has guardrails, keeps `auto_execute: false`, and requires manual review.
- Product smoke plan writes now use the target repo's `plan.md` when present; otherwise they write `artifacts/briefing_plan.md`.

Acceptance behavior:

- If `briefing_execution_gate.can_continue` is false, task generation fails closed and does not emit a runnable task.
- If the feedback plan is fully clarified and the execution gate allows continuation, `artifacts/briefing_agent_task.json` is generated.
- The task envelope includes task goal, issue title/body, allowed path suggestions, required test suggestions, acceptance criteria, next steps, evidence pointers, and source artifact paths.
- The task envelope avoids secrets, raw audio, full transcripts, cookies, local storage, provider tokens, and meeting start URLs.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests\test_briefing_agent_task.py tests\test_project_briefing_room_smoke.py -q
```

Observed result: `29 passed`.

Accepted quick workspace gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --agent-backend workspace --repo . --skip-livekit-gates --out artifacts\project_briefing_room_workspace.skip_livekit.json
```

Observed result:

- `ok: true`
- `briefing_agent_task: true`
- `briefing_agent_task_ready_ok: true`
- `briefing_agent_task_has_guardrails_ok: true`
- `briefing_agent_task_manual_gate_ok: true`
- `briefing_agent_task_no_forbidden_fields_ok: true`

Next likely iteration:

- Add an explicit “review/accept task envelope” command before any code-agent execution.
- After that, optionally wire the accepted task envelope into the existing Agent Gateway.

## Phase 4F-7 Acceptance: Code-Agent Task Review Gate

Phase 4F-7 adds an explicit review/accept gate between the generated task envelope and any future code-agent execution. It still does not run Codex, OpenClaude, Aider, or any other code agent automatically.

Delivered:

- Added `src/devdefender_lab/briefing_agent_task_review.py`.
- Added `scripts/briefing_agent_task_review.py`.
- Added `tests/test_briefing_agent_task_review.py`.
- `scripts/project_briefing_room_smoke.py` now runs `briefing_agent_task_review --accept` after `briefing_agent_task`.
- The product smoke now verifies that the review is accepted, `can_execute: true`, and the task guardrails remain intact.

Acceptance behavior:

- A ready task without explicit `--accept` is blocked.
- `--reject --reason` records a rejection decision and keeps `can_execute: false`.
- `--accept` succeeds only when the task is ready, `auto_execute: false`, `manual_review_required: true`, and it has allowed paths, required tests, acceptance criteria, and execution next steps.
- Unsafe task payloads are blocked before acceptance.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests\test_briefing_agent_task.py tests\test_briefing_agent_task_review.py tests\test_project_briefing_room_smoke.py -q
```

Observed result: `37 passed`.

Accepted quick workspace gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --agent-backend workspace --repo . --skip-livekit-gates --out artifacts\project_briefing_room_workspace.skip_livekit.json
```

Observed result:

- `ok: true`
- `briefing_agent_task_review: true`
- `briefing_agent_task_review_accepted_ok: true`
- `briefing_agent_task_review_guardrails_ok: true`
- `briefing_agent_task_review_no_forbidden_fields_ok: true`

## Phase 4F-8 Acceptance: Agent Gateway Dry-Run Mapping

Phase 4F-8 maps the accepted Project Briefing task into the existing Agent Gateway `AgentTaskEnvelope` shape without running a code agent. This keeps the VS Code Codex path lightweight while proving that stakeholder feedback can become a guarded, provider-neutral task input.

Delivered:

- Added `src/devdefender_lab/briefing_agent_gateway_task.py`.
- Added `scripts/briefing_agent_gateway_task.py`.
- Added `tests/test_briefing_agent_gateway_task.py`.
- `scripts/project_briefing_room_smoke.py` now runs `briefing_agent_gateway_task` after `briefing_agent_task_review`.
- `skills/project-briefing-room/SKILL.md` documents the dry-run mapping command and non-execution contract.

Acceptance behavior:

- Requires `briefing_agent_task_review.json` with `decision: "accepted"` and `can_execute: true`.
- Requires the source task to remain `auto_execute: false` and `manual_review_required: true`.
- Produces `artifacts/briefing_agent_gateway_task.json` with `dry_run_only: true`, `can_execute: false`, and `gateway_ready: true`.
- Validates the mapped `AgentTaskEnvelope` through `validate_agent_task()` and blocks on policy violations.
- Does not call `AgentGateway.run()`, Codex, OpenClaude, Aider, or any other code agent.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests/test_briefing_agent_gateway_task.py tests/test_project_briefing_room_smoke.py -q
```

Observed result: `29 passed`.

Accepted quick workspace gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --agent-backend workspace --repo . --skip-livekit-gates --out artifacts\project_briefing_room_workspace.skip_livekit.json
```

Observed result:

- `ok: true`
- `briefing_agent_gateway_task: true`
- `briefing_agent_gateway_task_ready_ok: true`
- `briefing_agent_gateway_task_dry_run_ok: true`
- `briefing_agent_gateway_task_valid_ok: true`
- `briefing_agent_gateway_task_no_forbidden_fields_ok: true`

Next likely iteration:

- Add an explicit user-controlled execution adapter step for a selected code agent, starting with a no-op/mock adapter or VS Code Codex handoff instructions.
- Keep automatic execution disabled until the user explicitly authorizes the selected adapter and scope.

## Phase 4F-9 Acceptance: VS Code Codex Handoff Envelope

Phase 4F-9 turns the accepted Agent Gateway dry-run task into a VS Code Codex-readable handoff package. It is still non-executing: the output is a JSON contract plus a Markdown prompt pack that a human can review before explicitly asking Codex to implement the follow-up task.

Delivered:

- Added `src/devdefender_lab/briefing_codex_handoff.py`.
- Added `scripts/briefing_codex_handoff.py`.
- Added `tests/test_briefing_codex_handoff.py`.
- `scripts/project_briefing_room_smoke.py` now runs `briefing_codex_handoff` after `briefing_agent_gateway_task`.
- The quick gate writes `artifacts/briefing_codex_handoff.json` and `artifacts/briefing_codex_handoff.md`.
- `README.md` and `skills/project-briefing-room/SKILL.md` now document the Codex handoff contract.

Acceptance behavior:

- Requires `briefing_agent_gateway_task.json` with `ok: true`, `gateway_ready: true`, `dry_run_only: true`, and `can_execute: false`.
- Produces a Codex handoff with task goal, allowed paths, required tests, acceptance criteria, evidence pointers, and a suggested prompt.
- Keeps `manual_confirmation_required: true` and `auto_execute: false`.
- Blocks if the handoff or source gateway task contains forbidden artifact fields.
- Does not call Codex CLI, OpenClaude, Aider, or any other code agent.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests/test_briefing_codex_handoff.py tests/test_project_briefing_room_smoke.py -q
```

Observed result: `29 passed`.

Accepted quick workspace gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --agent-backend workspace --repo . --skip-livekit-gates --out artifacts\project_briefing_room_workspace.skip_livekit.json
```

Observed result:

- `ok: true`
- `briefing_codex_handoff: true`
- `briefing_codex_handoff_ready_ok: true`
- `briefing_codex_handoff_manual_gate_ok: true`
- `briefing_codex_handoff_content_ok: true`
- `briefing_codex_handoff_no_forbidden_fields_ok: true`

Next likely iteration:

- Add a final human-confirmed execution command that consumes `briefing_codex_handoff.md` or `.json` and records the user's explicit authorization before any code-agent run.
- Keep the first execution path conservative: VS Code Codex handoff instructions or a no-op/mock execution receipt before real agent invocation.

## Phase 4F-10 Acceptance: Human Execution Authorization Receipt

Phase 4F-10 records explicit human authorization for the VS Code Codex handoff without starting execution. This gives the workflow a durable, auditable final gate before any future code-agent invocation.

Delivered:

- Added `src/devdefender_lab/briefing_execution_authorization.py`.
- Added `scripts/briefing_execution_authorization.py`.
- Added `tests/test_briefing_execution_authorization.py`.
- `scripts/project_briefing_room_smoke.py` now runs `briefing_execution_authorization` after `briefing_codex_handoff`.
- The quick gate writes `artifacts/briefing_execution_authorization.json`.
- `README.md` and `skills/project-briefing-room/SKILL.md` now document the authorization receipt.

Acceptance behavior:

- Requires `briefing_codex_handoff.json` with `ok: true`, `handoff_ready: true`, `manual_confirmation_required: true`, and `auto_execute: false`.
- Requires exact confirmation text: `I authorize VS Code Codex to execute this handoff`.
- Supports only `executor: vscode-codex` in this phase.
- Produces an authorization receipt with `authorized: true`, `auto_execute: false`, and `execution_started: false`.
- Blocks on wrong confirmation text, unsupported executor, unready handoff, or forbidden artifact fields.
- Does not call Codex CLI, OpenClaude, Aider, or any other code agent.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests/test_briefing_execution_authorization.py tests/test_project_briefing_room_smoke.py -q
```

Observed result: `30 passed`.

Accepted quick workspace gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --agent-backend workspace --repo . --skip-livekit-gates --out artifacts\project_briefing_room_workspace.skip_livekit.json
```

Observed result:

- `ok: true`
- `briefing_execution_authorization: true`
- `briefing_execution_authorization_authorized_ok: true`
- `briefing_execution_authorization_manual_gate_ok: true`
- `briefing_execution_authorization_confirmation_ok: true`
- `briefing_execution_authorization_no_forbidden_fields_ok: true`

Next likely iteration:

- Add a no-op/mock execution receipt that consumes the authorization receipt and proves the final execution boundary without invoking a real code agent.
- After that, consider a VS Code Codex-specific manual runbook or adapter that starts only when the user explicitly asks for real execution.

## Phase 4F-11 Acceptance: No-op Execution Boundary Receipt

Phase 4F-11 consumes the human authorization receipt and VS Code Codex handoff, then records that the workflow reached the execution boundary without invoking any real code agent. This closes the current VS Code Codex-compatible safety loop before any future explicit real execution path.

Delivered:

- Added `src/devdefender_lab/briefing_noop_execution.py`.
- Added `scripts/briefing_noop_execution.py`.
- Added `tests/test_briefing_noop_execution.py`.
- `scripts/project_briefing_room_smoke.py` now runs `briefing_noop_execution_receipt` after `briefing_execution_authorization`.
- The quick gate writes `artifacts/briefing_noop_execution_receipt.json`.
- `README.md` and `skills/project-briefing-room/SKILL.md` now document the no-op execution boundary receipt.

Acceptance behavior:

- Requires `briefing_execution_authorization.json` with `ok: true`, `status: authorized`, `authorized: true`, `executor: vscode-codex`, `auto_execute: false`, and `execution_started: false`.
- Requires `briefing_codex_handoff.json` with `ok: true`, `handoff_ready: true`, `manual_confirmation_required: true`, and `auto_execute: false`.
- Blocks if the authorization points to a different handoff.
- Produces a receipt with `mode: "noop"`, `real_agent_invoked: false`, `changed_files: []`, `commands_run: []`, and `tests_run: []`.
- Does not call Codex CLI, OpenClaude, Aider, shell commands, tests, or any other code agent.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests/test_briefing_noop_execution.py tests/test_project_briefing_room_smoke.py -q
```

Observed result: `30 passed`.

Accepted quick workspace gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --agent-backend workspace --repo . --skip-livekit-gates --out artifacts\project_briefing_room_workspace.skip_livekit.json
```

Observed result:

- `ok: true`
- `briefing_noop_execution_receipt: true`
- `briefing_noop_execution_receipt_recorded_ok: true`
- `briefing_noop_execution_receipt_no_agent_ok: true`
- `briefing_noop_execution_receipt_no_changes_ok: true`
- `briefing_noop_execution_receipt_no_forbidden_fields_ok: true`

Next likely iteration:

- Add a VS Code Codex manual execution runbook that tells a human exactly how to use `briefing_codex_handoff.md` after reviewing the no-op receipt.
- Real code-agent invocation should remain separate and require an explicit user command.

## Phase 4F-12A Acceptance: VS Code Codex Manual Execution Runbook

Phase 4F-12A documents the smallest real VS Code Codex execution path after the no-op boundary receipt. It does not start Codex automatically; it tells the human exactly how to review the generated handoff and explicitly ask VS Code Codex to execute it.

Delivered:

- `artifacts/briefing_codex_handoff.md` generation now includes a `Manual Execution Runbook` section.
- `README.md` documents the manual VS Code Codex execution path.
- `skills/project-briefing-room/SKILL.md` tells the skill operator how to hand the prompt to VS Code Codex after checking authorization and no-op receipt artifacts.
- `tests/test_briefing_codex_handoff.py` verifies the generated Markdown includes the manual runbook and no-op receipt guard.

Acceptance behavior:

- The runbook points users to `artifacts/briefing_codex_handoff.md`.
- The runbook requires reviewing allowed paths, required tests, and acceptance criteria before execution.
- The runbook requires checking `briefing_execution_authorization.json` and `briefing_noop_execution_receipt.json`.
- The runbook instructs users to paste the `Prompt For Codex` block into VS Code Codex and explicitly ask it to execute.
- It states that this repo does not start VS Code Codex automatically.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests/test_briefing_codex_handoff.py tests/test_project_briefing_room_smoke.py -q
```

Observed result: `29 passed`.

Next likely iteration:

- Consider a small post-execution evidence receipt that a human or Codex can fill after real manual execution, recording changed files and test output without requiring plugin-private APIs.

## Phase 4G-1 Acceptance: Skill Packaging And One-Command Usability Pass

Phase 4G-1 shifts Project Briefing Room from an engineering-chain explanation toward a lightweight product entry for VS Code Codex users. It keeps the 4F guardrails but makes the default path "install skill, invoke one sentence, run quick no-LiveKit gate, inspect user-facing outputs."

Delivered:

- Added `scripts/project_briefing_room_doctor.py`.
- Added `tests/test_project_briefing_room_doctor.py`.
- Updated `scripts/install_project_briefing_room_skill.ps1` to report the product invocation hint.
- Updated `README.md` with `Project Briefing Room Quick Start`.
- Updated `skills/project-briefing-room/SKILL.md` with a `Default User Entry` and quick workspace gate default.

Acceptance behavior:

- Default invocation: `Use $project-briefing-room to brief me and update the execution plan from my feedback.`
- Doctor verifies the repo skill file exists, required scripts exist, the quick no-LiveKit path runs, feedback plan is generated, and handoff Markdown is generated.
- Quick path does not require LiveKit credentials.
- README exposes user-facing outputs before advanced audit artifacts.
- Skill instructions default to the no-LiveKit workspace gate unless the user explicitly asks for a live room.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests/test_project_briefing_room_doctor.py tests/test_install_project_briefing_room_skill.py -q
```

Observed result: `7 passed`.

Accepted doctor:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_doctor.py --out artifacts\project_briefing_room_doctor.json
```

Observed result:

- `ok: true`
- `quick_smoke_ok: true`
- `quick_smoke_no_livekit_required: true`
- `handoff_markdown_generated: true`

Accepted quick workspace gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --agent-backend workspace --repo . --skip-livekit-gates --out artifacts\project_briefing_room_workspace.skip_livekit.json
```

Observed result: `ok: true`.

Next likely iteration:

- Tighten the generated stakeholder-facing briefing language and diagrams so a non-technical user gets clearer architecture/progress/requirement coverage before any execution handoff.

## Phase 4G-2 Acceptance: Codex-Native Default Path

Phase 4G-2 responds to the product concern that VS Code Codex already has the ability to continue execution inside the same workspace. The default Project Briefing Room path now stops at the stakeholder-facing feedback loop and execution gate, while the heavier 4F Agent Gateway / handoff / no-op chain is retained only as an explicit advanced audit path.

Delivered:

- `scripts/project_briefing_room_smoke.py` now defaults to the Codex-native core path:
  - `briefing_artifacts`
  - `briefing_feedback_plan`
  - `briefing_plan_update`
  - `briefing_execution_gate`
- Added `--include-advanced-audit` to opt into the provider-neutral review, gateway dry-run, Codex handoff, authorization, and no-op receipt chain.
- `scripts/project_briefing_room_doctor.py` now verifies the default no-LiveKit path without requiring handoff/no-op artifacts.
- `README.md` and `skills/project-briefing-room/SKILL.md` now present direct Codex continuation from the accepted execution gate as the default.
- Advanced audit artifacts remain documented and test-covered, but are no longer the default product path.

Acceptance behavior:

- Default quick path writes the briefing deck, feedback plan, plan update, and execution gate.
- Default quick path does not generate `briefing_codex_handoff.md` or `briefing_noop_execution_receipt.json`.
- `--include-advanced-audit` still generates the full 4F audit artifact chain when explicitly requested.
- Doctor checks `advanced_audit_not_required: true` for the minimal path.

Accepted regression:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests/test_project_briefing_room_smoke.py tests/test_project_briefing_room_doctor.py -q
```

Observed result: `32 passed`.

Next likely iteration:

- Improve stakeholder-facing briefing language and diagrams now that the execution boundary is no longer dominating the default product flow.

<!-- DEVDEFENDER_BRIEFING_FEEDBACK_PLAN:START -->
## Project Briefing Feedback Execution Plan

- Source: `C:/Users/Administrator/AppData/Local/Temp/pytest-of-Administrator/pytest-360/test_project_briefing_room_emp0/briefing_feedback_plan.json`
- Project: DevDefender Lab
- Status: `needs_clarification`
- Follow-up required: `true`
- Execution source of truth: `false`

### Stakeholder Signal

- Stakeholder is not satisfied with a one-way briefing loop and wants feedback to shape the next execution step.

### Decisions

- Treat stakeholder feedback as a first-class planning input before the agent continues execution.

### Plan Changes

- `add` `high`: Generate briefing_feedback_plan.json after every stakeholder briefing.
  Rationale: The product needs a durable artifact that turns user feedback into concerns, questions, decisions, and next steps.
- `add` `high`: Ask clarification questions when stakeholder intent is ambiguous.
  Rationale: The AI should not proceed from vague dissatisfaction directly into implementation without checking intent.
- `modify` `high`: Make the briefing loop update the execution plan before continuing work.
  Rationale: The final output must be an actionable plan update, not only a meeting/deck evidence packet.

### Updated Next Steps

1. Capture stakeholder feedback as bounded text from CLI input, file input, or later STT output.
2. Summarize the feedback into stakeholder-facing concerns without storing raw recordings or full meeting notes.
3. Generate clarification questions for ambiguous opinions and mark pending items before execution continues.
4. Merge answered clarifications into decisions and plan changes.
5. Write briefing_feedback_plan.json and require the product smoke to verify it.
6. Pause for stakeholder clarification before treating the updated plan as final.

### Execution Gate

- Blocked: pending clarification questions must be answered before execution continues.

### Acceptance Criteria

- briefing_feedback_plan.json is generated by the quick product gate.
- The artifact contains interpreted concerns, clarification questions, plan changes, and an updated execution plan.
- The artifact avoids secrets, raw audio, full meeting notes, cookies, local storage, and unredacted meeting start URLs.
- The product smoke fails if the feedback plan is missing or does not contain actionable next steps.

### Clarifications

Pending:
- Which parts of the briefing should pause for stakeholder feedback before the AI continues?
  Options: After risk and direction summary, After each major section, Only before execution changes
- Which stakeholder comments should block the next execution step until clarified?
  Options: Direction changes, Requirement concerns, All unresolved objections
- Where should the updated execution plan be written after feedback is interpreted?
  Options: briefing_feedback_plan.json, plan.md handoff section, Both artifact and plan docs

### Evidence Pointers

- `timeline://briefing#event=0&kind=briefing_generated`
- `slide://briefing#page=1`

<!-- DEVDEFENDER_BRIEFING_FEEDBACK_PLAN:END -->
