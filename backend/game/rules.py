from dataclasses import dataclass


DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))


@dataclass
class RuleResult:
    ok: bool
    reason: str = ""
    status: str = "playing"
    winner: str = ""
    forbidden: bool = False


def opponent(color):
    return "white" if color == "black" else "black"


def key(x, y):
    return f"{x},{y}"


def board_from(stones):
    return {key(stone["x"], stone["y"]): stone["color"] for stone in stones}


def inside(x, y, board_size=15):
    return 0 <= x < board_size and 0 <= y < board_size


def count_dir(board, x, y, dx, dy, color):
    count = 0
    cx = x + dx
    cy = y + dy
    while board.get(key(cx, cy)) == color:
        count += 1
        cx += dx
        cy += dy
    return count


def line_cells(board, x, y, dx, dy, board_size=15):
    cells = []
    for offset in range(-5, 6):
        cx = x + dx * offset
        cy = y + dy * offset
        value = board.get(key(cx, cy))
        if not inside(cx, cy, board_size):
            cells.append("X")
        elif value is None:
            cells.append(".")
        else:
            cells.append("B" if value == "black" else "W")
    return cells, 5


def window_includes_center(start, length, center):
    return start <= center < start + length


def line_positions(x, y, dx, dy, board_size=15):
    sx, sy = x, y
    while inside(sx - dx, sy - dy, board_size):
        sx -= dx
        sy -= dy
    positions = []
    while inside(sx, sy, board_size):
        positions.append((sx, sy))
        sx += dx
        sy += dy
    return positions


def open_four_exists(board, x, y, dx, dy, color, board_size=15, required=()):
    required = set(required)
    positions = line_positions(x, y, dx, dy, board_size)
    values = [board.get(key(px, py), ".") for px, py in positions]
    for start in range(0, len(values) - 5):
        window = values[start : start + 6]
        if window != [".", color, color, color, color, "."]:
            continue
        window_positions = set(positions[start : start + 6])
        if required.issubset(window_positions):
            return True
    return False


def exact_five_exists(board, x, y, dx, dy, color, board_size=15, required=()):
    required = set(required)
    positions = line_positions(x, y, dx, dy, board_size)
    values = [board.get(key(px, py), ".") for px, py in positions]
    for start in range(0, len(values) - 4):
        window = values[start : start + 5]
        if window != [color, color, color, color, color]:
            continue
        before = values[start - 1] if start > 0 else "."
        after = values[start + 5] if start + 5 < len(values) else "."
        if before == color or after == color:
            continue
        window_positions = set(positions[start : start + 5])
        if required.issubset(window_positions):
            return True
    return False


def winning_extensions_in_direction(board, x, y, dx, dy, color, board_size=15, required=()):
    required = set(required) | {(x, y)}
    wins = []
    for px, py in line_positions(x, y, dx, dy, board_size):
        if board.get(key(px, py)) is not None:
            continue
        test_board = {**board, key(px, py): color}
        if exact_five_exists(test_board, x, y, dx, dy, color, board_size, required=required | {(px, py)}):
            wins.append((px, py))
    return wins


def direction_has_four(board, x, y, dx, dy, color, board_size=15):
    return bool(winning_extensions_in_direction(board, x, y, dx, dy, color, board_size))


def pattern_open_three_exists(board, x, y, dx, dy, color, board_size=15):
    patterns = (
        (".", color, color, color, "."),
        (".", color, color, ".", color, "."),
        (".", color, ".", color, color, "."),
        (".", color, ".", color, ".", color, "."),
    )
    positions = line_positions(x, y, dx, dy, board_size)
    values = [board.get(key(px, py), ".") for px, py in positions]
    for pattern in patterns:
        size = len(pattern)
        for start in range(0, len(values) - size + 1):
            if tuple(values[start : start + size]) != pattern:
                continue
            if (x, y) in set(positions[start : start + size]):
                return True
    return False


def direction_has_open_three(board, x, y, dx, dy, color, board_size=15):
    if pattern_open_three_exists(board, x, y, dx, dy, color, board_size):
        return True
    for px, py in line_positions(x, y, dx, dy, board_size):
        if board.get(key(px, py)) is not None:
            continue
        test_board = {**board, key(px, py): color}
        if open_four_exists(test_board, x, y, dx, dy, color, board_size, required=((x, y), (px, py))):
            return True
        if len(winning_extensions_in_direction(test_board, x, y, dx, dy, color, board_size, required=((x, y), (px, py)))) >= 2:
            return True
    return False


def validate_move(stones, x, y, color, rule_set="standard", board_size=15):
    board = board_from(stones)
    if not inside(x, y, board_size):
        return RuleResult(False, "落子超出棋盘范围")
    if key(x, y) in board:
        return RuleResult(False, "该交点已有棋子")
    if rule_set != "renju" or color != "black":
        return RuleResult(True)

    next_board = board_from([*stones, {"x": x, "y": y, "color": color}])
    line_lengths = [
        1 + count_dir(next_board, x, y, dx, dy, color) + count_dir(next_board, x, y, -dx, -dy, color)
        for dx, dy in DIRECTIONS
    ]
    if any(length > 5 for length in line_lengths):
        return RuleResult(True, "黑棋长连禁手，白棋获胜", status="white_win", winner="white", forbidden=True)
    if any(length == 5 for length in line_lengths):
        return RuleResult(True)

    four_count = 0
    three_count = 0
    for dx, dy in DIRECTIONS:
        four_count += int(direction_has_four(next_board, x, y, dx, dy, color, board_size))
        three_count += int(direction_has_open_three(next_board, x, y, dx, dy, color, board_size))
    if four_count >= 2:
        return RuleResult(True, "黑棋双四禁手，白棋获胜", status="white_win", winner="white", forbidden=True)
    if three_count >= 2:
        return RuleResult(True, "黑棋双三禁手，白棋获胜", status="white_win", winner="white", forbidden=True)
    return RuleResult(True)


def evaluate_move(stones, x, y, color, rule_set="standard", board_size=15):
    validation = validate_move(stones, x, y, color, rule_set, board_size)
    if not validation.ok:
        return validation
    if validation.forbidden:
        return validation

    next_stones = [*stones, {"x": x, "y": y, "color": color}]
    board = board_from(next_stones)
    max_line = max(
        1 + count_dir(board, x, y, dx, dy, color) + count_dir(board, x, y, -dx, -dy, color)
        for dx, dy in DIRECTIONS
    )
    wins = max_line == 5 if rule_set == "renju" and color == "black" else max_line >= 5
    if wins:
        return RuleResult(True, status=f"{color}_win", winner=color)
    if len(next_stones) >= board_size * board_size:
        return RuleResult(True, status="draw")
    return RuleResult(True)


def next_turn(stones):
    return "black" if len(stones) % 2 == 0 else "white"
