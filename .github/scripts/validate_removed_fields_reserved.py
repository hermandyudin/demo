import os
import re


def parse_proto_dir(path):
    fields = {}
    reserved_nums = {}  # Dictionary to hold reserved numbers per message
    reserved_names = {}  # Dictionary to hold reserved names per message

    for root, _, files in os.walk(path):
        for file in files:
            if not file.endswith(".proto"):
                continue
            with open(os.path.join(root, file)) as f:
                text = f.read()

                # Find all message definitions
                message_blocks = re.findall(r'message\s+(\w+)\s*{([^}]*)}', text, re.DOTALL)
                for msg_name, msg_body in message_blocks:
                    # Initialize reserved numbers and names for this message
                    reserved_nums[msg_name] = set()
                    reserved_names[msg_name] = set()

                    # Process each line in the message body
                    for line in msg_body.splitlines():
                        # Match fields
                        field_match = re.search(r'\s*\w+\s+(\w+)\s*=\s*(\d+);', line)
                        if field_match:
                            fname, fnum = field_match.groups()
                            fields.setdefault(msg_name, {})[fname] = fnum

                        # Match reserved numbers
                        reserved_nums_matches = re.findall(r'reserved\s+([0-9,\s]+);', line)
                        for match in reserved_nums_matches:
                            nums = [n.strip() for n in match.split(',') if n.strip()]
                            reserved_nums[msg_name].update(nums)

                        # Match reserved names
                        reserved_names_matches = re.findall(r'reserved\s+((?:"[^"]+",?\s*)+);', line)
                        for match in reserved_names_matches:
                            names = re.findall(r'"([^"]+)"', match)
                            reserved_names[msg_name].update(names)

    return fields, reserved_nums, reserved_names


prev_fields, prev_reserved_nums, prev_reserved_names = parse_proto_dir("master")
curr_fields, curr_reserved_nums, curr_reserved_names = parse_proto_dir("current")

errors = []

# Check for removed fields and if they are properly reserved in the same message
for msg, fields in prev_fields.items():
    curr_msg_fields = curr_fields.get(msg, {})
    for fname, fnum in fields.items():
        if fname not in curr_msg_fields:
            # Check if the field number or name is reserved *only in the same message*
            if fnum not in prev_reserved_nums.get(msg, set()) and fname not in prev_reserved_names.get(msg, set()):
                errors.append(f'Message "{msg}" - removed field "{fname}" (#{fnum}) not reserved.')

if errors:
    for e in errors:
        print("❌ " + e)
    exit(1)
else:
    print("✅ All removed fields are properly reserved.")
