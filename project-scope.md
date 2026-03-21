# Part 1: Project Description Document
Project Title: GenAI Knowledge & Assessment Ecosystem
Department: Product R&D
Team Size: 2-3 Students 

## 0. Executive Summary: The "AI Support Deflector"
The Problem:
Our Business Development (BD) team is currently overwhelmed. As our platform grows, teachers and students constantly reach out with functional questions (e.g., "How do I upload a video?" or "Where is the grading button?").
These answers exist in our Notion User Manuals, but users don't read them. Instead, they message our staff, causing a massive support bottleneck.
The Solution:
We are building a RAG (Retrieval-Augmented Generation) Chatbot.
Instead of a human answering these tickets, an AI will:
Read our internal Notion User Manuals.
Understand the user's question via a Next.js Chat Interface.
Retrieve the exact steps from the manual.
Answer the user instantly with citations.
Goal: Reduce Tier-1 Support tickets by 60%.

## 1. Technical Architecture
The project is a Next.js Web Application supported by a Python Data Pipeline.
Frontend: Next.js 14+ (App Router).
Database: Supabase (PostgreSQL + pgvector).
AI Model: OpenAI (GPT-4o) or Gemini Pro.
Knowledge Base Source: Notion (Exported Markdown/PDFs).

## 2. Group Allocations & Responsibilities
Group 1: The Core RAG Pipeline (Support Chatbot)
This group builds the primary "BD Support" solution.
Focus: Building the Data Ingestion Pipeline and the Customer-Facing Chatbot.
Key Responsibilities:
Ingestion Engine (Python): Build a script to pull data from Notion (User Manuals), chunk the text, and generate embeddings.
Vector Database: Manage Supabase pgvector to store the knowledge base.
Chat Application (Next.js): Develop the web-based chat interface where teachers/students ask questions.
Accuracy: Implement "Citation Logic"—the bot must say "According to the 'Grading Guide'..." and provide a link to the source.



## 3. The 12-Week Roadmap (Group 1 Focus)
| Phase           | Weeks | Milestone        | Group 1 Deliverables                                                                 |
|-----------------|-------|------------------|--------------------------------------------------------------------------------------|
| I: Setup        | 1-2   | Architecture     | Next.js Repo Init. Supabase Setup. Notion Data Export.                               |
| II: Ingestion   | 3-5   | The Pipeline     | Python script that successfully reads Notion pages and inserts vectors into Supabase. |
| III: The Brain  | 6-7   | Retrieval Logic  | Implementing "Hybrid Search" (Keyword + Semantic). Ensuring the bot doesn't hallucinate. |
| IV: The UI      | 8-9   | Chat Interface   | Building the Chat UI with streaming responses and "Source Citations."               |
| V: Integration  | 10    | Testing          | Testing with real teacher queries (e.g., "How do I reset password?").               |
| VI: Launch      | 12    | Final Demo       | A live demo where we ask a support question and the AI answers correctly.           |


## 4. Grading Rubric (Group 1 Specific)
Retrieval Accuracy (35%): Does the bot answer correctly based only on the Notion documents? (No hallucinations).
Pipeline Automation (25%): How easy is it to update the knowledge base when we change the User Manual?
Next.js Implementation (20%): Code quality, UI responsiveness, and Server Actions usage.
User Experience (20%): Is the chat interface intuitive for non-technical teachers?

