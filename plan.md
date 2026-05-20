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
