# Contributing

1. Create a virtual environment.
2. Install development dependencies: `python -m pip install -e ".[dev]"`.
3. Run `ruff check src tests` and `pytest` before opening a pull request.

## Adding a source adapter

A source adapter must return normalized `Job` objects and should not contain ranking logic. Add focused tests for parsing edge cases and keep network-dependent behavior out of the unit suite.

## Changing scoring rules

Scoring changes require regression tests demonstrating the false positive or false negative being fixed. Prefer the smallest rule change that explains the observed case.
