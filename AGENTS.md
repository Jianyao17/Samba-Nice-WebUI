# AGENTS.md

Samba-Nice-WebUI is a NiceGUI + Pydantic web UI for managing Samba shares on Linux. The app is the `src` package (imports are `src.*`, not a distributable package name); always run commands from the repository root.

## Commands

- Install: `uv sync --extra dev` (Python >= 3.11; Docker/CI pin uv 0.5.26 and Python 3.12).
- Dev server: `docker compose -f docker-compose.test.yml up --build --watch` (UI on 8080, SMB on 1445). Running `uv run python -m src.main` directly is supported only on Linux with `testparm` installed; the process refuses to start elsewhere.
- All tests: `uv run pytest -v`. Single file/test: `uv run pytest tests/unit/test_parser.py -v`, `uv run pytest -k rename`.
- Real-Samba integration suite (skipped locally without `smbd`/`smbclient`):
  `docker build -f Dockerfile.test -t samba-nice-test .` then `docker run --rm samba-nice-test`.
- Build Linux release bundle:
  `bash scripts/build-bundle.sh`
- Test Linux release bundle:
  `bash scripts/tests/test-bundle.sh`
- Verify systemd service unit:
  `docker run --rm -v "${PWD}:/repo" -w /repo ubuntu:22.04 bash -c "apt-get update -qq && apt-get install -y -qq systemd >/dev/null && mkdir -p /opt/samba-nice-webui/venv/bin && touch /opt/samba-nice-webui/venv/bin/samba-nice-webui && chmod +x /opt/samba-nice-webui/venv/bin/samba-nice-webui && mkdir -p /etc/samba-nice-webui && touch /etc/samba-nice-webui/webui.env && systemd-analyze verify packaging/samba-nice-webui.service"`
- Isolated dev stack: `docker compose -f docker-compose.test.yml up --build --watch` (UI on 8080, SMB on 1445). Reset with `... down -v`.
- No linter, formatter, or typechecker is configured. Do not invent commands.

## Architecture and invariants

- `src/main.py` wires global singletons (`BackupManager` -> backend -> `StorageDirectoryManager`) and registers NiceGUI page routes. It always constructs `LinuxHostSambaBackend` and calls `ensure_supported_runtime()`, which refuses to start outside Linux or without `testparm`.
- Only `SAMBA_INCLUDE_CONF_PATH` is read/written. Never touch the primary `smb.conf`; users add `include = ...` themselves. That include should be the last line of `[global]`, otherwise following lines are parsed as part of the first included share.
- Linux backend validates the new file with `testparm`, atomically replaces the include file, then SIGHUP-reloads smbd. Docker needs a shared PID namespace (`pid: host` or `pid: service:samba-server`); without it the save can still succeed while the reload fails.
- Every successful save/delete records before/after snapshots in `SAMBA_BACKUP_DIR`. Consecutive identical content is deduplicated by SHA-256; undo restores the prior state and deletes the selected entry plus all newer ones.
- Share create/update/rename planning lives in `src/samba/share_ops.py`; the backend must use it so duplicate and rename rules stay identical. Names are sanitized to `\w-_.`, max 64 chars, case-insensitively unique, and `global`/`homes`/`printers` are reserved.
- All filesystem browsing/creation/rename/delete must go through `StorageDirectoryManager` and `ensure_safe_storage_path`; resolved paths must remain under `ALLOWED_STORAGE_ROOTS`. The manager creates and canonicalizes roots at init.
- Auth uses constant-time env-credential comparison and `app.storage.user`; `ui.run(storage_secret=...)` is required for sessions. New pages must use `page_layout` from `src/ui/layout.py` for auth and navigation.
- Parsing is case-insensitive: parameter keys are collapsed (repeated whitespace) and canonicalized, documented synonyms (`browseable`, `public`, `writeable`/`writable`/`write ok`) map to their canonical option, and repeated sections that differ only by case are merged with later values winning. Sections without `path` are skipped; serialization rewrites the whole include file in a canonical order, so comments and unknown formatting are not preserved (unknown options survive as `extra_options`).

## Code style

Match the surrounding file; there is no auto-formatter to normalize things later.

- 4-space indentation, double-quoted strings, two blank lines between top-level definitions, one blank line between methods. Keep lines around 100 characters and wrap long NiceGUI chains by concatenating class strings.
- Group imports as stdlib, third-party, then `src.*`, separated by blank lines. Use `from __future__ import annotations` only where the file already does.
- Annotate function signatures. Newer code uses `list[str]` and `str | None`; older files use `Optional`/`Union`, so stay consistent with the file you edit.
- Give modules, classes, and functions short docstrings that explain intent. Put the opening and closing `"""` on their own lines, with the summary between them, even for a single sentence.
- Separate logical phases with blank lines and plain comments such as `# Validate before writing`; do not number comments or restate the code. Existing numbered comments are legacy.
- Use `pathlib.Path` and argument-list subprocess calls. User-facing share errors should return `ValidationResult`; unexpected filesystem failures may raise.
- UI files use `create_*_page` factories, `render_*` components, and `_private` helpers. Put repeated Tailwind class strings in module constants as `shares_components.py` does.
- New comments and docstrings should be in English. Existing Indonesian comments are legacy; do not translate them as part of unrelated changes.

```python
class ShareMutationError(ValueError):
    """
    Raised when a share change cannot be applied.
    """


def save_share(
    self,
    share: ShareConfig,
    original_name: str | None = None,
) -> ValidationResult:
    """
    Create, update, or rename a share and apply it to Samba.
    """
    # Validate the change before touching the include file
    try:
        plan = prepare_share_save(self.list_shares(), share, original_name)
    except ShareMutationError as exc:
        return ValidationResult(is_valid=False, message=str(exc))

    # Write and validate a temp file, then replace it atomically
    temp_file = self.include_conf_path.with_name(f".tmp_{self.include_conf_path.name}")
    temp_file.write_text(serialize_all_shares(plan.shares), encoding="utf-8")

    result = self.validate_config(temp_file)
    if not result.is_valid:
        temp_file.unlink(missing_ok=True)
        return result

    temp_file.replace(self.include_conf_path)
    self.reload_service()
    return ValidationResult(is_valid=True, message=f"Share '{plan.share.name}' applied.")
```

```python
# Avoid: one-line docstrings, numbered or redundant comments, cramped spacing
def save(self, share):
    """Save the share."""
    # 1. write file
    self.path.write_text(serialize(share), encoding="utf-8")
```

## Commit messages

Use Conventional Commits, matching the existing history:

```text
<type>(<scope>): <lowercase imperative summary>
```

- Types: `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`, `chore`, `perf`, `style`, `revert`.
- Scope: the affected area, such as `ui`, `samba`, `core`, `storage`, `config`, `docker`, `ci`, `tests`, or `repo`.
- Subject: lowercase after the colon, no trailing period, at most 72 characters. Describe the behavior change, not the files touched.
- Body: optional, wrapped at 72 characters, explaining why the change was needed and any notable behavior. Use `BREAKING CHANGE:` for incompatible changes.
- Keep one logical change per commit. Do not mix refactors with fixes.
- Do not add AI attribution, `Co-authored-by` trailers, emojis, or generated-by text.

```text
feat(shares): add duplicate-name protection
fix(storage): reject deleting folders that still contain files
docs(agents): document commit message conventions
refactor(core): centralize share save planning
test(samba): cover rename collisions
```

When asked for a commit message, inspect `git diff --staged` and `git status --short`. If nothing is staged, inspect `git diff` and say the message is for unstaged changes. Return only the message unless the user asks to commit or explain it. Never stage or commit without an explicit request.

## Testing gotchas

- pytest is configured in `pyproject.toml` with `pythonpath = ["."]` and `asyncio_mode = "auto"`; run from the repo root.
- Shared fixtures live in `tests/conftest.py` and use temporary directories, never the real `/etc/samba`. The `linux_backend` fixture stubs only the process boundaries (`testparm`, `os.kill`, `reload_service`) and seeds the `public` share explicitly.
- `tests/integration/conftest.py` starts a real `smbd` as root on an ephemeral port with all state in `/tmp`; it skips when Samba binaries are absent. Do not use `tmp_path_factory` for Samba roots because its `0700` mode blocks guest access.

## Deployment notes

- The production image contains only `testparm` (not `smbd`/`smbclient`) plus the venv. Do not assume a full Samba install at runtime.
- CI runs unit tests via `uv sync --locked --extra dev` + `uv run pytest -v`, then the Docker integration suite. Images publish to GHCR only on `v*` tags. Keep `uv.lock` updated when dependencies change because Docker and CI use `--locked`.
- Release tags follow `v*` (e.g., `v0.1.0`). Pushing a `v*` tag triggers CI to test, build the Linux x86_64 bundle, generate `SHA256SUMS`, create a GitHub Release, and publish the installer to GitHub Pages. The release carries two assets: `samba-nice-webui-<version>-linux-x86_64.tar.gz` and `SHA256SUMS`; `scripts/setup.sh` is not a release asset. The build reads the tag version and syncs `pyproject.toml` and `uv.lock` to it before packaging. Checksums are verified with `sha256sum -c SHA256SUMS`. The public setup URL is `https://jianyao17.github.io/Samba-Nice-WebUI/setup.sh`, and its path is case-sensitive because GitHub Pages paths are case-sensitive.
- Default paths in `src/config.py` are Linux paths, and the app runs only on Linux or in Docker. Direct `python -m src.main` runs outside Linux fail at startup.
