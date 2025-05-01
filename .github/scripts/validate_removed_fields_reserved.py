import os
import re

def parse_proto_dir(path):
    messages = {}
    enums = {}

    for root, _, files in os.walk(path):
        for file in files:
            if not file.endswith(".proto"):
                continue
            with open(os.path.join(root, file)) as f:
                text = f.read()

                # MESSAGE PARSING
                message_blocks = re.findall(r'message\s+(\w+)\s*{([^}]*)}', text, re.DOTALL)
                for msg_name, msg_body in message_blocks:
                    msg_info = {
                        "fields": {},           # name -> (type, number)
                        "num_to_name": {},      # number -> name
                        "reserved_nums": set(),
                        "reserved_names": set()
                    }

                    for line in msg_body.splitlines():
                        field_match = re.match(r'\s*(\w+)\s+(\w+)\s*=\s*(\d+);', line)
                        if field_match:
                            ftype, fname, fnum = field_match.groups()
                            msg_info["fields"][fname] = (ftype, fnum)
                            msg_info["num_to_name"][fnum] = fname

                        reserved_nums = re.findall(r'reserved\s+([0-9,\s]+);', line)
                        for match in reserved_nums:
                            nums = [n.strip() for n in match.split(',') if n.strip()]
                            msg_info["reserved_nums"].update(nums)

                        reserved_names = re.findall(r'reserved\s+((?:"[^"]+",?\s*)+);', line)
                        for match in reserved_names:
                            names = re.findall(r'"([^"]+)"', match)
                            msg_info["reserved_names"].update(names)

                    messages[msg_name] = msg_info

                # ENUM PARSING
                enum_blocks = re.findall(r'enum\s+(\w+)\s*{([^}]*)}', text, re.DOTALL)
                for enum_name, enum_body in enum_blocks:
                    enum_info = {
                        "values": {},          # name -> number
                        "reserved_nums": set(),
                        "reserved_names": set()
                    }

                    for line in enum_body.splitlines():
                        value_match = re.match(r'\s*(\w+)\s*=\s*(\d+);', line)
                        if value_match:
                            vname, vnum = value_match.groups()
                            enum_info["values"][vname] = vnum

                        reserved_nums = re.findall(r'reserved\s+([0-9,\s]+);', line)
                        for match in reserved_nums:
                            nums = [n.strip() for n in match.split(',') if n.strip()]
                            enum_info["reserved_nums"].update(nums)

                        reserved_names = re.findall(r'reserved\s+((?:"[^"]+",?\s*)+);', line)
                        for match in reserved_names:
                            names = re.findall(r'"([^"]+)"', match)
                            enum_info["reserved_names"].update(names)

                    enums[enum_name] = enum_info

    return messages, enums


# === MAIN VALIDATION ===

prev_messages, prev_enums = parse_proto_dir("master")
curr_messages, curr_enums = parse_proto_dir("current")

errors = []

# MESSAGE CHANGES
for msg_name, prev_info in prev_messages.items():
    curr_info = curr_messages.get(msg_name)

    prev_fields = prev_info["fields"]
    prev_num_to_name = prev_info["num_to_name"]

    if not curr_info:
        errors.append(f'Message "{msg_name}" was completely removed.')
        continue

    curr_fields = curr_info["fields"]
    curr_reserved_nums = curr_info["reserved_nums"]
    curr_reserved_names = curr_info["reserved_names"]

    for fname, (prev_type, prev_num) in prev_fields.items():
        if fname not in curr_fields:
            # Field was removed
            if prev_num not in curr_reserved_nums or fname not in curr_reserved_names:
                errors.append(f'Message "{msg_name}": field "{fname}" (#{prev_num}) was removed and not reserved.')
        else:
            curr_type, curr_num = curr_fields[fname]
            if curr_type != prev_type or curr_num != prev_num:
                errors.append(f'Message "{msg_name}": field "{fname}" changed from {prev_type} #{prev_num} to {curr_type} #{curr_num}.')

# ENUM CHANGES
for enum_name, prev_info in prev_enums.items():
    curr_info = curr_enums.get(enum_name)

    if not curr_info:
        errors.append(f'Enum "{enum_name}" was completely removed.')
        continue

    for vname, vnum in prev_info["values"].items():
        if vname not in curr_info["values"]:
            if vnum not in curr_info["reserved_nums"] or vname not in curr_info["reserved_names"]:
                errors.append(f'Enum "{enum_name}": value "{vname}" (#{vnum}) was removed and not reserved.')
        else:
            curr_vnum = curr_info["values"][vname]
            if curr_vnum != vnum:
                errors.append(f'Enum "{enum_name}": value "{vname}" changed number from #{vnum} to #{curr_vnum}.')

# === REPORT ===

if errors:
    for e in errors:
        print("❌ " + e)
    exit(1)
else:
    print("✅ All protobuf fields and enums are backward compatible.")
