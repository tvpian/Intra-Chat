#!/usr/bin/env python3
"""
Simple script to set up the application password.
This will create a .env file with your secure password.
"""

import os
import secrets
import getpass

def main():
    print("TeamChat Password Setup")
    print("=" * 30)
    
    # Check if .env already exists
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        print("⚠️  .env file already exists!")
        choice = input("Do you want to update the password? (y/N): ").lower()
        if choice != 'y':
            print("Password setup cancelled.")
            return
    
    # Get password from user
    while True:
        password = getpass.getpass("Enter your secure password: ")
        if len(password) < 8:
            print("❌ Password must be at least 8 characters long.")
            continue
        
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("❌ Passwords do not match.")
            continue
        
        break
    
    # Generate a secure secret key
    secret_key = secrets.token_hex(32)
    
    # Create .env file
    env_content = f"""# TeamChat Application Configuration
# Generated on {os.path.basename(__file__)}

APP_PASSWORD={password}
SECRET_KEY={secret_key}

# Optional: Adjust security settings
# MAX_ATTEMPTS=5
# LOCK_MS=30000
"""
    
    try:
        with open(env_path, 'w') as f:
            f.write(env_content)
        
        print("✅ Password setup complete!")
        print(f"📁 Configuration saved to: {env_path}")
        print("\n📋 Next steps:")
        print("1. Install python-dotenv: pip install python-dotenv")
        print("2. Restart your application")
        print("3. Your app is now password protected!")
        
    except Exception as e:
        print(f"❌ Error creating .env file: {e}")

if __name__ == "__main__":
    main()
