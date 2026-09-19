# NashvilleHealth: Understanding Nashville's Health Through Data

A conversational Streamlit prototype that turns curated County Health Rankings & Roadmaps data into clear Nashville health stories, peer comparisons, trends, related measures, practical next steps, local resources, and a professional multi-page PDF brief.

## Run locally on Windows

1. Open Ollama and keep it running.
2. Confirm the `llama3.2` model is installed.
3. Double-click `run_windows.bat`.
4. Open `http://localhost:8501` if the browser does not open automatically.

The first launch installs the required Python packages. Later launches are faster.

## Communities included

The prototype supports Nashville and eight comparison communities:

- Nashville
- Austin
- Raleigh
- Durham
- Charlotte
- Denver
- Atlanta
- Fort Worth
- Dallas

## Main features

- Compact custom NashvilleHealth landing page with Tennessee, Davidson County, and Parthenon visuals
- Question box visible directly beneath the hero on a typical laptop screen
- Conversational follow-ups with progressive answer presentation
- Current values, peer averages, rankings, named-city comparisons, and trend interpretation
- Clear explanation of single-year data and multi-year data periods
- Compact Browse Topics view
- In-session chat history for up to ten conversations
- Multi-page PDF brief that includes every question and follow-up in the current conversation
- Related measures, practical next steps, local resources, and date details

## Data behavior

Python retrieves every value and calculates the statistics. The local language model interprets questions and helps explain verified facts. It does not create Nashville's health numbers or calculate the comparisons.

Replace `data/health_data.csv` later with a corrected file using the same columns without redesigning the app.

## Tests

```bash
pytest -q
```
