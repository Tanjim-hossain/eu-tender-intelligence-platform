"""Verify that the API wheel ships its browser assets and package modules."""
from pathlib import Path
from zipfile import ZipFile


def main() -> None:
    wheels = sorted(Path("dist").glob("tendergraph-*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Expected exactly one TenderGraph wheel in dist/")
    with ZipFile(wheels[0]) as archive:
        required = {
            "tendergraph/api/web/index.html", "tendergraph/api/web/style.css",
            "tendergraph/api/web/app.js", "tendergraph/api/app.py",
            "tendergraph/pipeline/status.py",
        }
        missing = required - set(archive.namelist())
        if missing:
            raise SystemExit(f"Wheel is missing required assets: {sorted(missing)}")
    print(f"Wheel assets verified: {wheels[0]}")


if __name__ == "__main__":
    main()
