#!/usr/bin/env python3
"""
Temporary script to fix the UUID mismatch issue for API keys.
This will update the UUID and handle the encryption issue.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add the app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.supabase_client import get_supabase_client
from app.api_keys.encryption import get_encryption_service
from app.api_keys.schemas import APIKeyType

async def fix_api_key_uuid():
    """Fix the UUID mismatch for the user's API key."""
    
    # UUIDs
    WRONG_UUID = "86c5eeb9-367c-4948-82ba-52132596c846"
    CORRECT_UUID = "86c5eeb9-367c-4948-82ba-5213259c684f"
    
    print(f"Fixing UUID mismatch...")
    print(f"Wrong UUID:   {WRONG_UUID}")
    print(f"Correct UUID: {CORRECT_UUID}")
    
    # Get Supabase client
    supabase = get_supabase_client()
    
    # Step 1: Check if the wrong UUID exists
    print("\nStep 1: Checking for API key with wrong UUID...")
    response = supabase.client.table("user_api_keys")\
        .select("*")\
        .eq("user_uuid", WRONG_UUID)\
        .execute()
    
    if not response.data:
        # Check if it was already fixed
        response = supabase.client.table("user_api_keys")\
            .select("*")\
            .eq("user_uuid", CORRECT_UUID)\
            .execute()
        
        if response.data:
            print("✓ API key already has the correct UUID!")
            print(f"  Last used: {response.data[0].get('last_used_at', 'Never')}")
            return
        else:
            print("✗ No API key found for either UUID")
            return
    
    # Step 2: Get the encrypted key data
    api_key_data = response.data[0]
    print(f"✓ Found API key: {api_key_data['api_key_type']}")
    print(f"  Created: {api_key_data['created_at']}")
    print(f"  Last used: {api_key_data.get('last_used_at', 'Never')}")
    
    # Step 3: Try to decrypt with wrong UUID (to get the original key)
    encryption_service = get_encryption_service()
    try:
        print("\nStep 2: Attempting to decrypt with wrong UUID...")
        decrypted_key = encryption_service.decrypt_api_key(WRONG_UUID, api_key_data["encrypted_key"])
        print(f"✓ Successfully decrypted API key: {decrypted_key[:8]}...{decrypted_key[-4:]}")
        
        # Step 4: Re-encrypt with correct UUID
        print("\nStep 3: Re-encrypting with correct UUID...")
        new_encrypted_key = encryption_service.encrypt_api_key(CORRECT_UUID, decrypted_key)
        print("✓ Re-encrypted API key with correct UUID")
        
        # Step 5: Update the database
        print("\nStep 4: Updating database...")
        update_response = supabase.client.table("user_api_keys")\
            .update({
                "user_uuid": CORRECT_UUID,
                "user_id": CORRECT_UUID,
                "encrypted_key": new_encrypted_key
            })\
            .eq("user_uuid", WRONG_UUID)\
            .execute()
        
        if update_response.data:
            print("✓ Successfully updated API key with correct UUID!")
            print("\nThe API key should now work correctly.")
        else:
            print("✗ Failed to update database")
            
    except Exception as e:
        print(f"✗ Decryption failed: {e}")
        print("\nThe API key cannot be recovered due to encryption mismatch.")
        print("The user will need to re-enter their API key through the frontend.")
        
        # Step 6: Just update the UUID (user will need to re-enter key)
        print("\nUpdating UUID anyway (key will need to be re-entered)...")
        update_response = supabase.client.table("user_api_keys")\
            .update({
                "user_uuid": CORRECT_UUID,
                "user_id": CORRECT_UUID
            })\
            .eq("user_uuid", WRONG_UUID)\
            .execute()
        
        if update_response.data:
            print("✓ Updated UUID. User needs to re-enter their API key.")

if __name__ == "__main__":
    asyncio.run(fix_api_key_uuid())