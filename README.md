# Fresh Air 🌿 — AI-Powered Nature Missions

**Reconnect with the outdoors. Reset your mind. Make the world around you better.**

Fresh Air is an AI-powered wellness application that turns a user's mood, energy level, available time, interests, and accessibility needs into personalized, nature-focused missions. Originally developed under the concept **Touch Grass / Mood Dividend**, Fresh Air encourages people to step away from digital overload, reconnect with the physical world, and make small, meaningful changes to their surroundings.

Each mission transforms the idea of taking a break into an achievable plan with a friendly description, three timed steps, points, an explanation of its intended impact, and an alternative when the original activity is not practical.

## 🌱 The Problem

People spend much of their time indoors and on digital devices. Even when they want to take a break, reduce stress, or spend more time outside, it can be difficult to decide what to do or find an activity that fits their schedule, energy, interests, budget, and circumstances.

Generic wellness advice can be too vague, expensive, inaccessible, or unrealistic.

Fresh Air bridges this gap by making outdoor engagement easier, more personal, and more actionable. Instead of simply telling users to go outside, Fresh Air gives them a manageable mission they can actually complete.

## 💡 Our Solution

Fresh Air combines AI-generated recommendations with accessible, real-world activities to help users build healthier routines and strengthen their connection with nature and their communities.

The experience is designed to be encouraging rather than overwhelming. Users receive practical missions tailored to their stated preferences, with alternatives when they lack supplies, time, suitable weather, or access to a particular location.

Whether someone has five minutes for a mindful outdoor break or more time for an environmental activity, Fresh Air helps them find a meaningful place to start.

## ✨ Features

* **🤖 AI-Powered Recommendations:** Generate personalized nature-focused missions based on mood, energy, available time, interests, and accessibility needs.
* **🎯 Actionable Missions:** Turn recommendations into achievable real-world tasks with a friendly description and three timed steps.
* **♻️ Accessible Alternatives:** Offer practical alternatives when an activity requires unavailable supplies, resources, locations, or conditions, including suitable indoor options.
* **⭐ Mission Points:** Encourage participation with points that recognize completed activities.
* **📖 Mission Journal:** Track completed missions, selected activities, and optional user feedback.
* **🧠 Adaptive Personalization:** Use recent mission history and feedback to improve future recommendations and reduce repetitive or unwanted suggestions.
* **🌎 Environmental Awareness:** Encourage activities that help users appreciate and care for their surroundings.
* **😊 Interactive Smiley Mascot:** Add an animated, encouraging visual element to make the experience more engaging.
* **📍 Destination Search:** Find relevant outdoor destinations through SerpApi when configured.
* **🔊 Voice Integration:** Narrate mission text using ElevenLabs when configured and audio is requested.
* **🛟 Reliable Fallback Missions:** Provide a built-in mission when the AI service is unavailable or returns an invalid response.
* **🔄 Optional Workflow Orchestration:** Support a Temporal workflow for configured deployments that need workflow execution and retries.
* **🔒 Privacy-Conscious Design:** Keep credentials out of source control and explain how configured services handle user information.

## 🧠 How AI Is Used

Fresh Air uses the original mission-generation AI workflow powered by **Ollama**, rather than depending on a separate hosted generative AI API for its core mission-generation process.

The application is configured to use `llama3.2:1b` by default. Another locally available Ollama model can be selected through configuration.

The AI workflow:

1. **Understands user preferences:** Receives a compact set of user-provided preferences, including mood, energy, available time, interests, and accessibility considerations.
2. **Considers recent history:** Uses a short summary of recent missions and feedback when available to help reduce repetitive recommendations.
3. **Generates a mission:** Produces one concise mission in a structured JSON format, including its description, three timed steps, intended impact, points, and an alternative.
4. **Validates the result:** The application checks the generated output and applies preference and accessibility checks before displaying the mission.
5. **Provides a fallback:** If Ollama is unreachable or the generated response cannot be validated, a built-in fallback mission keeps the experience usable.

Generating one concise mission helps keep responses manageable and reduces failures associated with incomplete structured output.

Ollama can run locally, giving developers greater control over model selection and the AI environment. However, requests sent to a remotely hosted Ollama server are processed by that server, so local-only privacy should not be assumed for every deployment.

The optional Temporal workflow can coordinate generation and retries when a Temporal server and worker are configured. Temporal is not required for the standard direct-Ollama workflow.

## 🛠️ Technology Stack

Fresh Air combines Python-based application logic, AI inference, persistent storage, and optional integrations.

| Technology                       | Purpose                                                       |
| -------------------------------- | ------------------------------------------------------------- |
| **Python**                       | Core application logic and integrations                       |
| **Streamlit**                    | Interactive web application and user interface                |
| **Ollama**                       | Runs and serves the language model                            |
| **Llama 3.2 1B** (`llama3.2:1b`) | Default mission-generation model                              |
| **Requests**                     | HTTP communication with Ollama and supported APIs             |
| **python-dotenv**                | Loads local environment configuration                         |
| **MongoDB Atlas**                | Optional persistent mission journal                           |
| **PyMongo**                      | Python interface for MongoDB                                  |
| **SerpApi**                      | Optional outdoor destination search                           |
| **ElevenLabs**                   | Optional text-to-speech narration                             |
| **Temporal / temporalio**        | Optional workflow orchestration                               |
| **HTML and CSS**                 | Visual styling, animated backgrounds, and mascot presentation |
| **Git and GitHub**               | Version control and project collaboration                     |

Optional integrations require their respective credentials and services. Fresh Air can generate missions without configuring SerpApi, ElevenLabs, MongoDB Atlas, or Temporal. The Ollama service must be reachable from the environment running the application.

## 🚀 Getting Started

Follow these instructions to run Fresh Air on your local machine.

### Prerequisites

Install the following:

* Python 3.10 or newer, compatible with the project's dependencies
* Git
* [Ollama](https://ollama.com/) and a compatible language model
* Optional API credentials for external services
* A MongoDB connection if persistent cloud storage is enabled
* Temporal CLI and a running Temporal server if using the optional workflow

### 1. Clone the Repository

```bash
git clone https://github.com/jhusk003/Fresh-Air.git
cd Fresh-Air
```

If you already have the repository downloaded, open a terminal in the project directory.

### 2. Create a Virtual Environment

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

On macOS or Linux:

```bash
source .venv/bin/activate
```

### 3. Install Dependencies

If the repository contains a `requirements.txt` file, install its dependencies:

```bash
python -m pip install -r requirements.txt
```

Alternatively, install the main dependencies directly:

```bash
python -m pip install streamlit requests python-dotenv pymongo
```

If you plan to use the optional Temporal workflow, install its additional dependency:

```bash
python -m pip install temporalio
```

### 4. Download the AI Model

Make sure Ollama is installed and running, then download the default model:

```bash
ollama pull llama3.2:1b
```

Verify that the model is available:

```bash
ollama list
```

The model name in your configuration must match an installed Ollama model.

### 5. Configure Environment Variables

Create a `.env` file in the same directory as `app.py` to configure your services.

Example configuration:

```dotenv
OLLAMA_MODEL=llama3.2:1b
OLLAMA_URL=http://localhost:11434

SERPAPI_API_KEY=

ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb

MONGODB_URI=
MONGODB_DATABASE=fresh_air
MONGODB_COLLECTION=mission_journal
```

Fill in only the values required by your enabled features. The ElevenLabs voice ID is an example configuration value; use a voice ID supported by your account.

Make sure `.env` is included in `.gitignore` so that credentials are not committed to GitHub.

**Important:** `OLLAMA_URL=http://localhost:11434` works only when Ollama is reachable at that address from the application's runtime. In a cloud deployment, `localhost` refers to the cloud container itself, not your personal computer. Configure a reachable Ollama endpoint instead.

### 6. Run the Application

From the project directory, execute:

```bash
python -m streamlit run app.py
```

Streamlit will display a local URL, usually:

```text
http://localhost:8501
```

Open that address in your browser to use Fresh Air.

## ⚙️ Optional Integrations

### 📍 SerpApi — Outdoor Destination Search

SerpApi supports destination-search functionality when configured.

Set `SERPAPI_API_KEY` in your environment variables. Search functionality depends on valid credentials, network access, and the application's implementation.

### 🔊 ElevenLabs — Voice Narration

ElevenLabs can convert mission text into spoken audio when voice functionality is enabled and requested.

Configure:

* `ELEVENLABS_API_KEY`
* `ELEVENLABS_VOICE_ID`

Audio generation requires a valid API key and a supported voice. Requests may be subject to the service's usage limits and pricing.

### 📖 MongoDB Atlas — Persistent Mission Journal

MongoDB Atlas can store mission history and optional feedback beyond a single application session.

Configure:

* `MONGODB_URI`
* `MONGODB_DATABASE`
* `MONGODB_COLLECTION`

The example database and collection names are `fresh_air` and `mission_journal`.

Persistence requires a valid connection string, suitable database permissions, and working application code. Without MongoDB, journal persistence depends on the application's session or local-storage implementation.

### 🔄 Temporal — Optional Workflow Orchestration

Temporal is optional and is not required for standard mission generation.

If the project includes the corresponding worker implementation and you want to enable Temporal, install the Temporal CLI and start a development server:

```bash
temporal server start-dev
```

In a separate terminal, run the worker from the project directory:

```bash
python temporal_worker.py
```

Keep the server and worker running, then enable the Temporal option in the application.

This integration requires the project's Temporal workflow and worker to be implemented and configured correctly. If Temporal is not configured, use the normal direct-Ollama workflow.

## ☁️ Deployment

Fresh Air can be deployed to a Python-capable hosting service, such as Render, provided the host supports the application's dependencies and network requirements.

A typical Streamlit start command for a host that provides a `PORT` environment variable is:

```bash
streamlit run app.py --server.port $PORT --server.address 0.0.0.0
```

Before deploying:

1. Push the application code to your GitHub repository.
2. Configure the hosting service to install the project's dependencies.
3. Add required environment variables through the host's environment or secrets settings.
4. Configure `OLLAMA_URL` to point to a reachable Ollama server.
5. Enable only the optional services needed by the deployment.
6. Test mission generation, fallback behavior, and any enabled integrations.
7. Review database permissions, logs, API usage, and privacy disclosures.

A successful deployment depends on the host's available resources, model-serving configuration, and support for external connections. Hosting the Streamlit interface does not automatically host the Ollama model.

## 🔒 Privacy, Security, and Limitations

Fresh Air is designed to encourage everyday outdoor engagement, not to replace professional medical care.

* **Credentials:** Store API keys and database credentials in environment variables or an appropriate secrets manager.
* **AI processing:** Mission preferences and any included history summary are sent to the configured Ollama endpoint. A remote endpoint may process or retain requests according to its configuration and policies.
* **Destination searches:** SerpApi may receive search terms and location details when destination search is used.
* **Voice narration:** ElevenLabs receives text submitted for audio generation when narration is requested.
* **Mission history:** If MongoDB Atlas is configured, journal information may be stored in the connected database. Without it, persistence depends on the application's session or local implementation.
* **Data minimization:** Collect only the information needed for the enabled features, and make optional feedback and data collection clear to users.
* **Safe activities:** Users should choose activities appropriate to their surroundings, abilities, weather, and local rules.
* **Wellbeing disclaimer:** Fresh Air does not diagnose, prevent, or treat medical or mental-health conditions.

Do not claim that all user information stays exclusively on the user's device when remote AI services, external APIs, or cloud databases are enabled.

## 🗺️ Roadmap

* [ ] Improve personalization and mission quality.
* [ ] Expand the persistent mission journal.
* [ ] Use feedback to reduce repetitive or unwanted recommendations.
* [ ] Improve accessibility checks and practical alternatives.
* [ ] Expand environmental and community-focused missions.
* [ ] Refine the animated interface and interactive mascot.
* [ ] Improve voice interaction and destination discovery.
* [ ] Strengthen testing, documentation, and deployment reliability.
* [ ] Evaluate offline functionality and minimize unnecessary external dependencies.

## 🤝 Contributing

Contributions, bug reports, accessibility improvements, and feature suggestions are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Implement your changes.
4. Test the relevant features and integrations.
5. Submit a pull request explaining the improvement.

Please avoid committing credentials, private user data, or generated files containing secrets.

## 👩🏽‍💻 Developer

**Jasmine Huskey** — Project Creator and Developer

Fresh Air began as the Touch Grass / Mood Dividend concept and evolved into a personalized AI experience focused on nature, accessible activities, environmental awareness, and small real-world actions.

## 📄 License

This project is licensed under the MIT License, subject to the terms in the repository's `LICENSE` file.

---

**Fresh Air 🌿 — Small steps outside. A better connection with the world.**
