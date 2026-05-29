import random

from .rules import evaluate_move, key, opponent, validate_move


def candidates(stones, board_size=15):
    if not stones:
        center = board_size // 2
        return [{"x": center, "y": center}]
    occupied = {key(stone["x"], stone["y"]) for stone in stones}
    result = {}
    for stone in stones:
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                x = stone["x"] + dx
                y = stone["y"] + dy
                if 0 <= x < board_size and 0 <= y < board_size and key(x, y) not in occupied:
                    result[key(x, y)] = {"x": x, "y": y}
    return list(result.values())


def line_score(stones, x, y, color):
    board = {key(stone["x"], stone["y"]): stone["color"] for stone in stones}
    score = 0
    for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
        count = 1
        open_ends = 0
        for sign in (-1, 1):
            cx = x + dx * sign
            cy = y + dy * sign
            while board.get(key(cx, cy)) == color:
                count += 1
                cx += dx * sign
                cy += dy * sign
            if key(cx, cy) not in board:
                open_ends += 1
        score += count**3 * (open_ends + 1)
    return score


def choose_ai_move(stones, board_size, ai_color, rule_set, ai_level):
    legal = [
        move
        for move in candidates(stones, board_size)
        if validate_move(stones, move["x"], move["y"], ai_color, rule_set, board_size).ok
    ]
    if not legal:
        return None
    safe_legal = [
        move
        for move in legal
        if not evaluate_move(stones, move["x"], move["y"], ai_color, rule_set, board_size).forbidden
    ]
    choices = safe_legal or legal
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

    scored = sorted(
        (
            {
                **move,
                "score": line_score(stones, move["x"], move["y"], ai_color) * (1.5 if ai_level == "hard" else 1)
                + line_score(stones, move["x"], move["y"], player_color),
            }
            for move in choices
        ),
        key=lambda item: item["score"],
        reverse=True,
    )
    if ai_level == "normal":
        return random.choice(scored[: min(4, len(scored))])
    return scored[0]
