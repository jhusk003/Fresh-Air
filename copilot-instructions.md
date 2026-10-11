# GitHub Copilot instructions for Fresh Air

## Project purpose
Fresh Air is a Streamlit app that creates accessible, no-cost nature and wellbeing missions. The app should encourage safe real-world activity while respecting a user's energy, time, accessibility needs, resources, and indoor-only constraints.

## Preserve existing behavior
- Before editing, inspect the current implementation and preserve existing features unless the task explicitly asks to remove them.
- Keep the app runnable with `streamlit run app.py` and keep dependencies in `requirements.txt`.
- Use `get_setting()` for deployment secrets and environment configuration. Never hardcode API keys or credentials.
- Ollama is the mission-generation backend. The selected model must be reported honestly; never claim a model generated a mission if the app used the fallback.
- SerpApi destination search and ElevenLabs audio are optional features and should fail gracefully when keys or services are unavailable.
- Mission history is session-only unless persistent storage is explicitly implemented and tested. Do not describe it as database-backed.
- Temporal is optional and requires a separately configured server and worker; do not imply it is running unless the workflow succeeds.

## Safety and quality
- Do not require users to spend money, travel, trespass, touch hazardous waste, disturb wildlife, damage plants, or approach unsafe water or roads.
- Provide practical alternatives for bad weather, lack of outdoor access, limited energy, and accessibility needs.
- Validate and bound AI-generated output before rendering it. Escape untrusted dynamic text before embedding it in HTML.
- Do not log or display API keys, secrets, or sensitive environment values.
- Keep UI copy accessible, concise, and mobile-friendly.

## Testing expectations
- Run `python -m py_compile app.py` after Python edits.
- Verify `requirements.txt` and `render.yaml` remain consistent with the deployment command.
- When changing model selection or generation, test both successful AI generation and fallback behavior when the model is unavailable.
- Do not state that a third-party integration or prize-category requirement is fulfilled based only on configuration or code references; require an end-to-end test.
