"""
Round Cache Service

Centralized caching strategy for round data and state management.
Provides consistent cache key naming and TTL management for round-related data.
"""

import logging
from typing import Dict, Any, Optional, List
from django.core.cache import cache

logger = logging.getLogger(__name__)


class RoundCacheService:
    """
    Centralized service for round-related caching operations.
    
    Provides consistent cache key naming, TTL management, and cache
    invalidation strategies for round data across the application.
    """
    
    # Cache key patterns
    ROUND_DATA_KEY = 'game_{game_code}_round_{round_number}_data'
    QUESTION_ID_KEY = 'game_{game_code}_round_{round_number}_question_id'
    ROUND_STATE_KEY = 'game_{game_code}_round_{round_number}_state'
    USED_LETTERS_KEY = 'game_{game_code}_used_letters'
    
    # Default TTL values (in seconds)
    ROUND_DATA_TTL = 3600  # 1 hour
    QUESTION_TTL = 3600    # 1 hour
    STATE_TTL = 1800       # 30 minutes
    LETTERS_TTL = 7200     # 2 hours
    
    def __init__(self, game_code: str):
        self.game_code = game_code
    
    def get_round_data(self, round_number: int) -> Optional[Dict[str, Any]]:
        """Get cached round data"""
        cache_key = self.ROUND_DATA_KEY.format(
            game_code=self.game_code, 
            round_number=round_number
        )
        return cache.get(cache_key)
    
    def set_round_data(self, round_number: int, round_data: Dict[str, Any], 
                      ttl: Optional[int] = None) -> bool:
        """Cache round data"""
        cache_key = self.ROUND_DATA_KEY.format(
            game_code=self.game_code, 
            round_number=round_number
        )
        ttl = ttl or self.ROUND_DATA_TTL
        
        try:
            cache.set(cache_key, round_data, timeout=ttl)
            logger.debug(f"Cached round data for game {self.game_code}, round {round_number}")
            return True
        except Exception as e:
            logger.error(f"Failed to cache round data: {e}")
            return False
    
    def get_question_id(self, round_number: int) -> Optional[int]:
        """Get cached question ID for multiple choice rounds"""
        cache_key = self.QUESTION_ID_KEY.format(
            game_code=self.game_code, 
            round_number=round_number
        )
        return cache.get(cache_key)
    
    def set_question_id(self, round_number: int, question_id: int, 
                       ttl: Optional[int] = None) -> bool:
        """Cache question ID for multiple choice rounds"""
        cache_key = self.QUESTION_ID_KEY.format(
            game_code=self.game_code, 
            round_number=round_number
        )
        ttl = ttl or self.QUESTION_TTL
        
        try:
            cache.set(cache_key, question_id, timeout=ttl)
            logger.debug(f"Cached question ID {question_id} for game {self.game_code}, round {round_number}")
            return True
        except Exception as e:
            logger.error(f"Failed to cache question ID: {e}")
            return False
    
    def get_round_state(self, round_number: int) -> Optional[Dict[str, Any]]:
        """Get cached round state information"""
        cache_key = self.ROUND_STATE_KEY.format(
            game_code=self.game_code, 
            round_number=round_number
        )
        return cache.get(cache_key)
    
    def set_round_state(self, round_number: int, state_data: Dict[str, Any], 
                       ttl: Optional[int] = None) -> bool:
        """Cache round state information"""
        cache_key = self.ROUND_STATE_KEY.format(
            game_code=self.game_code, 
            round_number=round_number
        )
        ttl = ttl or self.STATE_TTL
        
        try:
            cache.set(cache_key, state_data, timeout=ttl)
            logger.debug(f"Cached round state for game {self.game_code}, round {round_number}")
            return True
        except Exception as e:
            logger.error(f"Failed to cache round state: {e}")
            return False
    
    def get_used_letters(self) -> List[str]:
        """Get cached list of used letters"""
        cache_key = self.USED_LETTERS_KEY.format(game_code=self.game_code)
        return cache.get(cache_key, [])
    
    def set_used_letters(self, used_letters: List[str], 
                        ttl: Optional[int] = None) -> bool:
        """Cache list of used letters"""
        cache_key = self.USED_LETTERS_KEY.format(game_code=self.game_code)
        ttl = ttl or self.LETTERS_TTL
        
        try:
            cache.set(cache_key, used_letters, timeout=ttl)
            logger.debug(f"Cached used letters for game {self.game_code}: {used_letters}")
            return True
        except Exception as e:
            logger.error(f"Failed to cache used letters: {e}")
            return False
    
    def clear_round_cache(self, round_number: int) -> bool:
        """Clear all cached data for a specific round"""
        keys_to_clear = [
            self.ROUND_DATA_KEY.format(game_code=self.game_code, round_number=round_number),
            self.QUESTION_ID_KEY.format(game_code=self.game_code, round_number=round_number),
            self.ROUND_STATE_KEY.format(game_code=self.game_code, round_number=round_number)
        ]
        
        success = True
        for cache_key in keys_to_clear:
            try:
                cache.delete(cache_key)
                logger.debug(f"Cleared cache key: {cache_key}")
            except Exception as e:
                logger.error(f"Failed to clear cache key {cache_key}: {e}")
                success = False
        
        return success
    
    def clear_all_round_cache(self, max_rounds: int = 50) -> bool:
        """Clear all cached round data for this game"""
        success = True
        
        # Clear round-specific caches
        for round_number in range(1, max_rounds + 1):
            if not self.clear_round_cache(round_number):
                success = False
        
        # Clear game-wide caches
        game_wide_keys = [
            self.USED_LETTERS_KEY.format(game_code=self.game_code)
        ]
        
        for cache_key in game_wide_keys:
            try:
                cache.delete(cache_key)
                logger.debug(f"Cleared game-wide cache key: {cache_key}")
            except Exception as e:
                logger.error(f"Failed to clear game-wide cache key {cache_key}: {e}")
                success = False
        
        return success
    
    def get_cache_stats(self, max_rounds: int = 20) -> Dict[str, Any]:
        """Get statistics about cached data for debugging"""
        stats = {
            'game_code': self.game_code,
            'cached_rounds': [],
            'cached_questions': [],
            'cached_states': [],
            'has_used_letters': False
        }
        
        for round_number in range(1, max_rounds + 1):
            # Check round data cache
            round_data = self.get_round_data(round_number)
            if round_data:
                stats['cached_rounds'].append(round_number)
            
            # Check question cache
            question_id = self.get_question_id(round_number)
            if question_id:
                stats['cached_questions'].append(round_number)
            
            # Check state cache
            state_data = self.get_round_state(round_number)
            if state_data:
                stats['cached_states'].append(round_number)
        
        # Check used letters
        used_letters = self.get_used_letters()
        stats['has_used_letters'] = len(used_letters) > 0
        
        return stats