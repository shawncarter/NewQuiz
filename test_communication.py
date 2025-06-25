#!/usr/bin/env python3
"""
Test script to verify the quiz game communication flow
"""
import requests
import json
import time
import sys
import os

# Add the Django project to the Python path
sys.path.append('/home/shwan/Development/NewQuiz')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'quiz_game.settings')

import django
django.setup()

from game_sessions.models import GameSession, GameConfiguration, GameType, GameCategory
from players.models import Player

BASE_URL = 'http://localhost:8000'

def test_game_flow():
    print("🧪 Testing Quiz Game Communication Flow")
    print("=" * 50)
    
    # Step 1: Create a new game
    print("\n1️⃣ Creating a new game...")
    
    # Get available game types and categories
    game_type = GameType.objects.filter(is_active=True).first()
    categories = GameCategory.objects.filter(is_active=True, game_type=game_type)[:3]
    
    if not game_type or not categories:
        print("❌ No game types or categories found. Run setup_game_data first.")
        return
    
    create_data = {
        'game_type': game_type.id,
        'categories': [cat.id for cat in categories],
        'num_rounds': 3,
        'round_time': 30
    }
    
    response = requests.post(f'{BASE_URL}/game_sessions/create_game/', data=create_data)
    if response.status_code == 302:  # Redirect to game master page
        game_code = response.url.split('/')[-2]  # Extract game code from redirect
        print(f"✅ Game created successfully! Game code: {game_code}")
    else:
        print(f"❌ Failed to create game. Status: {response.status_code}")
        print(response.text[:200])
        return
    
    # Step 2: Add test players
    print(f"\n2️⃣ Adding test players to game {game_code}...")
    
    players = []
    for i, name in enumerate(['Alice', 'Bob'], 1):
        join_data = {
            'game_code': game_code,
            'player_name': name
        }
        response = requests.post(f'{BASE_URL}/game_sessions/join_game/', data=join_data)
        if response.status_code == 302:
            player_id = response.url.split('/')[-2]  # Extract player ID from redirect
            players.append({'name': name, 'id': player_id})
            print(f"✅ Player {name} joined! (ID: {player_id})")
        else:
            print(f"❌ Failed to add player {name}")
    
    # Step 3: Start the game
    print(f"\n3️⃣ Starting game {game_code}...")
    
    # Get CSRF token first
    response = requests.get(f'{BASE_URL}/game_sessions/game_master/{game_code}/')
    csrf_token = None
    if 'csrftoken' in response.cookies:
        csrf_token = response.cookies['csrftoken']
    
    headers = {
        'X-CSRFToken': csrf_token,
        'Content-Type': 'application/json'
    } if csrf_token else {}
    
    response = requests.post(f'{BASE_URL}/game_sessions/start_game/{game_code}/', 
                           headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Game started! Status: {result.get('status')}")
        if 'round_number' in result:
            print(f"   Round {result['round_number']}: {result.get('prompt', 'N/A')}")
    else:
        print(f"❌ Failed to start game. Status: {response.status_code}")
        print(response.text[:200])
        return
    
    # Step 4: Check game status
    print(f"\n4️⃣ Checking game status...")
    response = requests.get(f'{BASE_URL}/game_sessions/game_status/{game_code}/')
    if response.status_code == 200:
        status = response.json()
        print(f"✅ Game Status: {status}")
    else:
        print(f"❌ Failed to get game status")
    
    # Step 5: End the round after a short delay
    print(f"\n5️⃣ Ending the round...")
    time.sleep(2)  # Wait a bit
    
    response = requests.post(f'{BASE_URL}/game_sessions/end_round/{game_code}/', 
                           headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Round ended! Answers: {len(result.get('answers', []))}")
    else:
        print(f"❌ Failed to end round. Status: {response.status_code}")
        print(response.text[:200])
    
    print(f"\n🎯 Test completed for game {game_code}")
    print(f"   Check the logs and browser windows for WebSocket communication.")
    
    return game_code

if __name__ == '__main__':
    test_game_flow()