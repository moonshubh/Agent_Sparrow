#!/usr/bin/env python3
"""
Update existing conversations to have proper versioning data
"""

import requests
import psycopg2
import psycopg2.extras
import uuid
from app.db.connection_manager import get_connection_manager

def update_conversations_versioning():
    """Update existing conversations to have proper versioning fields"""
    print("🔄 Updating existing conversations with versioning data...")
    
    manager = get_connection_manager()
    
    try:
        with manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Get all conversations without uuid or version
                cur.execute("""
                    SELECT id, title, raw_transcript, created_at, updated_at
                    FROM feedme_conversations 
                    WHERE uuid IS NULL OR version IS NULL OR is_active IS NULL
                """)
                
                conversations = cur.fetchall()
                print(f"Found {len(conversations)} conversations to update")
                
                for conv in conversations:
                    conversation_id = conv[0]
                    
                    # Generate UUID and set version/active status
                    conversation_uuid = str(uuid.uuid4())
                    
                    cur.execute("""
                        UPDATE feedme_conversations 
                        SET uuid = %s, version = 1, is_active = true, updated_at = NOW()
                        WHERE id = %s
                    """, (conversation_uuid, conversation_id))
                    
                    print(f"  ✅ Updated conversation {conversation_id} with UUID {conversation_uuid}")
                
                conn.commit()
                print(f"🎉 Successfully updated {len(conversations)} conversations!")
                
    except Exception as e:
        print(f"❌ Error updating conversations: {e}")
        raise

if __name__ == "__main__":
    update_conversations_versioning()