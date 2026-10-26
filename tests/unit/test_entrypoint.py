import ast
from pathlib import Path
import tomllib


def test_console_script_entrypoint() -> None:
    """
    Assert the console script target in pyproject.toml resolves to a top-level
    main function in src/main.py without importing the module.
    """
    repo_root = Path(__file__).resolve().parents[2]
    pyproject_path = repo_root / "pyproject.toml"

    with pyproject_path.open("rb") as f:
        pyproject_data = tomllib.load(f)

    scripts = pyproject_data.get("project", {}).get("scripts", {})
    assert "samba-nice-webui" in scripts
    entrypoint = scripts["samba-nice-webui"]
    assert entrypoint == "src.main:main"

    module_name, func_name = entrypoint.split(":")
    assert module_name == "src.main"
    assert func_name == "main"

    main_py_path = repo_root / "src" / "main.py"
    tree = ast.parse(main_py_path.read_text(encoding="utf-8"))

    top_level_functions = [
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    ]
    assert func_name in top_level_functions
