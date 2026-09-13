# Karyon 🌊🚁

![Python](https://img.shields.io/badge/Python-3.10%2B-3498db?style=for-the-badge&logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-2ecc71?style=for-the-badge&logo=fastapi&logoColor=white) ![Gemini](https://img.shields.io/badge/Google%20Gemini-Integrated-8e44ad?style=for-the-badge) ![OSRM](https://img.shields.io/badge/OSRM-Routing-f39c12?style=for-the-badge)

**Karyon** is an intelligent, real-time decision-support dashboard built for disaster-response coordinators. Designed initially for a **Delhi Flood** scenario, Karyon ingests emergency incidents, prioritizes them using a robust scoring engine, and optimally allocates rescue resources (Ambulances, NDRF boats, Fire trucks) on a live interactive map.

---

## 🛑 The Problem
During severe natural disasters like urban flooding, emergency response centers are overwhelmed with frantic calls. Human dispatchers struggle to:
1. Objectively prioritize who needs help first (e.g. an elderly person trapped vs. a stranded vehicle).
2. Optimally route resources across flooded streets.
3. Maintain situational awareness as conditions rapidly deteriorate.

## 💡 Our Solution
**Karyon** acts as an AI-powered co-pilot for emergency dispatchers. It automatically triages incidents, computes real-world driving routes, monitors rising floodwaters, and generates actionable tactical plans using Google Gemini AI. It keeps the human in the loop, allowing the commander to override the AI using natural language commands.

---

## ✨ Key Features

* 🧠 **AI Tactical Planner (Google Gemini 1.5 Flash)**
  * Automatically generates structured operational briefings (situational assessment, dispatch justifications, bottleneck alerts).
  * **Predictive Analytics:** Monitors environmental data (water level, time elapsed). If flood waters cross critical thresholds (e.g., >180cm), the AI proactively warns the commander to stage resources.
* 🗣️ **NLP Overwrite Engine**
  * Coordinators can override the AI plan using natural language commands like: *"Move Fatima to priority #1"*, *"Assign N01 to Ramesh"*, or *"Mark Ambulance A02 unavailable"*.
* 🗺️ **Real-World Live Routing (OSRM Integration)**
  * Replaces naive straight-line distances with **real-world driving routes** using the Open Source Routing Machine (OSRM) API. Click on any dispatched route to see the exact driving distance and real-time ETA in minutes.
* 🔒 **Secure Command Dashboard**
  * Protected by a custom HTTP middleware login gate. Prevents unauthorized access to the operations center using hashed session cookies.
* 🚀 **Interactive Live Map & Simulation**
  * Built with Leaflet.js. Visualizes incidents (with priority badges), available resources, and active dispatch routes.
  * Interactive Simulation Panel allows you to simulate advancing floodwaters and resources going offline to test system resilience.

---

## 🛠️ Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| **Backend** | Python + FastAPI | High-performance async API, custom Auth Middleware |
| **AI / NLP** | Google Gemini 1.5 Flash | Structured tactical planning and NLP command parsing |
| **Routing** | OSRM (Open Source Routing Machine) | Real-world driving ETAs and distances |
| **Data** | In-Memory JSON | Stateless, zero-config deployment |
| **Frontend** | Vanilla JS + Leaflet.js + OSM | Lightweight, ultra-fast mapping |

---

## 🚀 How to Run Locally

1. **Clone the repository:**
   ```bash
   git clone https://github.com/LogicDipesh/Karyon.git
   cd Karyon
   ```

2. **Set up a Virtual Environment & Install Dependencies:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate      # Windows
   source .venv/bin/activate   # Mac/Linux
   pip install -r requirements.txt
   ```

3. **Start the FastAPI Server:**
   ```bash
   python backend/main.py
   ```

4. **Access the Dashboard:**
   Open your browser and navigate to `http://localhost:8000`
   
   **Admin Credentials:**
   * **User ID:** `9368060619`
   * **Password:** `SP@0608`

5. **Enable AI Features:**
   In the dashboard's right panel, paste your **Google Gemini API Key** and click **Save**. The AI Tactical Planner and NLP engine will instantly activate!

---

## 📸 Screenshots
*(Add your hackathon screenshots here)*

---
> **Disclaimer:** Priority scores and AI suggestions are decision-support aids based on a configurable response policy. A human coordinator always makes the final call.
