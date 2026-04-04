from __future__ import annotations

import tasks


def test_pip_env_unsets_only_missing_bundle_paths(monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", "/missing/cert.pem")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/missing/requests.pem")
    monkeypatch.setenv("UNCHANGED_VAR", "present")

    env = tasks._pip_env()

    assert "SSL_CERT_FILE" not in env
    assert "REQUESTS_CA_BUNDLE" not in env
    assert env["UNCHANGED_VAR"] == "present"


def test_tool_path_prefers_current_interpreter_bin(monkeypatch, tmp_path):
    current_bin = tmp_path / "bin"
    current_bin.mkdir()
    tool = current_bin / "pytest"
    tool.write_text("", encoding="utf-8")

    monkeypatch.setattr(tasks.sys, "executable", str(current_bin / "python"))

    assert tasks._tool_path("pytest") == str(tool)


def test_tool_path_falls_back_to_repo_venv(monkeypatch, tmp_path):
    current_bin = tmp_path / "python-bin"
    current_bin.mkdir()
    monkeypatch.setattr(tasks.sys, "executable", str(current_bin / "python"))

    repo_root = tmp_path / "repo"
    venv_bin = repo_root / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    tool = venv_bin / "flake8"
    tool.write_text("", encoding="utf-8")

    monkeypatch.setattr(tasks, "ROOT", repo_root)

    assert tasks._tool_path("flake8") == str(tool)


def test_node_command_wraps_repo_command():
    command = tasks._node_command("npm run test:js")

    assert "nvm use 24" in command
    assert "Node 24.x is required" in command
    assert command.endswith("&& npm run test:js")


def test_black_command_uses_repo_black_binary():
    command = tasks._black_command("--check", ".")

    assert "--check" in command
    assert command.endswith(" .")
    assert "black" in command


def test_app_env_sets_ci_aligned_runtime_values(monkeypatch):
    monkeypatch.setenv("EXISTING", "1")

    env = tasks._app_env(
        seed_path="app/fixtures/review_seed_e2e.json",
        database_url="sqlite+aiosqlite:///./tmp.db",
        webauthn_rp_id="localhost",
    )

    assert env["PYTHONPATH"] == "."
    assert env["SEED_DATA_PATH"] == "app/fixtures/review_seed_e2e.json"
    assert env["DATABASE_URL"] == "sqlite+aiosqlite:///./tmp.db"
    assert env["WEBAUTHN_RP_ID"] == "localhost"
    assert env["EXISTING"] == "1"


def test_read_pid_returns_none_when_file_is_missing(tmp_path):
    assert tasks._read_pid(tmp_path / "missing.pid") is None


def test_read_pid_parses_integer_pid(tmp_path):
    pid_path = tmp_path / "server.pid"
    pid_path.write_text("12345\n", encoding="utf-8")

    assert tasks._read_pid(pid_path) == 12345


def test_pid_is_running_reports_missing_process():
    assert tasks._pid_is_running(999999) is False
