<div align="center">
    <img src="https://user-images.githubusercontent.com/52712273/194772406-301799a8-56ae-4c6d-ab00-7fc085bcd007.jpg" alt="SpexAI Logo" width="400"/>
    <h1>Hugin API Client & WUR Interface</h1>
    <p>
        <a href="https://github.com/SpexAI/Hugin_API/blob/main/LICENSE"><img src="https://img.shields.io/github/license/SpexAI/Hugin_API" alt="License"></a>
        <img src="https://img.shields.io/badge/python-3.8%2B-blue.svg" alt="Python 3.8+">
        <img src="https://img.shields.io/badge/ZeroMQ-4.3%2B-yellow.svg" alt="ZeroMQ 4.3+">
        <img src="https://img.shields.io/badge/API-REST%2BZMQ-green.svg" alt="API: REST+ZMQ">
    </p>
</div>

A comprehensive Python client and API server for interacting with SpexAI's [Hugin](https://spexai.com/hugin/) image acquisition system. This package enables automated control, monitoring, and integration of Hugin's multi-sensor imaging system.

<p align="center">
  <img src="Data_Flow_Client_side_v0.drawio.svg?raw=true&sanitize=true" alt="Flow Diagram" width="800">
</p>

## 📋 Overview

This repository provides two main interfaces to the Hugin system:

1. **ZMQ Direct Client**
   - Low-level communication with Hugin using ZeroMQ
   - Direct control of imaging parameters
   - Binary/YAML message-based interface

2. **WUR API Server** ✨ *New!*
   - RESTful API implementing the Remote Imaging Interface specification
   - Bridge between HTTP requests and ZMQ communication
   - Fully async with notification capabilities

Both interfaces provide robust functionality for:
- Configuring image acquisition parameters
- Triggering synchronized multi-sensor captures
- Monitoring system status and error conditions
- Managing data collection workflows

## 🚀 Installation

```bash
# Clone the repository
git clone https://github.com/SpexAI/Hugin_API.git
cd Hugin_API

# Install all dependencies
pip install -r python_examples/requirements.txt
```

### Environment Configuration

For the WUR API server, create a `.env` file based on the provided template:

```bash
cp .env.example .env
# Edit the .env file to match your environment
```

## 💻 Usage

### ZMQ Direct Client

#### Basic Example

```python
import asyncio
from hugin_client import ZMQClient

async def main():
    # Initialize client
    client = ZMQClient(host="localhost", port=5555)
    
    # Send trigger command
    await client.send_trigger()
    
    # Get response
    response = await client.receive()
    
    # Process error codes
    client.process_error_code(response)

if __name__ == "__main__":
    asyncio.run(main())
```

#### Command-Line Interface

```bash
# Run the ZMQ client with a specific configuration
python python_examples/trigger_image_acquistion.py \
    --host 192.168.1.100 \
    --port 5555 \
    --config yaml/guideline.yaml \
    --debug
```

<details>
<summary>CLI Options</summary>

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | Hugin system hostname/IP | localhost |
| `--port` | ZMQ port number | 5555 |
| `--config` | Path to YAML config file | yaml/guideline.yaml |
| `--debug` | Enable debug logging | False |
| `--timeout` | Connection timeout (seconds) | 30.0 |

</details>

### WUR API Server

#### Running the Server

```bash
# Start the WUR API server
python -m wur_api.api_server
```

The server will be available at http://localhost:8000/RemoteImagingInterface.

#### Testing with Dummy Hugin

For development and testing without a physical Hugin system:

```bash
# Terminal 1: Start the dummy Hugin ZMQ server
python -m wur_api.dummy_hugin --port 5555 --error-rate 0.2

# Terminal 2: Start the WUR API server
python -m wur_api.api_server
```

<details>
<summary>Dummy Hugin Options</summary>

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | Host to bind to | * (all interfaces) |
| `--port` | Port to bind to | 5555 |
| `--error-rate` | Probability of generating errors (0.0-1.0) | 0.2 |
| `--delay-min` | Minimum processing delay (seconds) | 0.5 |
| `--delay-max` | Maximum processing delay (seconds) | 2.0 |
| `--debug` | Enable debug logging | False |

</details>

### YAML Configuration

The ZMQ client uses YAML configuration files to specify image acquisition parameters:

<details>
<summary>Example YAML Configuration</summary>

```yaml
required:
  path: 'test/test/'             # Path to the bucket
  plant-id: 'plant-id'           # Plant ID as used by client
  uuid: 'uuid'                   # UUID given by the system
  time-stamp: 'yy-mm-dd-hh-mm-ss'# UTC always
  position:
    greenhouse: 'greenhouse-name' # As it appears in the front end
    is-fixed: true               # false if one fixed position or table
    fixed:
      x: 1.2                     # Position x on the greenhouse grid
      y: 1.6                     # Position y on the greenhouse grid
    table:
      table-id: 'table-id'       # ID of the table
      row: 0                     # Row position on the table
      col: 0                     # Col position on the table
  sensors:
    spectral:
      in-use: true
      default-settings: true
    thermal:
      in-use: true
      default-settings: true
    3D:
      in-use: true
      default-settings: true
      settings:
        preset: 'day'            # The D415 can be configured through a config.json
```
</details>

### Error Code Handling

The client includes comprehensive error code handling for various system states:

<details>
<summary>Error Codes Table</summary>

| Code | Description | Details |
|------|-------------|---------|
| 0    | SUCCESS     | ≥ 1 main, ≥ 2 3ds, ≥ thermal images captured |
| 1    | MAIN_CORRUPT| No or corrupt main image |
| 2    | 3D0_CORRUPT | No or corrupt 3D camera 0 |
| 4    | 3D1_CORRUPT | No or corrupt 3D camera 1 |
| 8    | 3D2_CORRUPT | No or corrupt 3D camera 2 |
| 16   | THERMAL_CORRUPT | No or corrupt thermal image |
| 32   | RESET_TIMEOUT  | Timeout for reset (30s) |
| 64   | REBOOT_TIMEOUT | Timeout for reboot (1m) |
| 128  | FATAL_UNKNOWN  | Fatal unknown error |

**Common Combinations**:
- `14`: All 3D cameras missing (2 + 4 + 8)
- `15`: Only thermal present (1 + 2 + 4 + 8)
</details>

#### Error Handling Example

```python
from hugin_client import ImageError, ZMQClient

async def handle_acquisition():
    client = ZMQClient()
    response = await client.receive()
    error, plant_id, image_dir = ImageError.parse_response(response)
    
    if error == ImageError.SUCCESS:
        logger.info(f"Acquisition successful for {plant_id}, stored at {image_dir}")
        return True
        
    if error & ImageError.THREE_D0_CORRUPT:
        logger.error("3D camera 0 failed")
    
    if error.value == 14:
        logger.error("All 3D cameras missing")
        
    return False
```

### ZMQ Response Format

ZMQ responses from Hugin follow this space-separated format:
```
ERROR_CODE PLANT_ID IMAGE_DIRECTORY
```

Example:
```
0 DOR-1049-03 ImageSet_2025_03_01_20_10_58
```

## 🌐 WUR API Documentation

The WUR API implements the Remote Imaging Interface specification, providing a RESTful interface to the Hugin system. It works by translating HTTP requests to ZMQ messages and handling the response.

<div align="center">
  <img src="https://mermaid.ink/img/pako:eNqFks1OwkAQx1-l2RML6aSFQmNj4gc3o8aLF1MPy3bamli2YTuIF9-Ad5_BeCQxmvgYPbUm6owFL30ke_j_fv_Z2ekBwTkF1Aa3lnGRJPwccCl4ykzPSJkNuhbI0HEZKdE1fPAAZQdE1zqhJXt_n-7I4-fL2jEJ-FBu_CbEV_Kx3-Bj_HV5MQZrTYjvcdtILGF-BaxXX8YEIu-xMRYX7F71rbvs3Q9vbs8Ou6vO48dFHSKAwuVSMxsIkY69jdWbFDxmbXVJsyuDCm6FLkpR7Y05N-Ns2wjlJa211RKCCDreQHvRaUejoV7sNFXRgimAQcyFrRu2Yk5sRrgnfU08JRQzIcEAG0mXs9NyldtZRXQttD7KssPz4HrISrEu-JiiHxOyP4-A-yZI5QSzDJCTcpYbf3hKSZ-xsOAaqQ5VCO2kmzB7CQWyQDYxl4zYoC0Vyxcj4nUn4XmVynvp_i_zM8jM7OwHmdMpHQ?type=png" width="800" alt="WUR API Flowchart">
</div>

### API Workflow

The typical workflow for interacting with the WUR API:

1. **Check Camera Status** - `GET /status`
2. **Get Available Settings** - `GET /settings`
3. **Apply Settings** - `PUT /settings/{settingsName}`
4. **Set Metadata** - `POST /metadata`
5. **Trigger Image Acquisition** - `PUT /trigger/{plantId}`
6. **Poll Trigger Status** - `GET /status/{triggerId}`
7. **Retrieve Image ID** - `GET /getimageid/{triggerId}`
8. **Repeat**

### Base URLs

- `http://localhost:8000/RemoteImagingInterface`
- `https://localhost:8000/RemoteImagingInterface`

### Notifications

The WUR API supports client notifications via webhooks:

1. **Register** - `POST /register` to receive notifications
2. **Image Acquisition** - Notifications sent when images are taken
3. **Heartbeats** - Optional periodic health checks
4. **Unregister** - `POST /unregister` to stop notifications

### Testing with Automated Test Suite

A comprehensive test suite is available for validation:

```bash
# Run all tests
pytest tests/

# Run API tests only
pytest tests/test_wur_api.py -v
```

### API Reference

<details>
<summary>View Detailed API Reference</summary>

#### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/status` | Get overall system status |
| GET | `/settings` | List available settings files |
| PUT | `/settings/{settingsName}` | Apply settings file |
| POST | `/metadata` | Set metadata for next imaging task |
| PUT | `/trigger/{plantId}` | Trigger new imaging task |
| GET | `/status/{triggerId}` | Check status of triggered task |
| GET | `/getimageid/{triggerId}` | Get image ID after completion |
| POST | `/register` | Register for notifications |
| POST | `/unregister` | Unregister from notifications |

#### Data Models

<details>
<summary>ImagingMetaData</summary>

```json
{
  "PlantId": "string",        // Plant identifier, unique within experiment
  "ExperimentId": "string",   // Experiment identifier
  "TreatmentId": "string",    // Treatment identifier
  "Height": 0.0,              // Height at which the plant is elevated
  "Angle": 0.0                // Angle at which the plant is rotated for imaging
}
```
</details>

<details>
<summary>CallBackRegistrationData</summary>

```json
{
  "ClientName": "string",     // Name to identify a registered client
  "Uri": "string",            // URI where notifications should be sent
  "SendPathInfo": true,       // Whether to send the path where an image is stored
  "SendData": true,           // Whether to send the image data as binary blob
  "HeartBeatInterval": 0      // Interval in ms for heartbeat (0 = no heartbeat)
}
```
</details>

<details>
<summary>Response</summary>

```json
{
  "Values": ["string"],       // Values returned, if any
  "Message": {
    "MessageText": "string",  // Extra info about the status of the call
    "Type": "string"          // Type: None, Error, Warning, Message, Success
  }
}
```
</details>

#### Response Message Types

- **None**: No specific message, operation completed
- **Error**: Operation failed with error
- **Warning**: Operation completed with warnings
- **Message**: Informational message
- **Success**: Operation completed successfully

#### Example API Sequence

<details>
<summary>Complete API Interaction Example</summary>

```javascript
// 1. Check camera status
GET /status
// Response: { "Values": [], "Message": { "MessageText": "idle", "Type": "Message" } }

// 2. Get available settings
GET /settings
// Response: { "Values": ["standard", "high_res"], "Message": { "MessageText": "", "Type": "None" } }

// 3. Apply settings
PUT /settings/high_res
// Response: { "Values": [], "Message": { "MessageText": "", "Type": "Success" } }

// 4. Set metadata
POST /metadata
{
  "PlantId": "PLANT-001",
  "ExperimentId": "EXP-2025-03",
  "TreatmentId": "CONTROL",
  "Height": 1.2,
  "Angle": 45.0
}
// Response: { "Values": [], "Message": { "MessageText": "", "Type": "Success" } }

// 5. Trigger imaging
PUT /trigger/PLANT-001
// Response: { "Values": ["trigger-123"], "Message": { "MessageText": "", "Type": "Success" } }

// 6. Poll status
GET /status/trigger-123
// Response: { "Values": [], "Message": { "MessageText": "busy", "Type": "Message" } }
// ... wait ...
GET /status/trigger-123
// Response: { "Values": [], "Message": { "MessageText": "finished", "Type": "Message" } }

// 7. Get image ID
GET /getimageid/trigger-123
// Response: { "Values": ["PLANT-001_ImageSet_20250301_123456"], "Message": { "MessageText": "", "Type": "Success" } }
```
</details>

</details>

### Environment Configuration

The WUR API server and ZMQ client are configured using environment variables:

<details>
<summary>Configuration Options</summary>

| Variable | Description | Default |
|----------|-------------|---------|
| HUGIN_ZMQ_HOST | ZMQ server hostname/IP | localhost |
| HUGIN_ZMQ_PORT | ZMQ server port | 5555 |
| HUGIN_ZMQ_TIMEOUT | ZMQ timeout (seconds) | 20.0 |
| HUGIN_S3_BUCKET | S3 bucket for image storage | hugin-images |
| HUGIN_S3_BASE_PATH | Base path in bucket | images |
| WUR_API_HOST | API server host | 0.0.0.0 |
| WUR_API_PORT | API server port | 8000 |
| LOG_LEVEL | Logging level | INFO |

</details>


## 🔬 Testing

Comprehensive testing tools are included to validate both the ZMQ client and the WUR API server:

```bash
# Run all tests
pytest tests/

# Run specific test suite
pytest tests/test_wur_api.py
pytest tests/test_dummy_hugin.py

# Run with coverage report
pytest --cov=wur_api tests/
```

<details>
<summary>Test Coverage Overview</summary>

| Component | Description |
|-----------|-------------|
| API Endpoints | Tests for all API endpoints and response formats |
| ZMQ Communication | Tests for ZMQ client/server messaging |
| Error Handling | Tests for error detection and recovery |
| Notifications | Tests for client registration and notification delivery |
| Concurrency | Tests for async operations and request handling |

</details>

## 🤝 Contributing

Contributions to the Hugin API are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes following the project's coding style
4. Add tests for your changes
5. Run existing tests to ensure nothing was broken
6. Commit your changes (`git commit -am 'Add new feature: description'`)
7. Push to your branch (`git push origin feature/my-feature`)
8. Create a new Pull Request

## 📝 Development Practices

Please follow these practices when contributing:

- Use [semantic commit messages](https://gist.github.com/joshbuchea/6f47e86d2510bce28f8e7f42ae84c716)
- Add comprehensive docstrings and type hints
- Ensure async/await patterns are used for I/O operations
- Write unit tests for new functionality
- Follow the style guide in CLAUDE.md

## 📄 License

This project is licensed under the [MIT License](LICENSE).

## 💬 Support

For support and questions about the Hugin system, please contact SpexAI support or visit [spexai.com/hugin](https://spexai.com/hugin/).

---

<div align="center">
    <p>Developed with ❤️ by <a href="https://spexai.com">SpexAI</a></p>
</div>

