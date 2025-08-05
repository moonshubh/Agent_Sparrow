#!/bin/bash
echo "=== Railway SSH Debug Instructions ==="
echo ""
echo "1. SSH into your Railway service:"
echo "   railway ssh"
echo ""
echo "2. Once connected, run:"
echo "   python debug_endpoints.py"
echo ""
echo "3. If that file doesn't exist, create it:"
cat << 'EOF' > debug_quick.py
import os
print("=== CHECKING IMPORTS ===")
try:
    from app.api.v1.endpoints import auth as auth_endpoints
    print("✅ auth endpoints imported")
except Exception as e:
    print(f"❌ auth import failed: {e}")

try:
    from app.api.v1.endpoints import api_key_endpoints
    print("✅ api_key_endpoints imported")
except Exception as e:
    print(f"❌ api_key_endpoints import failed: {e}")
    import traceback
    traceback.print_exc()

print("\n=== CHECKING SUPABASE ===")
try:
    from supabase import create_client, Client
    print("✅ supabase module imported")
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if url and key:
        client = create_client(url, key)
        print(f"✅ Supabase client created: {type(client)}")
        print(f"   Has 'table' attribute: {hasattr(client, 'table')}")
    else:
        print("❌ Missing SUPABASE_URL or SUPABASE_ANON_KEY")
except Exception as e:
    print(f"❌ Supabase error: {e}")
EOF

echo ""
echo "4. Then run: python debug_quick.py"