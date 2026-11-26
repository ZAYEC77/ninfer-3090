#!/usr/bin/env python3
"""Exercise native NInfer conversational compatibility without the old proxy."""
import argparse
import json
import time
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:18082")
parser.add_argument("--model", default="qwen3.8-27b")
parser.add_argument("--output")
args = parser.parse_args()
BASE = args.base_url.rstrip("/")
MODEL = args.model
RESULTS = []


def request(path, data=None, expected=200):
    headers = {"Content-Type": "application/json"}
    if path == "/v1/messages":
        headers["anthropic-version"] = "2023-06-01"
    req = urllib.request.Request(BASE + path,
        data=None if data is None else json.dumps(data, ensure_ascii=False).encode(),
        headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
    assert status == expected, (path, status, body[:1000])
    return json.loads(body)


def create(items, **extra):
    body = {"model": MODEL, "input": items, "store": False,
            "include": ["reasoning.encrypted_content"], "reasoning": {"effort": "none"},
            "max_output_tokens": 96}
    body.update(extra)
    return request("/v1/responses", body)


def text(response):
    return "".join(p.get("text", "") for i in response.get("output", [])
                   if i.get("type") == "message" for p in i.get("content", [])
                   if p.get("type") == "output_text").strip()


def user(value):
    return {"role": "user", "content": value}


def context(name, output, namespace="agent"):
    return {"id": "fco_" + name, "type": "function_call_output", "name": name,
            "namespace": namespace, "output": output,
            "internal_chat_message_metadata_passthrough": {"turn_id": "fixture", "create_time": 1}}


def record(name, action):
    started = time.monotonic()
    details = action()
    RESULTS.append({"test": name, "status": "passed", "seconds": round(time.monotonic()-started, 3),
                    "details": details})
    print(json.dumps(RESULTS[-1], ensure_ascii=False), flush=True)


def health_and_models():
    assert request("/health")["status"] == "ok"
    assert any(m["id"] == MODEL for m in request("/v1/models")["data"])
    return "Model available on the direct native endpoint"


record("health_and_models", health_and_models)

frames = [context("codex_apps_open_page", '{"page_id":null}'),
          context("codex_apps_selected_page_part_1_of_1",
                  'Companion Page snapshot part 1 of 1:\n{"page_id":null,"document_view":null}')]


def app_context():
    response = create(frames + [user("Reply with exactly NATIVE_APP_OK. No tools.")], store=True)
    assert response["status"] == "completed" and text(response) == "NATIVE_APP_OK", response
    items = request("/v1/responses/" + response["id"] + "/input_items?order=asc")["data"]
    assert items[0]["type"] == "function_call_output" and items[0]["name"] == frames[0]["name"]
    assert "call_id" not in items[0] and items[0]["output"] == frames[0]["output"]
    assert items[0]["internal_chat_message_metadata_passthrough"] == frames[0]["internal_chat_message_metadata_passthrough"]
    return "App context and canonical input storage preserved"


record("app_without_selected_page_and_storage", app_context)


def generic_peer():
    peer = context("context_from_new_agent", "Source: peer-agent. Shared marker: PEER_NATIVE_42", "team")
    response = create([peer, user("Return only the shared marker from the peer context. No tools.")])
    assert text(response) == "PEER_NATIVE_42", response
    counted = request("/v1/responses/input_tokens", {"model": MODEL, "input": [peer]})
    assert counted["input_tokens"] > 0, counted
    return "Arbitrary named peer context works without a source-name allowlist"


record("generic_peer_context_and_input_tokens", generic_peer)


def image_context():
    image = ("data:image/png;base64,"
             "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
             "AScY42YAAAAASUVORK5CYII=")
    page = context("page_with_image", [
        {"type": "input_text", "text": "A page image supplied as context."},
        {"type": "input_image", "image_url": image}])
    response = create([page, user("Reply exactly IMAGE_CONTEXT_OK. No tools.")])
    assert text(response) == "IMAGE_CONTEXT_OK", response
    return "Structured external image context accepted by the vision frontend"


record("structured_image_context", image_context)


def stored_and_forked():
    initial = [context("remember", "Remember marker STORED_NATIVE_29", "peer"),
               user("Acknowledge with OK. No tools.")]
    first = create(initial, store=True)
    assert first["status"] == "completed", first
    next_input = [user("Return only the marker from the peer context. No tools.")]
    continuation = create(next_input, previous_response_id=first["id"])
    replay = create(initial + first["output"] + next_input)
    assert text(continuation) == "STORED_NATIVE_29", continuation
    assert text(replay) == "STORED_NATIVE_29", replay
    return "Stored continuation and stateless fork-style replay agree"


record("stored_continuation_and_fork_replay", stored_and_forked)


def stream_reasoning():
    body = {"model": MODEL, "input": frames + [user("What is 7 plus 8? Reply with only the number.")],
            "store": False, "stream": True, "reasoning": {"effort": "low"},
            "include": ["reasoning.encrypted_content"], "max_output_tokens": 192}
    req = urllib.request.Request(BASE + "/v1/responses", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    terminal = None
    tokens = []
    event_count = 0
    with urllib.request.urlopen(req, timeout=180) as response:
        for line in response:
            line = line.decode().strip()
            if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                continue
            event = json.loads(line[5:])
            event_count += 1
            if event.get("type") == "response.output_item.done" and event.get("item", {}).get("type") == "reasoning":
                tokens.append(event["item"]["encrypted_content"])
            if event.get("type") == "response.completed":
                terminal = event["response"]
    assert terminal and text(terminal) == "15" and tokens, terminal
    reasoning = next(i for i in terminal["output"] if i["type"] == "reasoning")
    assert reasoning["encrypted_content"] == tokens[-1]
    restored_items = []
    for item in terminal["output"]:
        item = dict(item)
        if item["type"] == "reasoning":
            item.pop("content", None)
        restored_items.append(item)
    replay = create(body["input"] + restored_items + [user("Reply exactly REASONING_REPLAY_OK. No tools.")])
    assert text(replay) == "REASONING_REPLAY_OK", replay
    return {"sse_events": event_count, "reasoning_token_replay": "passed"}


record("streaming_and_opaque_reasoning_replay", stream_reasoning)


def tools_roundtrip(custom=False):
    name = "raw_echo" if custom else "lookup"
    tool = {"type": "custom", "name": name, "description": "Return the literal text ping.",
            "format": {"type": "text"}} if custom else {
                "type": "function", "name": name, "description": "Look up the shared marker.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}
    inputs = [user("Call " + name + " once now.")]
    first = create(inputs, tools=[tool], tool_choice={"type": tool["type"], "name": name})
    kind = "custom_tool_call" if custom else "function_call"
    calls = [i for i in first["output"] if i["type"] == kind]
    assert len(calls) == 1 and calls[0].get("call_id"), first
    result = {"type": kind + "_output", "call_id": calls[0]["call_id"], "output": "TOOL_NATIVE_57"}
    peer = context("concurrent_notice", "Another peer joined while the tool was executing.", "team")
    second = create(inputs + first["output"] + [peer, result, user("Return exactly the marker supplied by the tool. No tools.")],
                    tools=[tool], tool_choice="none")
    assert text(second) == "TOOL_NATIVE_57", second
    return "Real tool IDs stay paired with results despite interleaved peer context"


record("function_tool_roundtrip_with_interleaved_context", tools_roundtrip)
record("custom_tool_roundtrip_with_interleaved_context", lambda: tools_roundtrip(True))


def rejection_cases():
    cases = [
        {"type": "function_call_output", "output": "unnamed"},
        dict(context("named", "x"), call_id=17),
        dict(context("named", "x"), internal_chat_message_metadata_passthrough="invalid"),
        {"type": "custom_tool_call_output", "name": "raw_echo", "output": "no call"},
        {"type": "function_call_output", "call_id": "nonexistent", "output": "fake result"},
    ]
    for invalid in cases:
        data = request("/v1/responses", {"model": MODEL, "input": [user("hello"), invalid]}, expected=400)
        assert data.get("error"), data
    return len(cases)


record("malformed_real_tool_histories_still_rejected", rejection_cases)


def other_protocols():
    chat = request("/v1/chat/completions", {"model": MODEL,
        "messages": [user("Reply exactly CHAT_NATIVE_OK.")], "max_tokens": 48,
        "enable_thinking": False})
    assert chat["choices"][0]["message"]["content"].strip() == "CHAT_NATIVE_OK", chat
    anthropic = request("/v1/messages", {"model": MODEL,
        "messages": [user("Reply exactly ANTHROPIC_NATIVE_OK.")], "max_tokens": 48,
        "thinking": {"type": "disabled"}})
    answer = "".join(p.get("text", "") for p in anthropic.get("content", []) if p.get("type") == "text")
    assert answer.strip() == "ANTHROPIC_NATIVE_OK", anthropic
    return "Existing Chat Completions and Anthropic clients still answer"


record("existing_other_protocols", other_protocols)
if args.output:
    from pathlib import Path
    Path(args.output).write_text(json.dumps({"base_url": BASE, "results": RESULTS}, ensure_ascii=False, indent=2))
print("Native conversational compatibility: PASS", flush=True)
