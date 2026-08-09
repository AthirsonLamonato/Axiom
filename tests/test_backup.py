"""Backup local verificável e restauração sem sobrescrita."""

from pathlib import Path

from modules import backup


class _Config:
    def __init__(self, root: Path, drive=False):
        self.values = {
            "backup.local_dir": str(root / "data" / "backups"),
            "backup.google_drive.enabled": drive,
            "external_actions.mode": "simulate",
            "external_actions.live_enabled": False,
        }

    def get(self, key, default=None):
        return self.values.get(key, default)


def _prepare_workspace(tmp_path, monkeypatch, drive=False):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "data" / "transcriptions"
    source.mkdir(parents=True)
    (source / "meeting.txt").write_text("conteúdo", encoding="utf-8")
    config = _Config(tmp_path, drive=drive)
    monkeypatch.setattr(backup, "_get_config", lambda: config)
    return config


def test_backup_creates_verifiable_manifest(tmp_path, monkeypatch):
    config = _prepare_workspace(tmp_path, monkeypatch)

    backup.backup_all()

    created = next(Path(config.get("backup.local_dir")).glob("backup_*"))
    valid, detail = backup.verify_backup(created)
    assert valid is True
    assert "1 arquivo" in detail


def test_verify_detects_tampering(tmp_path, monkeypatch):
    config = _prepare_workspace(tmp_path, monkeypatch)
    backup.backup_all()
    created = next(Path(config.get("backup.local_dir")).glob("backup_*"))
    (created / "transcriptions" / "meeting.txt").write_text("alterado", encoding="utf-8")

    valid, detail = backup.verify_backup(created)

    assert valid is False
    assert "corrompido" in detail


def test_restore_copies_to_new_verified_directory(tmp_path, monkeypatch):
    config = _prepare_workspace(tmp_path, monkeypatch)
    backup.backup_all()
    created = next(Path(config.get("backup.local_dir")).glob("backup_*"))

    result = backup.restore_backup(created.name)

    restored = tmp_path / "data" / "restored" / created.name
    assert "restaurado e verificado" in result
    assert (restored / "transcriptions" / "meeting.txt").read_text(encoding="utf-8") == "conteúdo"


def test_restore_rejects_traversal_and_existing_destination(tmp_path, monkeypatch):
    config = _prepare_workspace(tmp_path, monkeypatch)
    backup.backup_all()
    created = next(Path(config.get("backup.local_dir")).glob("backup_*"))
    existing = tmp_path / "existing"
    existing.mkdir()

    assert "fora" in backup.restore_backup("../fora").lower()
    assert "já existe" in backup.restore_backup(created.name, str(existing)).lower()


def test_drive_upload_is_simulated_without_call(tmp_path, monkeypatch):
    _prepare_workspace(tmp_path, monkeypatch, drive=True)
    monkeypatch.setattr(
        backup,
        "_upload_to_drive",
        lambda *_: (_ for _ in ()).throw(AssertionError("upload real não deve ocorrer")),
    )

    result = backup.backup_all()

    assert "SIMULAÇÃO" in result
    assert "não executado" in result
