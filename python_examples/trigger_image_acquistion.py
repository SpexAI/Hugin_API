import asyncio
import logging
import zmq.asyncio
import yaml
import sys

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def receive():
    message = await socket.recv()
    logger.info(f"Received response: {message}")
    return message

async def send(message):
    logger.info(f"Sending trigger yaml: {message}")
    await socket.send_string(message)

port = 5555
context = zmq.asyncio.Context.instance()
socket = context.socket(zmq.REQ)
socket.connect(f"tcp://localhost:{port}")

async def main():
    with socket:
        with open('../yaml/guideline.yaml') as stream:
            message = yaml.safe_load(stream)
            await send(yaml.dump(message, default_flow_style=False, allow_unicode=True))
            response = await receive()
            await asyncio.sleep(1)

asyncio.run(main())

sys.exit(0)