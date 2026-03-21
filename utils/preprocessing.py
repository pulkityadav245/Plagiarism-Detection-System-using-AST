import re

def clean_code(code):
    # remove comments
    code = re.sub(r'#.*', '', code)

    # DO NOT remove newlines ❗
    return code.strip()