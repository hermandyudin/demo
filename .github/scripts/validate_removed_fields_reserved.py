import os
import re


def parse_proto_dir(path):
    fields = {}
    reserved_nums = {}  # Reserved numbers per message (as ints)
    reserved_names = {}  # Reserved names per message (as strings)

    for root, _, files in os.walk(path):
        for file in files:
            if not file.endswith(".proto"):
                continue
            with open(os.path.join(root, file)) as f:
                text = f.read()

                # Find all message definitions
                message_blocks = re.findall(r'message\s+(\w+)\s*{([^}]*)}', text, re.DOTALL)
                for msg_name, msg_body in message_blocks:
                    reserved_nums.setdefault(msg_name, set())
                    reserved_names.setdefault(msg_name, set())

                    for line in msg_body.splitlines():
                        # Match fields
                        field_match = re.search(r'\s*\w+\s+(\w+)\s*=\s*(\d+);', line)
                        if field_match:
                            fname, fnum = field_match.groups()
                            fields.setdefault(msg_name, {})[fname] = int(fnum)

                        # Match reserved numbers
                        reserved_nums_matches = re.findall(r'reserved\s+([0-9,\s]+);', line)
                        for match in reserved_nums_matches:
                            nums = [int(n.strip()) for n in match.split(',') if n.strip()]
                            reserved_nums[msg_name].update(nums)

                        # Match reserved names
                        reserved_names_matches = re.findall(r'reserved\s+((?:"[^"]+",?\s*)+);', line)
                        for match in reserved_names_matches:
                            names = re.findall(r'"([^"]+)"', match)
                            reserved_names[msg_name].update(names)

    return fields, reserved_nums, reserved_names


# Parse both versions
prev_fields, _, _ = parse_proto_dir("master")
curr_fields, curr_reserved_nums, curr_reserved_names = parse_proto_dir("current")

errors = []

# Check for removed fields and whether they are reserved in the current version
for msg, fields in prev_fields.items():
    curr_msg_fields = curr_fields.get(msg, {})
    for fname, fnum in fields.items():
        if fname not in curr_msg_fields:
            # Fail if EITHER name OR number is not reserved
            if fnum not in curr_reserved_nums.get(msg, set()) or fname not in curr_reserved_names.get(msg, set()):
                errors.append(f'Message "{msg}" - removed field "{fname}" (#{fnum}) not reserved.')

# Output result
if errors:
    for e in errors:
        print("❌ " + e)
    exit(1)
else:
    print("✅ All removed fields are properly reserved.")
