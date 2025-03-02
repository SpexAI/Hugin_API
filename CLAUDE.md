# Hugin API Development Guide

## Build & Test Commands
- Install dependencies: `pip install -r python_examples/requirements.txt`
- Run example client: `python python_examples/trigger_image_acquistion.py --host localhost --port 5555 --config yaml/guideline.yaml`
- Run WUR API server: `python -m wur_api.api_server`
- Run dummy Hugin: `python -m wur_api.dummy_hugin --port 5555 --error-rate 0.2`
- Linting: `flake8 wur_api python_examples --max-line-length=100`
- Type checking: `mypy wur_api python_examples --python-version 3.8 --strict`
- Run tests: `pytest tests/` or single test: `pytest tests/test_wur_api.py::test_api_status -v`

## Code Style Guidelines
- **Imports**: Standard library → third-party → local modules (alphabetical within groups)
- **Type Hints**: Required for all function parameters and return values
- **Naming**: snake_case for variables/functions, CamelCase for classes, UPPER_CASE for constants
- **Docstrings**: Google style with Args, Returns, Raises sections
- **Error Handling**: Use specific exceptions with detailed logging; use IntFlag for error codes
- **Logging**: Use consistent levels (DEBUG, INFO, ERROR) with both console and file handlers
- **Line Length**: Maximum 100 characters
- **Async**: Use asyncio for I/O-bound operations; prefer async/await over callbacks

## API Conventions
- RESTful API follows OpenAPI v3 specification in `wur_api/RemoteImagingInterface_openapi_v3.yaml`
- ZMQ communication uses YAML for message formatting (PyYAML)
- ZMQ response format: "ERROR_CODE PLANT_ID IMAGE_DIRECTORY" (space-separated)