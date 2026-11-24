import json

from fastapi.testclient import TestClient

from algoviz.api.app import create_app
from algoviz.batch import load_batch
from algoviz.config import Settings, get_settings


def test_batch_loader(tmp_path) -> None:
    path = tmp_path / "tasks.json"
    path.write_text(
        json.dumps(
            {
                "batch_name": "test_batch",
                "defaults": {"render_quality": "low", "tts": False},
                "tasks": [
                    {"id": "bubble", "algorithm": "bubble_sort", "params": {"array": [3, 1, 2]}},
                    {"prompt": "用 BFS 遍历图，起点 A，边 A-B"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    name, tasks = load_batch(path, get_settings())
    assert name == "test_batch"
    assert len(tasks) == 2
    assert tasks[0].task_id == "bubble"
    assert tasks[0].options.render_quality == "low"
    assert tasks[1].prompt.startswith("用 BFS")


def test_api_health_and_algorithms(tmp_path) -> None:
    # 使用独立的输出目录，避免测试触碰到正在运行的批处理任务库
    settings = Settings()
    settings.output_dir = tmp_path
    client = TestClient(create_app(settings))
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    algorithms = client.get("/api/v1/algorithms")
    assert algorithms.status_code == 200
    assert any(item["key"] == "quick_sort" for item in algorithms.json())
    assert client.get("/gallery").status_code == 200
