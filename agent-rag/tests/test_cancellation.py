from rag.cancellation import begin_run, end_run, is_cancelled, request_cancel


def test_cancel_flow():
    begin_run("t1", "thread-1")
    assert not is_cancelled("t1", "thread-1")
    assert request_cancel("t1", "thread-1") is True
    assert is_cancelled("t1", "thread-1")
    end_run("t1", "thread-1")
    assert not is_cancelled("t1", "thread-1")
    assert request_cancel("t1", "thread-1") is False
