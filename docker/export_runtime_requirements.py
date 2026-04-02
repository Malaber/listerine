from __future__ import annotations

import tomllib
from pathlib import Path


def main() -> None:
    pyproject = Path("pyproject.toml")
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    for dependency in data["project"]["dependencies"]:
        print(dependency)


if __name__ == "__main__":
    main()
