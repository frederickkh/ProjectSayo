#!/usr/bin/env python3
"""Demo script to test the RAG Chatbot API"""

import requests
import json
import time
from typing import Optional

# Configuration
API_URL = "http://localhost:8000"
CHAT_ENDPOINT = f"{API_URL}/chat"
HEALTH_ENDPOINT = f"{API_URL}/health"

def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)

def print_response(data):
    """Pretty print API response."""
    print(json.dumps(data, indent=2))

def test_health():
    """Test health check endpoint."""
    print_header("Testing Health Check")
    try:
        response = requests.get(HEALTH_ENDPOINT, timeout=5)
        response.raise_for_status()
        print("✅ Health check passed")
        print_response(response.json())
        return True
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def test_chat(message: str, manual_type: Optional[str] = None):
    """Test chat endpoint."""
    print_header(f"Testing Chat: '{message}'")
    print(f"Manual Type: {manual_type or 'None (all documents)'}\n")
    
    payload = {
        "message": message,
        "manual_type": manual_type
    }
    
    try:
        print("📤 Sending request...")
        start_time = time.time()
        
        response = requests.post(
            CHAT_ENDPOINT,
            json=payload,
            timeout=60
        )
        
        elapsed = time.time() - start_time
        
        response.raise_for_status()
        data = response.json()
        
        print(f"✅ Response received in {elapsed:.2f}s\n")
        print(f"🤖 Response:\n{data['response']}\n")
        
        if data.get("sources"):
            print(f"📚 Sources ({len(data['sources'])}):")
            for i, source in enumerate(data["sources"], 1):
                similarity = source.get("similarity", 0)
                print(f"  {i}. {source['title']} (type: {source['type']}, similarity: {similarity:.2%})")
        else:
            print("📚 No sources found")
        
        return True
    except requests.exceptions.Timeout:
        print("❌ Request timeout (>60s)")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API. Is the server running?")
        print(f"   Expected: {API_URL}")
        return False
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP Error: {e.response.status_code}")
        print(f"   Response: {e.response.text}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def interactive_chat():
    """Interactive chat mode."""
    print_header("Interactive Chat Mode")
    print("Type 'quit' to exit")
    print("Type 'teacher' or 'student' followed by your message to filter documents")
    print("Examples:")
    print("  - 'What is active learning?'")
    print("  - 'teacher: How do I use Sayo?'")
    print("  - 'student: Tell me about the course'")
    print()
    
    while True:
        try:
            user_input = input("\n✉️  You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() == 'quit':
                print("\nGoodbye! 👋")
                break
            
            # Check for manual type prefix
            manual_type = None
            message = user_input
            
            if user_input.lower().startswith("teacher:"):
                manual_type = "teacher"
                message = user_input[8:].strip()
            elif user_input.lower().startswith("student:"):
                manual_type = "student"
                message = user_input[8:].strip()
            
            if not message:
                continue
            
            # Send to API
            payload = {
                "message": message,
                "manual_type": manual_type
            }
            
            response = requests.post(CHAT_ENDPOINT, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            
            print(f"\n🤖 Bot: {data['response']}")
            
            if data.get("sources"):
                print(f"\n📚 Sources: {', '.join([s['title'] for s in data['sources']])}")
        
        except KeyboardInterrupt:
            print("\n\nGoodbye! 👋")
            break
        except Exception as e:
            print(f"❌ Error: {e}")

def main():
    """Run demo tests."""
    print_header("RAG Chatbot API Demo")
    
    print("""
This demo will test the RAG Chatbot API endpoints.

Features being tested:
1. ✓ Health check endpoint
2. ✓ Chat with RAG context retrieval
3. ✓ Document source attribution
4. ✓ Manual type filtering (teacher/student)
5. ✓ Interactive mode
""")
    
    # Test health check
    if not test_health():
        print("\n⚠️  Cannot proceed without a running API server.")
        print("   Start the backend with:")
        print("   python -m uvicorn chat_api:app --reload --host 0.0.0.0 --port 8000")
        return
    
    # Test chat without documents
    print_header("Testing API Without Documents")
    print("⚠️  Note: No documents have been ingested yet.")
    print("    The API will still work, but sources will be empty.\n")
    
    test_chat("Hello! How are you?")
    test_chat("How to create a new classroom?", manual_type="teacher")
    test_chat("How track my progress?", manual_type="student")
    
    # Ask user to ingest documents
    print_header("About Documents")
    print("""
To get the full RAG experience with document retrieval:

1. Place your PDF files in: backend/Notion_Export/
2. Run the ingestion script:
   cd backend
   python ingest_notion_pdfs.py

3. The API will then retrieve relevant documents from your PDFs
   when you ask questions.

Currently: No documents ingested (API working, but no context)
""")
    
    # Interactive mode
    print_header("Interactive Chat Demo")
    response = input("\nEnter interactive chat mode? (y/n): ").lower()
    if response == 'y':
        interactive_chat()
    
    print_header("Demo Complete")
    print("""
✅ API is working!

Next steps:
1. Ingest documents: python backend/ingest_notion_pdfs.py
2. Ask questions with context: http://localhost:3000
3. See full API docs: http://localhost:8000/docs

Resources:
- OpenAPI Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health Check: http://localhost:8000/health
""")

if __name__ == "__main__":
    main()
