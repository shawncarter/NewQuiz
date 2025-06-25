from django.test import TestCase, Client
from django.urls import reverse
from channels.testing import WebsocketCommunicator
import asyncio

from .models import GameSession, GameType, GameCategory, GameConfiguration
from players.models import Player
from .consumers import GameConsumer


class GameSessionModelTest(TestCase):
    """Test GameSession model functionality"""

    def setUp(self):
        """Set up test data"""
        self.game_type = GameType.objects.create(
            name="Letter Categories",
            description="Players think of items in specific categories that start with a given letter"
        )
        self.category = GameCategory.objects.create(
            name="Flowers",
            game_type=self.game_type
        )

    def test_game_session_creation(self):
        """Test creating a new game session"""
        game_session = GameSession.objects.create()

        # Check default values
        self.assertEqual(game_session.status, 'waiting')
        self.assertEqual(game_session.current_round_number, 0)
        self.assertFalse(game_session.is_round_active)
        self.assertEqual(game_session.max_players, 10)

        # Check game code generation
        self.assertIsNotNone(game_session.game_code)
        self.assertEqual(len(game_session.game_code), 6)

        # Check properties
        self.assertEqual(game_session.player_count, 0)
        self.assertTrue(game_session.can_join)

    def test_game_code_uniqueness(self):
        """Test that game codes are unique"""
        game1 = GameSession.objects.create()
        game2 = GameSession.objects.create()

        self.assertNotEqual(game1.game_code, game2.game_code)

    def test_start_game(self):
        """Test starting a game session"""
        game_session = GameSession.objects.create()

        # Create configuration
        config = GameConfiguration.objects.create(
            game_session=game_session,
            game_type=self.game_type,
            num_rounds=5,
            round_time_seconds=30
        )
        config.categories.add(self.category)

        # Start the game
        game_session.start_game()

        self.assertEqual(game_session.status, 'active')
        self.assertIsNotNone(game_session.started_at)

    def test_restart_game(self):
        """Test restarting a game session"""
        game_session = GameSession.objects.create()
        game_session.status = 'active'
        game_session.current_round_number = 3
        game_session.save()

        # Add a player and answer
        player = Player.objects.create(
            name="Test Player",
            game_session=game_session,
            session_key="test_session"
        )

        # Restart the game
        game_session.restart_game()

        self.assertEqual(game_session.status, 'waiting')
        self.assertEqual(game_session.current_round_number, 0)
        self.assertFalse(game_session.is_round_active)
        self.assertIsNone(game_session.started_at)

        # Check player is still there but marked as connected
        player.refresh_from_db()
        self.assertTrue(player.is_connected)


class GameCreationViewTest(TestCase):
    """Test game creation through web interface"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.game_type = GameType.objects.create(
            name="Letter Categories",
            description="Players think of items in specific categories that start with a given letter"
        )
        self.category1 = GameCategory.objects.create(
            name="Flowers",
            game_type=self.game_type
        )
        self.category2 = GameCategory.objects.create(
            name="Fruits",
            game_type=self.game_type
        )

    def test_create_game_get(self):
        """Test GET request to create game page"""
        response = self.client.get(reverse('create_game'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create New Game')
        self.assertContains(response, self.game_type.name)
        self.assertContains(response, self.category1.name)
        self.assertContains(response, self.category2.name)

    def test_create_game_post_success(self):
        """Test successful game creation via POST"""
        response = self.client.post(reverse('create_game'), {
            'game_type': self.game_type.id,
            'categories': [self.category1.id, self.category2.id],
            'num_rounds': 8,
            'round_time': 45
        })

        # Should redirect to game master page
        self.assertEqual(response.status_code, 302)

        # Check game was created
        game_session = GameSession.objects.latest('created_at')
        self.assertEqual(game_session.status, 'waiting')

        # Check configuration
        config = game_session.configuration
        self.assertEqual(config.game_type, self.game_type)
        self.assertEqual(config.num_rounds, 8)
        self.assertEqual(config.round_time_seconds, 45)
        self.assertEqual(list(config.categories.all()), [self.category1, self.category2])

        # Check redirect URL
        expected_url = reverse('game_master', kwargs={'game_code': game_session.game_code})
        self.assertRedirects(response, expected_url)

    def test_create_game_post_minimal(self):
        """Test game creation with minimal data"""
        response = self.client.post(reverse('create_game'), {
            'game_type': self.game_type.id,
            'categories': [self.category1.id],
        })

        self.assertEqual(response.status_code, 302)

        # Check defaults were applied
        game_session = GameSession.objects.latest('created_at')
        config = game_session.configuration
        self.assertEqual(config.num_rounds, 10)  # default
        self.assertEqual(config.round_time_seconds, 30)  # default


class PlayerJoiningTest(TestCase):
    """Test player joining functionality"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.game_type = GameType.objects.create(
            name="Letter Categories",
            description="Players think of items in specific categories that start with a given letter"
        )
        self.category = GameCategory.objects.create(
            name="Flowers",
            game_type=self.game_type
        )

        # Create a game session
        self.game_session = GameSession.objects.create()
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type,
            num_rounds=5,
            round_time_seconds=30
        )
        self.config.categories.add(self.category)

    def test_join_game_get(self):
        """Test GET request to join game page"""
        response = self.client.get(reverse('join_game'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Join Game')
        self.assertContains(response, 'Game Code')
        self.assertContains(response, 'Your Name')

    def test_join_game_success(self):
        """Test successful player joining"""
        response = self.client.post(reverse('join_game'), {
            'game_code': self.game_session.game_code,
            'player_name': 'Test Player'
        })

        # Should redirect to player lobby
        self.assertEqual(response.status_code, 302)
        expected_url = reverse('player_lobby', kwargs={'game_code': self.game_session.game_code})
        self.assertRedirects(response, expected_url)

        # Check player was created
        player = Player.objects.get(game_session=self.game_session)
        self.assertEqual(player.name, 'Test Player')
        self.assertTrue(player.is_connected)
        self.assertIsNotNone(player.session_key)

        # Check game session player count
        self.assertEqual(self.game_session.player_count, 1)

    def test_join_game_invalid_code(self):
        """Test joining with invalid game code"""
        response = self.client.post(reverse('join_game'), {
            'game_code': 'INVALID',
            'player_name': 'Test Player'
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Game not found')

        # No player should be created
        self.assertEqual(Player.objects.count(), 0)

    def test_join_game_empty_name(self):
        """Test joining with empty player name"""
        response = self.client.post(reverse('join_game'), {
            'game_code': self.game_session.game_code,
            'player_name': ''
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please provide both game code and your name')

        # No player should be created
        self.assertEqual(Player.objects.count(), 0)

    def test_join_game_duplicate_name(self):
        """Test joining with duplicate player name in same game"""
        # Create first player
        Player.objects.create(
            name="Test Player",
            game_session=self.game_session,
            session_key="session1"
        )

        response = self.client.post(reverse('join_game'), {
            'game_code': self.game_session.game_code,
            'player_name': 'Test Player'
        })

        # The current implementation allows duplicate names but uses session_key to identify players
        # So this will actually succeed and create a new player with different session
        self.assertEqual(response.status_code, 302)

        # Should have two players now (different sessions)
        self.assertEqual(Player.objects.count(), 2)

    def test_join_game_full_capacity(self):
        """Test joining when game is at full capacity"""
        # Set max players to 2
        self.game_session.max_players = 2
        self.game_session.save()

        # Add 2 players
        Player.objects.create(
            name="Player 1",
            game_session=self.game_session,
            session_key="session1"
        )
        Player.objects.create(
            name="Player 2",
            game_session=self.game_session,
            session_key="session2"
        )

        response = self.client.post(reverse('join_game'), {
            'game_code': self.game_session.game_code,
            'player_name': 'Player 3'
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cannot join this game. It may be full or already started')

        # Should still only have 2 players
        self.assertEqual(Player.objects.count(), 2)

    def test_join_active_game(self):
        """Test joining a game that has already started"""
        self.game_session.status = 'active'
        self.game_session.save()

        response = self.client.post(reverse('join_game'), {
            'game_code': self.game_session.game_code,
            'player_name': 'Test Player'
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cannot join this game. It may be full or already started')

        # No player should be created
        self.assertEqual(Player.objects.count(), 0)

    def test_multiple_players_joining(self):
        """Test multiple players joining the same game"""
        # First player
        response1 = self.client.post(reverse('join_game'), {
            'game_code': self.game_session.game_code,
            'player_name': 'Player 1'
        })
        self.assertEqual(response1.status_code, 302)

        # Second player (using different client to simulate different session)
        client2 = Client()
        response2 = client2.post(reverse('join_game'), {
            'game_code': self.game_session.game_code,
            'player_name': 'Player 2'
        })
        self.assertEqual(response2.status_code, 302)

        # Check both players were created
        players = Player.objects.filter(game_session=self.game_session).order_by('joined_at')
        self.assertEqual(len(players), 2)
        self.assertEqual(players[0].name, 'Player 1')
        self.assertEqual(players[1].name, 'Player 2')

        # Check game session player count
        self.assertEqual(self.game_session.player_count, 2)


class WebSocketGameTest(TestCase):
    """Test WebSocket functionality for real-time game updates"""

    def setUp(self):
        """Set up test data"""
        self.game_type = GameType.objects.create(
            name="Letter Categories",
            description="Players think of items in specific categories that start with a given letter"
        )
        self.category = GameCategory.objects.create(
            name="Flowers",
            game_type=self.game_type
        )

        # Create a game session
        self.game_session = GameSession.objects.create()
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type,
            num_rounds=5,
            round_time_seconds=30
        )
        self.config.categories.add(self.category)

    async def test_websocket_connection(self):
        """Test WebSocket connection to game"""
        communicator = WebsocketCommunicator(
            GameConsumer.as_asgi(),
            f"/ws/game/{self.game_session.game_code}/"
        )

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # Should receive initial game state
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'game_state')
        self.assertIn('data', response)

        game_data = response['data']
        self.assertEqual(game_data['game_code'], self.game_session.game_code)
        self.assertEqual(game_data['status'], 'waiting')
        self.assertEqual(game_data['player_count'], 0)

        await communicator.disconnect()

    async def test_websocket_ping(self):
        """Test WebSocket ping functionality"""
        communicator = WebsocketCommunicator(
            GameConsumer.as_asgi(),
            f"/ws/game/{self.game_session.game_code}/"
        )

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # Consume initial game state
        await communicator.receive_json_from()

        # Send ping
        await communicator.send_json_to({'type': 'ping'})

        # Should receive game state response
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'game_state')

        await communicator.disconnect()

    def test_websocket_connection_sync(self):
        """Synchronous wrapper for WebSocket connection test"""
        asyncio.run(self.test_websocket_connection())

    async def test_websocket_game_updates(self):
        """Test WebSocket game update broadcasts"""
        communicator = WebsocketCommunicator(
            GameConsumer.as_asgi(),
            f"/ws/game/{self.game_session.game_code}/"
        )

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # Consume initial game state
        initial_response = await communicator.receive_json_from()
        self.assertEqual(initial_response['type'], 'game_state')

        # Simulate player join by calling the broadcast function directly
        from .websocket_utils import broadcast_to_game
        broadcast_to_game(self.game_session.game_code, 'game_update', {
            'game_status': 'waiting',
            'player_count': 1,
            'message': 'Test player joined!'
        })

        # Should receive game update
        update_response = await communicator.receive_json_from()
        self.assertEqual(update_response['type'], 'game_update')
        self.assertEqual(update_response['data']['message'], 'Test player joined!')
        self.assertEqual(update_response['data']['player_count'], 1)

        await communicator.disconnect()

    async def test_websocket_game_restart(self):
        """Test WebSocket game restart broadcasts"""
        communicator = WebsocketCommunicator(
            GameConsumer.as_asgi(),
            f"/ws/game/{self.game_session.game_code}/"
        )

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # Consume initial game state
        await communicator.receive_json_from()

        # Simulate game restart
        from .websocket_utils import broadcast_to_game
        broadcast_to_game(self.game_session.game_code, 'game_update', {
            'game_status': 'waiting',
            'player_count': 0,
            'message': 'Game restarted! Get ready for a new game.'
        })

        # Should receive restart notification
        restart_response = await communicator.receive_json_from()
        self.assertEqual(restart_response['type'], 'game_update')
        self.assertEqual(restart_response['data']['game_status'], 'waiting')
        self.assertIn('restarted', restart_response['data']['message'])

        await communicator.disconnect()

    def test_websocket_game_updates_sync(self):
        """Synchronous wrapper for WebSocket game updates test"""
        asyncio.run(self.test_websocket_game_updates())

    def test_websocket_game_restart_sync(self):
        """Synchronous wrapper for WebSocket game restart test"""
        asyncio.run(self.test_websocket_game_restart())

    def test_websocket_ping_sync(self):
        """Synchronous wrapper for WebSocket ping test"""
        asyncio.run(self.test_websocket_ping())


class GameStartTest(TestCase):
    """Test game starting functionality"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.game_type = GameType.objects.create(
            name="Letter Categories",
            description="Players think of items in specific categories that start with a given letter"
        )
        self.category = GameCategory.objects.create(
            name="Flowers",
            game_type=self.game_type
        )

        # Create a game session with configuration
        self.game_session = GameSession.objects.create()
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type,
            num_rounds=5,
            round_time_seconds=30
        )
        self.config.categories.add(self.category)

        # Add a player
        self.player = Player.objects.create(
            name="Test Player",
            game_session=self.game_session,
            session_key="test_session"
        )

    def test_start_game_success(self):
        """Test successfully starting a game"""
        url = reverse('start_game', kwargs={'game_code': self.game_session.game_code})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)

        # Check response is JSON
        data = response.json()
        self.assertIn('success', data)

        # Check game status changed
        self.game_session.refresh_from_db()
        self.assertEqual(self.game_session.status, 'active')
        self.assertIsNotNone(self.game_session.started_at)

    def test_start_game_no_players(self):
        """Test starting game with no players"""
        # Remove the player
        self.player.delete()

        url = reverse('start_game', kwargs={'game_code': self.game_session.game_code})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('No players', data['error'])

        # Game should still be waiting
        self.game_session.refresh_from_db()
        self.assertEqual(self.game_session.status, 'waiting')

    def test_start_already_active_game(self):
        """Test starting a game that's already active"""
        self.game_session.status = 'active'
        self.game_session.save()

        url = reverse('start_game', kwargs={'game_code': self.game_session.game_code})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('not in waiting state', data['error'])
