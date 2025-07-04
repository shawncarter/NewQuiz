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
        """
        Initializes the test client and creates a game type with two associated categories for use in test cases.
        """
        self.client = Client()
        self.game_type = GameType.objects.create(
            name="Flower, Fruit & Veg",
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
        """
        Verifies that the game creation page renders successfully and displays the expected form elements and available game types and categories.
        """
        response = self.client.get(reverse('game_sessions:create_game'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create New Game')
        self.assertContains(response, self.game_type.name)
        self.assertContains(response, self.category1.name)
        self.assertContains(response, self.category2.name)

    def test_create_game_post_success(self):
        """
        Test that posting valid data to the game creation endpoint successfully creates a new game session and configuration, then redirects to the game master page.
        """
        response = self.client.post(reverse('game_sessions:create_game'), {
            'game_type': 'flower_fruit_veg',
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
        expected_url = reverse('game_sessions:game_master', kwargs={'game_code': game_session.game_code})
        self.assertRedirects(response, expected_url)

    def test_create_game_post_minimal(self):
        """
        Test that a game can be created with only the required fields, and that default configuration values are applied for unspecified options.
        """
        response = self.client.post(reverse('game_sessions:create_game'), {
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
        """
        Test that a GET request to the join game page returns a 200 response and contains the expected form fields.
        """
        response = self.client.get(reverse('game_sessions:join_game'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Join Game')
        self.assertContains(response, 'Game Code')
        self.assertContains(response, 'Your Name')

    def test_join_game_success(self):
        """
        Test that a player can successfully join a game session via POST request.
        
        Verifies that a new player is created, marked as connected, and redirected to the player lobby. Also checks that the game session's player count is updated accordingly.
        """
        response = self.client.post(reverse('game_sessions:join_game'), {
            'game_code': self.game_session.game_code,
            'player_name': 'Test Player'
        })

        # Should redirect to player lobby
        self.assertEqual(response.status_code, 302)
        # The view redirects to player_lobby_with_id, so we need to get the player ID
        player = Player.objects.get(name='Test Player', game_session=self.game_session)
        expected_url = reverse('players:player_lobby_with_id', kwargs={'game_code': self.game_session.game_code, 'player_id': player.id})
        self.assertRedirects(response, expected_url)

        # Check player was created
        player = Player.objects.get(game_session=self.game_session)
        self.assertEqual(player.name, 'Test Player')
        self.assertTrue(player.is_connected)
        # session_key is not set in the current implementation (set to None for development)
        self.assertIsNone(player.session_key)

        # Check game session player count
        self.assertEqual(self.game_session.player_count, 1)

    def test_join_game_invalid_code(self):
        """
        Test that submitting an invalid game code when joining a game returns an error message and does not create a player.
        """
        response = self.client.post(reverse('game_sessions:join_game'), {
            'game_code': 'INVALID',
            'player_name': 'Test Player'
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Game not found')

        # No player should be created
        self.assertEqual(Player.objects.count(), 0)

    def test_join_game_empty_name(self):
        """
        Test that submitting an empty player name when joining a game returns an error message and does not create a player.
        """
        response = self.client.post(reverse('game_sessions:join_game'), {
            'game_code': self.game_session.game_code,
            'player_name': ''
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please provide both game code and your name')

        # No player should be created
        self.assertEqual(Player.objects.count(), 0)

    def test_join_game_duplicate_name(self):
        """
        Test that joining a game with a duplicate player name reconnects the existing player instead of creating a new one.
        
        Verifies that submitting a join request with a player name already present in the game session results in reconnecting the existing player, maintains a single player record, and marks the player as connected.
        """
        # Create first player
        Player.objects.create(
            name="Test Player",
            game_session=self.game_session,
            session_key="session1"
        )

        response = self.client.post(reverse('game_sessions:join_game'), {
            'game_code': self.game_session.game_code,
            'player_name': 'Test Player'
        })

        # The current implementation reconnects existing players with the same name
        # So this will succeed but reconnect the existing player instead of creating a new one
        self.assertEqual(response.status_code, 302)

        # Should still have only one player (reconnected)
        self.assertEqual(Player.objects.count(), 1)

        # Check that the player was reconnected
        player = Player.objects.get(name="Test Player", game_session=self.game_session)
        self.assertTrue(player.is_connected)

    def test_join_game_full_capacity(self):
        """
        Verifies that attempting to join a game session at full player capacity fails and does not create a new player.
        """
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

        response = self.client.post(reverse('game_sessions:join_game'), {
            'game_code': self.game_session.game_code,
            'player_name': 'Player 3'
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cannot join this game. It may be full or already started')

        # Should still only have 2 players
        self.assertEqual(Player.objects.count(), 2)

    def test_join_active_game(self):
        """
        Verify that attempting to join a game session with status 'active' fails and does not create a player.
        
        Ensures the join attempt returns an appropriate error message and no new player is added to the session.
        """
        self.game_session.status = 'active'
        self.game_session.save()

        response = self.client.post(reverse('game_sessions:join_game'), {
            'game_code': self.game_session.game_code,
            'player_name': 'Test Player'
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cannot join this game. It may be full or already started')

        # No player should be created
        self.assertEqual(Player.objects.count(), 0)

    def test_multiple_players_joining(self):
        """
        Verifies that multiple players can join the same game session using separate clients, and that both players are created and counted correctly.
        """
        # First player
        response1 = self.client.post(reverse('game_sessions:join_game'), {
            'game_code': self.game_session.game_code,
            'player_name': 'Player 1'
        })
        self.assertEqual(response1.status_code, 302)

        # Second player (using different client to simulate different session)
        client2 = Client()
        response2 = client2.post(reverse('game_sessions:join_game'), {
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
        """
        Tests that a WebSocket connection to the game endpoint can be established and receives the initial game state sync message with expected fields.
        """
        communicator = WebsocketCommunicator(
            GameConsumer.as_asgi(),
            f"/ws/game/{self.game_session.game_code}/"
        )

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # Should receive initial game state
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'game_state_sync')
        self.assertIn('data', response)

        game_data = response['data']
        self.assertEqual(game_data['game_status'], 'waiting')
        self.assertEqual(game_data['player_count'], 0)
        self.assertIn('players', game_data)

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
        """
        Tests that the WebSocket connection receives broadcasted game update messages, such as player join notifications, for the associated game session.
        """
        communicator = WebsocketCommunicator(
            GameConsumer.as_asgi(),
            f"/ws/game/{self.game_session.game_code}/"
        )

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # Consume initial game state
        initial_response = await communicator.receive_json_from()
        self.assertEqual(initial_response['type'], 'game_state_sync')

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
        """
        Verifies that starting a game via the start endpoint succeeds, updates the game session status to 'active', sets the start time, and returns a success response.
        """
        url = reverse('game_sessions:start_game', kwargs={'game_code': self.game_session.game_code})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)

        # Check response is JSON
        data = response.json()
        self.assertIn('status', data)
        self.assertEqual(data['status'], 'success')

        # Check game status changed
        self.game_session.refresh_from_db()
        self.assertEqual(self.game_session.status, 'active')
        self.assertIsNotNone(self.game_session.started_at)

    def test_start_game_no_players(self):
        """
        Verify that attempting to start a game session with no players returns a 400 error and leaves the session in the 'waiting' state.
        """
        # Remove the player
        self.player.delete()

        url = reverse('game_sessions:start_game', kwargs={'game_code': self.game_session.game_code})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('No players', data['error'])

        # Game should still be waiting
        self.game_session.refresh_from_db()
        self.assertEqual(self.game_session.status, 'waiting')

    def test_start_already_active_game(self):
        """
        Test that attempting to start a game session that is already active returns a 400 response with an appropriate error message.
        """
        self.game_session.status = 'active'
        self.game_session.save()

        url = reverse('game_sessions:start_game', kwargs={'game_code': self.game_session.game_code})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('not in waiting state', data['error'])
