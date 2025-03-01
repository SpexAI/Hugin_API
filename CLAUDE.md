# Hugin API Development Guide

## Build & Test Commands
- Install dependencies: `pip install -r python_examples/requirements.txt`
- Run example client: `python python_examples/trigger_image_acquistion.py --host localhost --port 5555 --config yaml/guideline.yaml`
- Debug mode: Add `--debug` flag to enable verbose logging
- Linting: `flake8 wur_api python_examples --max-line-length=100`
- Type checking: `mypy wur_api python_examples --python-version 3.8 --strict`
- Run single test: `python -m unittest tests/test_file.py::TestClass::test_method`

## Code Style Guidelines
- **Imports**: Standard library → third-party → local modules (alphabetical within groups)
- **Type Hints**: Required for all function parameters and return values
- **Naming**: snake_case for variables/functions, CamelCase for classes, UPPER_CASE for constants
- **Docstrings**: Google style with Args, Returns, Raises sections
- **Error Handling**: Use specific exceptions with detailed logging; use IntFlag for error codes
- **Logging**: Use consistent levels (DEBUG, INFO, ERROR) with both console and file handlers
- **Line Length**: Maximum 100 characters

## API Conventions
- RESTful API follows OpenAPI v3 specification in `wur_api/RemoteImagingInterface_openapi_v3.yaml`
- ZMQ communication uses YAML for message formatting (PyYAML)
- Async/await pattern for network operations and event handling