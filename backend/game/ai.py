import random

from .rules import evaluate_move, key, opponent, validate_move


DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))


def inside(x, y, board_size=15):
    return 0 <= x < board_size and 0 <= y < board_size


def candidates(stones, board_size=15, radius=2):
    if not stones:
        center = board_size // 2
        return [{"x": center, "y": center}]
    occupied = {key(stone["x"], stone["y"]) for stone in stones}
    result = {}
    for stone in stones:
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                x = stone["x"] + dx
                y = stone["y"] + dy
                if inside(x, y, board_size) and key(x, y) not in occupied:
                    result[key(x, y)] = {"x": x, "y": y}
    return list(result.values())


def board_after(stones, x, y, color):
    board = {key(stone["x"], stone["y"]): stone["color"] for stone in stones}
    board[key(x, y)] = color
    return board


def line_shape_score(board, x, y, color, board_size=15):
    score = 0
    for dx, dy in DIRECTIONS:
        count = 1
        open_ends = 0
        for sign in (-1, 1):
            cx = x + dx * sign
            cy = y + dy * sign
            while inside(cx, cy, board_size) and board.get(key(cx, cy)) == color:
                count += 1
                cx += dx * sign
                cy += dy * sign
            if inside(cx, cy, board_size) and key(cx, cy) not in board:
                open_ends += 1
        if count >= 5:
            score += 5_000_000
        elif count == 4 and open_ends == 2:
            score += 900_000
        elif count == 4 and open_ends == 1:
            score += 260_000
        elif count == 3 and open_ends == 2:
            score += 95_000
        elif count == 3 and open_ends == 1:
            score += 18_000
        elif count == 2 and open_ends == 2:
            score += 7_000
        elif count == 2 and open_ends == 1:
            score += 1_200
        else:
            score += count * 90 + open_ends * 35
    return score


def center_score(x, y, board_size=15):
    center = (board_size - 1) / 2
    return max(0, 60 - int((abs(x - center) + abs(y - center)) * 5))


def legal_candidates(stones, board_size, color, rule_set, radius):
    return [
        move
        for move in candidates(stones, board_size, radius)
        if validate_move(stones, move["x"], move["y"], color, rule_set, board_size).ok
    ]


def safe_candidates(stones, board_size, color, rule_set, radius):
    legal = legal_candidates(stones, board_size, color, rule_set, radius)
    safe = [
        move
        for move in legal
        if not evaluate_move(stones, move["x"], move["y"], color, rule_set, board_size).forbidden
    ]
    return safe or legal


def immediate_winning_moves(stones, board_size, color, rule_set, radius=2):
    moves = []
    for move in safe_candidates(stones, board_size, color, rule_set, radius):
        result = evaluate_move(stones, move["x"], move["y"], color, rule_set, board_size)
        if result.winner == color:
            moves.append(move)
    return moves


def move_score(stones, move, color, rule_set, board_size):
    result = evaluate_move(stones, move["x"], move["y"], color, rule_set, board_size)
    if result.forbidden:
        return -8_000_000
    if result.winner == color:
        return 9_000_000
    other = opponent(color)
    attack_board = board_after(stones, move["x"], move["y"], color)
    defense_board = board_after(stones, move["x"], move["y"], other)
    attack = line_shape_score(attack_board, move["x"], move["y"], color, board_size)
    defense = line_shape_score(defense_board, move["x"], move["y"], other, board_size)
    next_stones = [*stones, {"x": move["x"], "y": move["y"], "color": color}]
    threat_count = len(immediate_winning_moves(next_stones, board_size, color, rule_set, 2))
    return attack * 1.28 + defense * 1.12 + threat_count * 360_000 + center_score(move["x"], move["y"], board_size)


def ordered_candidates(stones, board_size, color, rule_set, radius, limit=None):
    moves = safe_candidates(stones, board_size, color, rule_set, radius)
    moves = sorted(moves, key=lambda move: move_score(stones, move, color, rule_set, board_size), reverse=True)
    return moves[:limit] if limit else moves


def creates_double_threat(stones, move, board_size, color, rule_set):
    next_stones = [*stones, {"x": move["x"], "y": move["y"], "color": color}]
    return len(immediate_winning_moves(next_stones, board_size, color, rule_set, 2)) >= 2


def best_static_score(stones, board_size, color, rule_set):
    own = ordered_candidates(stones, board_size, color, rule_set, 2, 5)
    other = ordered_candidates(stones, board_size, opponent(color), rule_set, 2, 5)
    own_score = max((move_score(stones, move, color, rule_set, board_size) for move in own), default=0)
    other_score = max((move_score(stones, move, opponent(color), rule_set, board_size) for move in other), default=0)
    return own_score - other_score * 0.92


def hard_search_score(stones, move, board_size, ai_color, rule_set):
    player_color = opponent(ai_color)
    next_stones = [*stones, {"x": move["x"], "y": move["y"], "color": ai_color}]
    score = move_score(stones, move, ai_color, rule_set, board_size)
    if creates_double_threat(stones, move, board_size, ai_color, rule_set):
        score += 1_400_000

    player_wins = immediate_winning_moves(next_stones, board_size, player_color, rule_set, 2)
    if player_wins:
        score -= 2_800_000 * len(player_wins)

    replies = ordered_candidates(next_stones, board_size, player_color, rule_set, 2, 8)
    if replies:
        worst_reply = -10_000_000
        for reply in replies:
            after_reply = [*next_stones, {"x": reply["x"], "y": reply["y"], "color": player_color}]
            reply_score = move_score(next_stones, reply, player_color, rule_set, board_size) - best_static_score(after_reply, board_size, ai_color, rule_set) * 0.35
            worst_reply = max(worst_reply, reply_score)
        score -= worst_reply * 0.88
    followups = ordered_candidates(next_stones, board_size, ai_color, rule_set, 2, 4)
    if followups:
        score += max(move_score(next_stones, follow, ai_color, rule_set, board_size) for follow in followups) * 0.18
    return score


def choose_ai_move(stones, board_size, ai_color, rule_set, ai_level):
    radius = 3 if ai_level == "hard" else 2
    choices = safe_candidates(stones, board_size, ai_color, rule_set, radius)
    if not choices:
        return None
    if ai_level == "easy":
        return random.choice(choices)

    player_color = opponent(ai_color)
    own_wins = immediate_winning_moves(stones, board_size, ai_color, rule_set, radius)
    if own_wins:
        return sorted(own_wins, key=lambda move: center_score(move["x"], move["y"], board_size), reverse=True)[0]

    player_wins = immediate_winning_moves(stones, board_size, player_color, rule_set, radius)
    if player_wins:
        return sorted(player_wins, key=lambda move: move_score(stones, move, ai_color, rule_set, board_size), reverse=True)[0]

    own_forks = [move for move in choices if creates_double_threat(stones, move, board_size, ai_color, rule_set)]
    if own_forks:
        return sorted(own_forks, key=lambda move: move_score(stones, move, ai_color, rule_set, board_size), reverse=True)[0]

    opponent_forks = [
        move
        for move in safe_candidates(stones, board_size, player_color, rule_set, radius)
        if creates_double_threat(stones, move, board_size, player_color, rule_set)
    ]
    if opponent_forks:
        blocks = [move for move in opponent_forks if validate_move(stones, move["x"], move["y"], ai_color, rule_set, board_size).ok]
        if blocks:
            return sorted(blocks, key=lambda move: move_score(stones, move, ai_color, rule_set, board_size), reverse=True)[0]

    scored = []
    for move in ordered_candidates(stones, board_size, ai_color, rule_set, radius, 14 if ai_level == "hard" else 8):
        score = move_score(stones, move, ai_color, rule_set, board_size)
        if ai_level == "hard":
            score = hard_search_score(stones, move, board_size, ai_color, rule_set)
        scored.append({**move, "score": score})
    scored.sort(key=lambda item: item["score"], reverse=True)
    if ai_level == "normal":
        return random.choice(scored[: min(2, len(scored))])
    return {"x": scored[0]["x"], "y": scored[0]["y"]}
