import json
import os

import requests
from prometheus_client import Gauge

import logging

# Load config
config_path = os.environ.get("CONFIG_PATH", "config.json")
with open(config_path) as f:
    config = json.load(f)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger()

# Replace with your actual RabbitMQ settings
RABBITMQ_API_URL = f"http://{config['rabbitmq']['host']}:{config['rabbitmq']['port']}/api/queues"
RABBITMQ_USER = config['rabbitmq']['user']
RABBITMQ_PASS = config['rabbitmq']['password']

# Prometheus metric
QUEUE_SIZE_METRIC = Gauge("rabbitmq_queue_size", "Queue size from RabbitMQ", ["queue"])


def fetch_queue_sizes():
    try:
        response = requests.get(RABBITMQ_API_URL, auth=(RABBITMQ_USER, RABBITMQ_PASS))
        response.raise_for_status()
        queues = response.json()

        for queue in queues:
            queue_name = queue["name"]
            queue_size = queue.get("messages", 0)

            QUEUE_SIZE_METRIC.labels(queue=queue_name).set(queue_size)
            logger.debug(f"[RabbitMQ] Queue '{queue_name}' has {queue_size} messages.")

    except requests.RequestException as e:
        logger.error(f"Failed to fetch RabbitMQ queue sizes: {e}")
