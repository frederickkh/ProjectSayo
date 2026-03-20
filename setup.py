#!/usr/bin/env python3
"""
Interactive setup script for RAG Chatbot System
Guides users through configuration and validation
"""

import os
import sys
from pathlib import Path
import subprocess
from typing import Optional

def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)

def print_step(num: int, text: str):
    """Print a formatted step."""
    print(f"\n📍 Step {num}: {text}")

def print_success(text: str):
    """Print success message."""
    print(f"✅ {text}")

def print_error(text: str):
    """Print error message."""
    print(f"❌ {text}")

def print_info(text: str):
    """Print info message."""
    print(f"ℹ️  {text}")

def get_input(prompt: str, default: Optional[str] = None) -> str:
    """Get user input with optional default."""
    if default:
        prompt = f"{prompt} [{default}]: "
    else:
        prompt = f"{prompt}: "
    
    value = input(prompt).strip()
    return value if value else default

def check_python():
    """Check Python version."""
    print_step(1, "Checking Python version")
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print_error(f"Python 3.10+ required, you have {version.major}.{version.minor}")
        sys.exit(1)
    print_success(f"Python {version.major}.{version.minor} ✓")

def check_node():
    """Check Node.js version."""
    print_step(2, "Checking Node.js version")
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        print_success(f"Node.js {result.stdout.strip()} ✓")
    except FileNotFoundError:
        print_error("Node.js not found. Install from https://nodejs.org")
        sys.exit(1)

def setup_backend_env():
    """Set up backend environment variables."""
    print_step(3, "Setting up Backend Environment")
    
    backend_dir = Path("backend")
    env_path = backend_dir / ".env"
    
    if env_path.exists():
        print_info(f"Found existing {env_path}")
        overwrite = input("Overwrite? (y/N): ").lower()
        if overwrite != 'y':
            return
    
    print("\nEnter your credentials (or press Enter to skip):")
    
    openrouter_key = get_input("OpenRouter API Key", "sk-or-...")
    if not openrouter_key or openrouter_key == "sk-or-...":
        print_error("OpenRouter API Key required")
        print_info("Get one from: https://openrouter.io")
        return False
    
    supabase_url = get_input("Supabase URL", "https://xxx.supabase.co")
    if not supabase_url or supabase_url.startswith("https://xxx"):
        print_error("Supabase URL required")
        return False
    
    supabase_key = get_input("Supabase Service Role Key", "eyJ...")
    if not supabase_key or supabase_key == "eyJ...":
        print_error("Supabase Service Role Key required")
        return False
    
    # Write .env file
    env_content = f"""# OpenRouter API Key
OPENROUTER_API_KEY={openrouter_key}

# Supabase Configuration
SUPABASE_URL={supabase_url}
SUPABASE_SERVICE_ROLE_KEY={supabase_key}

# Optional Configuration
NOTION_EXPORT_DIR=./backend/Notion_Export
EMBEDDING_MODEL=openai/text-embedding-3-small
CHAT_MODEL=openrouter/auto
RAG_CONTEXT_LIMIT=3
ENABLE_OCR=true
"""
    
    env_path.write_text(env_content)
    print_success(f"Created {env_path}")
    return True

def setup_frontend_env():
    """Set up frontend environment variables."""
    print_step(4, "Setting up Frontend Environment")
    
    frontend_dir = Path("frontend")
    env_path = frontend_dir / ".env.local"
    
    if env_path.exists():
        print_info(f"Found existing {env_path}")
        return
    
    api_url = get_input(
        "Backend API URL",
        "http://localhost:8000"
    )
    
    env_content = f"NEXT_PUBLIC_API_URL={api_url}\n"
    env_path.write_text(env_content)
    print_success(f"Created {env_path}")

def install_backend_deps():
    """Install backend dependencies."""
    print_step(5, "Installing Backend Dependencies")
    
    backend_dir = Path("backend")
    if not (backend_dir / "requirements.txt").exists():
        print_error("requirements.txt not found")
        return False
    
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(backend_dir / "requirements.txt")],
            check=True,
            cwd=backend_dir
        )
        print_success("Backend dependencies installed")
        return True
    except subprocess.CalledProcessError:
        print_error("Failed to install backend dependencies")
        return False

def install_frontend_deps():
    """Install frontend dependencies."""
    print_step(6, "Installing Frontend Dependencies")
    
    frontend_dir = Path("frontend")
    
    try:
        subprocess.run(
            ["npm", "install"],
            check=True,
            cwd=frontend_dir
        )
        print_success("Frontend dependencies installed")
        return True
    except subprocess.CalledProcessError:
        print_error("Failed to install frontend dependencies")
        return False

def show_next_steps():
    """Show next steps to user."""
    print_header("Setup Complete! 🎉")
    
    print("""
Next steps:

1. Set up Supabase database:
   - Go to https://supabase.com and open your project
   - Open SQL Editor
   - Copy content from: backend/supabase_setup.sql
   - Paste and run in the SQL editor
   - Wait for all queries to complete

2. Ingest your documents:
   cd backend
   python ingest_notion_pdfs.py

3. Start the backend server:
   cd backend
   python -m uvicorn chat_api:app --reload --host 0.0.0.0 --port 8000

4. In a new terminal, start the frontend:
   cd frontend
   npm run dev

5. Open http://localhost:3000 in your browser

Documentation:
   - Full setup guide: README.md
   - API documentation: backend/chat_api.py
   - Backend configuration: backend/.env
   - Frontend configuration: frontend/.env.local

Support:
   - OpenRouter docs: https://openrouter.io/docs
   - Supabase docs: https://supabase.com/docs
   - Next.js docs: https://nextjs.org/docs
""")

def main():
    """Run setup."""
    print_header("RAG Chatbot System - Setup Wizard")
    
    print("""
This script will help you set up:
✓ Backend (FastAPI + Supabase)
✓ Frontend (Next.js)
✓ Environment variables
✓ Dependencies
""")
    
    if input("\nContinue? (y/N): ").lower() != 'y':
        print("Setup cancelled")
        sys.exit(0)
    
    # Run setup steps
    check_python()
    check_node()
    
    if not setup_backend_env():
        sys.exit(1)
    
    setup_frontend_env()
    
    print_step(5, "Installing Dependencies")
    if not install_backend_deps():
        sys.exit(1)
    
    if not install_frontend_deps():
        sys.exit(1)
    
    show_next_steps()

if __name__ == "__main__":
    main()
