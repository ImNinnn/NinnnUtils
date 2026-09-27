"""Counter channels: evaluating a counted number and reading/updating the counter state.

Used by the misc cog (counting, /counter-number-set) and the levels cog (no XP for counting).
The counter channels themselves are added and removed in /settings.
"""

import ast
import math

import save



MAX_EXPRESSION_LENGTH = 200
MAX_EXPONENT = 64
MAX_DIGITS = 100
MAX_VALUE = 10 ** MAX_DIGITS


def safe_eval_math_expr(expr: str) -> int | None:
    if len(expr) > MAX_EXPRESSION_LENGTH:
        return None
    try:
        tree = ast.parse(expr.strip(), mode='eval')
    except (SyntaxError, ValueError):
        return None

    def _check(value):
        if isinstance(value, complex) or abs(value) > MAX_VALUE:
            raise ValueError("Result too large")
        return value

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                raise ValueError("Boolean values are not allowed")
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Unsupported constant")
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return _check(left + right)
            if isinstance(node.op, ast.Sub):
                return _check(left - right)
            if isinstance(node.op, ast.Mult):
                return _check(left * right)
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.FloorDiv):
                return left // right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.Pow):
                # Huge powers (9**9**9) would freeze the bot while Python computes them.
                if abs(right) > MAX_EXPONENT or (abs(left) > 1 and abs(right) * math.log10(abs(left)) > MAX_DIGITS):
                    raise ValueError("Result too large")
                return _check(left ** right)
            raise ValueError("Unsupported operator")
        if isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +operand
            if isinstance(node.op, ast.USub):
                return -operand
            raise ValueError("Unsupported unary operator")
        if isinstance(node, ast.Tuple):
            raise ValueError("Tuples are not allowed")
        raise ValueError("Unsupported expression")

    try:
        value = _eval(tree)
    except (ValueError, OverflowError, ZeroDivisionError, TypeError, RecursionError):
        return None

    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if not value.is_integer():
            return None
        value = int(value)
    if not isinstance(value, int):
        return None
    return value


def get_counter_channel_config(guild_id: str, channel_id: int) -> dict | None:
    guild_config, _ = save.get_guild_config(str(guild_id))
    return guild_config.get("counter_channels", {}).get(str(channel_id))


def update_counter_state(guild_id: str, channel_id: int, current_value: int, last_user_id: int | None) -> bool:
    guild_config, data = save.get_guild_config(str(guild_id))
    cfg = guild_config.setdefault("counter_channels", {}).get(str(channel_id))
    if cfg is None:
        return False
    cfg["current_value"] = current_value
    cfg["last_user_id"] = last_user_id
    save.save_guild_data(data)
    return True


def set_counter_value(guild_id: str, channel_id: int, value: int) -> bool:
    return update_counter_state(guild_id, channel_id, value, None)


def is_counter_number_message(guild_id: str, channel_id: int, content: str) -> bool:
    """True when the message is a counting attempt in a counter channel."""
    if get_counter_channel_config(guild_id, channel_id) is None:
        return False
    content = (content or "").strip()
    return bool(content) and safe_eval_math_expr(content) is not None
