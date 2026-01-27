# Installation & Setup Guide

This document describes how to set up the local development environment and run the Streamlit application for this project.
It is intended to help new contributors or consultants onboard quickly and reproduce the application reliably.

---

## 1. Prerequisites

Ensure the following are installed on your system:

* Python 3.10+ (3.12 recommended)
* `pip` or `conda`
* A Unix-based shell (macOS or Linux recommended)

> ⚠️ Using an isolated Python environment is **strongly recommended** to avoid dependency conflicts.

---

## 2. Environment Setup (Recommended)

### Option A: Python Virtual Environment (venv)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r grad_matching_system/requirements.txt
```

### Option B: Conda Environment

```bash
conda create -n gradmatch python=3.12
conda activate gradmatch
pip install -r grad_matching_system/requirements.txt
```

---

## 3. Running the Application

From the project root directory, start the Streamlit application:

```bash
streamlit run grad_matching_system/streamlit_app.py
```

Once running, the app will be available locally in your browser (default: `http://localhost:8501`).

---

## 4. Dependency Compatibility Notes

### NumPy ABI Compatibility

Some compiled Python dependencies (e.g., `pandas`, `pyarrow`, `scipy`) may not yet be compatible with NumPy 2.x due to ABI changes.
If you encounter import errors related to NumPy (e.g., `numpy.core.multiarray failed to import`), pin NumPy to a stable 1.x version:

```bash
pip install numpy==1.26.4 --force-reinstall
```

To prevent future issues, it is recommended to explicitly pin NumPy in `grad_matching_system/requirements.txt`:

```
numpy==1.26.4
```

---

## 5. Best Practices & Recommendations

* Always use an isolated environment (`venv` or `conda`)
* Pin critical dependencies to ensure reproducibility
* Avoid using system-level Python installations
* Update this document if environment assumptions change

---

## 6. Troubleshooting

If the application fails to start:

1. Verify the active Python environment
2. Reinstall dependencies from `requirements.txt`
3. Check for version conflicts in compiled libraries
4. Ensure Streamlit is installed in the active environment

---

## 7. Notes for Contributors

This setup guide is designed to minimize onboarding time and ensure consistent execution across environments.
Please keep it updated if new dependencies or system requirements are introduced.
