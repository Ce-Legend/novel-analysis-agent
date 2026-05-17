from __future__ import annotations

import argparse
from pathlib import Path
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a client delivery bundle zip.")
    parser.add_argument(
        "--output-dir",
        default="dist",
        help="Directory where the bundle folder and zip will be written.",
    )
    parser.add_argument(
        "--bundle-name",
        default=None,
        help="Optional bundle directory/zip base name.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root / "src"))

    from novel_agent.client_bundle import build_client_bundle

    output_dir = (project_root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    result = build_client_bundle(
        project_root,
        output_dir,
        bundle_name=args.bundle_name,
    )
    print(f"bundle_dir: {result.bundle_dir}")
    print(f"zip_path: {result.zip_path}")


if __name__ == "__main__":
    main()
