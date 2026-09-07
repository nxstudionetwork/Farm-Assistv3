#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for document upload functionality
"""
import requests
import os
import sys

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Configuration
API_BASE_URL = "http://localhost:8000/api/v1"
TEST_FILE = "test_sample.txt"

def test_upload():
    """Test document upload with authentication"""

    # First, try to login or register
    print("Testing authentication...")

    # Try different login methods
    login_methods = [
        {
            "method": "password (existing user)",
            "data": {
                "phone_number": "9876543210",
                "password": "Test123456"
            }
        },
        {
            "method": "email (existing user)",
            "data": {
                "email": "test@farmassist.com",
                "password": "Test123456"
            }
        },
        {
            "method": "password (test user 1)",
            "data": {
                "phone_number": "9998887776",
                "password": "TestDoc123"
            }
        }
    ]

    token = None
    for login_attempt in login_methods:
        try:
            print(f"Attempting login with {login_attempt['method']}...")
            response = requests.post(f"{API_BASE_URL}/auth/login", json=login_attempt['data'])
            if response.status_code == 200:
                print("[OK] Login successful")
                token_data = response.json()
                token = token_data.get("access_token")
                if not token:
                    print("[ERROR] No token in response")
                else:
                    break
            else:
                print(f"[INFO] Login failed: {response.status_code}")
        except Exception as e:
            print(f"[INFO] Login error: {e}")

    # If still no token, try to register or login with existing user
    if not token:
        print("Attempting to login with existing test user (9998887776)...")
        login_data = {
            "phone_number": "9998887776",
            "password": "TestDoc123"
        }

        try:
            response = requests.post(f"{API_BASE_URL}/auth/login", json=login_data)
            if response.status_code == 200:
                print("[OK] Login successful with existing user")
                token_data = response.json()
                token = token_data.get("access_token")
            else:
                print(f"[INFO] Login with existing user failed: {response.status_code}")
                # Try to register a new user with different number
                print("Attempting to register new test user...")
                register_data = {
                    "full_name": "Test Document User 2",
                    "phone_number": "9988776655",
                    "email": "testdoc2@farmassist.com",
                    "password": "TestDoc456",
                    "pin": "1234"
                }

                response = requests.post(f"{API_BASE_URL}/auth/register", json=register_data)
                if response.status_code in [200, 201]:
                    print("[OK] User registered successfully")
                    # Try login with new user
                    login_data = {
                        "phone_number": "9988776655",
                        "password": "TestDoc456"
                    }
                    response = requests.post(f"{API_BASE_URL}/auth/login", json=login_data)
                    if response.status_code == 200:
                        print("[OK] Login successful with new user")
                        token_data = response.json()
                        token = token_data.get("access_token")
                    else:
                        print(f"[ERROR] Login after registration failed: {response.status_code}")
                else:
                    print(f"[ERROR] Registration failed: {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Auth error: {e}")

    # Test document upload only if we have a token
    if not token:
        print("[ERROR] No authentication token available after all attempts")
        print("Please use the web interface to test document upload instead.")
        print("Navigate to http://localhost:3000 and login, then go to documents page.")
        return

    print("\nTesting document upload...")

    if not os.path.exists(TEST_FILE):
        print(f"[ERROR] Test file {TEST_FILE} not found")
        return

    headers = {
        "Authorization": f"Bearer {token}"
    }

    files = {
        "file": (TEST_FILE, open(TEST_FILE, "rb"), "text/plain")
    }

    data = {
        "document_category": "Other",
        "description": "Test document upload"
    }

    try:
        response = requests.post(
            f"{API_BASE_URL}/documents/upload",
            headers=headers,
            files=files,
            data=data
        )

        if response.status_code == 201:
            print("[OK] Document upload successful")
            result = response.json()
            print(f"Document ID: {result.get('data', {}).get('document_id')}")
            print(f"File name: {result.get('data', {}).get('document_name')}")
            print(f"File size: {result.get('data', {}).get('file_size_bytes')} bytes")
        else:
            print(f"[ERROR] Upload failed: {response.status_code}")
            print(f"Response: {response.text}")

    except Exception as e:
        print(f"[ERROR] Upload error: {e}")
    finally:
        files["file"][1].close()

    # Test listing documents
    print("\nTesting document list...")
    try:
        response = requests.get(
            f"{API_BASE_URL}/documents",
            headers=headers
        )

        if response.status_code == 200:
            print("[OK] Document list successful")
            result = response.json()
            docs = result.get("data", {}).get("items", [])
            print(f"Total documents: {len(docs)}")
            for doc in docs:
                print(f"  - {doc.get('document_name')} ({doc.get('file_type')})")
        else:
            print(f"[ERROR] List failed: {response.status_code}")
            print(f"Response: {response.text}")

    except Exception as e:
        print(f"[ERROR] List error: {e}")

if __name__ == "__main__":
    print("Farm Assist Document Upload Test")
    print("=" * 40)
    test_upload()