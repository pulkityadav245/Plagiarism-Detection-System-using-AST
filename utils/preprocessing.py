import re

def clean_code(code):
    # AST naturally ignores comments, so removing them via naive regex 
    # is dangerous (breaks strings with #). We just return the code.
    return code.strip()
