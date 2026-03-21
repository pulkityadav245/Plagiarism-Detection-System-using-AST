import streamlit as st
import ast
from core.parser import get_ast_tree, pretty_ast
from core.tokenizer import get_tokens
from core.similarity import final_similarity
from utils.preprocessing import clean_code

st.set_page_config(page_title="PlagiCheck")
st.title("PlagiCheck - Code Plagiarism Detector (Phase 1)")

uploaded_files = st.file_uploader(
    "Upload multiple Python files",
    type=["py"],
    accept_multiple_files=True
)

if uploaded_files and len(uploaded_files) > 1:

    codes = []
    filenames = []

    # Step 1: Read files
    for file in uploaded_files:
        code = clean_code(file.read().decode())
        codes.append(code)
        filenames.append(file.name)

    st.subheader("Uploaded Files (Individual View)")

    for i in range(len(codes)):
        fname = filenames[i]
        code = codes[i]

        tree, err = get_ast_tree(code)

        with st.expander(f"{fname}"):

            st.write("### Code")
            st.code(code, language="python")

            st.write("### AST (Readable)")
            if err:
                st.error(err)
            else:
                st.code(pretty_ast(tree))

            st.write("### Raw AST")
            if not err:
                st.code(ast.dump(tree, indent=2)[:1000])

    # Step 2: Pairwise comparison
    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):

            f1 = filenames[i]
            f2 = filenames[j]

            code1 = codes[i]
            code2 = codes[j]

            tree1, err1 = get_ast_tree(code1)
            tree2, err2 = get_ast_tree(code2)

            tokens1 = get_tokens(code1)
            tokens2 = get_tokens(code2)

            # Similarity
            if err1 or err2:
                score = 0
            else:
                ast1 = ast.dump(tree1)
                ast2 = ast.dump(tree2)
                score = final_similarity(ast1, ast2, tokens1, tokens2)

            # Label
            if score > 0.8:
                label = "Highly Plagiarized 🔴"
            elif score > 0.6:
                label = "Moderate Similarity 🟡"
            else:
                label = "Low Similarity 🟢"

            st.write(f"**{f1} vs {f2} → {score:.2f} ({label})**")

            # Details
            with st.expander(f"Details: {f1} vs {f2}"):

                # 🔥 Code display
                st.write("### Code - File 1")
                st.code(code1, language="python")

                st.write("### Code - File 2")
                st.code(code2, language="python")

                # AST readable
                st.write("### AST (Readable) - File 1")
                if err1:
                    st.error(err1)
                    st.code(code1)
                else:
                    st.code(pretty_ast(tree1))

                st.write("### AST (Readable) - File 2")
                if err2:
                    st.error(err2)
                    st.code(code2)
                else:
                    st.code(pretty_ast(tree2))

                # Raw AST
                st.write("### Raw AST (File 1)")
                if not err1:
                    st.code(ast.dump(tree1, indent=2)[:1000])

                st.write("### Raw AST (File 2)")
                if not err2:
                    st.code(ast.dump(tree2, indent=2)[:1000])

                # Tokens
                st.write("### Tokens (File 1)")
                st.write(tokens1[:20])

                st.write("### Tokens (File 2)")
                st.write(tokens2[:20])

else:
    st.info("Upload at least 2 Python files")