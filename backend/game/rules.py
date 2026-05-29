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


def has_four_threat(cells, center):
    for start in range(0, len(cells) - 4):
        if not window_includes_center(start, 5, center):
            continue
        window = cells[start : start + 5]
        if window.count("B") == 4 and window.count(".") == 1:
            return True
    return False


def has_open_three(cells, center):
    patterns = {".BBB.", ".BB.B.", ".B.BB."}
    for size in (5, 6):
        for start in range(0, len(cells) - size + 1):
            if window_includes_center(start, size, center) and "".join(cells[start : start + size]) in patterns:
                return True
    return False


def normalize(cells, color):
    if color == "black":
        return cells
    return ["W" if cell == "B" else "B" if cell == "W" else cell for cell in cells]


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
        return RuleResult(False, "有禁手规则下，黑棋不可形成长连", forbidden=True)
    if any(length == 5 for length in line_lengths):
        return RuleResult(True)

    four_count = 0
    three_count = 0
    for dx, dy in DIRECTIONS:
        cells, center = line_cells(next_board, x, y, dx, dy, board_size)
        cells = normalize(cells, color)
        four_count += int(has_four_threat(cells, center))
        three_count += int(has_open_three(cells, center))
    if four_count >= 2:
        return RuleResult(False, "有禁手规则下，黑棋不可下双四", forbidden=True)
    if three_count >= 2:
        return RuleResult(False, "有禁手规则下，黑棋不可下双三", forbidden=True)
    return RuleResult(True)


def evaluate_move(stones, x, y, color, rule_set="standard", board_size=15):
    validation = validate_move(stones, x, y, color, rule_set, board_size)
    if not validation.ok:
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
