import streamlit as st
import streamlit.components.v1 as components
import ast
import html as html_lib
from core.parser import get_ast_tree, pretty_ast
from core.tokenizer import get_tokens
from core.similarity import final_similarity
from utils.preprocessing import clean_code

st.set_page_config(
    page_title="PlagiCheck",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── SESSION STATE ─────────────────────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "landing"

# ── SHARED CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;700;800&display=swap');

:root {
    --bg:        #080a0f;
    --surface:   #0e1218;
    --card:      #121820;
    --border:    #1a2230;
    --border-hi: #263040;
    --cyan:      #00e5ff;
    --cyan-glow: rgba(0,229,255,0.15);
    --amber:     #ffc400;
    --red:       #ff3d5a;
    --green:     #00e676;
    --text:      #c8d6e8;
    --text-dim:  #4a6080;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body,
[data-testid="stAppViewContainer"],
[data-testid="stApp"] {
    background: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'Syne', sans-serif !important;
}

[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stSidebar"],
[data-testid="stStatusWidget"],
footer { display: none !important; }

[data-testid="stMainBlockContainer"] {
    max-width: 100% !important;
    padding: 0 !important;
}
[data-testid="stMain"] { padding: 0 !important; }
[data-testid="stVerticalBlock"] { gap: 0 !important; }

/* Kill streamlit default button styles globally, re-theme ours */
button[kind="primary"], button[kind="secondary"] {
    font-family: 'Space Mono', monospace !important;
}

/* File uploader */
[data-testid="stFileUploader"] {
    background: var(--surface) !important;
    border: 1.5px dashed var(--border-hi) !important;
    border-radius: 10px !important;
    padding: 1rem !important;
}
[data-testid="stFileUploaderDropzone"] {
    background: transparent !important;
    border: none !important;
}
[data-testid="stFileUploaderDropzone"] > div {
    color: var(--text-dim) !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 0.75rem !important;
}
[data-testid="stFileUploaderDropzone"] button {
    background: rgba(0,229,255,0.08) !important;
    border: 1px solid rgba(0,229,255,0.3) !important;
    color: var(--cyan) !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 0.68rem !important;
    letter-spacing: 0.1em !important;
    border-radius: 4px !important;
    padding: 0.35rem 1rem !important;
}

/* Alerts */
[data-testid="stAlert"] {
    background: rgba(0,229,255,0.05) !important;
    border: 1px solid rgba(0,229,255,0.15) !important;
    border-radius: 8px !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 0.75rem !important;
}

/* Columns gap */
[data-testid="stHorizontalBlock"] {
    gap: 1.5rem !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border-hi); border-radius: 3px; }

/* Code blocks (for st.code inside app) */
[data-testid="stCode"] pre {
    background: #0a0d14 !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 0.7rem !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
}

/* App page wrapper */
.app-wrap {
    padding: 2rem 3rem 5rem;
    max-width: 1280px;
    margin: 0 auto;
}

/* Section label */
.sec-label {
    font-family: 'Space Mono', monospace;
    font-size: 0.6rem;
    letter-spacing: 0.3em;
    text-transform: uppercase;
    color: var(--cyan);
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 1.25rem;
}
.sec-label::after { content:''; flex:1; height:1px; background:var(--border); }

/* Score card */
.sc {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 0.6rem;
    display: flex;
    align-items: center;
    gap: 1.5rem;
    position: relative;
    overflow: hidden;
    transition: border-color 0.25s, transform 0.2s;
    cursor: pointer;
}
.sc:hover { border-color: var(--border-hi); transform: translateY(-1px); }
.sc::before { content:''; position:absolute; left:0; top:0; bottom:0; width:3px; }
.sc.H::before { background: var(--red); }
.sc.M::before { background: var(--amber); }
.sc.L::before { background: var(--green); }

.sc-names { font-family:'Space Mono',monospace; font-size:0.75rem; flex:1; }
.sc-vs { color:var(--text-dim); font-size:0.6rem; margin:0 0.4em; }
.sc-bar-wrap { width:160px; height:4px; background:var(--border); border-radius:99px; overflow:hidden; }
.sc-bar { height:100%; border-radius:99px; }
.sc.H .sc-bar { background: var(--red); }
.sc.M .sc-bar { background: var(--amber); }
.sc.L .sc-bar { background: var(--green); }
.sc-pct { font-family:'Space Mono',monospace; font-size:1.6rem; font-weight:700; min-width:64px; text-align:right; }
.sc.H .sc-pct { color: var(--red); }
.sc.M .sc-pct { color: var(--amber); }
.sc.L .sc-pct { color: var(--green); }
.sc-verdict { font-family:'Space Mono',monospace; font-size:0.55rem; letter-spacing:0.15em; text-transform:uppercase; opacity:0.65; margin-top:2px; text-align:right; }
.sc-right { display:flex; flex-direction:column; align-items:flex-end; }

/* Divider */
.divider { border:none; border-top:1px solid var(--border); margin:2rem 0; }

/* Back button */
.back-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-family: 'Space Mono', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.1em;
    color: var(--text-dim);
    background: none;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.4rem 0.9rem;
    cursor: pointer;
    margin-bottom: 2rem;
    transition: color 0.2s, border-color 0.2s;
    text-transform: uppercase;
}
.back-btn:hover { color: var(--cyan); border-color: var(--cyan); }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  LANDING PAGE
# ══════════════════════════════════════════════════════════════════════════════
def landing_page():
    components.html("""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;700;800&display=swap');

* { box-sizing:border-box; margin:0; padding:0; }

body {
    background: #080a0f;
    color: #c8d6e8;
    font-family: 'Syne', sans-serif;
    min-height: 100vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}

/* Grid background */
body::before {
    content:'';
    position:fixed; inset:0;
    background:
        repeating-linear-gradient(0deg, transparent, transparent 39px, #1a2230 39px, #1a2230 40px),
        repeating-linear-gradient(90deg, transparent, transparent 39px, #1a2230 39px, #1a2230 40px);
    pointer-events:none;
    z-index:0;
}

/* Glow orb */
.orb {
    position:fixed;
    top: -10%;
    left: 50%;
    transform: translateX(-50%);
    width: 700px;
    height: 500px;
    background: radial-gradient(ellipse, rgba(0,229,255,0.09) 0%, transparent 70%);
    pointer-events:none;
    z-index:0;
}

.wrap {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0;
    text-align: center;
    padding: 2rem;
}

/* ── FLOATING ICON ── */
.icon-ring {
    width: 130px;
    height: 130px;
    border-radius: 50%;
    background: linear-gradient(135deg, #0e1a28 0%, #0a1018 100%);
    border: 1.5px solid rgba(0,229,255,0.25);
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    margin-bottom: 2.5rem;
    animation: float 4s ease-in-out infinite;
    box-shadow:
        0 0 0 1px rgba(0,229,255,0.08),
        0 0 40px rgba(0,229,255,0.12),
        0 20px 60px rgba(0,0,0,0.5);
}

/* Orbit ring */
.icon-ring::before {
    content:'';
    position:absolute;
    inset: -12px;
    border-radius:50%;
    border: 1px dashed rgba(0,229,255,0.18);
    animation: spin 12s linear infinite;
}

/* Orbit dot */
.icon-ring::after {
    content:'';
    position:absolute;
    inset: -12px;
    border-radius:50%;
    animation: spin 12s linear infinite;
}

.orbit-dot {
    position:absolute;
    width:7px; height:7px;
    background:var(--cyan,#00e5ff);
    border-radius:50%;
    top: -3px;
    left: 50%;
    transform: translateX(-50%);
    box-shadow: 0 0 10px #00e5ff;
    animation: spin 12s linear infinite;
    transform-origin: 50% calc(65px + 12px);
}

.icon-svg {
    width: 56px;
    height: 56px;
    filter: drop-shadow(0 0 14px rgba(0,229,255,0.5));
}

@keyframes float {
    0%, 100% { transform: translateY(0px); }
    50%       { transform: translateY(-14px); }
}
@keyframes spin {
    from { transform: rotate(0deg); }
    to   { transform: rotate(360deg); }
}

/* Badge */
.badge {
    font-family: 'Space Mono', monospace;
    font-size: 0.6rem;
    letter-spacing: 0.25em;
    text-transform: uppercase;
    color: #00e5ff;
    background: rgba(0,229,255,0.07);
    border: 1px solid rgba(0,229,255,0.2);
    padding: 0.3rem 0.9rem;
    border-radius: 2px;
    margin-bottom: 1.2rem;
    display: inline-block;
}

/* Title */
h1 {
    font-family: 'Syne', sans-serif;
    font-size: clamp(3rem, 8vw, 5.5rem);
    font-weight: 800;
    color: #fff;
    letter-spacing: -0.03em;
    line-height: 1;
    margin-bottom: 0.15em;
}
h1 span { color: #00e5ff; }

/* Tagline */
.tagline {
    font-family: 'Space Mono', monospace;
    font-size: 0.78rem;
    color: #4a6080;
    letter-spacing: 0.05em;
    margin-bottom: 2.5rem;
    line-height: 1.8;
}

/* Pills */
.pills {
    display: flex;
    gap: 0.6rem;
    flex-wrap: wrap;
    justify-content: center;
    margin-bottom: 3rem;
}
.pill {
    font-family: 'Space Mono', monospace;
    font-size: 0.6rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #4a6080;
    border: 1px solid #1a2230;
    border-radius: 99px;
    padding: 0.3rem 0.85rem;
    background: rgba(14,18,24,0.8);
}

/* CTA */
.cta {
    display: inline-flex;
    align-items: center;
    gap: 0.6rem;
    background: #00e5ff;
    color: #080a0f;
    font-family: 'Space Mono', monospace;
    font-weight: 700;
    font-size: 0.75rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 0.85rem 2rem;
    border-radius: 6px;
    border: none;
    cursor: pointer;
    transition: background 0.2s, transform 0.2s, box-shadow 0.2s;
    box-shadow: 0 0 30px rgba(0,229,255,0.25);
    text-decoration: none;
}
.cta:hover {
    background: #33ecff;
    transform: translateY(-2px);
    box-shadow: 0 0 50px rgba(0,229,255,0.4);
}
.cta-arrow { font-size: 1rem; }

/* Stats row */
.stats {
    display: flex;
    gap: 3rem;
    margin-top: 3.5rem;
    padding-top: 2rem;
    border-top: 1px solid #1a2230;
}
.stat-num {
    font-family: 'Syne', sans-serif;
    font-size: 1.6rem;
    font-weight: 800;
    color: #fff;
}
.stat-num span { color: #00e5ff; }
.stat-lbl {
    font-family: 'Space Mono', monospace;
    font-size: 0.58rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #4a6080;
    margin-top: 0.2rem;
}
</style>
</head>
<body>
<div class="orb"></div>
<div class="wrap">

  <!-- Floating icon -->
  <div class="icon-ring">
    <div class="orbit-dot"></div>
    <svg class="icon-svg" viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg">
      <!-- Magnifier -->
      <circle cx="22" cy="22" r="13" stroke="#00e5ff" stroke-width="2.5" fill="none"/>
      <line x1="31.5" y1="31.5" x2="46" y2="46" stroke="#00e5ff" stroke-width="3" stroke-linecap="round"/>
      <!-- Code lines inside -->
      <line x1="16" y1="19" x2="28" y2="19" stroke="#00e5ff" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
      <line x1="16" y1="23" x2="25" y2="23" stroke="#00e5ff" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
      <line x1="16" y1="27" x2="27" y2="27" stroke="#00e5ff" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
    </svg>
  </div>

  <span class="badge">&#11042; AST &middot; Cosine &middot; Token Analysis</span>
  <h1>Plagi<span>Check</span></h1>
  <p class="tagline">
    Detect code plagiarism through structural analysis.<br>
    Beyond text — we compare logic.
  </p>

  <div class="pills">
    <span class="pill">AST Parsing</span>
    <span class="pill">Variable Normalization</span>
    <span class="pill">Token Similarity</span>
    <span class="pill">Cosine Distance</span>
    <span class="pill">Hybrid Scoring</span>
  </div>

  <a class="cta" href="#" onclick="
    const btns = window.parent.document.querySelectorAll('button');
    btns.forEach(b => { if(b.innerText.includes('Start Analysis')) b.click() });
    return false;
  ">
    Start Analysis <span class="cta-arrow">&#8594;</span>
  </a>

  <div class="stats">
    <div>
      <div class="stat-num">85<span>%</span></div>
      <div class="stat-lbl">AST Weight</div>
    </div>
    <div>
      <div class="stat-num">15<span>%</span></div>
      <div class="stat-lbl">Token Weight</div>
    </div>
    <div>
      <div class="stat-num">O<span>(n²)</span></div>
      <div class="stat-lbl">Pair Comparison</div>
    </div>
  </div>

</div>

<script>
// Listener replaced by direct querySelector inside the onclick handler
</script>
</body>
</html>
""", height=700, scrolling=False)

    # Hidden button that JS triggers via postMessage — we poll session_state
    # Streamlit can't receive postMessage directly, so we use a real button below
    st.markdown("""
    <style>
    /* Make the streamlit button invisible — we use the HTML CTA instead */
    div[data-testid="stButton"] > button {
        position: fixed !important;
        opacity: 0 !important;
        pointer-events: none !important;
        width: 1px !important; height: 1px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # Visible "Enter App" button as fallback below the iframe
    st.markdown("""
    <div style="display:flex;justify-content:center;margin-top:-1rem;margin-bottom:2rem;">
      <style>
        .enter-btn {
            display:inline-flex; align-items:center; gap:0.6rem;
            background:#00e5ff; color:#080a0f;
            font-family:'Space Mono',monospace; font-weight:700;
            font-size:0.75rem; letter-spacing:0.1em; text-transform:uppercase;
            padding:0.85rem 2rem; border-radius:6px; border:none; cursor:pointer;
            box-shadow:0 0 30px rgba(0,229,255,0.25);
            transition:background 0.2s, transform 0.2s;
        }
        .enter-btn:hover { background:#33ecff; transform:translateY(-2px); }
      </style>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([2, 1, 2])
    with col2:
        if st.button("→  Start Analysis", key="go_app", use_container_width=True):
            st.session_state.page = "app"
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  APP PAGE
# ══════════════════════════════════════════════════════════════════════════════
def app_page():
    # ── helpers ───────────────────────────────────────────────────────────
    def esc(s): return html_lib.escape(str(s))

    # ── top bar ───────────────────────────────────────────────────────────
    st.markdown("""
    <div style="background:rgba(8,10,15,0.95);border-bottom:1px solid #1a2230;
                padding:0.9rem 3rem;display:flex;align-items:center;
                justify-content:space-between;position:sticky;top:0;z-index:100;">
      <div style="display:flex;align-items:center;gap:0.75rem;">
        <svg width="22" height="22" viewBox="0 0 56 56" fill="none">
          <circle cx="22" cy="22" r="13" stroke="#00e5ff" stroke-width="2.5" fill="none"/>
          <line x1="31.5" y1="31.5" x2="46" y2="46" stroke="#00e5ff" stroke-width="3" stroke-linecap="round"/>
          <line x1="16" y1="19" x2="28" y2="19" stroke="#00e5ff" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
          <line x1="16" y1="23" x2="25" y2="23" stroke="#00e5ff" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
          <line x1="16" y1="27" x2="27" y2="27" stroke="#00e5ff" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
        </svg>
        <span style="font-family:'Syne',sans-serif;font-weight:800;font-size:1.1rem;color:#fff;">
          Plagi<span style="color:#00e5ff;">Check</span>
        </span>
      </div>
      <span style="font-family:'Space Mono',monospace;font-size:0.6rem;
                   letter-spacing:0.2em;color:#4a6080;text-transform:uppercase;">
        Phase 1 &mdash; Analysis Engine
      </span>
    </div>
    """, unsafe_allow_html=True)

    # ── back button ───────────────────────────────────────────────────────
    st.markdown('<div class="app-wrap">', unsafe_allow_html=True)

    if st.button("← Back to Home", key="back"):
        st.session_state.page = "landing"
        st.rerun()

    # ── upload section ────────────────────────────────────────────────────
    st.markdown('<div class="sec-label">01 &nbsp; Upload Python Files</div>', unsafe_allow_html=True)

    uploaded_files = st.file_uploader(
        "upload",
        type=["py"],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )

    # ── process ───────────────────────────────────────────────────────────
    if uploaded_files and len(uploaded_files) > 1:
        codes, filenames = [], []
        for f in uploaded_files:
            codes.append(clean_code(f.getvalue().decode("utf-8", "ignore")))
            filenames.append(f.name)

        # ── similarity report ──────────────────────────────────────────
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        st.markdown('<div class="sec-label">02 &nbsp; Similarity Report</div>', unsafe_allow_html=True)

        parsed_data = []
        for code in codes:
            tree, err = get_ast_tree(code)
            tokens = get_tokens(code)
            parsed_data.append((tree, err, tokens))

        pairs = []
        for i in range(len(codes)):
            for j in range(i + 1, len(codes)):
                tree1, err1, tokens1 = parsed_data[i]
                tree2, err2, tokens2 = parsed_data[j]
                score = 0.0
                if not err1 and not err2:
                    score = final_similarity(ast.dump(tree1), ast.dump(tree2), tokens1, tokens2)
                pairs.append((i, j, score, err1, err2, tree1, tree2, tokens1, tokens2))

        pairs.sort(key=lambda x: x[2], reverse=True)

        # Build the full report HTML (score cards + accordions) in one component
        # so <script> tags work
        report_html = """
<!DOCTYPE html><html><head>
<meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@700;800&display=swap');
*{box-sizing:border-box;margin:0;padding:0;}
body{background:transparent;font-family:'Syne',sans-serif;color:#c8d6e8;}

.sc{background:#121820;border:1px solid #1a2230;border-radius:10px;
    padding:1.1rem 1.4rem;margin-bottom:0.5rem;display:flex;
    align-items:center;gap:1.2rem;position:relative;overflow:hidden;
    transition:border-color .25s,transform .2s;cursor:pointer;}
.sc:hover{border-color:#263040;transform:translateY(-1px);}
.sc::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;}
.sc.H::before{background:#ff3d5a;}.sc.M::before{background:#ffc400;}.sc.L::before{background:#00e676;}
.sc-names{font-family:'Space Mono',monospace;font-size:0.72rem;flex:1;color:#c8d6e8;}
.sc-vs{color:#4a6080;font-size:0.58rem;margin:0 0.35em;}
.sc-bar-wrap{width:140px;height:4px;background:#1a2230;border-radius:99px;overflow:hidden;flex-shrink:0;}
.sc-bar{height:100%;border-radius:99px;}
.sc.H .sc-bar{background:#ff3d5a;}.sc.M .sc-bar{background:#ffc400;}.sc.L .sc-bar{background:#00e676;}
.sc-pct{font-family:'Space Mono',monospace;font-size:1.5rem;font-weight:700;min-width:60px;text-align:right;flex-shrink:0;}
.sc.H .sc-pct{color:#ff3d5a;}.sc.M .sc-pct{color:#ffc400;}.sc.L .sc-pct{color:#00e676;}
.sc-verd{font-family:'Space Mono',monospace;font-size:0.52rem;letter-spacing:.15em;text-transform:uppercase;opacity:.6;text-align:right;margin-top:2px;}
.sc-right{display:flex;flex-direction:column;align-items:flex-end;flex-shrink:0;}

/* accordion */
.acc{background:#0e1218;border:1px solid #1a2230;border-radius:8px;margin-bottom:0.5rem;overflow:hidden;}
.acc-head{display:flex;align-items:center;justify-content:space-between;
          padding:0.8rem 1.1rem;cursor:pointer;
          font-family:'Space Mono',monospace;font-size:0.68rem;color:#4a6080;
          user-select:none;background:none;border:none;width:100%;text-align:left;
          transition:color .2s,background .2s;}
.acc-head:hover{color:#c8d6e8;background:rgba(255,255,255,0.02);}
.chev{color:#00e5ff;display:inline-block;transition:transform .25s;font-size:0.7rem;}
.acc.open .chev{transform:rotate(90deg);}
.acc-body{display:none;padding:1rem 1.1rem 1.2rem;border-top:1px solid #1a2230;}
.acc.open .acc-body{display:block;}

/* two col */
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:1.25rem;}
.sub{font-family:'Space Mono',monospace;font-size:0.55rem;letter-spacing:.18em;
     text-transform:uppercase;color:#4a6080;margin:0.9rem 0 0.3rem;
     padding-bottom:.3rem;border-bottom:1px solid #1a2230;}
.sub:first-child{margin-top:0;}
pre.code{background:#080a0f;border:1px solid #1a2230;border-radius:6px;
         padding:.75rem 1rem;font-family:'Space Mono',monospace;font-size:0.65rem;
         line-height:1.6;color:#8aadcc;overflow-x:auto;white-space:pre;margin-bottom:0;}

/* section sep */
.sep{border:none;border-top:1px solid #1a2230;margin:1.5rem 0;}
.sec{font-family:'Space Mono',monospace;font-size:0.58rem;letter-spacing:.28em;
     text-transform:uppercase;color:#00e5ff;display:flex;align-items:center;gap:.65rem;margin-bottom:1rem;}
.sec::after{content:'';flex:1;height:1px;background:#1a2230;}
</style>
</head>
<body>
"""

        for (i, j, score, err1, err2, tree1, tree2, tokens1, tokens2) in pairs:
            f1, f2 = filenames[i], filenames[j]
            pct = int(score * 100)
            if   score > 0.8: tier, emoji, verdict = "H", "🔴", "HIGHLY PLAGIARIZED"
            elif score > 0.6: tier, emoji, verdict = "M", "🟡", "MODERATE SIMILARITY"
            else:             tier, emoji, verdict = "L", "🟢", "LOW SIMILARITY"

            uid = f"p{i}{j}"

            p1 = html_lib.escape(pretty_ast(tree1)) if not err1 else "Parse error"
            p2 = html_lib.escape(pretty_ast(tree2)) if not err2 else "Parse error"
            
            def safe_dump(t, limit):
                try: return html_lib.escape(ast.dump(t, indent=2)[:limit])
                except TypeError: return html_lib.escape(ast.dump(t)[:limit])
                
            r1 = safe_dump(tree1, 900) if not err1 else "Parse error"
            r2 = safe_dump(tree2, 900) if not err2 else "Parse error"
            c1 = html_lib.escape(codes[i])
            c2 = html_lib.escape(codes[j])
            t1 = html_lib.escape(str(tokens1[:20]))
            t2 = html_lib.escape(str(tokens2[:20]))

            report_html += f"""
<div class="sc {tier}" onclick="toggle('{uid}')">
  <div class="sc-names">
    {html_lib.escape(f1)}<span class="sc-vs">VS</span>{html_lib.escape(f2)}
  </div>
  <div class="sc-bar-wrap"><div class="sc-bar" style="width:{pct}%"></div></div>
  <div class="sc-right">
    <div class="sc-pct">{pct}%</div>
    <div class="sc-verd">{emoji} {verdict}</div>
  </div>
</div>
<div class="acc" id="{uid}">
  <button class="acc-head" onclick="event.stopPropagation();toggle('{uid}')">
    <span>Inspect &nbsp; {html_lib.escape(f1)} &nbsp;// &nbsp;{html_lib.escape(f2)}</span>
    <span class="chev">&#9654;</span>
  </button>
  <div class="acc-body">
    <div class="grid2">
      <div>
        <div class="sub">Source &mdash; {html_lib.escape(f1)}</div>
        <pre class="code">{c1}</pre>
        <div class="sub">AST Readable</div>
        <pre class="code">{p1}</pre>
        <div class="sub">Raw AST (truncated)</div>
        <pre class="code">{r1}</pre>
        <div class="sub">Tokens (first 20)</div>
        <pre class="code">{t1}</pre>
      </div>
      <div>
        <div class="sub">Source &mdash; {html_lib.escape(f2)}</div>
        <pre class="code">{c2}</pre>
        <div class="sub">AST Readable</div>
        <pre class="code">{p2}</pre>
        <div class="sub">Raw AST (truncated)</div>
        <pre class="code">{r2}</pre>
        <div class="sub">Tokens (first 20)</div>
        <pre class="code">{t2}</pre>
      </div>
    </div>
  </div>
</div>
"""

        # ── individual file section ────────────────────────────────────
        report_html += '<hr class="sep"><div class="sec">03 &nbsp; Individual File Analysis</div>'

        for i, (code, fname) in enumerate(zip(codes, filenames)):
            tree, err, _ = parsed_data[i]
            pretty_s = html_lib.escape(pretty_ast(tree)) if not err else "Parse error"
            try:
                raw_s = html_lib.escape(ast.dump(tree, indent=2)[:1000]) if not err else "Parse error"
            except TypeError:
                raw_s = html_lib.escape(ast.dump(tree)[:1000]) if not err else "Parse error"
            code_s   = html_lib.escape(code)
            uid      = f"f{i}"

            report_html += f"""
<div class="acc" id="{uid}">
  <button class="acc-head" onclick="toggle('{uid}')">
    <span>File &nbsp;// &nbsp;{html_lib.escape(fname)}</span>
    <span class="chev">&#9654;</span>
  </button>
  <div class="acc-body">
    <div class="sub">Source Code</div>
    <pre class="code">{code_s}</pre>
    <div class="sub">AST Readable</div>
    <pre class="code">{pretty_s}</pre>
    <div class="sub">Raw AST</div>
    <pre class="code">{raw_s}</pre>
  </div>
</div>
"""

        # ── footer ────────────────────────────────────────────────────
        report_html += f"""
<hr class="sep">
<div style="font-family:'Space Mono',monospace;font-size:0.58rem;color:#4a6080;
            display:flex;justify-content:space-between;padding:0.25rem 0;">
  <span>PLAGICHECK &middot; AST + TOKEN HYBRID ENGINE</span>
  <span>{len(filenames)} files &nbsp;&middot;&nbsp; {len(pairs)} pair(s)</span>
</div>

<script>
function toggle(id) {{
    var el = document.getElementById(id);
    if(el) el.classList.toggle('open');
}}
</script>
</body></html>
"""
        # Calculate height dynamically
        est_height = 200 + len(pairs) * 120 + len(codes) * 80
        components.html(report_html, height=max(est_height, 600), scrolling=True)

    elif uploaded_files and len(uploaded_files) == 1:
        st.info("Upload at least 2 Python files to run a comparison.")
    else:
        st.markdown("""
        <div style="margin-top:2rem;padding:3rem;border:1px dashed #1a2230;border-radius:12px;
                    text-align:center;background:rgba(14,18,24,0.6);">
          <div style="font-size:2.5rem;margin-bottom:1rem">&#11042;</div>
          <div style="font-family:'Syne',sans-serif;font-size:1rem;font-weight:700;
                      color:#c8d6e8;margin-bottom:0.5rem;">No files uploaded yet</div>
          <div style="font-family:'Space Mono',monospace;font-size:0.7rem;color:#4a6080;line-height:1.9;">
            Upload two or more
            <code style="color:#00e5ff;background:rgba(0,229,255,0.1);
                         padding:.1em .4em;border-radius:3px;">.py</code>
            files above to start analysis.<br>
            PlagiCheck compares AST structure &amp; token sequences to detect plagiarism.
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)  # close app-wrap


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTER
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.page == "landing":
    landing_page()
else:
    app_page()
