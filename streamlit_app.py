"""
Streamlit dashboard for the EGX Intraday Advisor. A thin client over the
FastAPI backend — talks to it over HTTP (requests), same way any other
client would. Doesn't import from `app/` directly on purpose: keeps this
independently deployable/swappable from the API itself.

Run with: streamlit run streamlit_app.py
(FastAPI backend must be running separately: uvicorn app.main:app --reload)
"""
import os

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="EGX Intraday Advisor", layout="wide")
st.title("📈 EGX Intraday Advisor")
st.caption("Advisory only — not investment advice. Same-session day-trading signals.")

# --- Sidebar -----------------------------------------------------------------

with st.sidebar:
    st.header("Data")

    if st.button("🔄 Refresh market data", help="Starts a background scrape. Can take several minutes — check back after."):
        try:
            resp = requests.post(f"{BACKEND_URL}/stocks/ingest", timeout=30)
            resp.raise_for_status()
            st.success(resp.json()["message"])
            st.info("Reload this page in a few minutes to see updated data.")
        except requests.RequestException as e:
            st.error(f"Couldn't start refresh: {e}")

    shariah_only = st.checkbox("☪️ Shariah-compliant only", value=False)

    st.divider()
    st.header("Your notes (RAG)")

    uploaded = st.file_uploader("Upload a .txt or .md file", type=["txt", "md"])
    if uploaded is not None and st.button("Upload notes"):
        with st.spinner("Chunking and embedding..."):
            try:
                files = {"file": (uploaded.name, uploaded.getvalue())}
                resp = requests.post(f"{BACKEND_URL}/rag/upload", files=files, timeout=60)
                resp.raise_for_status()
                result = resp.json()
                st.success(f"Stored {result['chunks_stored']} chunks from {result['filename']}")
            except requests.RequestException as e:
                st.error(f"Upload failed: {e}")

    try:
        docs_resp = requests.get(f"{BACKEND_URL}/rag/documents", timeout=10)
        docs_resp.raise_for_status()
        docs = docs_resp.json()
        if docs:
            st.caption("Uploaded documents:")
            for doc in docs:
                st.text(f"  {doc['filename']} ({doc['chunk_count']} chunks)")
    except requests.RequestException:
        st.caption("Couldn't load document list — is the backend running?")


# --- Stock list ----------------------------------------------------------------

@st.cache_data(ttl=60)
def fetch_stocks(shariah_filter: bool) -> list[dict]:
    params = {"shariah": "compliant"} if shariah_filter else {}
    resp = requests.get(f"{BACKEND_URL}/stocks", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


try:
    stocks = fetch_stocks(shariah_only)
except requests.RequestException as e:
    st.error(f"Couldn't reach the backend at {BACKEND_URL} — is uvicorn running? ({e})")
    st.stop()

if not stocks:
    st.warning("No stock data yet. Click 'Refresh market data' in the sidebar to run ingestion first.")
    st.stop()

st.subheader(f"Watchlist ({len(stocks)} stocks)")

table_rows = []
for s in stocks:
    price = s.get("latest_price")
    table_rows.append({
        "Ticker": s["ticker"],
        "Company": s["company_name"],
        "Sector": s["sector"] or "—",
        "Price (EGP)": price["price"] if price else None,
        "Change %": price["change_pct"] if price else None,
        "Shariah": s["shariah_status"] or "not checked",
    })

st.dataframe(table_rows, use_container_width=True, hide_index=True)

# --- Recommendation panel -------------------------------------------------------

st.subheader("Get a recommendation")

tickers = [s["ticker"] for s in stocks]
selected = st.selectbox("Choose a stock", tickers)

if st.button("Get same-session recommendation", type="primary"):
    with st.spinner(f"Analyzing {selected} — pulling price, news, and your notes..."):
        try:
            resp = requests.get(f"{BACKEND_URL}/stocks/{selected}/recommendation", timeout=60)
            resp.raise_for_status()
            rec = resp.json()

            rec_color = {"BUY": "green", "HOLD": "orange", "SELL": "red"}.get(rec["recommendation"], "gray")
            st.markdown(f"### :{rec_color}[{rec['recommendation']}] — {rec['ticker']}")
            if rec["change_pct"] is not None:
                st.caption(f"Confidence: {rec['confidence']} | Price: {rec['latest_price']} EGP ({rec['change_pct']:+.2f}%)")
            else:
                st.caption(f"Confidence: {rec['confidence']} | Price: {rec['latest_price']} EGP")
            st.write(rec["reasoning"])
            st.caption(rec["disclaimer"])
        except requests.RequestException as e:
            st.error(f"Couldn't get a recommendation: {e}")


st.divider()
st.subheader("📋 Buy Signals — full market scan")
st.caption("Long-running background scan. May not finish in one run due to daily API quota — that's expected, rerun later to fill in more.")

if st.button("Scan for buy signals"):
    try:
        resp = requests.post(f"{BACKEND_URL}/stocks/scan", timeout=30)
        resp.raise_for_status()
        st.success(resp.json()["message"])
    except requests.RequestException as e:
        st.error(f"Couldn't start scan: {e}")

try:
    buy_resp = requests.get(f"{BACKEND_URL}/stocks/buy-signals", timeout=30)
    buy_resp.raise_for_status()
    buy_signals = buy_resp.json()

    if buy_signals:
        buy_rows = [
            {
                "Ticker": s["ticker"],
                "Company": s["company_name"],
                "Confidence": s["last_confidence"],
                "Price (EGP)": s["latest_price"]["price"] if s["latest_price"] else None,
                "Reason": s["last_recommendation_reason"],
            }
            for s in buy_signals
        ]
        st.dataframe(buy_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No BUY signals yet — run a scan first, or none currently qualify.")
except requests.RequestException as e:
    st.error(f"Couldn't load buy signals: {e}")