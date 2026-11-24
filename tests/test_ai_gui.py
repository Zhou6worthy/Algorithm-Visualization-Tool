from types import SimpleNamespace

from fastapi.testclient import TestClient

from algoviz.ai.client import AIClient
from algoviz.api.app import create_app
from algoviz.config import Settings


def _settings(tmp_path) -> Settings:
    settings = Settings()
    settings.output_dir = tmp_path
    settings.env_path = tmp_path / ".env"
    settings.deepseek_api_key = ""
    return settings


def test_ai_usage_tracks_success(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    settings.deepseek_api_key = "sk-test"
    client = AIClient(settings)

    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
            )

    fake = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    client._client = fake
    client.start_usage()
    data = client.chat_json("system", "user", purpose="test")
    usage = client.finish_usage()
    assert data == {"ok": True}
    assert usage["status"] == "used"
    assert usage["calls"] == 1
    assert usage["successes"] == 1
    assert usage["details"][0]["purpose"] == "test"


def test_ai_usage_disabled_without_key(tmp_path) -> None:
    client = AIClient(_settings(tmp_path))
    client.start_usage()
    assert client.chat_json("s", "u") is None
    usage = client.finish_usage()
    assert usage["status"] == "disabled"
    assert usage["calls"] == 0
    assert "DEEPSEEK_API_KEY" in usage["reason"]


def test_gui_and_ai_settings_api(tmp_path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    index = client.get("/")
    assert index.status_code == 200
    assert "AlgoViz" in index.text
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200

    current = client.get("/api/v1/settings/ai").json()
    assert current["has_key"] is False
    assert current["masked_key"] == ""

    saved = client.post(
        "/api/v1/settings/ai",
        json={"api_key": "sk-abcdef123456", "model": "deepseek-chat", "mode": "auto"},
    )
    assert saved.status_code == 200
    assert saved.json()["has_key"] is True
    assert saved.json()["masked_key"] == "sk-abc...3456"
    assert "sk-abcdef123456" not in saved.text
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=sk-abcdef123456" in env_text

    # 没有真实网络调用：未配置 Key 的独立应用应返回可读错误
    other = _settings(tmp_path / "other")
    other.output_dir.mkdir(parents=True, exist_ok=True)
    result = TestClient(create_app(other)).post("/api/v1/ai/test").json()
    assert result["ok"] is False
    assert "未配置" in result["error"]
    app.state.store.close()
