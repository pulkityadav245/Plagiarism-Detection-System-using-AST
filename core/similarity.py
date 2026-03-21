from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def cosine_sim(a, b):
    try:
        cv = CountVectorizer().fit_transform([a, b])
        return cosine_similarity(cv)[0][1]
    except:
        return 0

def final_similarity(ast1, ast2, tokens1, tokens2):
    s1 = cosine_sim(ast1, ast2)
    s2 = cosine_sim(" ".join(tokens1), " ".join(tokens2))

    return 0.85 * s1 + 0.15 * s2   # reduce token impact