#!/usr/bin/env python3
"""Dependency-free examples for integrating Dify apps with a business backend."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import secrets
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


PROJECT_DIR = Path(__file__).resolve().parent
APP_KEYS = {
    "chat": "DIFY_CHAT_API_KEY",
    "workflow": "DIFY_WORKFLOW_API_KEY",
    "agent": "DIFY_AGENT_API_KEY",
}


def load_dotenv(path: Path = PROJECT_DIR / ".env") -> None:
    """Load simple KEY=VALUE pairs without overriding the process environment."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"缺少环境变量 {name}，请检查项目根目录下的 .env")
    return value


def base_url() -> str:
    return os.getenv("DIFY_BASE_URL", "https://api.dify.ai/v1").strip().rstrip("/")


def knowledge_base_url() -> str:
    return os.getenv("DIFY_KNOWLEDGE_BASE_URL", base_url()).strip().rstrip("/")


def api_url(path: str, root: str | None = None) -> str:
    return f"{(root or base_url()).rstrip('/')}/{path.lstrip('/')}"


def http_error_message(exc: HTTPError) -> str:
    raw = exc.read().decode("utf-8", errors="replace")
    try:
        error = json.loads(raw)
    except json.JSONDecodeError:
        error = None
    if isinstance(error, dict):
        detail = error.get("message") or error.get("code") or error
    else:
        detail = raw or exc.reason
    return f"Dify API 返回 HTTP {exc.code}: {detail}"


def request_bytes(
    path: str,
    api_key: str,
    payload: dict | None = None,
    *,
    root: str | None = None,
    timeout: int = 120,
) -> tuple[bytes, str]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(
        api_url(path, root),
        data=body,
        headers=headers,
        method="GET" if body is None else "POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read(), response.headers.get("Content-Type", "")
    except HTTPError as exc:
        raise RuntimeError(http_error_message(exc)) from None
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise RuntimeError("请求 Dify API 超时") from None
        raise RuntimeError(f"无法连接 Dify API: {exc.reason}") from None
    except TimeoutError:
        raise RuntimeError("请求 Dify API 超时") from None


def request_json(
    path: str,
    api_key: str,
    payload: dict | None = None,
    *,
    root: str | None = None,
) -> dict:
    raw, _content_type = request_bytes(path, api_key, payload, root=root)
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError(f"Dify API 返回非 JSON 响应: {raw[:300]!r}") from None
    if not isinstance(result, dict):
        raise RuntimeError("Dify API 返回的 JSON 顶层不是对象")
    return result


def request_multipart(
    path: str,
    api_key: str,
    fields: dict[str, str],
    file_path: str,
    *,
    root: str | None = None,
) -> dict:
    source = Path(file_path)
    if not source.is_file():
        raise ValueError(f"文件不存在: {source}")

    boundary = f"----DifyDemo{secrets.token_hex(16)}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{source.name}"\r\n'.encode(),
            f"Content-Type: {mime_type}\r\n\r\n".encode(),
            source.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    request = Request(
        api_url(path, root),
        data=b"".join(chunks),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            raw = response.read()
    except HTTPError as exc:
        raise RuntimeError(http_error_message(exc)) from None
    except URLError as exc:
        raise RuntimeError(f"无法连接 Dify API: {exc.reason}") from None
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError(f"Dify 文件 API 返回非 JSON 响应: {raw[:300]!r}") from None
    if not isinstance(result, dict):
        raise RuntimeError("Dify 文件 API 返回的 JSON 顶层不是对象")
    return result


def stream_events(path: str, api_key: str, payload: dict, timeout: int = 3600):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        api_url(path),
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        response = urlopen(request, timeout=timeout)
    except HTTPError as exc:
        raise RuntimeError(http_error_message(exc)) from None
    except URLError as exc:
        raise RuntimeError(f"无法连接 Dify API: {exc.reason}") from None

    with response:
        event_name = "message"
        data_lines: list[str] = []
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line:
                if data_lines:
                    data = "\n".join(data_lines)
                    if data == "[DONE]":
                        return
                    try:
                        value = json.loads(data)
                    except json.JSONDecodeError:
                        value = {"raw": data}
                    if isinstance(value, dict):
                        value.setdefault("event", event_name)
                        yield value
                    data_lines = []
                event_name = "message"
            elif line.startswith(":"):
                continue
            elif line.startswith("event:"):
                event_name = line[6:].strip() or "message"
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if data_lines:
            data = "\n".join(data_lines)
            if data != "[DONE]":
                try:
                    value = json.loads(data)
                except json.JSONDecodeError:
                    value = {"raw": data}
                if isinstance(value, dict):
                    value.setdefault("event", event_name)
                    yield value


def app_key(app: str) -> str:
    return required_env(APP_KEYS[app])


def app_user(args: argparse.Namespace) -> str:
    return args.user or os.getenv("DIFY_USER", "demo-user")


def upload_for_app(app: str, path: str, user: str) -> dict:
    return request_multipart("/files/upload", app_key(app), {"user": user}, path)


def run_info(_args: argparse.Namespace) -> None:
    result = request_json("/info", app_key("chat"))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run_chat(args: argparse.Namespace) -> None:
    user = app_user(args)
    payload = {
        "inputs": {},
        "query": args.query,
        "response_mode": "blocking",
        "user": user,
    }
    if args.conversation_id:
        payload["conversation_id"] = args.conversation_id
    if args.file:
        uploaded = upload_for_app("chat", args.file, user)
        payload["files"] = [
            {
                "type": args.file_type,
                "transfer_method": "local_file",
                "upload_file_id": uploaded["id"],
            }
        ]
    result = request_json("/chat-messages", app_key("chat"), payload)
    print(result.get("answer", json.dumps(result, ensure_ascii=False, indent=2)))
    if result.get("conversation_id"):
        print(f"\nconversation_id: {result['conversation_id']}")
    if result.get("message_id"):
        print(f"message_id: {result['message_id']}")


def run_conversations(args: argparse.Namespace) -> None:
    params = {"user": app_user(args), "limit": args.limit}
    if args.last_id:
        params["last_id"] = args.last_id
    result = request_json(f"/conversations?{urlencode(params)}", app_key(args.app))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run_messages(args: argparse.Namespace) -> None:
    params = {
        "user": app_user(args),
        "conversation_id": args.conversation_id,
        "limit": args.limit,
    }
    if args.first_id:
        params["first_id"] = args.first_id
    result = request_json(f"/messages?{urlencode(params)}", app_key(args.app))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run_agent(args: argparse.Namespace) -> None:
    user = app_user(args)
    payload = {
        "inputs": {},
        "query": args.query,
        "response_mode": "streaming",
        "user": user,
    }
    if args.conversation_id:
        payload["conversation_id"] = args.conversation_id
    if args.file:
        uploaded = upload_for_app("agent", args.file, user)
        payload["files"] = [
            {
                "type": args.file_type,
                "transfer_method": "local_file",
                "upload_file_id": uploaded["id"],
            }
        ]

    print("Agent 输出：", end="", flush=True)
    streamed_answer = False
    final_answer = ""
    conversation_id = args.conversation_id
    message_id = None
    for item in stream_events("/chat-messages", app_key("agent"), payload):
        kind = item.get("event", "")
        conversation_id = item.get("conversation_id") or conversation_id
        message_id = item.get("message_id") or message_id
        if kind == "agent_message":
            text = item.get("answer") or item.get("text") or ""
            if text:
                streamed_answer = True
                print(text, end="", flush=True)
        elif kind == "message":
            final_answer = item.get("answer") or final_answer
        elif kind == "agent_thought":
            tool = item.get("tool")
            if tool:
                print(f"\n[调用工具: {tool}]", file=sys.stderr)
        elif kind == "message_end":
            print()
        elif kind == "error":
            print("\nAgent API 错误:", json.dumps(item, ensure_ascii=False), file=sys.stderr)
        elif kind not in {"ping"}:
            print(f"\n[{kind}]", file=sys.stderr)
    if not streamed_answer and final_answer:
        print(final_answer, end="")
    print()
    if conversation_id:
        print(f"conversation_id: {conversation_id}")
    if message_id:
        print(f"message_id: {message_id}")


def parse_json_object(value: str, option_name: str) -> dict:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{option_name} 不是有效 JSON: {exc.msg}") from None
    if not isinstance(parsed, dict):
        raise ValueError(f"{option_name} 必须是 JSON 对象")
    return parsed


def run_workflow(args: argparse.Namespace) -> None:
    payload = {
        "inputs": parse_json_object(args.inputs, "--inputs"),
        "response_mode": "blocking",
        "user": app_user(args),
    }
    result = request_json("/workflows/run", app_key("workflow"), payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run_workflow_stream(args: argparse.Namespace) -> None:
    payload = {
        "inputs": parse_json_object(args.inputs, "--inputs"),
        "response_mode": "streaming",
        "user": app_user(args),
    }
    for item in stream_events("/workflows/run", app_key("workflow"), payload):
        print(json.dumps(item, ensure_ascii=False))
        if item.get("event") == "human_input_required":
            token = item.get("form_token")
            if token:
                print(f"表单 Token: {token}", file=sys.stderr)
                print("下一步运行 human-get 和 human-submit 子命令。", file=sys.stderr)
            else:
                print("此 Human Input 没有启用 Web App 投递，不能通过本 API 提交表单。", file=sys.stderr)


def run_retrieve(args: argparse.Namespace) -> None:
    dataset_id = args.dataset_id or required_env("DIFY_DATASET_ID")
    payload = {"query": args.query}
    result = request_json(
        f"/datasets/{quote(dataset_id, safe='')}/retrieve",
        required_env("DIFY_KNOWLEDGE_API_KEY"),
        payload,
        root=knowledge_base_url(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run_upload(args: argparse.Namespace) -> None:
    result = upload_for_app(args.app, args.file, app_user(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run_transcribe(args: argparse.Namespace) -> None:
    user = app_user(args)
    result = request_multipart("/audio-to-text", app_key(args.app), {"user": user}, args.file)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run_speak(args: argparse.Namespace) -> None:
    payload = {"text": args.text, "user": args.user or os.getenv("DIFY_USER", "demo-user")}
    raw, content_type = request_bytes("/text-to-audio", app_key(args.app), payload)
    if "json" in content_type:
        try:
            error = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            error = raw.decode("utf-8", errors="replace")
        raise RuntimeError(f"文本转语音未返回音频: {error}")
    output = Path(args.out)
    output.write_bytes(raw)
    print(f"音频已写入 {output} ({len(raw)} bytes)")


def run_feedback(args: argparse.Namespace) -> None:
    rating = None if args.rating == "revoke" else args.rating
    result = request_json(
        f"/messages/{quote(args.message_id, safe='')}/feedbacks",
        app_key("chat"),
        {
            "rating": rating,
            "content": args.content,
            "user": app_user(args),
        },
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run_annotation_add(args: argparse.Namespace) -> None:
    result = request_json(
        "/apps/annotations",
        app_key("chat"),
        {"question": args.question, "answer": args.answer},
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run_human_get(args: argparse.Namespace) -> None:
    token = quote(args.form_token, safe="")
    result = request_json(f"/form/human_input/{token}", app_key("workflow"))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run_human_submit(args: argparse.Namespace) -> None:
    token = quote(args.form_token, safe="")
    payload = {
        "action": args.action,
        "inputs": parse_json_object(args.inputs, "--inputs"),
        "user": app_user(args),
    }
    result = request_json(
        f"/form/human_input/{token}", app_key("workflow"), payload
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def add_user_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--user", help="Dify 侧终端用户标识；同一会话/文件/审核流程需保持一致")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dify 应用与业务系统集成示例")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("info", help="检查 Chat/Chatflow 应用 API Key")

    chat = commands.add_parser("chat", help="调用 Chat/Chatflow，可选上传文件")
    chat.add_argument("query")
    chat.add_argument("--conversation-id")
    chat.add_argument("--file", help="可选附件路径")
    chat.add_argument("--file-type", choices=["image", "document", "audio", "video", "custom"], default="document")
    add_user_argument(chat)

    conversations = commands.add_parser("conversations", help="列出终端用户的对话")
    conversations.add_argument("--app", choices=["chat", "agent"], default="chat")
    conversations.add_argument("--limit", type=int, default=20)
    conversations.add_argument("--last-id")
    add_user_argument(conversations)

    messages = commands.add_parser("messages", help="读取某个对话的消息历史")
    messages.add_argument("conversation_id")
    messages.add_argument("--app", choices=["chat", "agent"], default="chat")
    messages.add_argument("--limit", type=int, default=20)
    messages.add_argument("--first-id")
    add_user_argument(messages)

    agent = commands.add_parser("agent", help="以 SSE 调用 Agent，可选上传文件")
    agent.add_argument("query")
    agent.add_argument("--conversation-id")
    agent.add_argument("--file", help="可选附件路径")
    agent.add_argument("--file-type", choices=["image", "document", "audio", "video", "custom"], default="document")
    add_user_argument(agent)

    workflow = commands.add_parser("workflow", help="阻塞方式运行已发布 Workflow")
    workflow.add_argument("--inputs", default="{}", help="Start 节点输入变量 JSON")
    add_user_argument(workflow)

    workflow_stream = commands.add_parser("workflow-stream", help="流式运行 Workflow，查看节点与人工输入事件")
    workflow_stream.add_argument("--inputs", default="{}", help="Start 节点输入变量 JSON")
    add_user_argument(workflow_stream)

    retrieve = commands.add_parser("retrieve", help="直接检索经典知识库并查看命中片段")
    retrieve.add_argument("query")
    retrieve.add_argument("--dataset-id", help="默认读取 DIFY_DATASET_ID")

    upload = commands.add_parser("upload", help="上传文件到一个已发布的 Dify 应用")
    upload.add_argument("file")
    upload.add_argument("--app", choices=APP_KEYS, default="chat")
    add_user_argument(upload)

    transcribe = commands.add_parser("transcribe", help="上传音频并调用语音转文字")
    transcribe.add_argument("file")
    transcribe.add_argument("--app", choices=APP_KEYS, default="chat")
    add_user_argument(transcribe)

    speak = commands.add_parser("speak", help="将文字合成为音频文件")
    speak.add_argument("text")
    speak.add_argument("--app", choices=APP_KEYS, default="chat")
    speak.add_argument("--out", default="dify_speech.mp3")
    speak.add_argument("--user")

    feedback = commands.add_parser("feedback", help="对一条回答提交点赞/点踩/撤销反馈")
    feedback.add_argument("message_id")
    feedback.add_argument("--rating", choices=["like", "dislike", "revoke"], required=True)
    feedback.add_argument("--content", default="")
    add_user_argument(feedback)

    annotation = commands.add_parser("annotation-add", help="给 Chat/Chatflow 应用添加问答标注")
    annotation.add_argument("question")
    annotation.add_argument("answer")

    human_get = commands.add_parser("human-get", help="读取暂停的 Human Input 表单")
    human_get.add_argument("form_token")

    human_submit = commands.add_parser("human-submit", help="提交人工表单并恢复 Workflow")
    human_submit.add_argument("form_token")
    human_submit.add_argument("--action", required=True, help="表单定义中允许的 action")
    human_submit.add_argument("--inputs", default="{}", help="表单输入 JSON")
    add_user_argument(human_submit)

    handlers = {
        "info": run_info,
        "chat": run_chat,
        "conversations": run_conversations,
        "messages": run_messages,
        "agent": run_agent,
        "workflow": run_workflow,
        "workflow-stream": run_workflow_stream,
        "retrieve": run_retrieve,
        "upload": run_upload,
        "transcribe": run_transcribe,
        "speak": run_speak,
        "feedback": run_feedback,
        "annotation-add": run_annotation_add,
        "human-get": run_human_get,
        "human-submit": run_human_submit,
    }
    parser.set_defaults(handlers=handlers)
    return parser


def main() -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.handlers[args.command](args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
