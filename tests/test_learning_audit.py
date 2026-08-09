from storage import memory


def test_vocabulary_learning_can_be_rolled_back(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", str(tmp_path / "memory.db"))
    memory.init()
    memory.add_vocabulary("jarvis", "paçoca")
    assert memory.get_vocabulary()["jarvis"] == "paçoca"

    result = memory.rollback_last_learning()

    assert "desfeito" in result
    assert "jarvis" not in memory.get_vocabulary()


def test_rollback_restores_previous_vocabulary_value(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", str(tmp_path / "memory.db"))
    memory.init()
    memory.add_vocabulary("app", "aplicativo")
    memory.add_vocabulary("app", "programa")

    memory.rollback_last_learning()

    assert memory.get_vocabulary()["app"] == "aplicativo"
