# Chat History Implementation Guide

This document explains the chat history persistence feature that allows users to save and retrieve conversations per device/browser.

## Overview

The chat history system now enables:
- **Per-Device Tracking**: Each browser/device gets a unique ID
- **Persistent Sessions**: Conversations are saved to Supabase database
- **Easy History Access**: Users can load previous conversations from the sidebar
- **Automatic Saving**: Messages are automatically saved as they're sent

## Architecture

### Backend (FastAPI)

**New Models** (`backend/chat_api.py`):
- `ChatRequest`: Extended to include `device_id`
- `ChatSession`: Stores session metadata (id, title, created_at, updated_at, message_count)
- `ChatHistoryItem`: Individual message pairs from a session
- `CreateSessionRequest`: Request to create a new session

**New Functions**:
- `create_or_get_session()`: Creates or retrieves a session for a device
- `save_chat_message()`: Persists user/bot message pairs to database
- `get_device_sessions()`: Retrieves all sessions for a device (with message counts)
- `get_session_history()`: Retrieves all messages in a specific session

**New Endpoints**:
- `POST /chat`: Updated to save messages automatically
- `GET /chat/sessions/{device_id}`: Get all sessions for a device
- `GET /chat/history/{session_id}`: Get all messages in a session
- `POST /chat/sessions`: Create a new chat session

### Frontend (Next.js)

**New Files**:

1. **`frontend/lib/deviceId.ts`**:
   - `getOrCreateDeviceId()`: Gets or generates unique device ID, stores in localStorage
   - `clearDeviceId()`: Clears stored device ID

2. **`frontend/lib/chatService.ts`**:
   - `sendChatMessage()`: Sends message with device_id
   - `getChatSessions()`: Fetches all sessions for current device
   - `getChatHistory()`: Fetches messages from a session
   - `createNewSession()`: Creates a new session
   - Type definitions: `ChatSession`, `ChatMessage`, `ChatResponse`

3. **`frontend/components/ChatSkeleton.tsx`** (Updated):
   - Loads all chat sessions on component mount
   - Loads chat history when a session is selected
   - Automatically creates new sessions on first message
   - Updates session list after new messages
   - Shows loading states for history retrieval

### Database (Supabase)

**New Tables**:

1. **`chat_sessions`**:
   ```sql
   - id: UUID (primary key)
   - device_id: TEXT (for grouping by device)
   - title: TEXT (conversation title, auto-generated from first message)
   - created_at: TIMESTAMP
   - updated_at: TIMESTAMP
   ```

2. **`chat_history`**:
   ```sql
   - id: UUID (primary key)
   - session_id: UUID (foreign key to chat_sessions)
   - device_id: TEXT
   - user_message: TEXT
   - bot_response: TEXT
   - sources: JSONB (response sources/references)
   - manual_type_filter: TEXT (teacher/student filter used)
   - created_at: TIMESTAMP
   ```

**Indexes**:
- `chat_sessions` (session_id)
- `chat_history` (session_id, device_id, created_at)

## How It Works

### User Journey

1. **First Visit**:
   - Frontend generates unique device ID (if not in localStorage)
   - Device ID is stored in browser localStorage
   - Sidebar shows "No history yet"

2. **New Message**:
   - User types and sends a message
   - Request includes device_id
   - Backend creates/retrieves session for that device
   - Chat message pair is saved to `chat_history`
   - Session title is auto-generated from first message
   - Frontend receives session_id and stores it in state
   - Session appears in sidebar

3. **Load Previous Conversation**:
   - User clicks a session in the sidebar
   - Frontend calls `GET /chat/history/{session_id}`
   - Messages are loaded and displayed
   - User can continue the conversation in that session

4. **New Chat**:
   - User clicks "+ New Chat" button
   - `activeSessionId` is cleared
   - Next message will create a new session

## Setup Instructions

### 1. Database Setup

Run the SQL migration in your Supabase SQL Editor:

```bash
# Navigate to: https://app.supabase.com/project/[your-project]/sql/new
# Paste the contents of: backend/supabase_setup.sql

# Key tables needed:
- chat_sessions
- chat_history

# Add device_id column if updating existing database:
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS device_id TEXT;
ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS device_id TEXT;
CREATE INDEX IF NOT EXISTS chat_history_device_id_idx ON chat_history(device_id);
```

###  2. Backend Setup

The backend is already updated with:
- New models and request types
- Session management functions
- Chat history endpoints
- Automatic message persistence

**No additional backend setup required** - just restart your server:
```bash
python -m uvicorn chat_api:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend Setup

The frontend is already updated with:
- Device ID management utility
- Chat service API calls
- Updated ChatSkeleton component with history loading

**No additional frontend setup required** - just reload the app.

## Key Features

### Device Identification

Each browser/device gets a unique ID:
```
Format: device_[timestamp]_[random]
Example: device_2g5ybpk0_l3jk3k2k3j4k5
```

Stored in localStorage under key: `sayo_device_id`

### Session Management

- Sessions are automatically created on first message
- Session titles are extracted from the first user message (first 50 chars)
- Sessions show message count in the sidebar
- Sessions are ordered by most recent activity

### Message Persistence

Messages are saved with:
- User message text
- Bot response text
- Sources (references used by the bot)
- Manual type filter (if student/teacher filter was used)
- Timestamp of when the message was sent

### Context in Messages

The frontend now displays:
- Number of messages in each session (in sidebar)
- Loading state when fetching history
- Timestamp on hover for each message
- Clean separation between sessions

## API Reference

### POST /chat
```json
{
  "message": "string",
  "device_id": "string (optional, defaults to 'anonymous')",
  "session_id": "string (optional, UUID)",
  "manual_type": "string (optional, 'teacher' or 'student')"
}
```

Response:
```json
{
  "response": "string",
  "session_id": "string (UUID)",
  "sources": [...] 
}
```

### GET /chat/sessions/{device_id}
Retrieves all chat sessions for a device.

Query parameters:
- `limit`: number (default: 20)

Response:
```json
{
  "sessions": [
    {
      "id": "uuid",
      "title": "string",
      "created_at": "ISO8601",
      "updated_at": "ISO8601",
      "message_count": number
    }
  ],
  "total_count": number
}
```

### GET /chat/history/{session_id}
Retrieves all messages in a session.

Response:
```json
{
  "messages": [
    {
      "id": "string",
      "user_message": "string",
      "bot_response": "string",
      "sources": [...],
      "created_at": "ISO8601"
    }
  ],
  "count": number
}
```

### POST /chat/sessions
Creates a new chat session.

Request:
```json
{
  "device_id": "string",
  "title": "string (optional)"
}
```

Response:
```json
{
  "session_id": "string (UUID)",
  "created_at": "string"
}
```

## Usage Examples

### JavaScript/TypeScript

```typescript
import { 
  sendChatMessage, 
  getChatSessions, 
  getChatHistory 
} from '@/lib/chatService';
import { getOrCreateDeviceId } from '@/lib/deviceId';

// Get device ID (auto-generated on first call)
const deviceId = getOrCreateDeviceId();

// Send a message (creates session automatically)
const response = await sendChatMessage(
  "How do I use Sayo?",
  null, // session_id (null for new chat)
  null  // manual_type (optional)
);
console.log(response.session_id); // Use this for future messages

// Get all sessions for this device
const sessions = await getChatSessions(20);
console.log(sessions); // Array of ChatSession objects

// Load a specific session's history
const history = await getChatHistory(response.session_id);
console.log(history); // Array of ChatHistoryItem objects
```

## Troubleshooting

### Sessions not appearing in sidebar
1. Check browser console for errors
2. Verify Supabase connection
3. Check that database tables exist
4. Ensure `device_id` is being generated

### Messages not saving
1. Verify backend endpoints are running
2. Check network requests in DevTools
3. Verify Supabase `chat_history` table has correct schema
4. Check server logs for database errors

### Previous chat loading slowly
1. This is expected on large sessions (100+ messages)
2. Consider adding pagination for very large sessions
3. Optimize database queries if needed

### Device ID not persisting
1. Check if localStorage is enabled in browser
2. Verify no browser privacy mode is preventing storage
3. Check browser console for Storage API errors

## Future Enhancements

Potential improvements:
- User authentication (currently device-based)
- Chat session search/filtering
- Export chat history
- Share sessions with others
- Session renaming
- Conversation pinning
- Message-level reactions/feedback
- Pagination for large sessions

## Security Considerations

Current implementation:
- Device IDs are stored only in browser localStorage
- No user authentication required
- All data is stored per device
- Recommended: Add rate limiting to endpoints
- Recommended: Add input validation on messages

For production:
- Consider implementing user authentication
- Add encryption for sensitive data
- Implement data retention policies
- Add audit logging for sensitive operations

## Performance Notes

- Sessions list is loaded on component mount (fast for <20 sessions)
- Message history is loaded when session is selected (paginate for very large sessions)
- Saving messages is asynchronous (non-blocking)
- Database indexes optimize queries by device_id and session_id

## Support

For issues or questions:
1. Check the Troubleshooting section
2. Review API responses for error messages
3. Check Supabase logs for database errors
4. Review browser console for frontend errors
