from __future__ import annotations

from unittest.mock import patch

import rag.metrics as metrics_mod


@patch.object(metrics_mod, "_incr")
def test_record_tavily_search_increments_total_and_status(mock_incr):
    metrics_mod.record_tavily_search("ok", tenant="tenant_a")

    assert mock_incr.call_count == 2
    mock_incr.assert_any_call("metrics:rag:tenant_a:tavily_calls")
    mock_incr.assert_any_call("metrics:rag:tenant_a:tavily_calls_ok")


@patch.object(metrics_mod, "_get_int", return_value=3)
def test_get_totals_includes_tavily_fields(mock_get_int):
    totals = metrics_mod.get_totals("tenant_a")

    assert totals["tavily_calls_total"] == 3
    assert totals["tavily_calls_ok"] == 3
    assert totals["tavily_calls_empty"] == 3
    assert totals["tavily_calls_error"] == 3
    assert any("tavily_calls" in call.args[0] for call in mock_get_int.call_args_list)
