import json
from pathlib import Path


def test_backup_includes_manifest_and_supported_data(tmp_path, monkeypatch):
    from modules import backup

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "transcriptions").mkdir(parents=True)
    (tmp_path / "data" / "transcriptions" / "today.md").write_text("ok", encoding="utf-8")
    (tmp_path / "data" / "kb").mkdir(parents=True)
    (tmp_path / "data" / "kb" / "memory.md").write_text("private", encoding="utf-8")
    monkeypatch.setattr(backup, "_get_config", lambda: type("C", (), {"get": lambda self, key, default=None: default})())

    result = backup.backup_all()
    assert "Backup local criado" in result
    backups = list((tmp_path / "data" / "backups").glob("backup_*"))
    assert len(backups) == 1
    manifest = json.loads((backups[0] / "manifest.json").read_text(encoding="utf-8"))
    assert "data/transcriptions" in manifest["items"]
    assert (backups[0] / "kb" / "memory.md").exists()


def test_restore_rejects_path_outside_backup_root(tmp_path, monkeypatch):
    from modules import backup

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(backup, "_get_config", lambda: type("C", (), {"get": lambda self, key, default=None: str(tmp_path / "data" / "backups") if key == "backup.local_dir" else default})())
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        backup.restore_backup(str(outside))
    except ValueError as exc:
        assert "dentro do diretório" in str(exc)
    else:
        raise AssertionError("caminho externo deveria ser rejeitado")


def test_restore_only_supported_items(tmp_path, monkeypatch):
    from modules import backup

    monkeypatch.chdir(tmp_path)
    root = tmp_path / "data" / "backups"
    source = root / "backup_20260101_000000"
    source.mkdir(parents=True)
    (source / "task-plans.json").write_text("{}", encoding="utf-8")
    (source / "secret.txt").write_text("ignored", encoding="utf-8")
    monkeypatch.setattr(backup, "_get_config", lambda: type("C", (), {"get": lambda self, key, default=None: str(root) if key == "backup.local_dir" else default})())

    result = backup.restore_backup(str(source))
    assert "task-plans.json" in result
    assert (tmp_path / "data" / "task-plans.json").exists()
    assert not (tmp_path / "data" / "secret.txt").exists()
