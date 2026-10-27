#!/bin/sh
# Run the analyzer test suite with pytest from analyzer/, where pyproject.toml
# holds its settings. Arguments go to pytest: node ids such as
# tests/test_cli.py::DetectTests, and options such as -k or -x.
cd "$(dirname "$0")/.." || exit 2
exec python3 -m pytest "$@"
