import os
import re


def parse_proto_dir(path):
    fields = {}
    reserved_nums = set()
    reserved_names = set()

    for file in os.listdir(path):
        if not file.endswith(".proto"):
            continue
        with open(os.path.join(path, file)) as f:
            text = f.read()
            message_blocks = re.findall(r'message\s+(\w+)\s*{([^}]*)}', text, re.DOTALL)
            for msg_name, msg_body in message_blocks:
                for line in msg_body.splitlines():
                    field_match = re.search(r'\s*\w+\s+(\w+)\s*=\s*(\d+);', line)
                    reserved_num_match = re.findall(r'reserved\s+([0-9, ]+);', line)
                    reserved_name_match = re.findall(r'reserved\s+"([^"]+)";', line)

                    if field_match:
                        fields.setdefault(msg_name, {})[field_match.group(1)] = field_match.group(2)

                    for group in reserved_num_match:
                        nums = [n.strip() for n in group.split(',')]
                        reserved_nums.update(nums)

                    reserved_names.update(reserved_name_match)
    return fields, reserved_nums, reserved_names


prev_fields, prev_reserved_nums, prev_reserved_names = parse_proto_dir("master")
curr_fields, curr_reserved_nums, curr_reserved_names = parse_proto_dir("current")

errors = []

for msg, fields in prev_fields.items():
    curr_msg_fields = curr_fields.get(msg, {})
    for fname, fnum in fields.items():
        if fname not in curr_msg_fields:
            if fnum not in curr_reserved_nums or fname not in curr_reserved_names:
                errors.append(f'Message "{msg}" - removed field "{fname}" (#{fnum}) not reserved.')

if errors:
    for e in errors:
        print("❌ " + e)
    exit(1)
else:
    print("✅ All removed fields are properly reserved.")
