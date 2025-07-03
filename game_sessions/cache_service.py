"""
Cache Service for Quiz Game

Manages all caching operations to reduce database load and improve real-time performance.
Handles game state, player data, answers, and scores in Redis cache.
"""

import logging
from typing import Dict, List, Optional, Any
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger('game_sessions.cache')


class GameCacheService:
    """Service for managing game-related cache operations"""
    
    def __init__(self, game_code: str):
        self.game_code = game_code
        self.base_key = f'game_{game_code}'
    
    # Game State Caching
    
    def cache_game_state(self, game_session, connected_players_data: List[Dict]) -> None:
        """Cache current game state to reduce database queries"""
        game_state = {
            'status': game_session.status,
            'current_round_number': game_session.current_round_number,
            'is_round_active': game_session.is_round_active,
            'player_count': len(connected_players_data),
            'players': connected_players_data,
            'max_players': game_session.max_players,
            'updated_at': timezone.now().timestamp()
        }
        
        cache_key = f'{self.base_key}_state'
        cache.set(cache_key, game_state, timeout=300)  # 5 minutes
        logger.debug(f"Cached game state for {self.game_code}: {game_state['status']}, {game_state['player_count']} players")
    
    def get_cached_game_state(self) -> Optional[Dict]:
        """Get cached game state to avoid database queries"""
        cache_key = f'{self.base_key}_state'
        return cache.get(cache_key)
    
    def invalidate_game_state(self) -> None:
        """Invalidate cached game state when it changes"""
        cache_key = f'{self.base_key}_state'
        cache.delete(cache_key)
        logger.debug(f"Invalidated game state cache for {self.game_code}")
    
    # Player Answer Caching (Enhanced)
    
    def cache_player_answer(self, round_number: int, player_id: int, answer_text: str) -> None:
        """Cache player answer with extended duration"""
        cache_key = f'{self.base_key}_round_{round_number}_answers'
        cached_answers = cache.get(cache_key, {})
        cached_answers[str(player_id)] = answer_text
        
        # Extended timeout - keep answers cached longer
        cache.set(cache_key, cached_answers, timeout=1800)  # 30 minutes (was shorter)
        logger.debug(f"Cached answer for player {player_id} in round {round_number}: {answer_text[:20]}...")
    
    def get_cached_answers(self, round_number: int) -> Dict[str, str]:
        """Get all cached answers for a round"""
        cache_key = f'{self.base_key}_round_{round_number}_answers'
        return cache.get(cache_key, {})
    
    def clear_round_answers(self, round_number: int) -> None:
        """Clear cached answers for a round (after processing to DB)"""
        cache_key = f'{self.base_key}_round_{round_number}_answers'
        cache.delete(cache_key)
        logger.debug(f"Cleared cached answers for round {round_number}")
    
    # Live Score Caching
    
    def cache_live_scores(self, round_number: int, player_scores: Dict[int, Dict]) -> None:
        """Cache live scores during round for real-time updates"""
        cache_key = f'{self.base_key}_round_{round_number}_live_scores'
        cache.set(cache_key, player_scores, timeout=1800)  # 30 minutes
        logger.debug(f"Cached live scores for round {round_number}: {len(player_scores)} players")
    
    def get_live_scores(self, round_number: int) -> Dict[int, Dict]:
        """Get cached live scores for real-time display"""
        cache_key = f'{self.base_key}_round_{round_number}_live_scores'
        return cache.get(cache_key, {})
    
    def update_player_live_score(self, round_number: int, player_id: int, score_data: Dict) -> None:
        """Update individual player's live score in cache"""
        cache_key = f'{self.base_key}_round_{round_number}_live_scores'
        live_scores = cache.get(cache_key, {})
        live_scores[player_id] = score_data
        cache.set(cache_key, live_scores, timeout=1800)
        logger.debug(f"Updated live score for player {player_id}: {score_data}")
    
    # Round State Caching
    
    def cache_round_state(self, round_number: int, round_info: Dict) -> None:
        """Cache round information to reduce round handler queries"""
        cache_key = f'{self.base_key}_round_{round_number}_state'
        round_state = {
            'round_info': round_info,
            'started_at': timezone.now().timestamp(),
            'is_active': True
        }
        cache.set(cache_key, round_state, timeout=1800)  # 30 minutes
        logger.debug(f"Cached round state for round {round_number}: {round_info.get('round_type')}")
    
    def get_cached_round_state(self, round_number: int) -> Optional[Dict]:
        """Get cached round state to avoid handler queries"""
        cache_key = f'{self.base_key}_round_{round_number}_state'
        return cache.get(cache_key)
    
    def mark_round_ended(self, round_number: int) -> None:
        """Mark round as ended in cache"""
        cache_key = f'{self.base_key}_round_{round_number}_state'
        round_state = cache.get(cache_key, {})
        if round_state:
            round_state['is_active'] = False
            round_state['ended_at'] = timezone.now().timestamp()
            cache.set(cache_key, round_state, timeout=1800)
            logger.debug(f"Marked round {round_number} as ended in cache")
    
    # Bulk Cache Operations
    
    def clear_game_cache(self) -> None:
        """Clear all cache entries for this game"""
        patterns = [
            f'{self.base_key}_state',
            f'{self.base_key}_round_*_answers',
            f'{self.base_key}_round_*_live_scores',
            f'{self.base_key}_round_*_state'
        ]
        
        # Note: Django cache doesn't have pattern deletion, so we'll track keys
        # For now, clear known keys individually
        cache.delete_many([
            f'{self.base_key}_state',
        ])
        logger.info(f"Cleared cache for game {self.game_code}")


class PlayerCacheService:
    """Service for managing player-related cache operations"""
    
    @staticmethod
    def cache_connected_players(game_code: str, players_data: List[Dict]) -> None:
        """Cache list of connected players to reduce database queries"""
        cache_key = f'game_{game_code}_connected_players'
        cache.set(cache_key, players_data, timeout=300)  # 5 minutes
        logger.debug(f"Cached {len(players_data)} connected players for game {game_code}")
    
    @staticmethod
    def get_cached_connected_players(game_code: str) -> Optional[List[Dict]]:
        """Get cached connected players list"""
        cache_key = f'game_{game_code}_connected_players'
        return cache.get(cache_key)
    
    @staticmethod
    def invalidate_connected_players(game_code: str) -> None:
        """Invalidate cached players list when it changes"""
        cache_key = f'game_{game_code}_connected_players'
        cache.delete(cache_key)
        logger.debug(f"Invalidated connected players cache for game {game_code}")
    
    @staticmethod
    def cache_player_session(game_code: str, player_id: int, session_data: Dict) -> None:
        """Cache player session data for reconnection"""
        cache_key = f'game_{game_code}_player_{player_id}_session'
        cache.set(cache_key, session_data, timeout=3600)  # 1 hour
        logger.debug(f"Cached session data for player {player_id}")
    
    @staticmethod
    def get_cached_player_session(game_code: str, player_id: int) -> Optional[Dict]:
        """Get cached player session for reconnection"""
        cache_key = f'game_{game_code}_player_{player_id}_session'
        return cache.get(cache_key)


class ScoreCacheService:
    """Service for managing score-related cache operations"""
    
    @staticmethod
    def cache_leaderboard(game_code: str, round_number: int, leaderboard_data: List[Dict]) -> None:
        """Cache current leaderboard to reduce score calculations"""
        cache_key = f'game_{game_code}_round_{round_number}_leaderboard'
        cache.set(cache_key, leaderboard_data, timeout=600)  # 10 minutes
        logger.debug(f"Cached leaderboard for game {game_code} round {round_number}: {len(leaderboard_data)} players")
    
    @staticmethod
    def get_cached_leaderboard(game_code: str, round_number: int) -> Optional[List[Dict]]:
        """Get cached leaderboard"""
        cache_key = f'game_{game_code}_round_{round_number}_leaderboard'
        return cache.get(cache_key)
    
    @staticmethod
    def invalidate_leaderboard(game_code: str, round_number: int) -> None:
        """Invalidate leaderboard cache when scores change"""
        cache_key = f'game_{game_code}_round_{round_number}_leaderboard'
        cache.delete(cache_key)
        logger.debug(f"Invalidated leaderboard cache for game {game_code} round {round_number}")


# Convenience Functions

def get_game_cache(game_code: str) -> GameCacheService:
    """Get a GameCacheService instance for the specified game"""
    return GameCacheService(game_code)

def invalidate_all_game_cache(game_code: str) -> None:
    """Invalidate all cache entries for a game"""
    game_cache = GameCacheService(game_code)
    game_cache.clear_game_cache()
    PlayerCacheService.invalidate_connected_players(game_code)