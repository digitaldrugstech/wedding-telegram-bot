"""Text formatting utilities."""


def format_diamonds(count: int) -> str:
    """
    Format diamond count with proper Russian word ending.

    Examples:
        1 алмаз
        2 алмаза
        5 алмазов
        21 алмаз
        100 алмазов

    Args:
        count: Number of diamonds

    Returns:
        Formatted string with proper Russian ending
    """
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} алмаз"
    elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} алмаза"
    else:
        return f"{count} алмазов"


def format_time_remaining(seconds: float) -> str:
    """
    Format remaining time in Russian.

    Args:
        seconds: Time in seconds

    Returns:
        Formatted string like "2ч 30м" or "45м" or "30с"
    """
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds_remaining = divmod(remainder, 60)

    time_parts = []
    if hours > 0:
        time_parts.append(f"{int(hours)}ч")
    if minutes > 0:
        time_parts.append(f"{int(minutes)}м")
    if seconds_remaining > 0 and not time_parts:
        time_parts.append(f"{int(seconds_remaining)}с")

    return " ".join(time_parts)
