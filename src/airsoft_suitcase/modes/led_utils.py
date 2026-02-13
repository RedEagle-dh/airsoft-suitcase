from typing import Tuple

from ..hardware.led import Led

TEAM_RED = "red"
TEAM_BLUE = "blue"


def team_rgb(team: str) -> Tuple[int, int, int]:
    if team == TEAM_RED:
        return (255, 0, 0)
    return (0, 0, 255)


def reset_leds(led: Led) -> None:
    led.stop_all_blinkers()
    led.turn_off_all()
    led.pixel_fill((0, 0, 0))


def show_team_static(led: Led, team: str) -> None:
    reset_leds(led)
    if team == TEAM_RED:
        led.turn_red_on()
    else:
        led.turn_blue_on()
    led.pixel_fill(team_rgb(team))


def start_team_pulse(led: Led, team: str, stripe_interval: float) -> None:
    reset_leds(led)
    if team == TEAM_RED:
        led.turn_red_on()
    else:
        led.turn_blue_on()

    led.set_rgb(team_rgb(team))
    led.set_stripe_interval(stripe_interval)
    led.start_stripe_blinker(True)
