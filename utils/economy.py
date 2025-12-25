def calculate_multiplier(numbers: list[int], guess: int) -> tuple[float, list[str]]:
    multiplier = 0.0
    display = []
    for idx, num in enumerate(numbers):
        if num == guess:
            if (idx + 1) % 2 == 0:
                multiplier += 0.2
                display.append(f"**{num}**")
            else:
                multiplier -= 0.3
                display.append(f"~~{num}~~")
        else:
            display.append(str(num))
    multiplier = max(min(multiplier, 2.0), -2.0)
    return multiplier, display


def format_number(num: int) -> str:
    return f"{num:,}".replace(",", " ")
