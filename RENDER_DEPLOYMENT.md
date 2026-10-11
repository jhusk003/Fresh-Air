# Deploy Fresh Air to Render

1. Commit `app.py`, `requirements.txt`, `render.yaml`, and `.github/copilot-instructions.md` to the root of your GitHub repository. Keep `render.yaml` in the repository root.
2. In Render, choose **New + → Blueprint** and connect the GitHub repository. Render should detect `render.yaml`; review and create the `fresh-air-guided-missions` web service.
3. In the Render service's **Environment** settings, set `OLLAMA_URL` to the base URL of a reachable hosted Ollama server (for example, `https://your-ollama-host.example.com`, not `http://localhost:11434` unless Ollama is actually running inside the same service/container). The endpoint must expose Ollama's `/api/generate` and `/api/show` routes.
4. `OLLAMA_MODEL` defaults to `gemma2:2b`. Ensure that exact model is pulled/available on the configured Ollama server, or change the environment variable to a model that server has installed. The app's sidebar lets you switch between the configured default, `llama3.2:1b`, and `gemma2:2b`.
5. Add `SERPAPI_API_KEY` and `ELEVENLABS_API_KEY` in Render only if you want destination search and voice narration. Set `ELEVENLABS_VOICE_ID` only if you want a voice other than the built-in default. Do not commit secrets to GitHub.
6. Wait for the deploy to finish, open the Render URL, use **Test selected model**, then create a mission. The app should explicitly say whether Ollama generated the mission or whether it used the fallback.
7. Test place search and audio separately if their keys are configured. Temporal is optional and will not work unless its server and worker are separately configured. Mission history remains session-only.

## GitHub Copilot

`.github/copilot-instructions.md` gives GitHub Copilot repository-specific guidance when you use Copilot to edit this project. It is not a runtime Copilot API integration by itself. If you enter a Copilot-related prize category, make sure you actually use Copilot in development and follow the challenge's evidence/submission requirements.
