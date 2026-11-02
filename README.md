<div align="center">
  <img src="assets/readme/hero.svg" alt="FitAI — Train with Intelligence" width="100%" />
</div>

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10%2B-e2a24f?style=flat-square&labelColor=0a0806)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-e2a24f?style=flat-square&labelColor=0a0806)
![React](https://img.shields.io/badge/React-19-e2a24f?style=flat-square&labelColor=0a0806)
![LangGraph](https://img.shields.io/badge/LangGraph-agent%20orchestration-e2a24f?style=flat-square&labelColor=0a0806)
![ChromaDB](https://img.shields.io/badge/ChromaDB-vector%20store-e2a24f?style=flat-square&labelColor=0a0806)
![Groq](https://img.shields.io/badge/Groq-LLM%20inference-e2a24f?style=flat-square&labelColor=0a0806)
![Stage](https://img.shields.io/badge/stage-pre--alpha-b9773f?style=flat-square&labelColor=0a0806)

**[Key features](#key-features) · [How it works](#how-it-works) · [Architecture](#architecture) · [Tech stack](#technical-stack) · [Getting started](#getting-started) · [Deployment](#deployment) · [API](#api-overview)**

</div>

<br/>

## Overview

FitAI is a domain-specific, agentic RAG chatbot built for gym-goers, fitness enthusiasts, and nutrition-conscious users. It pairs retrieval-augmented generation over curated fitness and nutrition knowledge with persistent, structured user memory, deterministic fitness calculations, and a LangGraph-orchestrated agent — so every answer is grounded, personalized, and aware of what came before.

The system is built as a single, clearly-layered **modular monolith**: a React frontend talks to a FastAPI backend that coordinates authentication, persistence, memory, retrieval, fitness tools, safety policy, and LLM inference in one deployable application.

> FitAI offers general fitness and nutrition guidance. It is not a diagnostic or medical-treatment system.

## Key Features

| | |
|---|---|
| **Grounded chat** | Answers are grounded in retrieved knowledge, with sources surfaced directly in the UI. |
| **Persistent, structured memory** | Separates current facts from historical statements and asks for confirmation on ambiguous or conflicting updates. |
| **Cross-chat continuity** | Pinned core context, semantic recall of saved memories, and past-chat summaries carry earlier conversations into later ones. |
| **Deterministic fitness tools** | BMI, BMR, TDEE, calorie and macro targets, workout logging, personal-record detection, and progress analysis — computed, never guessed. |
| **Document ingestion** | Upload PDF, TXT, or DOCX (plus OCR for images); FitAI chunks, embeds, and indexes into ChromaDB with status tracking. |
| **Safety guardrails** | A deterministic rule set plus an optional LLM intent classifier gate every turn before any model or tool call — refusals never reach the model. |

## How It Works

Every user turn moves through a single LangGraph agent graph. Safety runs first and unconditionally — a blocked turn never reaches a tool, memory, or retrieval node. From there, the graph routes based on what the message actually needs: personal statements flow through fact extraction and memory update before any response; questions pull retrieved context first; everything else goes straight to a grounded response.

<div align="center">
  <img src="assets/readme/workflow.svg" alt="FitAI agent turn lifecycle" width="100%" />
</div>

| Node | Responsibility |
|---|---|
| `safety_check` | Deterministic rules plus an LLM intent classifier gate the turn before anything else runs. |
| `extract_facts` | Pulls structured, timestamped candidate facts out of personal statements. |
| `detect_changes` | Compares candidates against current memory and classifies them as current, historical, hypothetical, uncertain, or conflicting. |
| `apply_updates` | Persists only explicit, validated, high-confidence changes; ambiguous ones are proposed for user confirmation instead. |
| `retrieve_context` | Runs similarity search against ChromaDB for questions that need grounding. |
| `generate_response` | Produces the final, grounded reply through the Groq client. |

## Architecture

FitAI is a modular monolith, not a microservice mesh: one deployable application with clearly separated layers and an explicit dependency direction — **Router → Schema → Service → Repository → Model**. The AI engine (agent, memory, RAG, tools, LLM, safety) talks to persistence only through the same service layer the core backend uses; it never writes SQL or models directly.

<div align="center">
  <img src="assets/readme/architecture.svg" alt="FitAI system architecture" width="100%" />
</div>

PostgreSQL, reached through Supabase, is the authoritative store for user profiles, conversations, memory, and fitness history. ChromaDB stores searchable document chunks and embeddings alongside it — it is never the source of truth for user data.
