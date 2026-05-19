初始改造前code agent可以使用[Gitlawb/openclaude](https://github.com/Gitlawb/openclaude)

🌟 顶层编排设计：中心辐射型“黑板模式” (Hub-and-Spoke)
整个系统绝不能是一段从头跑到尾的 Python 脚本，而是一个支持“超长异步挂起”的分布式状态机。

编排大脑拼接：LangGraph + Pydantic。

超长异步挂起（HITL）：人类开会可能在代码提交后的几天。当系统备好 PPT 后，调用 LangGraph 的 interrupt() 机制与 Checkpointer (如 PostgresSaver)，进程瞬间持久化休眠，彻底释放服务器内存。会议结束后，收到 Webhook 带着 thread_id 携原图谱上下文精准唤醒。

防上下文爆炸契约：在全局黑板（Blackboard State）中，绝对禁止传递几万行的源代码全文。只流转结构化指针：agent_a_repo_commit_hash（代码版本指针）、slidev_url（幻灯片指针）以及 verified_architectural_decisions（人类确认后的共识记忆，防重构回退）。

🧩 四大子系统开源“物料清单”与缝合方案 (BOM & Stitching)
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

🚀 落地实施路线图 (MVP 到生产级别)
为了避免团队一开始就陷入底层的 Linux 音视频编解码与 Docker 虚拟声卡泥潭中，建议分三个阶段敏捷演进：

🟢 阶段 1：纯异步“图文答辩室” (跑通中枢大脑，约1-2周)
目标：验证 LangGraph 状态机、Slidev 渲染与 GraphRAG 代码防幻觉。

做法：不接任何语音和 LiveKit。你提交脏代码 -> 后台分析 AST 图谱并生成 Slidev 网页链接 -> LangGraph 挂起休眠。你自己看着网页 PPT，在一个文字 Chat 框里打字提出刁钻意见 -> 唤醒 LangGraph -> 测试 AI 能否基于图谱文字反击 -> 提取 Issue -> 触发 Aider 修改代码并生成红绿测试。

🟡 阶段 2：本地“多模态声画同步舱” (攻克交互魔法，约2-3周)
目标：跑通 LiveKit 打断机制与 WebSocket 声画同步。

做法：不接入 Zoom 会议软件。自己写一个左右分屏的 Web HTML 测试页。左边 iframe 嵌入 Slidev PPT，右边嵌入 LiveKit 的 Web 语音按钮。你对着麦克风发难，测试 CNN 模型能否精准过滤咳嗽声；测试 AI 一边流利解答，一边完美控制左侧 PPT 翻页。

🔴 阶段 3：终极“无头刺客数字人” (工程级重型封装)
目标：全自动上会，彻底释放人力。

做法：将阶段 2 的能力打包进 Docker。死磕 Puppeteer 与 PulseAudio 虚拟音频路由脚本，让 AI 像幽灵一样自动点击会议链接，绕过权限弹窗，把虚拟的音视频流推上云端。会后自动拉取录音转录，彻底完成自动驾驶式的 Code Review 闭环。