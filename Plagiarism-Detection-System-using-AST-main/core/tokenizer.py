import tokenize
from io import BytesIO

def get_tokens(code):
    tokens = []
    try:
        for tok in tokenize.tokenize(BytesIO(code.encode()).readline):
            tokens.append(tok.string)
    except:
        pass
    return tokens