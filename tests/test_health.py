"""/health 探活（09 T01：依赖探活正确；停容器 → 503 degraded）。

打桩 SessionLocal / get_redis 隔离外部依赖；真实容器路径在 CI/手动验收覆盖。
"""
import app.main as m


class _FakeSession:
    def execute(self, *a, **k):
        return None

    def close(self):
        return None


class _FakeRedis:
    def ping(self):
        return True


def _db_down():
    raise RuntimeError("db down")


def test_health_ok(client, monkeypatch):
    monkeypatch.setattr(m, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(m, "get_redis", lambda: _FakeRedis())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok", "redis": "ok"}


def test_health_degraded_when_db_down(client, monkeypatch):
    monkeypatch.setattr(m, "SessionLocal", _db_down)
    monkeypatch.setattr(m, "get_redis", lambda: _FakeRedis())
    r = client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["db"] == "fail" and body["redis"] == "ok"


def test_health_degraded_when_redis_down(client, monkeypatch):
    def _redis_down():
        raise RuntimeError("redis down")

    monkeypatch.setattr(m, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(m, "get_redis", _redis_down)
    r = client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["db"] == "ok" and body["redis"] == "fail"
