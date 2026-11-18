# Dify 业务接入 Demo

面向 AI 应用开发工程师的端到端示例，展示如何把 Dify 的 Agent、知识库、工具、文件/音频、人工审核和反馈能力接入自己的业务后端。示例使用 Python 标准库，不依赖 Dify SDK；所有业务订单都是假数据，退款接口只返回 `SIMULATED`，不会产生真实副作用。

截至 **2026-11-18**，官方 Releases 页面最近发布的版本为 **v1.19.0**（2026-11-04）。本项目主要调用公开 App API 和经典知识库 API，不依赖 v1.19.0 专属字段。Cloud、自托管和套餐间的功能可能不同；使用前请对照你部署实例的 API 文档。

## 项目结构

```text
dify_demo/
├── .cursor/mcp.json.example    # 将 Dify 应用接到 Cursor 的 MCP 配置样例
├── .env.example                # API Key、知识库和 mock 服务配置
├── business_api.py             # 假订单查询/模拟退款服务
├── dify_demo.py                # Dify API CLI：Agent、RAG、文件、音频、审核等
├── openapi/business_tools.yaml # 导入 Dify 的业务工具 OpenAPI 定义
├── tests/test_demo.py          # 本地 CLI 与 mock 业务 API 测试
└── README.md
```

## 集成架构

```text
你的 Web / App
    │  登录、权限、租户、业务规则
    ▼
你的后端 / BFF ──────► Dify App API（Chat / Agent / Workflow）
    │                           │
    │                           ├── 知识库检索 / RAG
    │                           ├── 模型、插件、MCP 工具
    │                           └── Human Input 暂停与恢复
    │
    └──── Dify 调用你的 OpenAPI 工具 ───► 业务服务 / 数据库
```

推荐让自己的后端持有 Dify App Key 并代用户调用。Dify 负责模型编排、知识检索和工具调度；用户身份、授权、租户隔离、交易校验和真实数据写入仍应由你的业务服务负责。

## 1. 配置 Dify 应用

在 Dify 中配置模型提供商，然后按要演示的能力创建应用：

- **Chatflow + 知识库**：创建知识库、导入并等待文档索引完成；在 Chatflow 中接入知识库节点并发布。这个路径最适合先做企业知识问答。
- **Agent**：创建 Agent 应用，选择模型并添加一个或多个工具；需要调用本项目的订单工具时，导入 `openapi/business_tools.yaml` 中的 OpenAPI 定义。
- **Workflow**：创建一个输入变量（例如 `text`）并添加输出。人工审核场景再加入 Human Input 节点，投递方式选 Web App，并配置表单字段和 action（例如 `approve`、`reject`）。

每个发布的应用分别在 API Access 页面创建 App API Key。Chat/Chatflow、Agent、Workflow 使用各自应用的 Key；知识库 API 使用单独的 Knowledge Service Key，二者不能混用。

## 2. 配置本地示例

```bash
cd /path/to/dify_demo
cp .env.example .env
```

编辑 `.env`，填入应用 Key、知识库 Service API Key 和知识库 ID。Cloud 默认 API 地址为 `https://api.dify.ai/v1`；自托管时改为你实例显示的 API 地址。不要把 `.env` 或真实 Key 提交到 Git。

检查 Chat 应用 Key：

```bash
python3 dify_demo.py info
```

## 3. Agent 和会话

Agent 使用工具进行自主调用，API 返回 SSE 事件。CLI 会流式打印 Agent 回复，只在 stderr 显示工具名，不打印内部 thought 内容。

```bash
python3 dify_demo.py agent "查询 order-1001 状态，并说明是否可以退款"
```

Agent API 是流式接口。创建多轮会话时，把返回的 `conversation_id` 传给下一轮：

```bash
python3 dify_demo.py agent "继续说明退款条件" --conversation-id YOUR_CONVERSATION_ID
```

Agent 需要文件时，可先上传并将文件引用随消息发送。Dify App 的文件上传设置必须允许相应类型：

```bash
python3 dify_demo.py agent "总结这份合同" --file ./contract.pdf --file-type document
```

## 4. 知识库与 RAG

**应用级问答：** 如果 Chatflow 已连接知识库，直接调用它即可，检索和回答由 Dify 流程完成：

```bash
python3 dify_demo.py chat "公司的退款政策是什么？"
```

**直接检查命中片段：** `retrieve` 示例调用经典知识库检索接口，适合验证切分、索引和检索配置：

```bash
python3 dify_demo.py retrieve "退款到账需要多久？"
```

命令会返回命中片段和相关分数等信息。这里用的是经典知识库 `/datasets/{dataset_id}/retrieve`；新版 Agent Knowledge Base 有单独的 API 与查询流程，不能直接把经典知识库 URL/请求体照搬过去。Knowledge Service API Key 需要在 Knowledge 的 API Access/Service API 页面创建，并限制到必要的知识库。

## 5. 让 Dify 调用你的业务系统

本项目提供一个安全边界清楚的 mock 业务 API：

```bash
python3 business_api.py
```

默认监听 `0.0.0.0:8088`。它提供：

- `GET /health`：无需鉴权的健康检查。
- `GET /orders/order-1001`：Bearer Token 鉴权后返回合成订单数据。
- `POST /refunds`：校验合成订单和金额，返回 `SIMULATED`，不会执行真实退款。

在 Dify 的 **Integrations > Tools > Swagger API** 中导入 `openapi/business_tools.yaml`，配置同一个 `DEMO_BUSINESS_API_TOKEN`，然后把工具加入 Agent 或 Workflow/Chatflow 的 Tool 节点。这里配置的是一个固定的 Dify-to-demo-service 凭证，不是终端用户的业务 Token。可以用这些假数据试跑：

```text
order-1001  已送达，总额 USD 58.50
order-1002  处理中，总额 USD 132.00
```

**网络地址要从 Dify 服务端可达。** 本地 Dify Docker 部署在 macOS/Windows 时，OpenAPI 文件里的 `host.docker.internal` 通常可访问宿主机；Linux 或不同网络拓扑请替换 `servers.url`。Dify Cloud 无法直接访问你的 `localhost`，应部署到可访问的 HTTPS 环境或使用受控的安全隧道。不要把无鉴权的开发服务直接暴露到公网。

真实业务接入时，将 mock handler 替换为你自己的订单/CRM/库存 API，并在业务服务端重新做身份授权、字段校验、金额上限、幂等、防重放和审计。不要让 LLM 自己决定是否有权退款，也不要把数据库写权限直接交给模型。

### 如果业务 API 要求用户自己的 Token

先区分四种值，避免把它们当成同一种凭证：

| 值 | 用途 | 当前 Demo 是否使用 |
| --- | --- | --- |
| Dify `user` | Dify 侧区分终端用户、隔离会话/文件；它不是认证凭证。 | 使用，例如 `customer-123`。 |
| Dify App API Key | 你的后端调用 Dify App API。 | 使用，放在后端 `.env`。 |
| `DEMO_BUSINESS_API_TOKEN` | Dify 工具调用本 Demo 业务 API 的固定服务凭证。 | 使用；所有 Demo 调用共享此值。 |
| 业务用户 Token | 代表一个真实业务用户访问上游业务 API。 | **当前 Demo 不使用，也不会由 Dify 自动传递。** |

Dify 不会根据 `user` 字段查找或生成业务用户 Token。当前 OpenAPI 工具里填写的 Bearer 凭证是固定配置；不会因为本轮请求的 `user` 不同而自动切换。Dify 官方也把终端用户 `user` 定义为标识，不是认证。参见 [End User Identity](https://docs.dify.ai/en/api-reference/guides/end-user-identity) 和 [Dify Tools](https://docs.dify.ai/en/cloud/use-dify/workspace/tools)。

#### 方案 A：由 BFF 把用户 Token 传入 Dify

只有在允许用户 Token 经过 Dify，且你已评估应用输入、运行日志和追踪数据的留存与访问控制时使用。调用方先在自己的后端完成登录验证，再把 Token 放到一个专用应用输入变量中；不要放在 `query`、提示词或模型可生成的工具参数里：

```python
payload = {
    "inputs": {
        "question": "查询我的订单",
        "business_access_token": user_access_token,
    },
    "query": "查询我的订单",
    "response_mode": "blocking",
    "user": internal_user_id,
}
```

在 Dify Workflow/Chatflow 中定义 `business_access_token` 输入变量，再用 HTTP Request 节点的变量选择器把它绑定到业务请求的 `Authorization` Header：`Bearer <business_access_token>`。不要把这个变量接入 LLM 节点的 Prompt。每个请求都应由 BFF 根据已认证的服务端会话填值，不能接受浏览器随意提交的 Token 或 `user` 字段。HTTP Request 节点见 [官方文档](https://docs.dify.ai/en/cloud/use-dify/nodes/http-request)。

这是“把原始用户 Token 交给 Dify”的方案：只使用短时、最小权限 Token，避免在 Agent 工具定义中让模型看到或控制该 Token，并核实你的 Dify 版本如何记录输入、节点运行数据和追踪。若不能接受 Token 出现在 Dify 的数据面，就不要选此方案。

#### 方案 B：Token Broker（优先推荐）

让用户 Token 始终留在你的后端或密钥库中：

```text
用户 → BFF：完成登录并取得/查到用户 Token
BFF → Dify：传普通业务输入 + 短时 request_context_id
Dify → 业务网关：使用固定 Dify 服务凭证 + request_context_id
业务网关 → Token Broker：校验并兑换一次性上下文，取得对应用户 Token
业务网关 → 原业务 API：Authorization: Bearer <用户自己的 Token>
```

`request_context_id` 应随机生成、短时有效、一次性使用，并绑定用户、租户、允许操作和当前请求；网关还要验证 Dify 服务身份。网关从服务端密钥库取回真实用户 Token 后再调用业务 API，因此**业务 API 仍然收到用户自己的 Token**，只是 Dify 不接触原始 Token。不要把这个上下文 ID 当作长期 API Key。

如果 Dify 必须直接调用上游且上游强制使用用户 Token，方案 A 是直接转发路径；若 Token 不得进入 Dify，则在 Dify 和上游之间增加网关/Token Broker。Agent 场景下尤其不要把用户 Token 设计成模型可填写的工具参数。当前项目里的 `business_api.py` 和 `openapi/business_tools.yaml` 是共享服务凭证的安全演示，不是用户级 OAuth/Token 转发实现。

## 6. 文件与音频

向 Chat 应用上传文件并在同一条消息里引用：

```bash
python3 dify_demo.py chat "请总结附件" --file ./report.pdf --file-type document
```

单独上传文件，查看返回的 `id`：

```bash
python3 dify_demo.py upload ./report.pdf --app chat
```

音频转文字前，需要在 Dify Workspace 配置可用的语音识别模型：

```bash
python3 dify_demo.py transcribe ./meeting.wav --app chat
```

文字转语音需要配置语音合成模型，结果默认写入 `dify_speech.mp3`：

```bash
python3 dify_demo.py speak "你的订单已经发货。" --out ./order-update.mp3
```

上传文件与后续使用文件的请求必须使用同一个 `user` 标识；支持的文件种类还取决于应用的上传设置和模型能力。

## 7. 人工审核与恢复执行

先确保 Workflow 已发布，且 Human Input 节点使用 Web App 投递。启动流式运行：

```bash
python3 dify_demo.py workflow-stream --inputs '{"text":"申请退款 order-1001"}' --user customer-123
```

当运行到 Human Input 节点，事件里会出现 `form_token`。在同一个项目目录下按顺序读取表单、提交人工选择：

```bash
python3 dify_demo.py human-get YOUR_FORM_TOKEN
python3 dify_demo.py human-submit YOUR_FORM_TOKEN \
  --action approve \
  --inputs '{"review_note":"核对通过"}' \
  --user customer-123
```

`--action` 必须与 Dify 表单中定义的 action 完全一致；输入字段也要匹配表单定义。提交成功会恢复暂停的运行。启动、上传、读取表单和提交时要使用同一个 `user`。生产系统应在自己的前端渲染表单，并将 token 与用户会话绑定，不要把它当作公开链接传播。

## 8. 会话、反馈和标注

应用 API 会按 `user` 隔离会话。查询会话列表和指定会话的消息历史，适合在自己的客服后台或管理界面展示：

```bash
python3 dify_demo.py conversations --app chat --user customer-123
python3 dify_demo.py messages YOUR_CONVERSATION_ID --app chat --user customer-123
```

将 `--app agent` 用于 Agent 会话。生产环境应先校验当前登录用户对该会话的访问权限，再向 Dify 请求，不能信任前端任意传入的 `user` 或 `conversation_id`。

Chat/Chatflow API 会返回 `message_id`。用它收集终端用户反馈；`user` 必须与原会话使用的身份一致：

```bash
python3 dify_demo.py feedback YOUR_MESSAGE_ID \
  --rating dislike \
  --content "政策版本过期" \
  --user customer-123
```

把常见问题和经过审核的标准答案作为 Annotation 加入支持的 Chatbot/Chatflow/Legacy Agent 应用：

```bash
python3 dify_demo.py annotation-add \
  "支持哪些退款方式？" \
  "目前支持原路退回。具体到账时间取决于支付渠道。"
```

反馈用于发现回答问题；标注是匹配时可直接返回的问答对。是否启用 Annotation Reply、反馈审核和知识库更新，应由产品/运营流程控制，而不是把用户反馈自动当作可信知识。实时节点事件可用 `workflow-stream` 查看；运行记录、用量与失败排查可在 Dify Monitor/Logs 页面检查，历史完成运行的节点级明细不一定能通过日志 API 取回。

## 9. 把 Dify 应用提供给 MCP 客户端

除了让 Dify 调你的工具，也可以反向把 Dify 应用作为 MCP Server 提供给 Cursor 等客户端：在应用 **Access Point** 页面启用 MCP Server，复制生成的服务地址，然后将 `.cursor/mcp.json.example` 复制为 `.cursor/mcp.json` 并替换占位地址。该 URL 本身含有凭证，按 API Key 管理并加入密钥管理流程；`.gitignore` 已忽略真实配置文件。

```bash
cp .cursor/mcp.json.example .cursor/mcp.json
```

Dify 也可以把外部 MCP Server 作为工具接入 Agent 或流程。具体传输方式、认证要求以对应 Dify 版本和客户端支持为准。

## 命令速查

| 命令 | 示例 | 用途 |
| --- | --- | --- |
| `info` | `python3 dify_demo.py info` | 检查 Chat 应用密钥 |
| `chat` | `python3 dify_demo.py chat "问题"` | Chat/Chatflow、可选会话和附件 |
| `conversations` | `python3 dify_demo.py conversations --user customer-123` | 列出当前用户的会话 |
| `messages` | `python3 dify_demo.py messages CONVERSATION_ID --user customer-123` | 查看会话消息历史 |
| `agent` | `python3 dify_demo.py agent "查订单"` | Agent SSE 流式回复和工具名提示 |
| `workflow` | `python3 dify_demo.py workflow --inputs '{"text":"..."}'` | 阻塞执行 Workflow |
| `workflow-stream` | `python3 dify_demo.py workflow-stream --inputs '{"text":"..."}'` | 查看节点事件和 Human Input 暂停 |
| `retrieve` | `python3 dify_demo.py retrieve "查询问题"` | 直接检索经典知识库 |
| `upload` | `python3 dify_demo.py upload ./file.pdf` | 上传文件并返回文件 ID |
| `transcribe` | `python3 dify_demo.py transcribe ./voice.wav` | 语音转文字 |
| `speak` | `python3 dify_demo.py speak "你好"` | 文字转语音并保存音频 |
| `feedback` | `python3 dify_demo.py feedback MESSAGE_ID --rating like` | 提交或撤销回答反馈 |
| `annotation-add` | `python3 dify_demo.py annotation-add "问题" "答案"` | 添加审核后的问答标注 |
| `human-get` | `python3 dify_demo.py human-get FORM_TOKEN` | 查看暂停的审核表单 |
| `human-submit` | `python3 dify_demo.py human-submit FORM_TOKEN --action approve` | 提交审核并恢复运行 |

## 本地验证

这些测试不需要 Dify API Key，也不会请求外网：

```bash
python3 -m unittest discover -s tests -v
```

测试会校验 CLI 参数解析、JSON 输入验证，以及 mock 订单接口的鉴权和“模拟退款”响应。

## 安全与生产化边界

- App API Key、Knowledge Service Key 和 MCP URL 都是凭证；只保存在后端 Secret Manager 或本地未跟踪的 `.env`，不要放进浏览器/移动端。
- 使用真实登录态映射稳定的 Dify `user`，并实施租户隔离、速率限制和审计。
- Dify 工具只应暴露最小权限的业务接口。高风险写操作在业务 API 做强校验，并要求显式人工确认。
- 对有副作用的调用设计幂等键、超时和重试策略；超时后不要假设业务操作没有发生。
- 对模型输出做 schema 校验，把关键授权、金额计算和数据库事务保留在传统后端。
- 生产聊天通常需要 SSE；当前 CLI 的 Agent/Workflow 命令演示了读取 SSE 的方式，但没有实现浏览器重连、并发治理和持久化状态。

## 官方资料

- [Dify API 快速开始](https://docs.dify.ai/en/api-reference/guides/get-started)
- [Agent API](https://docs.dify.ai/en/api-reference/guides/agent)
- [Workflow API](https://docs.dify.ai/en/api-reference/guides/workflow)
- [经典知识库 API](https://docs.dify.ai/en/api-reference/guides/knowledge)
- [Agent Knowledge Base API](https://docs.dify.ai/en/api-reference/guides/knowledge-base)
- [文件上传 API](https://docs.dify.ai/en/api-reference/files/upload-file)
- [语音转文字 API](https://docs.dify.ai/en/api-reference/audio/convert-audio-to-text)
- [文字转语音 API](https://docs.dify.ai/en/api-reference/audio/convert-text-to-audio)
- [Human Input API 流程](https://docs.dify.ai/en/api-reference/guides/human-input-flow)
- [会话列表 API](https://docs.dify.ai/en/api-reference/conversations/list-conversations)
- [会话消息 API](https://docs.dify.ai/en/api-reference/conversations/list-conversation-messages)
- [反馈 API](https://docs.dify.ai/en/api-reference/feedback/submit-message-feedback)
- [标注 API](https://docs.dify.ai/en/api-reference/annotations/create-annotation)
- [Dify 工具接入方式](https://docs.dify.ai/en/cloud/use-dify/workspace/tools)
- [将应用发布为 MCP Server](https://docs.dify.ai/en/cloud/use-dify/publish/publish-mcp)
- [v1.19.0 Release Notes](https://github.com/langgenius/dify/releases/tag/1.19.0)
