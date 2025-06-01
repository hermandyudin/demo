import requests
from prometheus_client import Gauge

import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger()

# Replace with your actual RabbitMQ settings
RABBITMQ_API_URL = "http://localhost:15672/api/queues"
RABBITMQ_USER = "guest"
RABBITMQ_PASS = "guest"

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