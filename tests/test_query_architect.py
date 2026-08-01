from unittest.mock import patch

from atlys_agentic import query_architect

_MANDATORY = ("device_type", "geoip_country_code", "destination")
_ROLE_CFG = {"role": "Text-to-SQL Query Architect", "backstory": "test backstory"}


def test_generate_sql_returns_deterministic_fallback_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = query_architect.generate_sql(_ROLE_CFG, "why did iOS drop?", "express_checkout", [], _MANDATORY)
    dims = {q["dimension"] for q in result}
    assert dims == set(_MANDATORY)
    for q in result:
        assert q["sql"].strip().upper().startswith("SELECT")


def test_fallback_queries_cover_every_mandatory_dimension():
    result = query_architect._fallback_queries("express_checkout", _MANDATORY)
    assert {q["dimension"] for q in result} == set(_MANDATORY)
    for q in result:
        assert q["sql"].startswith("SELECT")
        assert "express_checkout" in q["sql"]


def test_generate_sql_falls_back_when_llm_omits_a_mandatory_dimension(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    class _FakeResp:
        class _Choice:
            class _Msg:
                content = (
                    '{"queries": ['
                    '{"dimension": "device_type", "sql": "SELECT device_type, count() FROM express_checkout GROUP BY device_type"}'
                    "]}"
                )
            message = _Msg()
        choices = [_Choice()]
        usage = None

    with patch("litellm.completion", return_value=_FakeResp()):
        result = query_architect.generate_sql(_ROLE_CFG, "iOS drop?", "express_checkout", [], _MANDATORY)
    # geoip_country_code and destination were never covered -> full fallback, not a partial mix
    assert {q["dimension"] for q in result} == set(_MANDATORY)


def test_generate_sql_rejects_non_select_from_llm(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    class _FakeResp:
        class _Choice:
            class _Msg:
                content = (
                    '{"queries": ['
                    '{"dimension": "device_type", "sql": "DROP TABLE express_checkout"},'
                    '{"dimension": "geoip_country_code", "sql": "SELECT geoip_country_code, count() FROM express_checkout GROUP BY geoip_country_code"},'
                    '{"dimension": "destination", "sql": "SELECT destination, count() FROM express_checkout GROUP BY destination"}'
                    "]}"
                )
            message = _Msg()
        choices = [_Choice()]
        usage = None

    with patch("litellm.completion", return_value=_FakeResp()):
        result = query_architect.generate_sql(_ROLE_CFG, "iOS drop?", "express_checkout", [], _MANDATORY)
    # device_type's only candidate was a DROP -> rejected -> coverage incomplete -> full fallback
    assert {q["dimension"] for q in result} == set(_MANDATORY)
    for q in result:
        assert q["sql"].strip().upper().startswith("SELECT")


def test_generate_sql_accepts_full_coverage_plus_question_targeted_extra(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    class _FakeResp:
        class _Choice:
            class _Msg:
                content = (
                    '{"queries": ['
                    '{"dimension": "device_type", "sql": "SELECT device_type, count() FROM express_checkout GROUP BY device_type"},'
                    '{"dimension": "geoip_country_code", "sql": "SELECT geoip_country_code, count() FROM express_checkout GROUP BY geoip_country_code"},'
                    '{"dimension": "destination", "sql": "SELECT destination, count() FROM express_checkout GROUP BY destination"},'
                    '{"dimension": null, "sql": "SELECT count() FROM express_checkout WHERE device_type = \'ios\'"}'
                    "]}"
                )
            message = _Msg()
        choices = [_Choice()]
        usage = None

    with patch("litellm.completion", return_value=_FakeResp()):
        result = query_architect.generate_sql(_ROLE_CFG, "iOS drop?", "express_checkout", [], _MANDATORY)
    dims = [q["dimension"] for q in result]
    assert set(_MANDATORY) <= set(dims)
    assert None in dims
    assert len(result) == 4
