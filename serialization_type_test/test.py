import random
import json
from test_model_pb2 import DataMessage
from google.protobuf.json_format import MessageToDict


def random_string(length):
    return ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=length))


def generate_data_message(num_count, str_count, str_length_range=(5, 100)):
    msg = DataMessage()
    # Split numeric values equally across types
    each_type = num_count // 4
    msg.int32s.extend(random.randint(-2 ** 31, 2 ** 31 - 1) for _ in range(each_type))
    msg.int64s.extend(random.randint(-2 ** 63, 2 ** 63 - 1) for _ in range(each_type))
    msg.floats.extend(random.uniform(-1e6, 1e6) for _ in range(each_type))
    msg.doubles.extend(random.uniform(-1e10, 1e10) for _ in range(each_type))

    for _ in range(str_count):
        length = random.randint(*str_length_range)
        msg.strings.append(random_string(length))

    return msg


def serialize_and_measure(msg):
    proto_bytes = msg.SerializeToString()
    proto_size = len(proto_bytes)

    json_obj = MessageToDict(msg, preserving_proto_field_name=True)
    json_str = json.dumps(json_obj)
    json_size = len(json_str.encode('utf-8'))

    return proto_size, json_size


def run_tests(steps=11, total_fields=100, str_length_range=(5, 100)):
    print(f"{'Num%':>5} {'Str%':>5} {'Proto Size':>12} {'JSON Size':>10} {'Savings (%)':>12}")
    print("-" * 50)

    for i in range(steps):
        num_percent = i * 10
        str_percent = 100 - num_percent

        num_count = int((num_percent / 100.0) * total_fields)
        str_count = total_fields - num_count

        msg = generate_data_message(num_count, str_count, str_length_range)
        proto_size, json_size = serialize_and_measure(msg)

        savings = 100 * (1 - proto_size / json_size) if json_size != 0 else 0

        print(f"{num_percent:>5} {str_percent:>5} {proto_size:>12} {json_size:>10} {savings:>11.2f}%")


if __name__ == "__main__":
    run_tests(str_length_range=(10, 100))