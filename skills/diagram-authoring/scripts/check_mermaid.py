#!/usr/bin/env python3
"""Validate .mmd with the official Mermaid parser; no SVG/PNG is generated."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys


def check(source, browser=None):
    spec = importlib.util.spec_from_file_location('_mermaid_check_runtime', Path(__file__).resolve().parents[1] / 'dev-tools/export_mermaid.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run(source, browser=browser)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--browser')
    args = parser.parse_args(argv)
    result = check(args.source, args.browser)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
