# Local Development Guide (Week 3)

## 1. Activate Virtual Environment

source .venv/bin/activate

---

## 2. Run Applications

| Framework   | Startup Command | Local URL |
|-------------|-----------------|-----------|
| Streamlit   | python -m streamlit run gui/streamlit/app.py | http://127.0.0.1:8501 |
| NiceGUI     | python gui/nicegui/app.py | http://127.0.0.1:8080 |
| Gradio      | python gui/gradio/app.py | http://127.0.0.1:7860 |

---

## Notes
- Streamlit auto-refreshes.
- NiceGUI runs on port 8080.
- Gradio runs on port 7860.
- If URL does not auto-open, manually paste into browser.

## Evidence
- Gradio screenshot: shows multi-page PDF with page count detected
- Streamlit screenshot: shows upload interface in demo mode

## Deployment
- Not deployed yet
- Awaiting team discussion on preferred deployment platforms
