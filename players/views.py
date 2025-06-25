from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from game_sessions.models import GameSession
from .models import Player, PlayerAnswer


def player_lobby(request, game_code):
    """Player lobby view - waiting for game to start"""
    game_session = get_object_or_404(GameSession, game_code=game_code)

    # If game is active, redirect to game interface
    if game_session.status == 'active':
        return redirect('players:player_game_with_id', game_code=game_code, player_id=player.id)

    # Get the current player based on session key
    session_key = request.session.session_key
    if not session_key:
        # Redirect to join page if no session
        return redirect('game_sessions:join_game')

    try:
        player = Player.objects.get(
            game_session=game_session,
            session_key=session_key
        )
    except Player.DoesNotExist:
        # Redirect to join page if player not found
        return redirect('game_sessions:join_game')

    # Get all connected players for display
    players = game_session.players.filter(is_connected=True).order_by('joined_at')

    context = {
        'game_session': game_session,
        'player': player,
        'players': players,
        'player_count': players.count(),
    }
    return render(request, 'players/lobby.html', context)


def player_lobby_with_id(request, game_code, player_id):
    """Player lobby interface with player ID in URL"""
    game_session = get_object_or_404(GameSession, game_code=game_code)

    # If game is active or finished, redirect to game interface
    if game_session.status in ['active', 'finished']:
        return redirect('players:player_game_with_id', game_code=game_code, player_id=player_id)

    # Get the player by ID
    try:
        player = Player.objects.get(
            id=player_id,
            game_session=game_session,
            is_connected=True
        )
    except Player.DoesNotExist:
        # Redirect to join page if player not found
        return redirect('game_sessions:join_game')

    # Get all connected players for display
    players = game_session.players.filter(is_connected=True).order_by('joined_at')

    context = {
        'game_session': game_session,
        'player': player,
        'players': players,
        'player_count': players.count(),
    }
    return render(request, 'players/lobby.html', context)


@require_http_methods(["POST"])
def submit_answer(request, game_code):
    """Submit an answer for the current round"""
    game_session = get_object_or_404(GameSession, game_code=game_code)

    if game_session.status != 'active':
        return JsonResponse({'error': 'Game is not active'}, status=400)

    # Check if round is active using counter system
    if not game_session.is_round_active:
        return JsonResponse({'error': 'No active round'}, status=400)

    # Get player by ID (from POST data)
    player_id = request.POST.get('player_id', '').strip()
    if not player_id:
        return JsonResponse({'error': 'No player ID provided'}, status=400)

    try:
        player = Player.objects.get(
            id=int(player_id),
            game_session=game_session,
            is_connected=True
        )
    except (Player.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Player not found or not connected'}, status=404)

    # Get answer from request
    answer_text = request.POST.get('answer', '').strip()

    # Create or update answer using round_number
    answer, created = PlayerAnswer.objects.update_or_create(
        player=player,
        round_number=game_session.current_round_number,
        defaults={'answer_text': answer_text}
    )

    return JsonResponse({
        'status': 'success',
        'answer': answer_text,
        'created': created
    })


def player_game(request, game_code):
    """Player game interface during active game"""
    game_session = get_object_or_404(GameSession, game_code=game_code)

    # Get the current player based on session key
    session_key = request.session.session_key
    if not session_key:
        # Redirect to join page if no session
        return redirect('game_sessions:join_game')

    try:
        player = Player.objects.get(
            game_session=game_session,
            session_key=session_key
        )
    except Player.DoesNotExist:
        # Redirect to join page if player not found
        return redirect('game_sessions:join_game')

    # Get current round info using counter system
    current_round = game_session.get_current_round_info()

    # Get player's answer for current round if it exists
    player_answer = None
    if current_round and game_session.current_round_number > 0:
        try:
            player_answer = PlayerAnswer.objects.get(
                player=player,
                round_number=game_session.current_round_number
            )
        except PlayerAnswer.DoesNotExist:
            pass

    # Get game configuration
    try:
        config = game_session.configuration
    except:
        config = None

    context = {
        'game_session': game_session,
        'player': player,
        'current_round': current_round,
        'player_answer': player_answer,
        'config': config,
    }

    if game_session.status == 'active':
        return render(request, 'players/game.html', context)
    else:
        # If game is not active, redirect to lobby
        return redirect('players:player_lobby_with_id', game_code=game_code, player_id=player.id)


def player_game_with_id(request, game_code, player_id):
    """Player game interface with player ID in URL"""
    game_session = get_object_or_404(GameSession, game_code=game_code)

    # Get the player by ID
    try:
        player = Player.objects.get(
            id=player_id,
            game_session=game_session,
            is_connected=True
        )
    except Player.DoesNotExist:
        # Redirect to join page if player not found
        return redirect('game_sessions:join_game')

    # Get current round info using counter system
    current_round = game_session.get_current_round_info()

    # Get player's answer for current round if it exists
    player_answer = None
    if current_round and game_session.current_round_number > 0:
        try:
            player_answer = PlayerAnswer.objects.get(
                player=player,
                round_number=game_session.current_round_number
            )
        except PlayerAnswer.DoesNotExist:
            pass

    # Get game configuration
    try:
        config = game_session.configuration
    except:
        config = None

    context = {
        'game_session': game_session,
        'player': player,
        'current_round': current_round,
        'player_answer': player_answer,
        'config': config,
    }

    # Always render game template for active/finished games
    if game_session.status in ['active', 'finished']:
        return render(request, 'players/game.html', context)
    else:
        # If game is not active, redirect to lobby
        return redirect('players:player_lobby_with_id', game_code=game_code, player_id=player_id)
