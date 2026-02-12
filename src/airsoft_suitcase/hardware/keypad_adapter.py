import time
from typing import List

import RPi.GPIO as GPIO
from pynput.keyboard import Controller, Key

keyboard = Controller()

# Set side key pins.
B1_IN = 19
B1_OUT = 26
B2_IN = 6
B2_OUT = 13

# Set the row pins.
ROW_1 = 24
ROW_2 = 25
ROW_3 = 12
ROW_4 = 16

# Set the column pins.
COL_1 = 5
COL_2 = 17
COL_3 = 27
COL_4 = 22

HASH_HOLD_SECONDS = 3.0


def setup_gpio() -> None:
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    # Set row pins as output.
    GPIO.setup(ROW_1, GPIO.OUT)
    GPIO.setup(ROW_2, GPIO.OUT)
    GPIO.setup(ROW_3, GPIO.OUT)
    GPIO.setup(ROW_4, GPIO.OUT)
    GPIO.setup(B1_OUT, GPIO.OUT)
    GPIO.setup(B2_OUT, GPIO.OUT)

    # Set column pins as input and pulled up high by default.
    GPIO.setup(COL_1, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(COL_2, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(COL_3, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(COL_4, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(B1_IN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(B2_IN, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def send_key(key_value: object) -> None:
    keyboard.press(key_value)
    time.sleep(0.1)
    keyboard.release(key_value)


def send_key_while_pressed(key_value: object, pin: int) -> None:
    keyboard.press(key_value)
    wait_for(pin)
    time.sleep(0.01)
    keyboard.release(key_value)


def wait_for(pin: int) -> None:
    while GPIO.input(pin) == GPIO.LOW:
        # Avoid busy waiting at 100% CPU while a button is held.
        time.sleep(0.005)


def read_row(line: int, characters: List[str]) -> None:
    GPIO.output(line, GPIO.LOW)
    if GPIO.input(COL_1) == GPIO.LOW:
        send_key_while_pressed(characters[0], COL_1)
        print(characters[0])
    if GPIO.input(COL_2) == GPIO.LOW:
        send_key_while_pressed(characters[1], COL_2)
        print(characters[1])
    if GPIO.input(COL_3) == GPIO.LOW:
        if characters[2] == "#":
            start = time.monotonic()
            while GPIO.input(COL_3) == GPIO.LOW:
                if (time.monotonic() - start) >= HASH_HOLD_SECONDS:
                    print("hash-hold -> escape")
                    send_key(Key.esc)
                    wait_for(COL_3)
                    break
                time.sleep(0.01)
            else:
                send_key_while_pressed(characters[2], COL_3)
                print(characters[2])
        else:
            send_key_while_pressed(characters[2], COL_3)
            print(characters[2])
    if GPIO.input(COL_4) == GPIO.LOW:
        send_key_while_pressed(characters[3], COL_4)
        print(characters[3])
    GPIO.output(line, GPIO.HIGH)


def read_buttons() -> None:
    GPIO.output(B1_OUT, GPIO.LOW)
    if GPIO.input(B1_IN) == GPIO.LOW:
        print("delete")
        send_key_while_pressed(Key.delete, B1_IN)
    GPIO.output(B1_OUT, GPIO.HIGH)

    GPIO.output(B2_OUT, GPIO.LOW)
    if GPIO.input(B2_IN) == GPIO.LOW:
        print("enter")
        send_key_while_pressed(Key.enter, B2_IN)
    GPIO.output(B2_OUT, GPIO.HIGH)


def run() -> None:
    setup_gpio()
    # Endless loop by checking each row.
    while True:
        read_row(ROW_1, ["1", "2", "3", "A"])
        read_row(ROW_2, ["4", "5", "6", "B"])
        read_row(ROW_3, ["7", "8", "9", "C"])
        read_row(ROW_4, ["*", "0", "#", "D"])
        read_buttons()
        time.sleep(0.1)  # adjust this per your own setup


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        GPIO.cleanup()
