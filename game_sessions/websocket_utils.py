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


def broadcast_round_started(game_session, round_info):
    """Broadcast that a round has started"""
    # Map legacy round types for WebSocket compatibility
    mapped_round_type = round_info['round_type']
    if mapped_round_type == 'starts_with':
        mapped_round_type = 'flower_fruit_veg'
    
    data = {
        'round_number': round_info['round_number'],
        'total_time': game_session.configuration.round_time_seconds,
        'started_at': round_info['started_at'].isoformat() if round_info['started_at'] else None,
        'round_type': mapped_round_type,  # Send the mapped round type
        'is_active': True,
        'time_remaining': game_session.configuration.round_time_seconds
    }

    # Handle both new and legacy round types for WebSocket compatibility
    round_type = round_info['round_type']
    if round_type == 'starts_with':
        round_type = 'flower_fruit_veg'
    
    if round_type == 'flower_fruit_veg':
        data.update({
            'prompt': f"A {round_info['category'].name.lower()} that starts with '{round_info['prompt_letter']}'",
            'letter': round_info['prompt_letter'],
            'category': round_info['category'].name,
        })
    elif round_info['round_type'] == 'multiple_choice':
        data.update({
            'question_text': round_info['question_text'],
            'choices': round_info['choices'],
            'category': round_info['category'],
            'correct_answer': round_info.get('correct_answer'),  # Include for GM screen
            'is_ai_generated': round_info.get('is_ai_generated', False),  # Include for AI/DB badge
        })
    elif round_info['round_type'] == 'mastermind':
        # MasterMind has different states with different data structures
        mastermind_data = {
            'state': round_info.get('state', 'waiting_for_player_selection'),
            'phase': round_info.get('phase'),
            'current_player': round_info.get('current_player'),
            'current_player_index': round_info.get('current_player_index'),
            'total_players': round_info.get('total_players'),
            'current_question_index': round_info.get('current_question_index'),
            'questions_per_player': round_info.get('questions_per_player'),
            'available_players': round_info.get('available_players'),
            'completed_players': round_info.get('completed_players'),
            'message': round_info.get('message'),
        }
        
        # Only add question-related fields if we have a question (playing state)
        if round_info.get('question_text'):
            mastermind_data.update({
                'question_text': round_info['question_text'],
                'choices': round_info['choices'],
                'category': round_info['category'],
                'correct_answer': round_info.get('correct_answer'),
                'is_ai_generated': round_info.get('is_ai_generated', False),
                'rapid_fire_mode': round_info.get('rapid_fire_mode', False),
                'all_questions': round_info.get('all_questions', []),
            })
        
        data.update(mastermind_data)

    broadcast_to_game(game_session.game_code, 'round_started', data)


def broadcast_round_ended(game_session, round_info, answer_data=None):
    """Broadcast that a round has ended"""
    data = {
        'round_number': round_info['round_number'],
        'round_type': round_info['round_type'],
        'is_final_round': round_info['round_number'] >= game_session.configuration.num_rounds
    }

    if answer_data:
        data['answers'] = answer_data
    
    # Add correct answer for multiple choice questions
    if round_info['round_type'] == 'multiple_choice':
        data['correct_answer'] = round_info.get('correct_answer')
    elif round_info['round_type'] == 'mastermind':
        # Add MasterMind-specific data
        data.update({
            'state': round_info.get('state'),
            'phase': round_info.get('phase'),
            'current_player': round_info.get('current_player'),
            'correct_answer': round_info.get('correct_answer')
        })

    broadcast_to_game(game_session.game_code, 'round_ended', data)


def broadcast_timer_update(game_code, time_remaining):
    """Broadcast timer update to all clients"""
    data = {
        'time_remaining': time_remaining
    }
    
    broadcast_to_game(game_code, 'timer_update', data)


def broadcast_player_results(game_session, round_info, answers):
    """Broadcast individual results to each player"""
    from players.models import Player, PlayerAnswer
    
    logger.info(f"Broadcasting player results for game {game_session.game_code}, round {game_session.current_round_number}")
    logger.info(f"Round type: {round_info['round_type']}")
    
    # Get the correct answer for this round
    correct_answer = None
    if round_info['round_type'] == 'multiple_choice':
        correct_answer = round_info.get('correct_answer')
        logger.info(f"Correct answer for multiple choice: {correct_answer}")
    
    # Send personalized feedback to each player
    for player in game_session.players.filter(is_connected=True):
        logger.info(f"Processing result for player {player.name} (ID: {player.id})")
        
        # Find this player's answer for the current round
        player_answer = PlayerAnswer.objects.filter(
            player=player,
            round_number=game_session.current_round_number
        ).first()
        
        logger.info(f"Player answer found: {player_answer.answer_text if player_answer else 'None'}")
        
        if player_answer:
            # Player submitted an answer
            if round_info['round_type'] == 'multiple_choice':
                if player_answer.is_valid and player_answer.points_awarded > 0:
                    # Correct answer
                    message = f"🎉 Correct! You earned {player_answer.points_awarded} points."
                    if player.correct_answer_streak > 1:
                        message += f" ({player.correct_answer_streak} answer streak!)"
                    message += f"\n\nThe correct answer was: {correct_answer}"
                    message += f"\nYour answer: {player_answer.answer_text}"
                else:
                    # Incorrect answer
                    message = f"❌ Incorrect. The correct answer was: {correct_answer}"
                    message += f"\n\nYour answer: {player_answer.answer_text}"
            else:
                # Starts with round
                if player_answer.is_unique:
                    message = f"🌟 Unique answer! You earned {player_answer.points_awarded} points."
                elif player_answer.is_valid and player_answer.points_awarded > 0:
                    message = f"✅ Valid answer! You earned {player_answer.points_awarded} points."
                else:
                    message = f"❌ Invalid answer. No points awarded."
                message += f"\n\nYour answer: {player_answer.answer_text}"
        else:
            # Player didn't submit an answer
            message = "⏰ No answer submitted this round."
        
        # Broadcast to this specific player
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        player_group = f'player_{player.id}'
        result_data = {
            'round_number': game_session.current_round_number,
            'message': message,
            'points_earned': player_answer.points_awarded if player_answer else 0,
            'is_correct': player_answer.is_valid if player_answer else False,
            'correct_answer': correct_answer if round_info['round_type'] == 'multiple_choice' else None,
            'player_answer': player_answer.answer_text if player_answer else None,
            'round_type': round_info['round_type']
        }
        
        logger.info(f"Sending player result to group {player_group}: {result_data}")
        
        channel_layer = get_channel_layer()
        try:
            async_to_sync(channel_layer.group_send)(
                player_group,
                {
                    'type': 'player_result',
                    'data': result_data
                }
            )
            logger.info(f"Successfully sent player_result to {player_group}")
        except Exception as e:
            logger.error(f"Failed to send player_result to {player_group}: {e}")


def broadcast_individual_player_result(game_session, player, answer, points_awarded, is_valid):
    """Send individual result feedback to a specific player when their answer is validated"""
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    # Get round info for context
    round_info = game_session.get_current_round_info()
    if not round_info:
        logger.error(f"Could not get round info for individual player result")
        return
    
    # Create personalized message
    if round_info['round_type'] == 'flower_fruit_veg':
        if is_valid:
            if getattr(answer, 'is_unique', False):
                message = f"🌟 Unique answer! You earned {points_awarded} points."
            else:
                message = f"✅ Valid answer! You earned {points_awarded} points."
        else:
            message = f"❌ Invalid answer. No points awarded."
        message += f"\n\nYour answer: {answer.answer_text}"
    else:
        # Fallback for other round types
        message = f"{'✅ Correct!' if is_valid else '❌ Incorrect.'} You earned {points_awarded} points."
    
    player_group = f'player_{player.id}'
    result_data = {
        'round_number': game_session.current_round_number,
        'message': message,
        'points_earned': points_awarded,
        'is_correct': is_valid,
        'player_answer': answer.answer_text,
        'round_type': round_info['round_type']
    }
    
    logger.info(f"Sending individual validation result to player {player.name}: {result_data}")
    
    channel_layer = get_channel_layer()
    try:
        async_to_sync(channel_layer.group_send)(
            player_group,
            {
                'type': 'player_result',
                'data': result_data
            }
        )
        logger.info(f"Successfully sent individual player_result to {player_group}")
    except Exception as e:
        logger.error(f"Failed to send individual player_result to {player_group}: {e}")


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


def start_timer_broadcast(game_session, round_info, mastermind_duration=None):
    """Start broadcasting timer updates for a round"""
    import threading
    import time

    # Check if a timer thread is already running for this game
    thread_name = f"timer_{game_session.game_code}"
    existing_threads = [t for t in threading.enumerate() if t.name == thread_name]
    if existing_threads:
        logger.warning(f"Timer thread already running for game {game_session.game_code}, not starting new one")
        return

    # Capture the round_info in the closure
    captured_round_info = round_info

    def timer_worker():
        # Use MasterMind duration if provided, otherwise use default
        if mastermind_duration and captured_round_info and captured_round_info.get('round_type') == 'mastermind':
            total_time = mastermind_duration
            logger.info(f"Starting MasterMind timer for {total_time} seconds")
        else:
            total_time = game_session.configuration.round_time_seconds
        start_time = timezone.now()

        while True:
            elapsed = (timezone.now() - start_time).total_seconds()
            time_remaining = max(0, total_time - elapsed)

            # Broadcast timer update
            broadcast_timer_update(game_session.game_code, int(time_remaining))
            
            # Log timer updates every 10 seconds for debugging
            if int(time_remaining) % 10 == 0 or time_remaining <= 5:
                logger.info(f"Timer update for game {game_session.game_code}: {int(time_remaining)} seconds remaining")

            # Stop if time is up and automatically end the round
            if time_remaining <= 0:
                # Automatically end the round when timer expires
                logger.info(f"Timer expired for game {game_session.game_code}, automatically ending round")

                # Import here to avoid circular imports
                from .models import GameSession
                from players.models import PlayerAnswer

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
                                        # Use round handler to create appropriate PlayerAnswer
                                        from .round_handlers import get_round_handler
                                        round_handler = get_round_handler(current_game, current_game.current_round_number)
                                        round_handler.create_player_answer(player, answer_text.strip())
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

                            # Perform automatic scoring using round handler
                            from .round_handlers import get_round_handler
                            round_handler = get_round_handler(current_game, current_game.current_round_number)
                            round_handler.perform_automatic_scoring(answers)

                            # Send individual results to each player only if round type supports immediate feedback
                            # (same logic as manual end round)
                            if round_handler.should_send_immediate_feedback():
                                broadcast_player_results(current_game, round_info, answers)

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
    timer_thread = threading.Thread(target=timer_worker, name=thread_name)
    timer_thread.daemon = True
    timer_thread.start()
    logger.info(f"Started timer thread for game {game_session.game_code} with {game_session.configuration.round_time_seconds} seconds")
