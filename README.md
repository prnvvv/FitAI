# FitAI

FitAI is a domain-specific, agentic RAG chatbot for gym-goers, fitness enthusiasts,
and nutrition-conscious users. It pairs retrieval-augmented generation over curated
fitness and nutrition knowledge with persistent user memory, historical fitness
tracking, deterministic calculation tools, and a LangGraph agent — so answers are
grounded, personalized, and remember relevant context across conversations.

> **Not a medical system.** FitAI offers general fitness and nutrition guidance. It
> is not a diagnostic or medical-treatment tool and does not replace professional
> advice.

## Table of contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Repository structure](#repository-structure)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Testing and quality checks](#testing-and-quality-checks)
- [Architecture](#architecture)
- [API](#api)
- [Project documentation](#project-documentation)
- [Contributing and ownership](#contributing-and-ownership)
- [Status and limitations](#status-and-limitations)

## Features

- **Grounded chat:** answers grounded in retrieved knowledge, with sources surfaced
  in the UI.
- **Persistent, structured memory:** remembers relevant facts about the user,
  separates current facts from historical statements, and asks for confirmation on
  ambiguous or conflicting updates.
- **Cross-chat continuity:** pinned core context, semantic recall of saved memories,
  and past-chat summaries so earlier conversations inform later ones.
- **Safety guardrails:** a deterministic rule set plus an optional LLM intent
  classifier gates every turn before any model or tool call; refusals never reach
  the model.
- **Deterministic fitness tools:** BMI, BMR, TDEE, calorie and macro calculations,
  workout logging/summaries, personal-record detection, and progress analysis.
- **Document ingestion:** upload PDF/TXT/DOCX (and image text via OCR), chunk, embed,
  and index into ChromaDB with status tracking.
- **Fitness tracking UI:** profile, plan, progress, workouts, memory controls, and a
  ChatGPT-style chat history.

## Tech stack

| Layer          | Technologies                                                                                  |
| -------------- | --------------------------------------------------------------------------------------------- |
| Frontend       | React 19, TypeScript, Vite, Vitest, jsdom, react-router, react-markdown, Supabase JS           |
| Backend        | Python 3.10+, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, Uvicorn                              |
| Data & storage | PostgreSQL via Supabase, Supabase Auth, ChromaDB (vector store)                                |
| AI & retrieval | Groq (LLM inference), LangGraph (agent orchestration), ChromaDB embeddings                      |
| Tooling        | Ruff, MyPy, Pytest, oxlint, GitHub Actions, Dependabot                                          |

## Repository structure

```text
FitAI/
├── frontend/                 # React + TypeScript + Vite app
│   └── src/
│       ├── components/       # layout, chat, documents, profile, memory
│       ├── pages/            # Chat, Library, Memory, Plan, Profile, Progress, Login
│       ├── hooks/            # e.g. useConversations
│       ├── services/         # API client + Supabase
│       ├── context/          # auth context
│       ├── types/            # shared TypeScript types
│       └── utils/
│
├── backend/                  # FastAPI app (modular monolith)
│   ├── app/
│   │   ├── main.py
│   │   ├── api/              # deps + routers
│   │   ├── schemas/          # Pydantic request/response models
│   │   ├── models/           # SQLAlchemy entities
│   │   ├── repositories/     # database access
│   │   ├── services/         # business logic
│   │   ├── agent/            # LangGraph state, nodes, routing
│   │   ├── memory/           # fact extraction, temporal reasoning, confirmation
│   │   ├── rag/              # loading, chunking, embeddings, retrieval
│   │   ├── guardrails/       # deterministic rules + intent classifier
│   │   ├── tools/            # fitness calculators and helpers
│   │   ├── llm/              # Groq client + prompts
│   │   ├── safety/           # policy checks
│   │   ├── core/             # config, security, logging, errors
│   │   └── db/               # engine, session, base
│   ├── migrations/           # Alembic
│   └── tests/                # unit, integration, api, end_to_end
│
├── docs/                     # architecture, setup, API contracts, extraction
├── knowledge_base/           # curated fitness/nutrition source documents
├── scripts/                  # dev + audit + audit/smoke utilities
├── AGENTS.md                 # project conventions and ownership
└── README.md
```
