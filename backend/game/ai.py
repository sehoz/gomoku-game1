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


def line_score(stones, x, y, color, board_size=15):
    board = board_after(stones, x, y, color)
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
            score += 1_000_000
        elif count == 4 and open_ends == 2:
            score += 220_000
        elif count == 4 and open_ends == 1:
            score += 90_000
        elif count == 3 and open_ends == 2:
            score += 35_000
        elif count == 3 and open_ends == 1:
            score += 9_000
        elif count == 2 and open_ends == 2:
            score += 3_000
        elif count == 2 and open_ends == 1:
            score += 700
        else:
            score += count * 80 + open_ends * 20
    return score


def center_score(x, y, board_size=15):
    center = (board_size - 1) / 2
    return max(0, 40 - int((abs(x - center) + abs(y - center)) * 4))


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


def move_score(stones, move, color, rule_set, board_size):
    result = evaluate_move(stones, move["x"], move["y"], color, rule_set, board_size)
    if result.forbidden:
        return -2_000_000
    if result.winner == color:
        return 3_000_000
    other = opponent(color)
    attack = line_score(stones, move["x"], move["y"], color, board_size)
    defense = line_score(stones, move["x"], move["y"], other, board_size)
    return attack * 1.18 + defense * 1.05 + center_score(move["x"], move["y"], board_size)


def choose_ai_move(stones, board_size, ai_color, rule_set, ai_level):
    radius = 3 if ai_level == "hard" else 2
    choices = safe_candidates(stones, board_size, ai_color, rule_set, radius)
    if not choices:
        return None
    if ai_level == "easy":
        return random.choice(choices)

    player_color = opponent(ai_color)
    for move in choices:
        result = evaluate_move(stones, move["x"], move["y"], ai_color, rule_set, board_size)
        if result.winner == ai_color:
            return move
    for move in choices:
        if validate_move(stones, move["x"], move["y"], player_color, rule_set, board_size).ok:
            result = evaluate_move(stones, move["x"], move["y"], player_color, rule_set, board_size)
            if result.winner == player_color:
                return move

    scored = []
    for move in choices:
        score = move_score(stones, move, ai_color, rule_set, board_size)
        if ai_level == "hard":
            next_stones = [*stones, {"x": move["x"], "y": move["y"], "color": ai_color}]
            replies = safe_candidates(next_stones, board_size, player_color, rule_set, 2)
            if replies:
                best_reply = max(move_score(next_stones, reply, player_color, rule_set, board_size) for reply in replies)
                score -= best_reply * 0.62
        scored.append({**move, "score": score})
    scored.sort(key=lambda item: item["score"], reverse=True)
    if ai_level == "normal":
        return random.choice(scored[: min(2, len(scored))])
    return scored[0]
