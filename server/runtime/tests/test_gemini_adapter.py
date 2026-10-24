"""Checks the Gemini adapter builds valid SDK requests and parses responses (no network)."""

from google.genai import types

from server.runtime.llm import FunctionCall, GeminiLLM, LLMTurn
from tools.registry import registry


def make_resp(parts, usage=(10, 5)):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=usage[0], candidates_token_count=usage[1]),
    )


def test_adapter_round_trip(monkeypatch):
    llm = GeminiLLM(api_key="fake")
    seen = {}

    def fake_generate(model, contents, config):
        seen.update(model=model, contents=contents, config=config)
        return make_resp([types.Part(function_call=types.FunctionCall(id="c1", name="serpapi_shopping", args={"query": "AirPods"}))])

    monkeypatch.setattr(llm._client.models, "generate_content", fake_generate)
    tools = [registry.get("serpapi_shopping"), registry.get("nessie_purchases")]
    turn = llm.generate("gemini-x", "sys", [{"role": "user", "text": "hi"}], tools)
    assert turn.calls == [FunctionCall(name="serpapi_shopping", args={"query": "AirPods"}, id="c1")]
    assert turn.input_tokens == 10 and turn.output_tokens == 5
    decls = seen["config"].tools[0].function_declarations
    assert [d.name for d in decls] == ["serpapi_shopping", "nessie_purchases"]
    assert decls[0].parameters_json_schema["required"] == ["query"]
    assert seen["config"].automatic_function_calling.disable is True

    # second turn: history replays the raw model content + a function_response part
    def fake_generate2(model, contents, config):
        seen["contents2"] = contents
        return make_resp([types.Part(text="Final answer")])

    monkeypatch.setattr(llm._client.models, "generate_content", fake_generate2)
    history = [{"role": "user", "text": "hi"}, {"role": "model", "turn": turn},
               {"role": "tool", "results": [(turn.calls[0], {"ok": True, "data": {"x": 1}})]}]
    t2 = llm.generate("gemini-x", "sys", history, [])
    assert t2.text == "Final answer" and t2.calls == []
    fr = seen["contents2"][2].parts[0].function_response
    assert fr.name == "serpapi_shopping" and fr.id == "c1" and fr.response["data"] == {"x": 1}
    assert seen["contents2"][1] is turn.raw


def test_client_has_timeout_and_gemini3_uses_low_thinking(monkeypatch):
    """Real-data bug: a live run hung for minutes waiting on Gemini with no timeout."""
    llm = GeminiLLM(api_key="fake")
    assert llm._client._api_client._http_options.timeout == 60_000
    seen = {}

    def fake_generate(model, contents, config):
        seen[model] = config
        return make_resp([types.Part(text="ok")])

    monkeypatch.setattr(llm._client.models, "generate_content", fake_generate)
    for m in ("gemini-3.8-flash", "gemini-2.5-flash"):
        llm.generate(m, "sys", [{"role": "user", "text": "hi"}], [])
    assert seen["gemini-3.8-flash"].thinking_config.thinking_level == "LOW"
    assert seen["gemini-2.5-flash"].thinking_config is None


def test_overloaded_model_retries_then_falls_back(monkeypatch):
    """Real-data bug: gemini-3.8-flash returned 503 'high demand' and the whole run failed."""
    from google.genai import errors

    llm = GeminiLLM(api_key="fake")
    llm._sleep = lambda s: None
    tried = []

    def fake_generate(model, contents, config):
        tried.append(model)
        if model == "gemini-3.8-flash":
            raise errors.ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})
        return make_resp([types.Part(text="ok")])

    monkeypatch.setattr(llm._client.models, "generate_content", fake_generate)
    turn = llm.generate("gemini-3.8-flash", "sys", [{"role": "user", "text": "hi"}], [])
    assert turn.text == "ok"
    assert tried == ["gemini-3.8-flash", "gemini-3.8-flash", "gemini-3.7-flash"]
    assert turn.model == "gemini-3.7-flash" and len(turn.attempts) == 2 and "503" in turn.attempts[0]


def test_non_overload_errors_do_not_fall_back(monkeypatch):
    import pytest
    from google.genai import errors

    from server.runtime.llm import LLMError

    llm = GeminiLLM(api_key="fake")
    tried = []

    def fake_generate(model, contents, config):
        tried.append(model)
        raise errors.ClientError(404, {"error": {"code": 404, "message": "no longer available", "status": "NOT_FOUND"}})

    monkeypatch.setattr(llm._client.models, "generate_content", fake_generate)
    with pytest.raises(LLMError, match="404"):
        llm.generate("gemini-2.5-flash", "sys", [{"role": "user", "text": "hi"}], [])
    assert tried == ["gemini-2.5-flash"]
