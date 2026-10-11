# Mood Dividend — updated integration setup

## Features included in `app.py`
- Selectable local Ollama model: `llama3.2:1b` or `gemma2:2b`
- ElevenLabs mission narration (text is sent to ElevenLabs only when audio is requested)
- SerpApi outdoor destination search (search terms/location are sent to SerpApi)
- MongoDB Atlas persistent mission journal and optional feedback
- Optional Temporal workflow for mission generation + validation retries
- Direct Ollama fallback if Temporal is disabled or unavailable

## 1. Install packages
From the project folder in PowerShell:

```powershell
py -m pip install streamlit requests python-dotenv pymongo temporalio
```

## 2. Set up `.env`
Create or update `.env` in the same folder as `app.py`. Keep your existing API keys and add:

```dotenv
ELEVENLABS_API_KEY=your_elevenlabs_key
SERPAPI_API_KEY=your_serpapi_key
MONGODB_URI=mongodb+srv://USERNAME:PASSWORD@YOUR_CLUSTER_URL/
```

Do not put quotes around keys unless required by your actual value. Do not share `.env` or commit it to Git. Add `.env` to `.gitignore`.

## 3. Pull the Ollama models you want
In PowerShell:

```powershell
ollama pull llama3.2:1b
ollama pull gemma2:2b
```

Model availability depends on your installed Ollama version and device. If `gemma2:2b` is unavailable, use `ollama list` and select a model that is installed; update the options in the sidebar if needed. Ollama must be running locally.

## 4. Start the app
```powershell
py -m streamlit run app.py
```

The app can be used without Temporal. Leave “Use Temporal retry workflow” unchecked unless you have the Temporal server and worker running.

## 5. Enable Temporal (optional)
Open a separate PowerShell terminal and start the local Temporal development server:

```powershell
temporal server start-dev
```

In a second terminal, from the project folder:

```powershell
py temporal_worker.py
```

Keep both terminals running. In the Streamlit app, check “Use Temporal retry workflow” before creating a mission. If Temporal cannot connect or a workflow fails, the app falls back to direct local Ollama generation.

## 6. MongoDB Atlas journal
Create a database user and allow your current IP in Atlas Network Access. Put the connection URI in `.env`. The app stores completed mission title/activity, completion timestamp, status, and optional feedback. This is a shared journal collection, not an authenticated multi-user system; do not use it for sensitive personal data.

## 7. Privacy notes
- Ollama mission generation is local when using the local Ollama server.
- ElevenLabs receives mission narration text when audio is requested.
- SerpApi receives the destination search query and location when a search is submitted.
- MongoDB Atlas stores journal records in the configured cloud database.
- Temporal runs locally in this setup; workflow histories may include preference inputs and generated mission data. Keep the Temporal server private.

## 8. Troubleshooting
- `MONGODB_URI is missing`: add it to `.env`, then restart Streamlit.
- Atlas connection timeout: verify the URI, database user/password, and Network Access IP allowlist.
- `model not found`: run `ollama pull <model-name>`.
- Temporal connection error: uncheck the Temporal option or start the server and worker.
- If your Ollama version does not support a selected model, use an installed compatible model from `ollama list`.
