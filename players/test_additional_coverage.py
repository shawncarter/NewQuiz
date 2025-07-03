"""
Additional tests to improve coverage for the players app.
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.http import JsonResponse
from unittest.mock import patch, MagicMock

from game_sessions.models import GameSession, GameType, GameConfiguration
from players.models import Player, PlayerAnswer
# Import available views
from players.views import player_lobby, player_game


class PlayerViewsTest(TestCase):
    """Test player views functionality"""

    def setUp(self):
        """
        Initializes test data for player-related view tests, including a game type, game session, configuration, and player instance.
        """
        self.client = Client()
        self.game_type = GameType.objects.create(
            name="Flower, Fruit & Veg",
            description="Test description"
        )
        self.game_session = GameSession.objects.create()
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type
        )
        self.player = Player.objects.create(
            name="Test Player",
            game_session=self.game_session
        )

    def test_player_lobby_view(self):
        """
        Tests that the player lobby view returns a 200 response and displays the correct game code and player name for a valid game session and player.
        """
        url = reverse('players:player_lobby_with_id', kwargs={
            'game_code': self.game_session.game_code,
            'player_id': self.player.id
        })
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.game_session.game_code)
        self.assertContains(response, self.player.name)

    def test_player_lobby_invalid_game(self):
        """
        Verifies that accessing the player lobby view with an invalid game code returns a 404 response.
        """
        url = reverse('players:player_lobby_with_id', kwargs={
            'game_code': 'INVALID',
            'player_id': self.player.id
        })
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 404)

    def test_player_lobby_invalid_player(self):
        """
        Tests that accessing the player lobby view with an invalid player ID returns a 404 response.
        """
        url = reverse('players:player_lobby_with_id', kwargs={
            'game_code': self.game_session.game_code,
            'player_id': 999
        })
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 404)

    def test_player_lobby_redirect_when_active(self):
        """
        Verifies that the player lobby view redirects to the game view when the game session is active.
        """
        self.game_session.status = 'active'
        self.game_session.save()

        url = reverse('players:player_lobby_with_id', kwargs={
            'game_code': self.game_session.game_code,
            'player_id': self.player.id
        })

        response = self.client.get(url)

        # Should redirect to game view
        self.assertEqual(response.status_code, 302)
        expected_url = reverse('players:player_game_with_id', kwargs={
            'game_code': self.game_session.game_code,
            'player_id': self.player.id
        })
        self.assertRedirects(response, expected_url)

    def test_player_lobby_invalid_player_redirects(self):
        """
        Verify that accessing the player lobby with an invalid player ID redirects to the join game page instead of returning a 404 error.
        """
        url = reverse('players:player_lobby_with_id', kwargs={
            'game_code': self.game_session.game_code,
            'player_id': 999
        })

        response = self.client.get(url)

        # Should redirect to join game (not 404)
        self.assertEqual(response.status_code, 302)
        expected_url = reverse('game_sessions:join_game')
        self.assertRedirects(response, expected_url)

    def test_player_game_view(self):
        """
        Tests that the player game view returns a 200 response and displays the player's name when the game session is active.
        """
        self.game_session.status = 'active'
        self.game_session.current_round_number = 1
        self.game_session.save()

        url = reverse('players:player_game_with_id', kwargs={
            'game_code': self.game_session.game_code,
            'player_id': self.player.id
        })

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.player.name)


class PlayerModelTest(TestCase):
    """Test Player model edge cases"""

    def setUp(self):
        """
        Set up a test game session and player instance for use in Player model tests.
        """
        self.game_session = GameSession.objects.create()
        self.player = Player.objects.create(
            name="Test Player",
            game_session=self.game_session
        )

    def test_player_string_representation(self):
        """
        Tests that the string representation of a Player instance includes the player's name and associated game code.
        """
        expected = f"Test Player in {self.game_session.game_code}"
        self.assertEqual(str(self.player), expected)

    def test_player_total_score_property(self):
        """
        Tests that the Player model's total_score property correctly reflects the sum of points awarded to the player.
        """
        # Initially should be 0
        self.assertEqual(self.player.total_score, 0)
        
        # Award some points
        self.player.award_points(10, "test", 1)
        self.assertEqual(self.player.total_score, 10)

    def test_player_answers_relationship(self):
        """
        Verifies that the Player model's answers relationship correctly tracks associated PlayerAnswer instances.
        """
        # Initially should have no answers
        self.assertEqual(self.player.answers.count(), 0)

        # Create an answer
        answer = PlayerAnswer.objects.create(
            player=self.player,
            round_number=1,
            answer_text="Rose"
        )

        # Now should have one answer
        self.assertEqual(self.player.answers.count(), 1)
        self.assertEqual(self.player.answers.first(), answer)


class PlayerAnswerModelTest(TestCase):
    """Test PlayerAnswer model functionality"""

    def setUp(self):
        """
        Set up a test game session and player instance for use in Player model tests.
        """
        self.game_session = GameSession.objects.create()
        self.player = Player.objects.create(
            name="Test Player",
            game_session=self.game_session
        )

    def test_player_answer_creation(self):
        """
        Verifies that a PlayerAnswer instance can be created with all fields set and that its attributes match the expected values.
        """
        answer = PlayerAnswer.objects.create(
            player=self.player,
            round_number=1,
            answer_text="Rose",
            points_awarded=10,
            is_valid=True,
            is_unique=True
        )

        self.assertEqual(answer.player, self.player)
        self.assertEqual(answer.round_number, 1)
        self.assertEqual(answer.answer_text, "Rose")
        self.assertTrue(answer.is_valid)
        self.assertTrue(answer.is_unique)
        self.assertEqual(answer.points_awarded, 10)

    def test_player_answer_string_representation(self):
        """
        Verify that the string representation of a PlayerAnswer instance includes the player name, answer text, and round number in the expected format.
        """
        answer = PlayerAnswer.objects.create(
            player=self.player,
            round_number=1,
            answer_text="Rose"
        )

        expected = f"Test Player: Rose (Round 1)"
        self.assertEqual(str(answer), expected)

    def test_player_answer_defaults(self):
        """
        Verify that a newly created PlayerAnswer instance has the correct default values for validity, uniqueness, points awarded, and submission timestamp.
        """
        answer = PlayerAnswer.objects.create(
            player=self.player,
            round_number=1,
            answer_text="Rose"
        )

        self.assertTrue(answer.is_valid)  # Default is True
        self.assertFalse(answer.is_unique)  # Default is False
        self.assertEqual(answer.points_awarded, 0)
        self.assertIsNotNone(answer.submitted_at)

    def test_player_answer_validation_fields(self):
        """
        Verifies that the validation and uniqueness fields of a PlayerAnswer can be updated and saved correctly.
        """
        answer = PlayerAnswer.objects.create(
            player=self.player,
            round_number=1,
            answer_text="Rose"
        )

        # Initially should be valid but not unique
        self.assertTrue(answer.is_valid)
        self.assertFalse(answer.is_unique)

        # Mark as unique and award points
        answer.is_unique = True
        answer.points_awarded = 10
        answer.save()

        self.assertTrue(answer.is_valid)
        self.assertTrue(answer.is_unique)
        self.assertEqual(answer.points_awarded, 10)


class PlayerServiceIntegrationTest(TestCase):
    """Integration tests for player-related services"""

    def setUp(self):
        """
        Initializes test data by creating a game type, game session, and associated game configuration for use in test cases.
        """
        self.game_type = GameType.objects.create(
            name="Flower, Fruit & Veg",
            description="Test description"
        )
        self.game_session = GameSession.objects.create()
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type
        )

    def test_multiple_players_joining(self):
        """
        Verifies that multiple players can successfully join the same game session and are correctly recorded in the database.
        """
        from game_sessions.services import PlayerService
        
        # First player joins
        result1 = PlayerService.join_game(
            self.game_session.game_code,
            "Player 1"
        )
        self.assertTrue(result1['success'])
        
        # Second player joins
        result2 = PlayerService.join_game(
            self.game_session.game_code,
            "Player 2"
        )
        self.assertTrue(result2['success'])
        
        # Check both players exist
        self.assertEqual(Player.objects.filter(game_session=self.game_session).count(), 2)

    def test_player_reconnection_flow(self):
        """
        Tests that a player who disconnects from a game session can successfully reconnect using the same name, retaining their original player ID and connection status.
        """
        from game_sessions.services import PlayerService
        
        # Player joins initially
        result1 = PlayerService.join_game(
            self.game_session.game_code,
            "Test Player"
        )
        self.assertTrue(result1['success'])
        player_id = result1['player'].id
        
        # Player "disconnects"
        player = Player.objects.get(id=player_id)
        player.disconnect()
        
        # Player rejoins with same name
        result2 = PlayerService.join_game(
            self.game_session.game_code,
            "Test Player"
        )
        self.assertTrue(result2['success'])
        
        # Should be the same player, now reconnected
        self.assertEqual(result2['player'].id, player_id)
        self.assertTrue(result2['player'].is_connected)


class URLPatternsTest(TestCase):
    """Test URL patterns for players app"""

    def setUp(self):
        """
        Set up a test game session and player instance for use in Player model tests.
        """
        self.game_session = GameSession.objects.create()
        self.player = Player.objects.create(
            name="Test Player",
            game_session=self.game_session
        )

    def test_all_player_urls_resolve(self):
        """
        Verifies that all key player-related URL patterns resolve to valid paths.
        
        Ensures that reversing each player-related URL name with appropriate parameters returns a non-null URL that starts with '/'.
        """
        urls_to_test = [
            ('players:player_lobby_with_id', {
                'game_code': self.game_session.game_code,
                'player_id': self.player.id
            }),
            ('players:player_game_with_id', {
                'game_code': self.game_session.game_code,
                'player_id': self.player.id
            }),
            ('players:player_lobby', {
                'game_code': self.game_session.game_code,
            }),
            ('players:player_game', {
                'game_code': self.game_session.game_code,
            }),
        ]

        for url_name, kwargs in urls_to_test:
            with self.subTest(url=url_name):
                url = reverse(url_name, kwargs=kwargs)
                self.assertIsNotNone(url)
                self.assertTrue(url.startswith('/'))
