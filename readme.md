# Weather Assistant with SMHI, OpenCage & LLM

## 1. Overview
This project is a smart weather assistant built using Flask. The app allows users to enter a location and receive a localized weather summary based on SMHI's historical data. The summary is generated using a language model from OpenRouter. We use OpenCage for geocoding (converting place names to coordinates) and visualize the forecast in a user-friendly HTML interface.

## 2. Planning Week 1
- A working Flask application is up and running.
- The basic functionality is complete: location input → geocoding → SMHI data retrieval → LLM weather summary.  
- The UI is functional but will be improved further for usability.  
- First tests of OpenRouter-based summaries are implemented.

## 3. Project Goals & Roadmap
- **Short-Term (Week 2):**  
  - Finalize integration of all three APIs: SMHI, OpenCage, and OpenRouter.  
  - Improve error handling and input validation.

- **Week 2–3:**
  - Polish the UI and improve user interaction.
  - Auto-correction feature implemented.
  - Add support for more detailed weather insights (e.g., wind, precipitation) (OPTIONAL)
  - Improving documentation including how to run and install on different operating systems.

- **Week 4:**  
  - Final documentation and packaging.  
  - Deployable version for demo.

## 4. Repository Structure
> *May evolve over time:*
- `README.md` – This file  
- `app.py` – Main Flask application  
- `templates/` – HTML files (currently just `index.html`)  
- `static/` – Optional CSS/JS assets  
- `utils/` – Utility functions for API handling (can be modularized here)  
- `requirements.txt` – Python dependencies  
- `docs/` – Planning and documentation (if added)

## 5. How to Install & Use (Initial Instructions)

1. **Clone the Repository**
   ```bash
   git clone *REPOSITORY*
   python app.py
