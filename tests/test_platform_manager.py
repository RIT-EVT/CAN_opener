#--------------------#
# test_platform_manager.py
# tests for the platform manager dialog
#--------------------#
from pathlib import Path

import pytest

from core.config_loader import load_platform_config

FIXTURE_DBC = Path(__file__).parent / "fixtures" / "sample.dbc"

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from ui.platform_manager import PlatformManagerDialog, _slugify  # noqa: E402

_qt_app = QApplication.instance() or QApplication([])


# stubs modal popups and file dialogs so tests don't block
def _stub_dialogs(monkeypatch, open_file_returns=None, question_returns_yes=True):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.Yes if question_returns_yes else QMessageBox.No),
    )
    if open_file_returns is not None:
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: open_file_returns)
        )


def test_slugify():
    assert _slugify("2026 EV Chassis A") == "2026_ev_chassis_a"
    assert _slugify("  Weird!!Name  ") == "weird_name"
    assert _slugify("") == "platform"


def test_create_new_platform_with_imported_dbc(tmp_path, monkeypatch):
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))
    _stub_dialogs(monkeypatch, open_file_returns=(str(FIXTURE_DBC), ""))

    dlg = PlatformManagerDialog(tmp_path)
    dlg._on_new_platform()
    dlg.name_input.setText("Test Platform")
    dlg.description_input.setPlainText("A test vehicle platform.")
    dlg._on_import_dbc()
    dlg.important_values_input.setPlainText("RPM\nTemp")
    dlg.metadata_table.insertRow(0)
    from PySide6.QtWidgets import QTableWidgetItem
    dlg.metadata_table.setItem(0, 0, QTableWidgetItem("season"))
    dlg.metadata_table.setItem(0, 1, QTableWidgetItem("2026"))
    dlg._on_save()

    assert not critical_calls
    saved_path = tmp_path / "config" / "platforms" / "test_platform.yaml"
    assert saved_path.exists()

    config = load_platform_config(saved_path)
    assert config.name == "Test Platform"
    assert config.dbc_path == FIXTURE_DBC.name
    assert config.important_values == ["RPM", "Temp"]
    assert config.metadata == {"season": "2026"}
    # the dbc was copied into dbc_store/, not just referenced
    assert (tmp_path / "dbc_store" / FIXTURE_DBC.name).exists()


def test_reject_invalid_dbc(tmp_path, monkeypatch):
    bad_file = tmp_path / "not_a_dbc.txt"
    bad_file.write_text("this is not a DBC")
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))
    _stub_dialogs(monkeypatch, open_file_returns=(str(bad_file), ""))

    dlg = PlatformManagerDialog(tmp_path)
    dlg._on_new_platform()
    dlg._on_import_dbc()

    assert critical_calls, "an invalid DBC should be rejected with an error dialog"
    assert dlg.dbc_path_label.text() == "(none)"
    assert not (tmp_path / "dbc_store" / "not_a_dbc.txt").exists()


def test_edit_existing_platform_persists_changes(tmp_path, monkeypatch):
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))
    _stub_dialogs(monkeypatch)

    platforms_dir = tmp_path / "config" / "platforms"
    platforms_dir.mkdir(parents=True)
    (tmp_path / "dbc_store").mkdir(parents=True)
    import shutil
    shutil.copy(FIXTURE_DBC, tmp_path / "dbc_store" / FIXTURE_DBC.name)
    from core.config_loader import PlatformConfig, save_platform_config
    save_platform_config(
        platforms_dir / "existing.yaml",
        PlatformConfig(name="Existing", dbc_path=FIXTURE_DBC.name, description="old"),
    )

    dlg = PlatformManagerDialog(tmp_path)
    item = next(
        dlg.platform_list.item(i) for i in range(dlg.platform_list.count())
        if dlg.platform_list.item(i).data(Qt.UserRole) == "existing"  # Qt.UserRole == 256
    )
    dlg._on_select_platform(item)
    assert dlg.name_input.text() == "Existing"
    dlg.description_input.setPlainText("updated description")
    dlg._on_save()

    assert not critical_calls
    reloaded = load_platform_config(platforms_dir / "existing.yaml")
    assert reloaded.description == "updated description"
    assert reloaded.name == "Existing"  # unrelated fields untouched


def test_new_platform_rejects_colliding_slug(tmp_path, monkeypatch):
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))
    _stub_dialogs(monkeypatch, open_file_returns=(str(FIXTURE_DBC), ""))

    platforms_dir = tmp_path / "config" / "platforms"
    platforms_dir.mkdir(parents=True)
    from core.config_loader import PlatformConfig, save_platform_config
    save_platform_config(
        platforms_dir / "test_platform.yaml",
        PlatformConfig(name="Test Platform", dbc_path="x.dbc", description="original"),
    )

    dlg = PlatformManagerDialog(tmp_path)
    dlg._on_new_platform()
    dlg.name_input.setText("Test Platform")  # slugifies to the same "test_platform"
    dlg._on_import_dbc()
    dlg._on_save()

    assert critical_calls, "saving a new platform with a colliding slug should be rejected"
    # the original file is untouched
    reloaded = load_platform_config(platforms_dir / "test_platform.yaml")
    assert reloaded.description == "original"


def test_delete_platform_removes_file(tmp_path, monkeypatch):
    _stub_dialogs(monkeypatch, question_returns_yes=True)

    platforms_dir = tmp_path / "config" / "platforms"
    platforms_dir.mkdir(parents=True)
    from core.config_loader import PlatformConfig, save_platform_config
    save_platform_config(
        platforms_dir / "to_delete.yaml", PlatformConfig(name="ToDelete", dbc_path="x.dbc")
    )

    dlg = PlatformManagerDialog(tmp_path)
    item = next(
        dlg.platform_list.item(i) for i in range(dlg.platform_list.count())
        if dlg.platform_list.item(i).data(Qt.UserRole) == "to_delete"
    )
    dlg.platform_list.setCurrentItem(item)
    dlg._on_delete_platform()

    assert not (platforms_dir / "to_delete.yaml").exists()


def test_save_without_name_is_rejected(tmp_path, monkeypatch):
    _stub_dialogs(monkeypatch)
    warning_calls = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warning_calls.append(a)))

    dlg = PlatformManagerDialog(tmp_path)
    dlg._on_new_platform()
    dlg._on_save()

    assert warning_calls
    assert list((tmp_path / "config" / "platforms").glob("*.yaml")) == []


def test_save_without_dbc_is_rejected(tmp_path, monkeypatch):
    _stub_dialogs(monkeypatch)
    warning_calls = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warning_calls.append(a)))

    dlg = PlatformManagerDialog(tmp_path)
    dlg._on_new_platform()
    dlg.name_input.setText("No DBC Yet")
    dlg._on_save()

    assert warning_calls
    assert list((tmp_path / "config" / "platforms").glob("*.yaml")) == []
