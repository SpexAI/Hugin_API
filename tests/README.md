# Testing the WUR API and Hugin Interface

This directory contains tests for the WUR API and the Hugin ZMQ interface. The tests verify the correct functionality of both components, individually and when working together.

## Running the Tests

To run all tests:

```bash
cd /path/to/Hugin_API
pytest tests/
```

To run specific test files:

```bash
# Test the WUR API
pytest tests/test_wur_api.py

# Test the dummy Hugin server
pytest tests/test_dummy_hugin.py
```

To run tests with detailed output:

```bash
pytest -v tests/
```

## Test Structure

The tests are organized as follows:

1. **WUR API Tests (`test_wur_api.py`)**
   - Tests the REST API endpoints defined in the OpenAPI specification
   - Tests the interaction between the API and the Hugin ZMQ server
   - Tests the notification system

2. **Dummy Hugin Tests (`test_dummy_hugin.py`)**
   - Tests the dummy Hugin ZMQ server implementation
   - Verifies correct response formats
   - Tests error handling

## Test Environment

The tests use pytest fixtures to set up a controlled test environment:

- `api_client`: A FastAPI test client for making HTTP requests to the API
- `dummy_hugin`: A dummy Hugin ZMQ server for testing
- `test_env`: Environment variables for testing
- `notification_server`: A mock server for receiving notifications

## Requirements

To run the tests, you'll need:

```bash
pip install pytest pytest-asyncio httpx
```

These are in addition to the regular dependencies for the project.

## Writing New Tests

When adding new tests:

1. Use the provided fixtures to set up the test environment
2. Test both success and error cases
3. Clean up any resources after the test (e.g., unregister clients, stop servers)
4. For async tests, use the `@pytest.mark.asyncio` decorator