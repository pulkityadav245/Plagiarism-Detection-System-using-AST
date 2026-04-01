from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def cosine_sim(a, b, ngram_range=(1, 1), token_pattern=r"(?u)\b\w+\b"):
    try:
        cv = CountVectorizer(ngram_range=ngram_range, token_pattern=token_pattern).fit_transform([a, b])
        return cosine_similarity(cv)[0][1]
    except:
        return 0

def final_similarity(ast1, ast2, tokens1, tokens2):
    # Strict AST matching: bigrams, trigrams, and 4-grams of AST structure.
    # We use default word pattern to extract node names like 'Expr', 'Assign'
    s1 = cosine_sim(ast1, ast2, ngram_range=(2, 4))
    
    # Strict Token matching: bi/tri-grams, catching OPERATORS AND SYMBOLS (+, -, =, (, ) and not just alphanumerics.
    # The pattern r"(?u)\S+" matches any non-whitespace sequence as a valid token.
    s2 = cosine_sim(" ".join(tokens1), " ".join(tokens2), ngram_range=(2, 3), token_pattern=r"(?u)\S+")

    return 0.85 * s1 + 0.15 * s2   # Final weighted strict score