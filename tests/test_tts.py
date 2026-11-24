from algoviz.tts import estimate_duration, speech_text


def test_speech_text_removes_brackets() -> None:
    text = speech_text("比较 a[0]=5 与 a[1]=3，区间 [lo, hi]，∞ 表示不可达")
    assert "[" not in text
    assert "无穷大" in text


def test_estimate_duration_positive() -> None:
    assert estimate_duration("快速排序") > 0.3
    assert estimate_duration("") >= 0.5
