#!/usr/bin/env python3
"""
Diagnostic script to verify OpenRouter API access and available embedding models.

Usage:
    python test_openrouter.py
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

print("\n" + "=" * 80)
print("OPENROUTER API DIAGNOSTIC")
print("=" * 80 + "\n")

# Check 1: API Key
print("[1/4] Checking API Key...")
if not OPENROUTER_API_KEY:
    print("❌ OPENROUTER_API_KEY not set!")
    print("   Set it: $env:OPENROUTER_API_KEY = 'your-key' (PowerShell)")
    sys.exit(1)
else:
    key_preview = OPENROUTER_API_KEY[:10] + "..." + OPENROUTER_API_KEY[-5:]
    print(f"✓ API Key found: {key_preview}")

# Check 2: List available models
print("\n[2/4] Fetching available models from OpenRouter...")
try:
    response = requests.get(
        f"{OPENROUTER_BASE_URL}/models",
        timeout=10,
    )
    response.raise_for_status()
    
    models = response.json()
    
    # Filter for embedding models
    embedding_models = [m for m in models.get("data", []) if "embed" in m.get("id", "").lower()]
    
    print(f"✓ Found {len(embedding_models)} embedding models:\n")
    for model in embedding_models:
        model_id = model.get("id", "unknown")
        print(f"  - {model_id}")
    
    if not embedding_models:
        print("⚠ No embedding models found in public list")
        print("  (Some may require authentication to view)")

except Exception as e:
    print(f"❌ Failed to fetch models: {e}")

# Check 3: Test with valid API key
print("\n[3/4] Testing API authentication...")
headers = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "HTTP-Referer": "https://github.com/DDA4080",
    "X-Title": "Embedding Diagnostic",
    "Content-Type": "application/json",
}

# Try basic request to get user info
try:
    response = requests.get(
        f"{OPENROUTER_BASE_URL}/auth/key",
        headers=headers,
        timeout=10,
    )
    
    if response.status_code == 200:
        print("✓ API Key is valid")
        data = response.json()
        print(f"  Account: {data.get('data', {}).get('label', 'unknown')}")
    elif response.status_code == 401:
        print("❌ API Key is invalid/expired")
        print("   Generate a new key at: https://openrouter.ai/keys")
    else:
        print(f"⚠ Got status {response.status_code}")
        print(f"  Response: {response.text[:200]}")

except Exception as e:
    print(f"❌ Connection error: {e}")

# Check 4: Test embedding endpoint with sample model
print("\n[4/4] Testing embedding endpoint...")

test_models = [
    "openrouter/auto",
    "openai/text-embedding-3-small",
    "openai/text-embedding-3-large",
]

for model in test_models:
    payload = {
        "model": model,
        "input": "test",
    }
    
    try:
        response = requests.post(
            f"{OPENROUTER_BASE_URL}/embeddings",
            headers=headers,
            json=payload,
            timeout=10,
        )
        
        if response.status_code == 200:
            data = response.json()
            embedding_dim = len(data["data"][0]["embedding"])
            print(f"✓ {model}")
            print(f"  Status: 200 OK")
            print(f"  Dimensions: {embedding_dim}")
        elif response.status_code == 403:
            print(f"❌ {model}")
            print(f"  Status: 403 FORBIDDEN - Model not available")
        elif response.status_code == 404:
            print(f"❌ {model}")
            print(f"  Status: 404 NOT FOUND - Model doesn't exist")
        else:
            print(f"⚠ {model}")
            print(f"  Status: {response.status_code}")
            try:
                print(f"  Error: {response.json()}")
            except:
                print(f"  Response: {response.text[:100]}")
    
    except requests.exceptions.Timeout:
        print(f"⚠ {model} - Request timed out")
    except Exception as e:
        print(f"❌ {model} - Connection error: {e}")

print("\n" + "=" * 80)
print("RECOMMENDATIONS")
print("=" * 80)
print("""
If you're getting 403 Forbidden:

1. Check your API key is correct:
   PowerShell: $env:OPENROUTER_API_KEY
   Unix/Mac:   echo $OPENROUTER_API_KEY

2. Use supported embedding models:
   ✓ openrouter/auto (recommended - OpenRouter's best)
   ✓ openai/text-embedding-3-small (1536 dims)
   ✓ openai/text-embedding-3-large (3072 dims)

3. Check account status:
   https://openrouter.ai/account

4. Try running:
   python generate_embeddings.py --model "openrouter/auto" --limit 5 --dry-run

More info: https://openrouter.ai/docs#embeddings
""")
print("=" * 80 + "\n")
