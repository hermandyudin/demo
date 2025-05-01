import os
import re


def parse_proto_dir(path):
    messages = {}
    enums = {}
    reserved_nums = {}
    reserved_names = {}

    for root, _, files in os.walk(path):
        for file in files:
            if not file.endswith(".proto"):
                continue
            with open(os.path.join(root, file)) as f:
                text = f.read()

                # Parse messages
                for msg_name, msg_body in re.findall(r'message\s+(\w+)\s*{([^}]*)}', text, re.DOTALL):
                    reserved_nums.setdefault(msg_name, set())
                    reserved_names.setdefault(msg_name, set())
                    messages.setdefault(msg_name, {})

                    for line in msg_body.splitlines():
                        # Match fields: <type> <name> = <number>;
                        field_match = re.search(r'\s*(\w+(?:<[^>]+>)?)\s+(\w+)\s*=\s*(\d+);', line)
                        if field_match:
                            ftype, fname, fnum = field_match.groups()
                            messages[msg_name][fname] = (int(fnum), ftype)

                        # Match reserved numbers
                        for match in re.findall(r'reserved\s+([0-9,\s]+);', line):
                            nums = [int(n.strip()) for n in match.split(',') if n.strip()]
                            reserved_nums[msg_name].update(nums)

                        # Match reserved names
                        for match in re.findall(r'reserved\s+((?:"[^"]+",?\s*)+);', line):
                            names = re.findall(r'"([^"]+)"', match)
                            reserved_names[msg_name].update(names)

                # Parse enums
                for enum_name, enum_body in re.findall(r'enum\s+(\w+)\s*{([^}]*)}', text, re.DOTALL):
                    enums.setdefault(enum_name, {})
                    reserved_nums.setdefault(enum_name, set())

                    for line in enum_body.splitlines():
                        val_match = re.search(r'\s*(\w+)\s*=\s*(\d+);', line)
                        if val_match:
                            name, num = val_match.groups()
                            enums[enum_name][name] = int(num)

                        for match in re.findall(r'reserved\s+([0-9,\s]+);', line):
                            nums = [int(n.strip()) for n in match.split(',') if n.strip()]
                            reserved_nums[enum_name].update(nums)

    return messages, enums, reserved_nums, reserved_names


# Parse both versions
prev_msgs, prev_enums, _, _ = parse_proto_dir("master")
curr_msgs, curr_enums, curr_reserved_nums, curr_reserved_names = parse_proto_dir("current")

errors = []

# Check messages
for msg, fields in prev_msgs.items():
    curr_fields = curr_msgs.get(msg, {})

    for fname, (fnum, ftype) in fields.items():
        if fname not in curr_fields:
            # Field removed — must be reserved
            if fnum not in curr_reserved_nums.get(msg, set()) or fname not in curr_reserved_names.get(msg, set()):
                errors.append(f'Message "{msg}" - removed field "{fname}" (#{fnum}) not reserved.')
        else:
            curr_fnum, curr_ftype = curr_fields[fname]
            if fnum != curr_fnum:
                errors.append(f'Message "{msg}" - field "{fname}" changed number from {fnum} to {curr_fnum}.')
            if ftype != curr_ftype:
                errors.append(f'Message "{msg}" - field "{fname}" changed type from "{ftype}" to "{curr_ftype}".')

# Check enums
for enum, values in prev_enums.items():
    curr_values = curr_enums.get(enum, {})
    for name, num in values.items():
        if name not in curr_values:
            if num not in curr_reserved_nums.get(enum, set()):
                errors.append(f'Enum "{enum}" - removed value "{name}" (#{num}) not reserved.')
        else:
            if curr_values[name] != num:
                errors.append(f'Enum "{enum}" - value "{name}" changed number from {num} to {curr_values[name]}.')

# Output results
if errors:
    for e in errors:
        print("❌ " + e)
    exit(1)
else:
    print("✅ All changes are backward compatible.")
