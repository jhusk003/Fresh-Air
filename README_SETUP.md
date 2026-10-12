# ⚙️ Fresh Air 🌿 — Setup & Integration Guide

This guide explains how to install, configure, and run Fresh Air (originally Mood Dividend / Touch Grass) on Windows using PowerShell.

## ✨ Features and Integrations

The application supports the following features when configured:

* 🤖 **Selectable local AI models:** Ollama with `llama3.2:1b` or `gemma2:2b`.
* 🔊 **ElevenLabs narration:** Generate spoken mission text when audio is requested.
* 📍 **SerpApi destination search:** Search for outdoor destinations using submitted search terms and location.
* 📖 **MongoDB Atlas mission journal:** Persist completed mission information and optional feedback.
* 🔄 **Optional Temporal workflow:** Coordinate mission generation and validation retries.
* 🛟 **Direct Ollama fallback:** Generate missions directly through Ollama when Temporal is disabled or unavailable.

Optional integrations require their respective services, credentials, and configuration. The application can generate missions without enabling ElevenLabs, SerpApi, MongoDB Atlas, or Temporal.

---

## 1. Install Dependencies

Open PowerShell in the project directory containing `app.py`.

Install the required Python packages:

```powershell
py -m pip install streamlit requests python-dotenv pymongo temporalio
```

If the repository contains a `requirements.txt` file, you can install the dependencies listed there instead:

```powershell
py -m pip install -r requirements.txt
```

Use the dependency list that matches the current application code.

## 2. Configure Environment Variables

Create or update a `.env` file in the same directory as `app.py`.

Add the following configuration, keeping your existing valid credentials:

```dotenv
OLLAMA_MODEL=llama3.2:1b
OLLAMA_URL=http://localhost:11434

ELEVENLABS_API_KEY=your_elevenlabs_key
ELEVENLABS_VOICE_ID=your_elevenlabs_voice_id

SERPAPI_API_KEY=your_serpapi_key

MONGODB_URI=mongodb+srv://USERNAME:PASSWORD@YOUR_CLUSTER_URL/
MONGODB_DATABASE=fresh_air
MONGODB_COLLECTION=mission_journal
```

Replace the example values with your actual configuration.

**Important security rules:**

* Do not share your `.env` file.
* Never commit API keys, database credentials, or private tokens to GitHub.
* Add `.env` to `.gitignore`.
* Do not add quotation marks around environment-variable values unless required by the actual value or configuration format.
* Restart Streamlit after changing environment variables.

If your application selects the model through its sidebar, use the model-selection controls provided by the application. The `OLLAMA_MODEL` variable should match your implementation's configuration behavior.

## 3. Install and Select Ollama Models

Fresh Air supports these model options:

* `llama3.2:1b`
* `gemma2:2b`

Install the models you want to use in PowerShell:

```powershell
ollama pull llama3.2:1b
ollama pull gemma2:2b
```

Check which models are installed:

```powershell
ollama list
```

Make sure Ollama is installed and running before starting the application.

If a model is unavailable or incompatible with your setup, select an installed model and update the application's available model options if necessary.

The model selected in Fresh Air must be available to the Ollama server.

## 4. Start Fresh Air

From the project directory, run:

```powershell
py -m streamlit run app.py
```

Open the local URL shown in the terminal, usually:

```text
http://localhost:8501
```

Select your preferred AI model if the model selector is enabled.

**Temporal is optional.** Leave **Use Temporal retry workflow** unchecked unless you have started the Temporal server and worker.

## 5. Enable Temporal (Optional)

Temporal provides optional workflow orchestration for mission generation and validation retries. Direct Ollama generation remains the standard fallback when Temporal is disabled or unavailable.

### Step 1 — Start the Temporal server

Open a separate PowerShell terminal and run:

```powershell
temporal server start-dev
```

Keep this terminal running.

If the `temporal` command is not recognized, install the Temporal CLI for your operating system and verify that it is available on your PATH.

### Step 2 — Start the worker

Open another PowerShell terminal in the Fresh Air project directory:

```powershell
py temporal_worker.py
```

Keep the worker running alongside the Temporal server.

### Step 3 — Enable the workflow

Return to the Streamlit application and check **Use Temporal retry workflow** before creating a mission.

If Temporal cannot connect or its workflow fails, Fresh Air is designed to fall back to direct Ollama generation.

If you do not need Temporal, skip this entire section.

## 6. Configure MongoDB Atlas

MongoDB Atlas provides persistent storage for mission journal records and optional feedback.

### Setup

1. Create a MongoDB Atlas cluster.
2. Create a database user with appropriate permissions.
3. Configure **Network Access** to allow connections from the machine or deployment running Fresh Air.
4. Copy your database connection URI.
5. Add the URI to `.env` as `MONGODB_URI`.
6. Set the database and collection names if required by your implementation.
7. Restart Fresh Air and test the journal by completing a mission.

Example:

```dotenv
MONGODB_URI=mongodb+srv://USERNAME:PASSWORD@YOUR_CLUSTER_URL/
MONGODB_DATABASE=fresh_air
MONGODB_COLLECTION=mission_journal
```

The application stores completed mission information, including the mission title or activity, completion timestamp, status, and optional feedback, according to the current implementation.

**Important:** This is a shared journal collection, not an authenticated multi-user system. Do not use it to store sensitive personal information. Review access permissions before exposing the application publicly.

## 7. Configure Optional External Services

### ElevenLabs — Voice Narration

1. Obtain an API key from [ElevenLabs](https://elevenlabs.io/).
2. Set `ELEVENLABS_API_KEY` in `.env`.
3. Set `ELEVENLABS_VOICE_ID` if required by your implementation.
4. Restart the application and request narration.

Mission text is sent to ElevenLabs only when audio is requested.

### SerpApi — Destination Search

1. Obtain an API key from [SerpApi](https://serpapi.com/).
2. Set `SERPAPI_API_KEY` in `.env`.
3. Restart the application and use the destination-search feature.

Search terms and submitted location details are sent to SerpApi when a search is performed.

## 8. Privacy and Data Handling

Fresh Air uses local AI processing alongside optional external services.

* **Ollama:** Mission generation is local when using the local Ollama server at `http://localhost:11434`.
* **ElevenLabs:** Receives mission narration text when audio is requested.
* **SerpApi:** Receives destination-search terms and location information when a search is submitted.
* **MongoDB Atlas:** Stores journal records in the configured cloud database.
* **Temporal:** Runs locally in this setup. Workflow histories may contain preference inputs and generated mission data.

Keep the Temporal server private and protect your database credentials. Do not commit secrets to GitHub.

If you deploy Fresh Air to a cloud host, remember that `localhost` refers to the application host or container, not your personal computer. Configure a reachable Ollama server and review the privacy implications of every enabled service.

## 9. Troubleshooting

| Problem                               | Solution                                                                                   |
| ------------------------------------- | ------------------------------------------------------------------------------------------ |
| `MONGODB_URI is missing`              | Add `MONGODB_URI` to `.env` and restart Streamlit.                                         |
| MongoDB Atlas connection timeout      | Check the connection URI, database username and password, and Network Access IP allowlist. |
| `model not found`                     | Run `ollama pull <model-name>` and verify the installation with `ollama list`.             |
| Ollama connection error               | Confirm Ollama is running and the configured URL is reachable.                             |
| Temporal connection error             | Uncheck the Temporal option or start the Temporal server and worker.                       |
| `temporal` command not recognized     | Install the Temporal CLI and ensure it is available on PATH.                               |
| Voice narration fails                 | Verify the ElevenLabs API key, voice configuration, and account usage limits.              |
| Destination search fails              | Check the SerpApi key, network connectivity, and API usage limits.                         |
| Changes to `.env` do not take effect  | Restart the Streamlit application.                                                         |
| A model is unavailable or runs poorly | Use a compatible installed model and update the model options as needed.                   |

---

**Fresh Air 🌿 — Small steps outside. A better connection with the world.**
