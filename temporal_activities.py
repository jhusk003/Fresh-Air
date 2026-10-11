import json
import requests
from temporalio import activity

OLLAMA_URL = "http://localhost:11434/api/generate"


@activity.defn
def generate_mission_activity(preferences: dict) -> dict:
    """Generate one mission using the user's locally running Ollama model."""
    model = preferences.get("model", "llama3.2:1b")
    prompt = f"""
Create one safe, realistic outdoor wellness mission for Mood Dividend.

User preferences:
Mood: {preferences.get("mood", "Just need a reset")}
Energy: {preferences.get("energy", 3)}/5
Available time: {preferences.get("minutes", 15)} minutes
Goal: {preferences.get("goal", "Feel calmer")}
Outdoor access: {preferences.get("access", "I can step outside near home")}

Rules:
- Fit the available time and do not require spending money, buying supplies, or travel.
- Include an indoor/doorway alternative if the user cannot go outside.
- Never recommend trespassing, entering dangerous areas, touching hazardous waste,
  disturbing wildlife, damaging plants, swimming, or approaching unsafe roads/water.
- Be practical, welcoming, and accessible.
- Return only valid JSON with this exact structure:
{{
  "title": "Short title",
  "description": "Two short sentences",
  "steps": ["Step one", "Step two", "Step three"],
  "points": 20,
  "impact": "A realistic explanation of the possible benefit",
  "goal": "{preferences.get("goal", "Feel calmer")}"
}}
"""
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.7},
        },
        timeout=90,
    )
    response.raise_for_status()
    result = response.json()
    mission = json.loads(result.get("response", ""))

    if not isinstance(mission, dict):
        raise ValueError("Ollama did not return a mission object.")
    mission["goal"] = preferences.get("goal", mission.get("goal", "General"))
    mission["points"] = max(5, min(50, int(mission.get("points", 20))))
    return mission


@activity.defn
def validate_mission_activity(mission: dict) -> dict:
    """Validate required fields and run a basic phrase safety check."""
    required = ("title", "description", "steps", "points", "impact")
    for field in required:
        if field not in mission:
            raise ValueError(f"Mission is missing required field: {field}")

    if not isinstance(mission["title"], str) or not mission["title"].strip():
        raise ValueError("Mission title is empty.")
    if not isinstance(mission["description"], str) or not mission["description"].strip():
        raise ValueError("Mission description is empty.")
    if not isinstance(mission["steps"], list) or not mission["steps"]:
        raise ValueError("Mission steps must be a non-empty list.")
    if not all(isinstance(step, str) and step.strip() for step in mission["steps"]):
        raise ValueError("Every mission step must be a non-empty string.")

    text = " ".join(
        [mission["title"], mission["description"], mission["impact"]]
        + mission["steps"]
    ).lower()
    prohibited_phrases = [
        "trespass",
        "enter restricted areas",
        "jump from a bridge",
        "touch hazardous waste",
        "swim in alligator",
    ]
    if any(phrase in text for phrase in prohibited_phrases):
        raise ValueError("Mission did not pass the basic safety phrase check.")

    mission["points"] = max(5, min(50, int(mission["points"])))
    return mission
