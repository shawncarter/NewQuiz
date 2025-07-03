from django.test import TestCase
from game_sessions.models import GameSession, GameType, GameCategory, GameConfiguration
from .models import Player, PlayerAnswer


class PlayerModelTest(TestCase):
    """Test Player model functionality"""

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

        self.game_session = GameSession.objects.create()
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type,
            num_rounds=5,
            round_time_seconds=30
        )
        self.config.categories.add(self.category)

    def test_player_creation(self):
        """Test creating a new player"""
        player = Player.objects.create(
            name="Test Player",
            game_session=self.game_session,
            session_key="test_session_123"
        )

        self.assertEqual(player.name, "Test Player")
        self.assertEqual(player.game_session, self.game_session)
        self.assertEqual(player.session_key, "test_session_123")
        self.assertTrue(player.is_connected)
        self.assertIsNotNone(player.joined_at)

    def test_player_string_representation(self):
        """Test player string representation"""
        player = Player.objects.create(
            name="Test Player",
            game_session=self.game_session,
            session_key="test_session"
        )

        expected = f"Test Player in {self.game_session.game_code}"
        self.assertEqual(str(player), expected)

    def test_player_disconnect_reconnect(self):
        """Test player disconnect and reconnect functionality"""
        player = Player.objects.create(
            name="Test Player",
            game_session=self.game_session,
            session_key="test_session"
        )

        # Test disconnect
        player.disconnect()
        self.assertFalse(player.is_connected)

        # Test reconnect
        player.reconnect()
        self.assertTrue(player.is_connected)

    def test_unique_session_per_game(self):
        """Test that multiple players can have same session key in same game (for development)"""
        # Create first player
        player1 = Player.objects.create(
            name="Player 1",
            game_session=self.game_session,
            session_key="same_session"
        )

        # Create second player with same session key in same game (should work for development)
        player2 = Player.objects.create(
            name="Player 2",
            game_session=self.game_session,
            session_key="same_session"
        )

        # Both players should exist
        self.assertEqual(Player.objects.filter(game_session=self.game_session).count(), 2)

        # But should work in different game
        game_session2 = GameSession.objects.create()
        player2 = Player.objects.create(
            name="Player 2",
            game_session=game_session2,
            session_key="same_session"
        )

        self.assertNotEqual(player1.game_session, player2.game_session)
        self.assertEqual(player1.session_key, player2.session_key)


class PlayerAnswerModelTest(TestCase):
    """Test PlayerAnswer model functionality"""

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

        self.game_session = GameSession.objects.create()
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type,
            num_rounds=5,
            round_time_seconds=30
        )
        self.config.categories.add(self.category)

        self.player = Player.objects.create(
            name="Test Player",
            game_session=self.game_session,
            session_key="test_session"
        )

    def test_player_answer_creation(self):
        """Test creating a player answer"""
        answer = PlayerAnswer.objects.create(
            player=self.player,
            round_number=1,
            answer_text="Rose"
        )

        self.assertEqual(answer.player, self.player)
        self.assertEqual(answer.round_number, 1)
        self.assertEqual(answer.answer_text, "Rose")
        self.assertEqual(answer.points_awarded, 0)
        self.assertTrue(answer.is_valid)
        self.assertFalse(answer.is_unique)
        self.assertIsNotNone(answer.submitted_at)

    def test_player_answer_string_representation(self):
        """Test player answer string representation"""
        answer = PlayerAnswer.objects.create(
            player=self.player,
            round_number=2,
            answer_text="Tulip"
        )

        expected = f"Test Player: Tulip (Round 2)"
        self.assertEqual(str(answer), expected)

    def test_unique_answer_per_round(self):
        """Test that players can only have one answer per round"""
        from django.db import IntegrityError, transaction

        # Create first answer
        answer1 = PlayerAnswer.objects.create(
            player=self.player,
            round_number=1,
            answer_text="Rose"
        )

        # Try to create second answer for same round
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PlayerAnswer.objects.create(
                    player=self.player,
                    round_number=1,
                    answer_text="Tulip"
                )

        # But should work for different round
        answer2 = PlayerAnswer.objects.create(
            player=self.player,
            round_number=2,
            answer_text="Tulip"
        )

        self.assertEqual(answer1.round_number, 1)
        self.assertEqual(answer2.round_number, 2)

    def test_answer_scoring(self):
        """Test answer scoring functionality"""
        answer = PlayerAnswer.objects.create(
            player=self.player,
            round_number=1,
            answer_text="Rose",
            points_awarded=10,
            is_unique=True
        )

        self.assertEqual(answer.points_awarded, 10)
        self.assertTrue(answer.is_unique)
        self.assertTrue(answer.is_valid)
