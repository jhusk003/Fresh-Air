
import asyncio
import json
import os
import random
import requests
import uuid
from datetime import datetime, timezone
from html import escape
from urllib.parse import quote

import streamlit as st
from dotenv import load_dotenv
from pymongo import MongoClient, DESCENDING

load_dotenv()

# =========================================================
# CONFIGURATION — LOCAL DEVELOPMENT AND DIGITALOCEAN
# =========================================================

DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434/api/generate",
)
TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_TASK_QUEUE = os.getenv(
    "TEMPORAL_TASK_QUEUE", "mood-dividend-queue"
)

st.set_page_config(
    page_title="Fresh Air",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =========================================================
# OUTDOOR DESTINATION SEARCH
# =========================================================

def find_outdoor_destinations(location, minutes):
    """Search for outdoor destinations using SerpApi."""
    api_key = os.getenv("SERPAPI_API_KEY")

    if not api_key:
        raise ValueError("SERPAPI_API_KEY is missing from your environment.")

    params = {
        "engine": "google_maps",
        "type": "search",
        "q": (
            f"parks, public gardens, and outdoor walking "
            f"places in {location}"
        ),
        "api_key": api_key,
    }

    response = requests.get(
        "https://serpapi.com/search.json",
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("error"):
        raise RuntimeError(data["error"])

    # Search results do not guarantee that a destination fits
    # the requested travel time.
    return data.get("local_results", [])[:8]


# =========================================================
# ELEVENLABS VOICE
# =========================================================

def generate_mission_audio(text):
    """Convert mission text into speech with ElevenLabs."""
    api_key = os.getenv("ELEVENLABS_API_KEY")

    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY is missing from your environment.")

    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    response = requests.post(
        url,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        json={
            "text": text,
            "model_id": "eleven_flash_v2_5",
        },
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"ElevenLabs error ({response.status_code}): "
            f"{response.text[:500]}"
        )

    return response.content


# =========================================================
# MONGODB ATLAS — PERSISTENT MISSION JOURNAL
# =========================================================

@st.cache_resource
def get_mission_collection():
    """Connect to Atlas and return the mission journal collection."""
    uri = os.getenv("MONGODB_URI")

    if not uri:
        raise ValueError("MONGODB_URI is missing from your environment.")

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")

    # Keep the existing database and collection so existing
    # journal records remain available.
    db = client["mood_dividend"]
    collection = db["mission_journal"]
    collection.create_index("mission_id", unique=True)

    return collection


def save_completed_mission(mission_id, title, activity, feedback=None):
    """Save a completed mission to the persistent journal."""
    collection = get_mission_collection()

    collection.update_one(
        {"mission_id": mission_id},
        {
            "$set": {
                "title": title,
                "activity": activity,
                "completed_at": datetime.now(timezone.utc),
                "feedback": feedback,
                "status": "completed",
            }
        },
        upsert=True,
    )


def get_mission_history(limit=20):
    """Return the most recent completed missions."""
    return list(
        get_mission_collection()
        .find({"status": "completed"}, {"_id": 0})
        .sort("completed_at", DESCENDING)
        .limit(limit)
    )


def get_disliked_activities():
    """Return previously disliked activities, if Atlas is available."""
    try:
        entries = get_mission_collection().find(
            {"feedback": "Didn't enjoy it"},
            {"activity": 1, "_id": 0},
        )
        return {
            entry["activity"]
            for entry in entries
            if entry.get("activity")
        }
    except Exception:
        return set()


# =========================================================
# LOCAL NATURE FACTS — WORKS WITHOUT AN INTERNET CONNECTION
# =========================================================

NATURE_FACTS = [
    {
        "category": "🐙 ANIMAL KINGDOM",
        "title": "Octopuses have three hearts",
        "fact": (
            "Two hearts pump blood toward the gills, while the third "
            "circulates blood to the rest of the body."
        ),
        "detail": "Their blood is blue because it uses a copper-containing protein called hemocyanin.",
    },
    {
        "category": "🌱 PLANT LIFE",
        "title": "Plants can communicate chemically",
        "fact": (
            "Some plants release airborne chemicals when damaged. "
            "Nearby plants can detect these signals and respond."
        ),
        "detail": "These chemical signals are one part of the complex relationships between plants and their environment.",
    },
    {
        "category": "🌧️ WEATHER",
        "title": "Rain has a recognizable scent",
        "fact": (
            "The earthy smell often associated with rain is called "
            "petrichor."
        ),
        "detail": "It can come from compounds released by soil and plants, including geosmin produced by certain bacteria.",
    },
    {
        "category": "🍄 FUNGI",
        "title": "Fungi are not plants",
        "fact": (
            "Fungi belong to their own biological kingdom. They obtain "
            "nutrients differently from plants, which make sugars through photosynthesis."
        ),
        "detail": "Fungi play important roles in decomposition and nutrient cycling.",
    },
    {
        "category": "🌊 OCEANS",
        "title": "The ocean helps regulate Earth's climate",
        "fact": (
            "Ocean water absorbs and redistributes enormous amounts "
            "of heat around the planet."
        ),
        "detail": "Ocean currents and exchanges with the atmosphere influence regional weather and climate.",
    },
    {
        "category": "✨ SPACE & NATURE",
        "title": "You can see the past in the night sky",
        "fact": (
            "Light takes time to travel. Sunlight takes about eight "
            "minutes and twenty seconds to reach Earth."
        ),
        "detail": "Looking at distant stars means seeing light that began its journey years, centuries, or much longer ago.",
    },
    {
        "category": "🦋 ANIMAL KINGDOM",
        "title": "Butterflies taste with their feet",
        "fact": (
            "Butterflies have sensory receptors on their feet that "
            "help them identify suitable plants."
        ),
        "detail": "This helps females assess plants where they may lay their eggs.",
    },
    {
        "category": "🌳 PLANT LIFE",
        "title": "A tree's rings can tell a story",
        "fact": (
            "Many trees form annual growth rings that can reveal "
            "information about past growing conditions."
        ),
        "detail": "Scientists study these patterns in a field called dendrochronology.",
    },
    {
        "category": "⚡ NATURAL PHENOMENA",
        "title": "Lightning is extremely hot",
        "fact": (
            "A lightning channel can heat the surrounding air to "
            "temperatures hotter than the surface of the Sun."
        ),
        "detail": "The rapid heating and expansion of air contribute to the sound we hear as thunder.",
    },
    {
        "category": "🐝 ANIMAL KINGDOM",
        "title": "Bees use movement to share information",
        "fact": (
            "Honeybees can perform a waggle dance that communicates "
            "the direction and distance of a food source."
        ),
        "detail": "The dance is one of the best-known examples of symbolic communication in nonhuman animals.",
    },
    {
        "category": "🌿 ECOSYSTEMS",
        "title": "Decomposers keep nutrients moving",
        "fact": (
            "Fungi, bacteria, and other decomposers break down dead "
            "organic material and return nutrients to ecosystems."
        ),
        "detail": "Without decomposition, nutrients would remain locked in dead material for much longer.",
    },
    {
        "category": "❄️ NATURAL PHENOMENA",
        "title": "Snowflakes form in many shapes",
        "fact": (
            "Snow crystals develop different patterns depending on "
            "temperature and humidity as they grow."
        ),
        "detail": "Their six-sided structure comes from the molecular arrangement of ice.",
    },
    {
        "category": "🌵 PLANT LIFE",
        "title": "Cacti have special water-saving adaptations",
        "fact": (
            "Many cacti use thick water-storing tissues, reduced leaves "
            "or spines, and specialized photosynthesis to cope with dry climates."
        ),
        "detail": "Some use a process called CAM photosynthesis that helps reduce water loss.",
    },
    {
        "category": "🐢 ANIMAL KINGDOM",
        "title": "Sea turtles navigate across oceans",
        "fact": (
            "Research indicates that sea turtles can use Earth's "
            "magnetic field as one of their navigation cues."
        ),
        "detail": "Their migrations can span enormous distances between feeding and nesting areas.",
    },
    {
        "category": "🌈 NATURAL PHENOMENA",
        "title": "Rainbows depend on where you stand",
        "fact": (
            "A rainbow forms when sunlight is refracted, reflected, "
            "and dispersed inside water droplets."
        ),
        "detail": "The geometry between the Sun, droplets, and your viewpoint determines where the rainbow appears.",
    },
    {
        "category": "🌲 FORESTS",
        "title": "Forests influence the water cycle",
        "fact": (
            "Trees release water vapor through transpiration, helping "
            "move water from soil and roots into the atmosphere."
        ),
        "detail": "Vegetation can influence local humidity, runoff, and regional water cycling.",
    },
]

if "nature_fact_index" not in st.session_state:
    st.session_state.nature_fact_index = random.randrange(len(NATURE_FACTS))


def show_another_fact():
    """Select a different fact when possible."""
    previous = st.session_state.nature_fact_index
    choices = [
        i for i in range(len(NATURE_FACTS))
        if i != previous
    ]
    st.session_state.nature_fact_index = random.choice(choices)


# =========================================================
# FALLBACK MISSIONS
# =========================================================

FALLBACK_MISSIONS = [
    {
        "title": "Notice Five Signs of Nature",
        "description": "Take a short break outdoors and reconnect with the environment by noticing details you might normally overlook.",
        "steps": [
            "Find a safe outdoor place you can access.",
            "Notice five natural details, such as clouds, leaves, shadows, or birds.",
            "Pause for a few slow breaths.",
            "Choose one detail you want to remember.",
        ],
        "points": 20,
        "impact": "Builds awareness of your surroundings without requiring equipment or money.",
    },
    {
        "title": "Give Your Neighborhood a Little Care",
        "description": "Make a small, safe contribution to a shared outdoor space using only what you already have.",
        "steps": [
            "Choose a familiar, safe public area.",
            "Look for one small improvement you can make without touching hazardous materials.",
            "If it is safe, tidy a small area or report a maintenance issue to the appropriate organization.",
            "Notice how the space feels afterward.",
        ],
        "points": 25,
        "impact": "Encourages shared responsibility for welcoming community spaces.",
    },
    {
        "title": "Take a Mindful Micro-Walk",
        "description": "Use a few minutes of movement and observation to create a little breathing room in your day.",
        "steps": [
            "Choose a safe route you already have access to.",
            "Walk or roll at a comfortable pace for five to ten minutes.",
            "Notice colors, textures, sounds, and changes in the weather.",
            "Finish by identifying one thing you appreciated.",
        ],
        "points": 20,
        "impact": "Encourages outdoor awareness and accessible everyday movement.",
    },
    {
        "title": "Become a Local Nature Observer",
        "description": "Learn something about the environment around you without disturbing plants or wildlife.",
        "steps": [
            "Look at the sky, trees, or other natural features from a safe place.",
            "Observe one change in the weather, light, or landscape.",
            "Think about how that change might affect the local environment.",
            "Write down your observation if you have a device or paper available.",
        ],
        "points": 20,
        "impact": "Builds environmental curiosity and observation skills.",
    },
    {
        "title": "Share One Useful Environmental Tip",
        "description": "Turn something you know about environmental care into a small act of community learning.",
        "steps": [
            "Think of one practical way to reduce waste or save energy.",
            "Make sure the tip is accurate and realistic.",
            "Share it with a friend or in an appropriate community space if you wish.",
            "Reflect on how small actions can spread through a community.",
        ],
        "points": 25,
        "impact": "Supports environmental learning and encourages practical action.",
    },
]


def make_fallback_mission(goal):
    mission = random.choice(FALLBACK_MISSIONS).copy()
    mission["goal"] = goal
    return mission


# =========================================================
# AI MISSION GENERATION
# =========================================================

def generate_mission(mood, energy, minutes, goal, access):
    prompt = f"""
You create safe, realistic outdoor missions for an app called Fresh Air.

Create one short mission using these user preferences:
Mood: {mood}
Energy: {energy}/5
Available time: {minutes} minutes
Goal: {goal}
Outdoor access and resources: {access}

Rules:
- Make the mission achievable within the available time.
- Do not require spending money, buying supplies, or traveling.
- Prefer free places the user can already access.
- Include an alternative if the user cannot go outside.
- Never recommend trespassing, dangerous areas, hazardous waste,
  disturbing wildlife, damaging plants, unsafe water, or unsafe roads.
- Do not claim that an environmental impact has been measured.
- Keep instructions practical, welcoming, and accessible.
- Return ONLY valid JSON. Do not use Markdown.

Use exactly this JSON structure:
{{
  "title": "Short mission title",
  "description": "Two short sentences explaining the mission",
  "steps": ["First step", "Second step", "Third step"],
  "points": 20,
  "impact": "A realistic explanation of the possible benefit"
}}
"""

    disliked = get_disliked_activities()
    if disliked:
        prompt += (
            "\nAvoid these activities where possible because they were "
            "previously disliked: "
            + ", ".join(sorted(disliked))
            + ". Suggest a different activity instead."
        )

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.8},
            },
            timeout=90,
        )
        response.raise_for_status()
        mission = json.loads(response.json().get("response", ""))

        required = ["title", "description", "steps", "points", "impact"]
        if not all(key in mission for key in required):
            raise ValueError("The AI response is missing required fields.")

        if not isinstance(mission["steps"], list):
            raise ValueError("Mission steps must be a list.")

        mission["points"] = max(5, min(50, int(mission["points"])))
        mission["goal"] = goal
        return mission, True

    except Exception:
        return make_fallback_mission(goal), False


async def run_temporal_mission(preferences):
    """Run mission generation through the configured Temporal server."""
    from temporalio.client import Client
    from temporal_workflow import MoodDividendWorkflow

    client = await asyncio.wait_for(
        Client.connect(TEMPORAL_ADDRESS),
        timeout=4,
    )

    return await client.execute_workflow(
        MoodDividendWorkflow.run,
        preferences,
        id=f"fresh-air-mission-{uuid.uuid4()}",
        task_queue=TEMPORAL_TASK_QUEUE,
    )


# =========================================================
# SIDEBAR SETTINGS
# =========================================================

with st.sidebar:
    st.header("⚙️ Mission Settings")

    available_models = ["llama3.2:1b", "gemma2:2b"]
    if DEFAULT_MODEL not in available_models:
        available_models.insert(0, DEFAULT_MODEL)

    selected_model = st.selectbox(
        "Local AI model",
        options=available_models,
        index=available_models.index(DEFAULT_MODEL),
        help="Choose a model installed on the Ollama server.",
    )

    st.caption(
        "Missions use Ollama. Set OLLAMA_URL to the model server's API "
        "address when deploying to DigitalOcean. Audio and destination "
        "search use external services when requested."
    )

    st.caption(f"Model endpoint: {OLLAMA_URL}")
    st.caption(f"Temporal endpoint: {TEMPORAL_ADDRESS}")

MODEL = selected_model

# =========================================================
# ANIMATED BACKGROUND AND RESPONSIVE DESIGN
# =========================================================

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap');

    :root {
        --ink: #f4faf7;
        --muted: #d0e1dc;
        --glass: rgba(10, 30, 34, 0.80);
        --line: rgba(255,255,255,0.16);
        --mint: #a8f0ce;
    }

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }

    .stApp {
        background: #102e37;
        color: var(--ink);
    }

    .stApp::before {
        content: "";
        position: fixed;
        inset: 0;
        z-index: 0;
        pointer-events: none;
        background:
            linear-gradient(180deg, rgba(5,22,33,.35), rgba(5,22,33,.60)),
            linear-gradient(90deg, rgba(8,30,36,.35), transparent 60%);
    }

    .stApp::after {
        content: "";
        position: fixed;
        inset: 0;
        z-index: 0;
        pointer-events: none;
        opacity: .8;
        background:
            radial-gradient(ellipse at 80% 15%, rgba(255,220,155,.18), transparent 35%),
            radial-gradient(ellipse at 10% 75%, rgba(94,211,173,.15), transparent 40%);
    }

    .environment {
        position: fixed;
        inset: 0;
        z-index: 0;
        overflow: hidden;
        pointer-events: none;
        background: linear-gradient(180deg, #497f91 0%, #8cb9ba 48%, #274f56 100%);
        animation: skyCycle 32s infinite;
    }

    .sun {
        position: absolute;
        width: 105px;
        height: 105px;
        top: 11%;
        right: 15%;
        border-radius: 50%;
        background: rgba(255,230,171,.88);
        box-shadow: 0 0 70px rgba(255,223,153,.4);
        animation: sunGlow 5s ease-in-out infinite alternate;
    }

    .cloud {
        position: absolute;
        top: 16%;
        left: -30%;
        width: 180px;
        height: 38px;
        border-radius: 50px;
        background: rgba(255,255,255,.26);
        filter: blur(2px);
        animation: cloudMove 38s linear infinite;
    }

    .cloud::before, .cloud::after {
        content: "";
        position: absolute;
        border-radius: 50%;
        background: inherit;
    }

    .cloud::before {
        width: 65px;
        height: 65px;
        left: 28px;
        top: -30px;
    }

    .cloud::after {
        width: 85px;
        height: 75px;
        right: 25px;
        top: -40px;
    }

    .cloud.two {
        top: 28%;
        animation-duration: 52s;
        animation-delay: -18s;
        transform: scale(.7);
        opacity: .65;
    }

    .mountain {
        position: absolute;
        bottom: 0;
        width: 0;
        height: 0;
        border-left: 35vw solid transparent;
        border-right: 35vw solid transparent;
        border-bottom: 52vh solid #335c59;
        left: -12%;
        animation: mountainCycle 32s infinite;
    }

    .mountain.back {
        left: 32%;
        border-left-width: 29vw;
        border-right-width: 29vw;
        border-bottom-width: 43vh;
        border-bottom-color: #47766d;
        opacity: .85;
    }

    .mountain.front {
        left: 52%;
        border-left-width: 34vw;
        border-right-width: 34vw;
        border-bottom-width: 35vh;
        border-bottom-color: #203f43;
    }

    .glacier {
        position: absolute;
        inset: 42% -10% 0;
        opacity: 0;
        background:
            linear-gradient(135deg, transparent 0 27%, rgba(225,249,251,.85) 27.2% 35%, transparent 35.2% 42%, rgba(181,229,239,.85) 42.2% 50%, transparent 50.2%),
            linear-gradient(180deg, #a8dbe4 0%, #5e9ba9 50%, #285666 100%);
        clip-path: polygon(0 45%,13% 20%,25% 38%,40% 0,53% 31%,66% 8%,78% 37%,91% 16%,100% 40%,100% 100%,0 100%);
        animation: glacierCycle 32s infinite;
    }

    .forest {
        position: absolute;
        inset: 48% 0 0;
        opacity: 0;
        background:
            repeating-linear-gradient(90deg, transparent 0 25px, rgba(13,53,43,.9) 26px 40px, transparent 41px 65px),
            linear-gradient(180deg, #477c63, #163e37);
        clip-path: polygon(0 35%,5% 10%,10% 42%,15% 5%,22% 44%,28% 0,35% 39%,42% 9%,50% 45%,58% 0,65% 42%,73% 8%,80% 40%,89% 2%,96% 42%,100% 18%,100% 100%,0 100%);
        animation: forestCycle 32s infinite;
    }

    .waves {
        position: absolute;
        bottom: -5%;
        left: -10%;
        width: 120%;
        height: 42%;
        border-radius: 48% 52% 0 0;
        background: linear-gradient(180deg, rgba(80,179,183,.85), rgba(20,85,105,.98));
        opacity: 0;
        animation: waveCycle 32s infinite;
    }

    .waves.second {
        bottom: -12%;
        height: 34%;
        left: -20%;
        background: linear-gradient(180deg, rgba(139,220,206,.65), rgba(31,106,122,.95));
        animation: waveCycle 32s infinite, waveMove 7s ease-in-out infinite;
    }

    @keyframes skyCycle {
        0%,24% { background: linear-gradient(180deg,#477f96,#9bc7c6 55%,#345d5c); }
        25%,49% { background: linear-gradient(180deg,#8dbac9,#d5e8e9 55%,#628c99); }
        50%,74% { background: linear-gradient(180deg,#426c87,#93b5c3 55%,#3e727a); }
        75%,100% { background: linear-gradient(180deg,#254f55,#659b88 55%,#183d37); }
    }

    @keyframes mountainCycle {
        0%,24% { opacity: 1; }
        25%,49% { opacity: .12; }
        50%,74% { opacity: .75; }
        75%,100% { opacity: .35; }
    }

    @keyframes glacierCycle {
        0%,24% { opacity: 0; }
        25%,49% { opacity: .92; }
        50%,100% { opacity: 0; }
    }

    @keyframes forestCycle {
        0%,74% { opacity: 0; }
        75%,100% { opacity: .9; }
    }

    @keyframes waveCycle {
        0%,49% { opacity: 0; }
        50%,74% { opacity: .95; }
        75%,100% { opacity: 0; }
    }

    @keyframes waveMove {
        0%,100% { transform: translateX(-2%) rotate(-2deg); }
        50% { transform: translateX(2%) rotate(2deg); }
    }

    @keyframes cloudMove {
        from { left: -30%; }
        to { left: 120%; }
    }

    @keyframes sunGlow {
        from { transform: scale(.96); opacity: .8; }
        to { transform: scale(1.04); opacity: 1; }
    }

    /* Animated Our Promise card */
    .promise-card {
        position: relative;
        isolation: isolate;
        overflow: hidden;
        padding: 1.3rem 1.5rem;
        margin: 0 0 1.4rem;
        border: 1px solid rgba(255,255,255,.38);
        border-radius: 22px;
        background: linear-gradient(120deg, #174e46, #397c65, #477f91, #6b6a43, #174e46);
        background-size: 300% 300%;
        animation: promiseColors 12s ease infinite;
        box-shadow: 0 14px 40px rgba(0,0,0,.22);
    }

    .promise-label {
        color: #d8ffeb;
        font-size: .76rem;
        font-weight: 800;
        letter-spacing: .18em;
        text-transform: uppercase;
        margin-bottom: .5rem;
    }

    .promise-title {
        color: #fff;
        font-family: 'Manrope', sans-serif;
        font-size: clamp(1.3rem, 3vw, 1.8rem);
        font-weight: 800;
        margin-bottom: .35rem;
    }

    .promise-copy {
        color: #f3fff8;
        font-size: 1rem;
        line-height: 1.7;
        margin: 0;
        max-width: 850px;
    }

    @keyframes promiseColors {
        0%,100% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
    }

    .hero {
        padding: .5rem 0 1.2rem;
        text-align: left;
    }

    .eyebrow {
        color: var(--mint);
        font-size: .76rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: .19em;
        margin-bottom: .75rem;
    }

    .hero h1 {
        font-family: 'Manrope', sans-serif;
        font-size: clamp(2.8rem, 7vw, 5.4rem);
        line-height: 1.02;
        font-weight: 800;
        letter-spacing: -.065em;
        color: #fff;
        margin: 0;
        text-shadow: 0 3px 30px rgba(0,0,0,.15);
    }

    .hero h1 span { color: #a8f0ce; }

    .hero p {
        color: #e0eeea;
        font-size: 1.08rem;
        max-width: 650px;
        line-height: 1.8;
        margin-top: 1.15rem;
    }

    .section-heading {
        font-family: 'Manrope', sans-serif;
        font-size: 1.45rem;
        font-weight: 800;
        letter-spacing: -.035em;
        color: #fff;
        margin: .7rem 0 .2rem;
    }

    .muted { color: var(--muted); line-height: 1.65; }

    .glass-card {
        background: var(--glass);
        border: 1px solid var(--line);
        border-radius: 22px;
        padding: 1.25rem;
        backdrop-filter: blur(18px);
        -webkit-backdrop-filter: blur(18px);
        box-shadow: 0 16px 45px rgba(0,0,0,.12);
        margin-bottom: 1rem;
    }

    .metric-label {
        color: #d0e1dc;
        font-size: .83rem;
        font-weight: 600;
    }

    .metric-number {
        color: #fff;
        font-family: 'Manrope', sans-serif;
        font-size: 2rem;
        font-weight: 800;
        letter-spacing: -.05em;
        margin-top: .2rem;
    }

    .mission-label {
        color: #a8f0ce;
        font-size: .75rem;
        font-weight: 700;
        letter-spacing: .13em;
        text-transform: uppercase;
    }

    .mission-title {
        color: #fff;
        font-family: 'Manrope', sans-serif;
        font-size: 1.65rem;
        font-weight: 800;
        line-height: 1.25;
        margin: .45rem 0 .75rem;
        overflow-wrap: anywhere;
    }

    .mission-description {
        color: #e0eeea;
        line-height: 1.75;
        font-size: 1rem;
        overflow-wrap: anywhere;
    }

    .step-item {
        padding: .65rem 0;
        border-bottom: 1px solid rgba(255,255,255,.10);
        color: #eef7f3;
        line-height: 1.6;
        overflow-wrap: anywhere;
    }

    .step-item:last-child { border-bottom: none; }

    /* Nature facts panel */
    .fact-card {
        position: relative;
        overflow: hidden;
        background: linear-gradient(135deg, rgba(16,65,55,.94), rgba(24,49,60,.94));
        border: 1px solid rgba(168,240,206,.42);
        border-radius: 22px;
        padding: clamp(1.1rem, 3vw, 1.7rem);
        margin: .6rem 0 1.2rem;
        box-shadow: 0 14px 40px rgba(0,0,0,.18);
    }

    .fact-kicker {
        color: #a8f0ce;
        font-size: .73rem;
        font-weight: 800;
        letter-spacing: .15em;
        text-transform: uppercase;
        margin-bottom: .65rem;
    }

    .fact-title {
        color: #fff;
        font-family: 'Manrope', sans-serif;
        font-size: clamp(1.2rem, 3vw, 1.8rem);
        font-weight: 800;
        line-height: 1.3;
        margin-bottom: .65rem;
        overflow-wrap: anywhere;
    }

    .fact-copy {
        color: #f0f7f4;
        font-size: 1rem;
        line-height: 1.75;
        margin-bottom: .7rem;
    }

    .fact-detail {
        color: #c7e9dc;
        font-size: .91rem;
        line-height: 1.7;
        border-top: 1px solid rgba(255,255,255,.14);
        padding-top: .7rem;
    }

    [data-testid="stAppViewContainer"],
    [data-testid="stHeader"],
    [data-testid="stMain"],
    [data-testid="stMainBlockContainer"] {
        position: relative;
        z-index: 1;
        background: transparent !important;
    }

    [data-testid="stHeader"] { background: transparent !important; }

    [data-testid="stMainBlockContainer"] {
        padding-top: 1.4rem;
        padding-bottom: 4rem;
        max-width: 1150px;
    }

    [data-testid="stWidgetLabel"] p {
        color: #f1faf6 !important;
        font-weight: 600 !important;
    }

    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div,
    div[data-baseweb="textarea"] > div {
        background: rgba(255,255,255,.94) !important;
        border: 1px solid rgba(255,255,255,.4) !important;
        border-radius: 12px !important;
    }

    div[data-baseweb="select"] *,
    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea {
        color: #173c3d !important;
    }

    .stButton > button, .stFormSubmitButton > button {
        border-radius: 13px;
        border: 1px solid rgba(255,255,255,.25);
        padding: .7rem 1rem;
        font-weight: 700;
        transition: all .2s ease;
        overflow-wrap: anywhere;
        white-space: normal;
        min-height: 2.8rem;
    }

    .stButton > button[kind="primary"],
    .stFormSubmitButton > button {
        background: #a8f0ce;
        color: #143a35;
        border: none;
    }

    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button:hover {
        background: #d0ffe7;
        color: #143a35;
        transform: translateY(-2px);
    }

    .stButton > button[kind="secondary"] {
        background: rgba(255,255,255,.10);
        color: #fff;
    }

    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li { color: #f0f7f4; }

    hr { border-color: rgba(255,255,255,.16) !important; }

    [data-testid="stAlert"] { border-radius: 14px; }

    @media (max-width: 700px) {
        [data-testid="stMainBlockContainer"] {
            padding: 1rem .85rem 3rem;
        }

        .hero { padding-top: .4rem; }
        .hero h1 { font-size: clamp(2.5rem, 12vw, 3.4rem); }
        .hero p { font-size: .98rem; }
        .glass-card { padding: 1rem; border-radius: 18px; }
        .promise-card { padding: 1.1rem; border-radius: 18px; }
        .fact-card { border-radius: 18px; }
        .sun { width: 70px; height: 70px; }
    }

    @media (prefers-reduced-motion: reduce) {
        .environment, .sun, .cloud, .mountain, .glacier,
        .forest, .waves, .promise-card {
            animation: none !important;
        }
    }
    </style>

    <div class="environment">
        <div class="sun"></div>
        <div class="cloud"></div>
        <div class="cloud two"></div>
        <div class="mountain"></div>
        <div class="mountain back"></div>
        <div class="mountain front"></div>
        <div class="glacier"></div>
        <div class="forest"></div>
        <div class="waves"></div>
        <div class="waves second"></div>
    </div>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# SESSION STATE
# =========================================================

defaults = {
    "points": 0,
    "completed": [],
    "completed_mission_ids": [],
    "current_mission_id": None,
    "mission_completed": False,
    "mission": None,
    "mission_number": 0,
    "last_inputs": {},
    "mission_used_ai": False,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# =========================================================
# OUR PROMISE — FIRST FEATURE ON THE PAGE
# =========================================================

st.markdown(
    """
    <div class="promise-card">
        <div class="promise-label">🌿 OUR PROMISE</div>
        <div class="promise-title">A little more nature. A little more room to breathe.</div>
        <p class="promise-copy">
            No purchases required. No perfect day required.
            No pressure to do everything. Fresh Air helps you find
            small, accessible ways to reconnect with the world around you,
            starting with what is available to you today.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# FRESH AIR HEADER
# =========================================================

st.markdown(
    """
    <div class="hero">
        <div class="eyebrow">YOUR WORLD. YOUR WELLBEING.</div>
        <h1>Fresh <span>Air.</span></h1>
        <p>
            Small actions can change how we experience the world around us.
            Find your next outdoor mission, discover something fascinating
            about nature, and make every little action count.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# NATURE FACTS PANEL
# =========================================================

fact = NATURE_FACTS[st.session_state.nature_fact_index]

st.markdown(
    '<div class="section-heading">A little wonder from the natural world</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p class="muted">Take a tiny curiosity break. These facts are built in, so this panel works offline.</p>',
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="fact-card">
        <div class="fact-kicker">{escape(fact["category"])}</div>
        <div class="fact-title">{escape(fact["title"])}</div>
        <div class="fact-copy">{escape(fact["fact"])}</div>
        <div class="fact-detail">{escape(fact["detail"])}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.button("🌎 Discover Another Nature Fact", use_container_width=True):
    show_another_fact()
    st.rerun()

# =========================================================
# PROGRESS METRICS
# =========================================================

metric1, metric2, metric3 = st.columns(3)

with metric1:
    st.markdown(
        f"""
        <div class="glass-card">
            <div class="metric-label">TOTAL POINTS</div>
            <div class="metric-number">{st.session_state.points}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with metric2:
    st.markdown(
        f"""
        <div class="glass-card">
            <div class="metric-label">MISSIONS COMPLETED</div>
            <div class="metric-number">{len(st.session_state.completed)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with metric3:
    if st.session_state.points >= 200:
        reward = "Earth Guardian"
    elif st.session_state.points >= 100:
        reward = "Nature Champion"
    elif st.session_state.points >= 40:
        reward = "Green Explorer"
    else:
        reward = "First Steps"

    st.markdown(
        f"""
        <div class="glass-card">
            <div class="metric-label">CURRENT TITLE</div>
            <div class="metric-number" style="font-size:1.45rem;">
                {reward}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# =========================================================
# MISSION PREFERENCES
# =========================================================

st.markdown(
    '<div class="section-heading">Find your next mission</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p class="muted">Tell us what you need today. Your mission should fit your life, not the other way around.</p>',
    unsafe_allow_html=True,
)

left, right = st.columns(2)

with left:
    mood = st.selectbox(
        "How are you feeling?",
        [
            "Stressed", "Overwhelmed", "Low energy", "Restless",
            "Curious", "Motivated", "Just need a reset",
        ],
    )

    energy = st.slider(
        "Your energy level",
        min_value=1,
        max_value=5,
        value=3,
        help="1 means very low energy; 5 means lots of energy.",
    )

    minutes = st.select_slider(
        "How much time do you have?",
        options=[5, 10, 15, 20, 30, 45, 60],
        value=15,
        format_func=lambda x: f"{x} minutes",
    )

with right:
    goal = st.selectbox(
        "What would you like to focus on?",
        [
            "Feel calmer",
            "Move a little",
            "Connect with nature",
            "Help my community",
            "Learn about the environment",
            "Build a better routine",
        ],
    )

    access = st.selectbox(
        "What access do you have today?",
        [
            "I can step outside near home",
            "I have access to a park or green space",
            "I can only use a balcony or doorway",
            "I cannot go outside right now",
            "I have limited mobility or accessibility needs",
        ],
    )

use_temporal = st.checkbox(
    "Use Temporal retry workflow (requires Temporal server and worker)",
    value=False,
    help=(
        "Generation and validation run as retryable Temporal activities. "
        "If Temporal is unavailable, the app falls back to direct Ollama."
    ),
)

if st.button("✨ Create My Mission", type="primary", use_container_width=True):
    with st.spinner("Finding a mission that fits your day..."):
        mission = None
        used_ai = False

        preferences = {
            "mood": mood,
            "energy": energy,
            "minutes": minutes,
            "goal": goal,
            "access": access,
            "model": MODEL,
        }

        if use_temporal:
            try:
                temporal_result = asyncio.run(
                    run_temporal_mission(preferences)
                )
                mission = temporal_result["mission"]
                used_ai = bool(temporal_result.get("used_ai", True))
                st.success("Mission generated and validated through Temporal.")
            except Exception as error:
                st.warning(
                    "Temporal was unavailable or the workflow failed. "
                    "Trying direct Ollama generation instead. "
                    f"Details: {error}"
                )

        if mission is None:
            mission, used_ai = generate_mission(
                mood, energy, minutes, goal, access
            )

        st.session_state.mission = mission
        st.session_state.current_mission_id = str(uuid.uuid4())
        st.session_state.mission_completed = False
        st.session_state.mission_number += 1
        st.session_state.last_inputs = preferences
        st.session_state.mission_used_ai = used_ai

# =========================================================
# CURRENT MISSION
# =========================================================

if st.session_state.mission:
    mission = st.session_state.mission

    st.markdown("---")
    st.markdown(
        '<div class="section-heading">Your mission</div>',
        unsafe_allow_html=True,
    )

    if not st.session_state.get("mission_used_ai", False):
        st.caption(
            "Using a ready-to-go mission right now. Check that your Ollama "
            "server is running and the selected model is installed for AI missions."
        )

    st.markdown(
        f"""
        <div class="glass-card">
            <div class="mission-label">YOUR NEXT SMALL WIN</div>
            <div class="mission-title">{escape(str(mission["title"]))}</div>
            <div class="mission-description">{escape(str(mission["description"]))}</div>
            <br>
            <div class="mission-label">WHY IT MATTERS</div>
            <div class="mission-description">{escape(str(mission["impact"]))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("#### Your steps")

    for i, step in enumerate(mission["steps"], start=1):
        step_text = step.get("text", str(step)) if isinstance(step, dict) else str(step)
        st.markdown(
            f"""
            <div class="step-item">
                <strong style="color:#a8f0ce;">{i:02d}</strong>
                &nbsp;&nbsp; {escape(step_text)}
            </div>
            """,
            unsafe_allow_html=True,
        )

    complete_col, another_col = st.columns(2)

    with complete_col:
        if st.button(
            f"✅ Complete Mission (+{mission['points']} points)",
            type="primary",
            use_container_width=True,
        ):
            mission_id = (
                st.session_state.current_mission_id or str(uuid.uuid4())
            )
            st.session_state.current_mission_id = mission_id

            completed_ids = st.session_state.completed_mission_ids
            if mission_id not in completed_ids:
                st.session_state.points += mission["points"]
                st.session_state.completed.append(
                    {
                        "title": mission["title"],
                        "points": mission["points"],
                        "goal": mission.get("goal", "General"),
                    }
                )
                completed_ids.append(mission_id)

            try:
                save_completed_mission(
                    mission_id=mission_id,
                    title=str(mission.get("title", "Outdoor Mission")),
                    activity=str(
                        mission.get("goal", mission.get("title", "Outdoor activity"))
                    ),
                )
                st.session_state.mission_completed = True
                st.success("Mission saved to your cloud journal.")
            except Exception as error:
                st.warning(
                    "Your session points were updated, but the cloud journal "
                    "could not save this mission. "
                    f"Details: {error}"
                )

            st.session_state.mission = None
            st.success(f"Mission completed! You earned {mission['points']} points.")
            st.rerun()

    with another_col:
        if st.button("🔄 Try Another Mission", use_container_width=True):
            st.session_state.mission = None
            st.rerun()

# =========================================================
# ELEVENLABS — LISTEN TO YOUR MISSION
# =========================================================

st.markdown("---")
st.markdown(
    '<div class="section-heading">🔊 Listen to your mission</div>',
    unsafe_allow_html=True,
)
st.caption(
    "Voice uses ElevenLabs. Mission text is sent to an external service "
    "only when you request audio."
)

if st.button("🎧 Listen to My Mission", use_container_width=True):
    mission = st.session_state.get("mission")

    if mission:
        narration_parts = [
            str(mission.get("title", "")),
            str(mission.get("description", "")),
        ]

        steps = mission.get("steps", [])
        if steps:
            narration_parts.append("Here are your steps.")
            for index, step in enumerate(steps, start=1):
                step_text = step.get("text", str(step)) if isinstance(step, dict) else str(step)
                narration_parts.append(f"Step {index}. {step_text}")

        try:
            with st.spinner("Creating your audio..."):
                audio_bytes = generate_mission_audio(
                    ". ".join(part for part in narration_parts if part)
                )
            st.audio(audio_bytes, format="audio/mpeg")
            st.success("Your mission is ready to listen to!")
        except Exception as error:
            st.error(f"Could not generate audio: {error}")
    else:
        st.warning("Generate a mission before listening.")

# =========================================================
# REWARDS
# =========================================================

st.markdown("---")
st.markdown(
    '<div class="section-heading">Your journey</div>',
    unsafe_allow_html=True,
)

reward_levels = [
    ("First Steps", 0),
    ("Green Explorer", 40),
    ("Nature Champion", 100),
    ("Earth Guardian", 200),
]

for title, threshold in reward_levels:
    earned = st.session_state.points >= threshold
    symbol = "🌿" if earned else "🔒"
    status = "Unlocked" if earned else f"{threshold} points needed"

    st.markdown(
        f"""
        <div class="glass-card" style="padding:.9rem 1.1rem; margin-bottom:.65rem;">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:1rem; flex-wrap:wrap;">
                <div style="font-weight:700; color:white;">{symbol} &nbsp; {title}</div>
                <div style="color:#a8f0ce; font-size:.85rem;">{status}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# =========================================================
# SESSION MISSION HISTORY
# =========================================================

if st.session_state.completed:
    st.markdown("---")
    st.markdown(
        '<div class="section-heading">Completed missions</div>',
        unsafe_allow_html=True,
    )

    for item in reversed(st.session_state.completed):
        st.markdown(
            f"""
            <div class="glass-card" style="padding:.9rem 1.1rem;">
                <div style="font-weight:700; color:white;">✓ {escape(str(item["title"]))}</div>
                <div style="color:#a8f0ce; font-size:.85rem;">+{item["points"]} points</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# =========================================================
# CLOUD MISSION JOURNAL
# =========================================================

st.markdown("---")
st.markdown(
    '<div class="section-heading">📖 My Mission Journal</div>',
    unsafe_allow_html=True,
)
st.caption(
    "Completed missions and optional feedback are stored in MongoDB Atlas "
    "when the database is configured and reachable."
)

try:
    journal = get_mission_history(limit=30)
    total_saved = get_mission_collection().count_documents(
        {"status": "completed"}
    )
    st.metric("Missions saved in journal", total_saved)

    if not journal:
        st.info("Your cloud journal is empty. Complete a mission to begin.")
    else:
        for entry in journal:
            with st.container(border=True):
                st.subheader(entry.get("title", "Outdoor Mission"))
                st.caption(
                    "Activity: " + str(entry.get("activity", "Outdoor activity"))
                )
                completed_at = entry.get("completed_at")
                if completed_at:
                    st.caption(
                        "Completed: "
                        + completed_at.strftime("%b %d, %Y at %I:%M %p UTC")
                    )
                if entry.get("feedback"):
                    st.write("Your feedback: " + str(entry["feedback"]))

    if st.session_state.get("mission_completed"):
        current_id = st.session_state.get("current_mission_id")
        feedback_choice = st.radio(
            "How did you feel about your last completed mission?",
            ["No feedback", "Enjoyed it", "It was okay", "Didn't enjoy it"],
            key="journal_feedback_choice",
        )

        if st.button("Save Mission Feedback"):
            try:
                get_mission_collection().update_one(
                    {"mission_id": current_id},
                    {
                        "$set": {
                            "feedback": (
                                None
                                if feedback_choice == "No feedback"
                                else feedback_choice
                            )
                        }
                    },
                )
                st.success("Feedback saved.")
                st.rerun()
            except Exception as error:
                st.error(f"Could not save feedback: {error}")

except Exception as error:
    st.info(
        "Cloud journal is not connected. Add a valid MONGODB_URI to your "
        "environment and check Atlas network access. "
        f"Details: {error}"
    )

# =========================================================
# FIND SOMEWHERE TO GO
# =========================================================

st.markdown("---")
st.markdown(
    '<div class="section-heading">📍 Find Somewhere to Go</div>',
    unsafe_allow_html=True,
)
st.write(
    "Turn your outdoor mission into a real destination. "
    "Enter a city or neighborhood to discover places to visit."
)

with st.form("outdoor_destination_form"):
    destination_location = st.text_input(
        "City or neighborhood",
        placeholder="e.g., Miami, Florida",
    )

    available_minutes = st.selectbox(
        "How much time do you have?",
        [10, 20, 30, 45, 60],
        index=1,
        format_func=lambda n: f"{n} minutes",
    )

    search_destinations = st.form_submit_button("Find Somewhere to Go")

if search_destinations:
    if not destination_location.strip():
        st.warning("Please enter a city or neighborhood.")
    else:
        try:
            with st.spinner("Finding outdoor destinations..."):
                places = find_outdoor_destinations(
                    destination_location.strip(),
                    available_minutes,
                )

            if not places:
                st.info(
                    "No places were returned. Try a nearby city or a more specific search."
                )
            else:
                st.subheader("Outdoor destinations to explore")
                st.caption(
                    f"You selected {available_minutes} minutes. Check travel "
                    "time, opening hours, and access before choosing a destination."
                )

                for place in places:
                    name = place.get("title", "Outdoor destination")
                    address = place.get("address", "Address unavailable")
                    rating = place.get("rating")
                    open_state = place.get("open_state")
                    description = place.get("description")
                    links = place.get("links") or {}
                    place_url = (
                        place.get("link")
                        or links.get("website")
                        or links.get("directions")
                    )

                    with st.container(border=True):
                        st.subheader(name)
                        st.write(address)

                        if rating is not None:
                            st.write(f"⭐ Rating: {rating}")
                        if open_state:
                            st.write(f"Hours/status: {open_state}")
                        if description:
                            st.write(description)
                        if place_url:
                            st.markdown(
                                f"[View destination and verify details]({place_url})"
                            )

                        st.caption(
                            "Verify the destination, access, and current conditions before visiting."
                        )

        except Exception as error:
            st.error(f"Destination search failed: {error}")
            st.info(
                "Check your internet connection, SerpApi key, and remaining API searches."
            )

# =========================================================
# FOOTER
# =========================================================

st.markdown(
    """
    <div style="text-align:center; padding:1.5rem 0 .5rem; color:#d0e9df;">
        <div style="font-size:1.4rem;">🌍 🌿 🌊 🏔️</div>
        <p style="font-size:.82rem;">
            Fresh Air — Small actions. Real places. A better connection with the world.
        </p>
        <p style="font-size:.72rem; opacity:.8;">
            Fresh Air is a prototype for outdoor engagement and community action.
            It does not diagnose or treat mental health conditions.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)