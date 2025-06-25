from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
import logging

logger = logging.getLogger('websockets')


def broadcast_to_game(game_code, message_type, data):
    """Broadcast a message to all clients connected to a game"""
    channel_layer = get_channel_layer()
    group_name = f'game_{game_code}'

    logger.info(f"Broadcasting {message_type} to group {group_name}: {data}")

    try:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': message_type,
                'data': data
            }
        )
        logger.info(f"Successfully broadcast {message_type} to {group_name}")
    except Exception as e:
        logger.error(f"Failed to broadcast {message_type} to {group_name}: {e}")
        # Retry once after a short delay
        import time
        time.sleep(0.1)
        try:
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': message_type,
                    'data': data
                }
            )
            logger.info(f"Successfully broadcast {message_type} to {group_name} on retry")
        except Exception as retry_e:
            logger.error(f"Failed to broadcast {message_type} to {group_name} on retry: {retry_e}")


def broadcast_round_started(game_session, round_obj):
    """Broadcast that a round has started"""
    data = {
        'round_number': round_obj['round_number'],
        'prompt': f"A {round_obj['category'].name.lower()} that starts with '{round_obj['prompt_letter']}'",
        'letter': round_obj['prompt_letter'],
        'category': round_obj['category'].name,
        'total_time': game_session.configuration.round_time_seconds,
        'started_at': round_obj['started_at'].isoformat() if round_obj['started_at'] else None,
        'current_round': {
            'round_number': round_obj['round_number'],
            'prompt': f"A {round_obj['category'].name.lower()} that starts with '{round_obj['prompt_letter']}'",
            'letter': round_obj['prompt_letter'],
            'category': round_obj['category'].name,
            'is_active': True,
            'time_remaining': game_session.configuration.round_time_seconds
        }
    }

    broadcast_to_game(game_session.game_code, 'round_started', data)


def broadcast_round_ended(game_session, round_obj, answers_data=None):
    """Broadcast that a round has ended"""
    data = {
        'round_number': round_obj['round_number'],
        'is_final_round': round_obj['round_number'] >= game_session.configuration.num_rounds
    }

    if answers_data:
        data['answers'] = answers_data

    broadcast_to_game(game_session.game_code, 'round_ended', data)


def broadcast_timer_update(game_code, time_remaining):
    """Broadcast timer update to all clients"""
    data = {
        'time_remaining': time_remaining
    }
    
    broadcast_to_game(game_code, 'timer_update', data)


def broadcast_score_update(game_session, player_name, points_awarded, reason="manual_validation"):
    """Broadcast score update to all clients"""
    # Find the player to get their ID and current score
    try:
        from players.models import Player
        player = Player.objects.get(game_session=game_session, name=player_name)
        
        data = {
            'player_name': player_name,
            'player_id': player.id,
            'points_awarded': points_awarded,
            'points': player.current_score,  # Total current score
            'reason': reason,
            'message': f'{player_name} received {points_awarded} points!'
        }
    except Player.DoesNotExist:
        # Fallback if player not found
        data = {
            'player_name': player_name,
            'points_awarded': points_awarded,
            'message': f'{player_name} received {points_awarded} points!'
        }

    broadcast_to_game(game_session.game_code, 'score_update', data)


def start_timer_broadcast(game_session, round_obj):
    """Start broadcasting timer updates for a round"""
    import threading
    import time

    def timer_worker():
        total_time = game_session.configuration.round_time_seconds
        start_time = timezone.now()

        while True:
            elapsed = (timezone.now() - start_time).total_seconds()
            time_remaining = max(0, total_time - elapsed)

            # Broadcast timer update
            broadcast_timer_update(game_session.game_code, int(time_remaining))

            # Stop if time is up and automatically end the round
            if time_remaining <= 0:
                # Automatically end the round when timer expires
                logger.info(f"Timer expired for game {game_session.game_code}, automatically ending round")

                # Import here to avoid circular imports
                from .models import GameSession
                from players.models import PlayerAnswer
                from .views import perform_automatic_scoring

                try:
                    # Refresh game session and check if round is still active
                    current_game = GameSession.objects.get(game_code=game_session.game_code)
                    if current_game.is_round_active:
                        # End the round
                        current_game.is_round_active = False
                        current_game.save()

                        # Get current round info
                        round_info = current_game.get_current_round_info()
                        if round_info:
                            # First, transfer cached answers to database (same logic as manual end_round)
                            from django.core.cache import cache
                            from players.models import PlayerAnswer, Player
                            
                            cache_key = f'game_{current_game.game_code}_round_{current_game.current_round_number}_answers'
                            cached_answers = cache.get(cache_key, {})
                            
                            # Create PlayerAnswer objects for any cached answers that don't exist in DB
                            for player_id_str, answer_text in cached_answers.items():
                                try:
                                    player_id = int(player_id_str)
                                    player = Player.objects.get(id=player_id, game_session=current_game)
                                    
                                    # Check if answer already exists in database
                                    existing_answer = PlayerAnswer.objects.filter(
                                        player=player,
                                        round_number=current_game.current_round_number
                                    ).first()
                                    
                                    if not existing_answer and answer_text.strip():
                                        # Create new answer object
                                        PlayerAnswer.objects.create(
                                            player=player,
                                            round_number=current_game.current_round_number,
                                            answer_text=answer_text.strip(),
                                            is_valid=True,  # Will be validated during scoring
                                            points_awarded=0
                                        )
                                        logger.info(f"Auto-end: Created PlayerAnswer for player {player.name}: {answer_text}")
                                except (ValueError, Player.DoesNotExist) as e:
                                    logger.warning(f"Auto-end: Could not create PlayerAnswer for player_id {player_id_str}: {e}")
                            
                            # Clear the cache for this round
                            cache.delete(cache_key)

                            # Now get all answers for this round from database
                            answers = PlayerAnswer.objects.filter(
                                player__game_session=current_game,
                                round_number=current_game.current_round_number
                            ).select_related('player').order_by('?')  # Random order

                            # Perform automatic scoring
                            perform_automatic_scoring(current_game, answers)

                            # Prepare answer data for broadcast
                            answer_data = []
                            for answer in answers:
                                answer_data.append({
                                    'player_name': answer.player.name,
                                    'answer_text': answer.answer_text,
                                    'points_awarded': answer.points_awarded,
                                    'is_valid': answer.is_valid,
                                    'is_unique': getattr(answer, 'is_unique', False),
                                })

                            # Broadcast round ended to all connected clients
                            broadcast_round_ended(current_game, round_info, answer_data)

                            logger.info(f"Round {current_game.current_round_number} automatically ended for game {game_session.game_code}")

                except Exception as e:
                    logger.error(f"Error automatically ending round for game {game_session.game_code}: {e}")

                break

            # Check if round is still active by refreshing game session from DB
            from .models import GameSession
            try:
                current_game = GameSession.objects.get(game_code=game_session.game_code)
                if not current_game.is_round_active:
                    break
            except GameSession.DoesNotExist:
                break

            time.sleep(1)  # Update every second

    # Start timer in background thread
    timer_thread = threading.Thread(target=timer_worker, name=f"timer_{game_session.game_code}")
    timer_thread.daemon = True
    timer_thread.start()
