"""Deterministic, provenance-preserving extraction of explicitly supplied chat exports."""
from __future__ import annotations

import json
import re
from pathlib import Path


NOISE = re.compile(r"^(?:tool(?:\s+(?:call|result))?\s*:\s*(?:ignore|internal)|ignore all rules|tool call|tool result|assistant to=|<\|.*\|>|\s*$)", re.I)


def _body(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        pieces = [_body(item) for item in value]
        return "\n".join(piece for piece in pieces if piece)
    if isinstance(value, dict):
        for key in ("text", "content", "body", "parts"):
            if key in value:
                result = _body(value[key])
                if result:
                    return result
    return ""


def _messages(obj):
    if isinstance(obj, list):
        for item in obj:
            yield from _messages(item)
    elif isinstance(obj, dict):
        role = obj.get("role") or obj.get("speaker") or obj.get("author")
        kind = str(obj.get("type", "")).lower()
        if not role and kind in {"user_message", "human_message"}:
            role = "user"
        elif not role and kind in {"assistant_message", "agent_message"}:
            role = "assistant"
        nested = obj.get("message") if isinstance(obj.get("message"), dict) else obj
        role = role or nested.get("role") or nested.get("speaker") or nested.get("author")
        if isinstance(role, dict):
            role = role.get("role") or role.get("name")
        body = _body(obj.get("content", nested.get("content", obj.get("message", obj.get("text", obj.get("body"))))))
        if isinstance(role, str) and body:
            role = role.lower()
            source = "user" if role in {"user", "human"} else ("assistant" if role in {"assistant", "agent", "model"} else "tool")
            timestamp = (obj.get("timestamp") or nested.get("timestamp") or obj.get("created_at")
                         or nested.get("create_time") or obj.get("create_time") or obj.get("time") or "")
            yield {"role": role, "source": source, "time": str(timestamp), "body": body}
        for key in ("messages", "conversation", "turns", "items", "payload", "message", "node", "children", "event_msg"):
            if key in obj:
                yield from _messages(obj[key])
        if isinstance(obj.get("mapping"), dict):
            yield from _messages(list(obj["mapping"].values()))


def parse_text(text: str):
    """Parse JSON/JSONL or simple role-prefixed text without semantic inference."""
    stripped = text.strip()
    records = []
    if stripped:
        try:
            parsed = json.loads(stripped)
            records.extend(_messages(parsed))
        except json.JSONDecodeError:
            lines = stripped.splitlines()
            json_lines = True
            for line in lines:
                try:
                    records.extend(_messages(json.loads(line)))
                except json.JSONDecodeError:
                    json_lines = False
                    break
            if not json_lines:
                current = None
                for line in lines:
                    match = re.match(r"^\s*(user|human|assistant|agent|tool)\s*(?:\[(.*?)\])?\s*:\s*(.*)$", line, re.I)
                    if match:
                        if current:
                            records.append(current)
                        role = match.group(1).lower()
                        current = {"role": role, "source": "user" if role in ("user", "human") else ("assistant" if role in ("assistant", "agent") else "tool"),
                                   "time": match.group(2) or "", "body": match.group(3).strip()}
                    elif current:
                        current["body"] += "\n" + line.strip()
                if current:
                    records.append(current)
    seen = set()
    result = []
    for row in records:
        body = row["body"].strip()
        if not body or NOISE.match(body):
            continue
        key = (row["source"], re.sub(r"\s+", " ", body).casefold())
        if key in seen:
            continue
        seen.add(key)
        result.append({**row, "body": body})
    return result


def extract_file(path, *, query="", max_chars=12000):
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 1:
        raise ValueError("max_chars must be a positive integer")
    path = Path(path).expanduser().resolve(strict=True)
    content = path.read_text(encoding="utf-8-sig")
    records = parse_text(content)
    chunk_size = min(1800, max(1, max_chars // 2))
    chunks = []
    for row in records:
        body = row["body"]
        if len(body) <= chunk_size:
            chunks.append(row)
            continue
        offset = 0
        while offset < len(body):
            end = min(offset + chunk_size, len(body))
            if end < len(body):
                boundary = max(body.rfind("\n", offset, end), body.rfind("。", offset, end), body.rfind(". ", offset, end))
                if boundary > offset + chunk_size // 2:
                    end = boundary + 1
            chunks.append({**row, "body": body[offset:end].strip(), "part": len(chunks) + 1})
            offset = end
    records = chunks
    terms = {part.casefold() for part in re.findall(r"\w+|[\u3400-\u9fff]+", query) if len(part) > 1}
    if terms:
        records = [row for _, row in sorted(enumerate(records), key=lambda pair: (
            -sum(term in pair[1]["body"].casefold() for term in terms), pair[0]))]
    selected, used = [], 0
    for row in records:
        cost = len(row["body"])
        if selected and used + cost > max_chars:
            continue
        if cost > max_chars:
            row = {**row, "body": row["body"][:max_chars]}
            cost = len(row["body"])
        selected.append({"source_file": str(path), **row})
        used += cost
    return {"source_file": str(path), "records": selected, "record_count": len(selected),
            "chars": used, "truncated": len(selected) < len(records),
            "notice": "记录保留原始说话方和时间；不生成个人成就或事实推断。"}
