# Fresh Air 🌿

**Reconnect with the outdoors. Reset your mind. Make the world around you better.**

Fresh Air is an AI-powered wellness application designed to help people step away from digital overload and reconnect with the physical world through personalized outdoor activities, environmental awareness, and meaningful real-world actions.

## 🌱 The Problem

People spend much of their time indoors and on digital devices, making it harder to build consistent outdoor habits and engage with their surrounding environment.

Fresh Air helps bridge that gap by turning the idea of taking a break into an achievable, personalized action.

## 💡 Our Solution

Fresh Air uses AI to recommend accessible activities that encourage users to spend time outdoors, explore their surroundings, and develop healthier routines.

The experience is designed to make recommendations practical, personalized, and adaptable to the user's circumstances.

## ✨ Features

* **AI-Powered Recommendations:** Generate personalized outdoor activities based on user needs and preferences.
* **Actionable Missions:** Turn recommendations into achievable real-world tasks.
* **Accessible Alternatives:** Offer alternative activities when a suggestion requires unavailable supplies, resources, or conditions.
* **Mission Journal:** Track completed missions, selected activities, and optional user feedback.
* **Personalized Experiences:** Use past feedback to improve recommendations and avoid repeatedly suggesting activities users dislike.
* **Environmental Awareness:** Encourage actions that strengthen users' connection to their surroundings.
* **Voice Integration:** Support spoken interactions where enabled.
* **Privacy-Conscious Design:** Keep credentials out of source control and clearly communicate how user information is handled.

## 🛠️ Technology Stack

The project may include the following technologies, depending on the enabled features:

* Python
* Streamlit
* Ollama for locally hosted language models
* MongoDB Atlas for persistent mission history
* SerpApi for supported web search functionality
* ElevenLabs for voice features

## 🚀 Getting Started

### Prerequisites

* Python 3.10 or later, compatible with the project's dependencies
* Git
* An Ollama installation and compatible model if using local AI
* API credentials for optional external services
* A MongoDB connection if persistent cloud storage is enabled

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/YOUR-USERNAME/fresh-air.git
   cd fresh-air
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   ```

   Windows:

   ```bash
   .venv\Scripts\activate
   ```

   macOS/Linux:

   ```bash
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Create a local environment file using `.env.example` as a reference. Add your own credentials and configuration values.

5. Start the application using the command documented for the current application entry point. For a Streamlit application named `app.py`, run:

   ```bash
   streamlit run app.py
   ```

## ⚙️ Configuration

Configure only the services required by your deployment.

Typical environment variables may include:

* `OLLAMA_URL` — address of the Ollama server
* `MONGODB_URI` — MongoDB connection string
* `SERPAPI_API_KEY` — SerpApi credential
* `ELEVENLABS_API_KEY` — ElevenLabs credential

Use `.env.example` to document the required variable names without including real secrets.

**Never commit API keys, database credentials, private tokens, or real user data to GitHub.**

## 🔒 Privacy and Security

Fresh Air aims to make outdoor wellness more accessible while treating user information responsibly.

* Keep credentials in environment variables or an appropriate secrets manager.
* Request only the information necessary for application features.
* Make feedback and optional data collection clear to users.
* Explain whether data is stored locally or transmitted to external services.
* Review database permissions before deploying.
* Do not claim that data stays exclusively on a user's device when cloud services are enabled.

## 🧪 Development

Contributions, issue reports, feature suggestions, and accessibility improvements are welcome.

Before submitting changes, verify that the application starts correctly and that relevant features work with the required services configured.

## 🗺️ Roadmap

* [ ] Improve personalization and activity recommendations
* [ ] Build a persistent mission journal
* [ ] Use user feedback to reduce repetitive recommendations
* [ ] Improve accessible alternatives for suggested activities
* [ ] Expand environmental and community-focused missions
* [ ] Improve testing, documentation, and deployment
* [ ] Evaluate offline functionality and minimize unnecessary external dependencies

## 🤝 Contributing

1. Fork the repository.
2. Create a feature branch.
3. Make and test your changes.
4. Submit a pull request explaining the improvement.

## 📄 License

This project is licensed under the MIT License, subject to the terms in the repository's `LICENSE` file.

---

**Fresh Air — Small steps outside. A better connection with the world.**
