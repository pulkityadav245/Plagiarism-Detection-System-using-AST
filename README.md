# PlagiCheck – Code Plagiarism Detection System

PlagiCheck is a machine learning based system designed to detect plagiarism in source code by analyzing the **structural similarity of programs** instead of simple text matching.  
It uses **Abstract Syntax Tree (AST) analysis, TF-IDF feature extraction, cosine similarity, and a neural network model** to identify potentially plagiarized code.

---

## 🚀 Features

- **AST Based Analysis**
  - Detects logical similarity even when variable names or formatting change.

- **TF-IDF Vectorization**
  - Converts code structure into numerical vectors.

- **Neural Network Model**
  - Deep learning classifier that predicts plagiarism probability.

- **Cosine Similarity**
  - Traditional similarity metric for baseline comparison.

- **Synthetic Training Data**
  - Automatically generates similar and dissimilar code pairs for training.

- **GPU Support**
  - Uses CUDA acceleration if available.

---

## 🧠 System Architecture

The system contains three main components:

### 1. AST Feature Extraction
- Parses Python code into **Abstract Syntax Trees**
- Counts occurrences of important AST nodes
- Generates **TF-IDF feature vectors**

### 2. Similarity Detection
- Computes **cosine similarity** between feature vectors.

## Features (Phase 2)
- Multi-file upload
- AST-based comparison
- Variable normalization
- Token similarity
- Hybrid scoring

## How to Run

pip install -r requirements.txt  
streamlit run app.py

## Approach

1. Convert code → AST
2. Normalize variable names
3. Extract tokens
4. Compute similarity using:
   - AST similarity (70%)
   - Token similarity (30%)

## Future Work
- CFG implementation
- Machine Learning model
- Line-level plagiarism detection

---

