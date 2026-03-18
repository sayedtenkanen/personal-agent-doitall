"""
CLI integration tests for high-value command paths.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from agent.cli.main import cli
from agent.core.storage import init_db


@pytest.fixture(autouse=True)
def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    import agent.core.storage as storage
    import agent.core.config as config

    storage._engine = None
    storage._SessionLocal = None
    config.settings = config.Settings()
    init_db()


def _combined_output(result) -> str:
    stderr = getattr(result, "stderr", "")
    return f"{result.output}\n{stderr}"


def test_init_command_bootstraps_data_dir_and_db():
    runner = CliRunner()
    result = runner.invoke(cli, ["init"])

    assert result.exit_code == 0
    assert "Ready." in result.output
    assert "Data directory:" in result.output
    assert "Database:" in result.output


def test_doc_create_and_view_with_file_content(tmp_path):
    runner = CliRunner()
    content_file = tmp_path / "doc.md"
    content_file.write_text("# Hello\n\nCLI document content.", encoding="utf-8")

    create_result = runner.invoke(
        cli,
        [
            "doc",
            "create",
            "--slug",
            "cli-doc",
            "--title",
            "CLI Doc",
            "--file",
            str(content_file),
            "--message",
            "seed",
        ],
    )

    assert create_result.exit_code == 0
    assert "Created" in create_result.output
    assert "cli-doc" in create_result.output

    view_result = runner.invoke(cli, ["doc", "view", "--slug", "cli-doc"])
    assert view_result.exit_code == 0
    assert "CLI Doc" in view_result.output
    assert "CLI document content." in view_result.output


def test_doc_view_missing_slug_exits_with_not_found():
    runner = CliRunner()
    result = runner.invoke(cli, ["doc", "view", "--slug", "missing"])

    assert result.exit_code == 1
    assert "Not found" in _combined_output(result)


def test_conflict_resolve_missing_id_exits_with_not_found():
    runner = CliRunner()
    result = runner.invoke(cli, ["conflict", "resolve", "--id", "missing"])

    assert result.exit_code == 1
    assert "Not found" in _combined_output(result)


def test_web_disallows_non_localhost_binding():
    runner = CliRunner()
    result = runner.invoke(cli, ["web", "--host", "0.0.0.0"])

    assert result.exit_code != 0
    assert "localhost only" in _combined_output(result)
