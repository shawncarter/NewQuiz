from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from game_sessions.models import GameSession
from .models import Player, PlayerAnswer


def player_lobby(request, game_code, player_id=None):
    """Player lobby view - waiting for game to start"""
    game_session = get_object_or_404(GameSession, game_code=game_code)

    # If game is active or finished, redirect to game interface
    if game_session.status in ['active', 'finished']:
        return redirect('players:player_game_with_id', game_code=game_code, player_id=player_id)

    # Get the player by ID or session key
    if player_id:
        try:
            player = Player.objects.get(
                id=player_id,
                game_session=game_session,
                is_connected=True
            )
        except Player.DoesNotExist:
            # Redirect to join page if player not found
            return redirect('game_sessions:join_game')
    else:
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





def player_game(request, game_code, player_id=None):
    """Player game interface during active game"""
    game_session = get_object_or_404(GameSession, game_code=game_code)

    # Get the player by ID or session key
    if player_id:
        try:
            player = Player.objects.get(
                id=player_id,
                game_session=game_session,
                is_connected=True
            )
        except Player.DoesNotExist:
            # Redirect to join page if player not found
            return redirect('game_sessions:join_game')
    else:
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

    # Always render game template for active/finished games
    if game_session.status in ['active', 'finished']:
        return render(request, 'players/game.html', context)
    else:
        # If game is not active, redirect to lobby
        return redirect('players:player_lobby_with_id', game_code=game_code, player_id=player_id)
