import os

# Force simulation mode for tests
os.environ["AIRSOFT_SIMULATE_GPIO"] = "1"

from airsoft_suitcase.hardware.led import Led


class TestLedSimulation:
    def setup_method(self) -> None:
        self.led = Led()

    def teardown_method(self) -> None:
        self.led.stop_all_blinkers()
        self.led.turn_off_all()

    def test_initialization_in_simulation(self) -> None:
        assert self.led._simulate_gpio is True

    def test_turn_red_on_off(self) -> None:
        self.led.turn_red_on()
        self.led.turn_off_red()

    def test_turn_blue_on_off(self) -> None:
        self.led.turn_blue_on()
        self.led.turn_off_blue()

    def test_turn_off_all(self) -> None:
        self.led.turn_red_on()
        self.led.turn_blue_on()
        self.led.turn_off_all()

    def test_pixel_fill(self) -> None:
        self.led.pixel_fill((255, 0, 0))
        assert self.led._stripe_rgb == (255, 0, 0)

    def test_pixel_fill_clamps_values(self) -> None:
        self.led.pixel_fill((300, -10, 128))
        assert self.led._stripe_rgb == (255, 0, 128)

    def test_set_rgb(self) -> None:
        self.led.set_rgb((0, 255, 0))
        assert self.led._stripe_rgb == (0, 255, 0)

    def test_normalize_rgb_rejects_wrong_length(self) -> None:
        try:
            self.led._normalize_rgb((1, 2))  # type: ignore[arg-type]
            raise AssertionError("Should have raised ValueError")
        except ValueError:
            pass

    def test_blue_blinker_lifecycle(self) -> None:
        assert self.led.get_blue_is_alive() is False
        self.led.start_blue_blinker()
        assert self.led.get_blue_is_alive() is True
        self.led.stop_blue_blinker()
        assert self.led.get_blue_is_alive() is False

    def test_red_blinker_lifecycle(self) -> None:
        assert self.led.get_red_is_alive() is False
        self.led.start_red_blinker()
        assert self.led.get_red_is_alive() is True
        self.led.stop_red_blinker()
        assert self.led.get_red_is_alive() is False

    def test_stripe_blinker_lifecycle(self) -> None:
        assert self.led.get_stripe_blinker_alive() is False
        self.led.set_rgb((0, 255, 0))
        self.led.start_stripe_blinker(pulse=False)
        assert self.led.get_stripe_blinker_alive() is True
        self.led.stop_stripe_blinker()
        assert self.led.get_stripe_blinker_alive() is False

    def test_stripe_pulse_blinker(self) -> None:
        self.led.set_rgb((0, 255, 0))
        self.led.start_stripe_blinker(pulse=True)
        assert self.led.get_stripe_blinker_alive() is True
        self.led.stop_stripe_blinker()
        assert self.led.get_stripe_blinker_alive() is False

    def test_stop_all_blinkers(self) -> None:
        self.led.start_blue_blinker()
        self.led.start_red_blinker()
        self.led.start_stripe_blinker(pulse=False)
        self.led.stop_all_blinkers()
        assert self.led.get_blue_is_alive() is False
        assert self.led.get_red_is_alive() is False
        assert self.led.get_stripe_blinker_alive() is False

    def test_double_start_is_safe(self) -> None:
        self.led.start_blue_blinker()
        self.led.start_blue_blinker()  # Should not crash
        assert self.led.get_blue_is_alive() is True
        self.led.stop_blue_blinker()

    def test_set_intervals(self) -> None:
        self.led.set_blue_interval(0.5)
        assert self.led._blue_blinker_interval == 0.5

        self.led.set_red_interval(2.0)
        assert self.led._red_blinker_interval == 2.0

        self.led.set_stripe_interval(0.001)
        assert self.led._stripe_interval >= 0.01  # clamped to minimum

    def test_stripe_off(self) -> None:
        self.led.pixel_fill((255, 0, 0))
        self.led.stripe_off()

    def test_pixel_runtime_failure_disables_neopixel_without_crashing(self) -> None:
        class FailingPixel:
            def fill(self, _rgb: tuple[int, int, int]) -> None:
                raise RuntimeError("NeoPixel support requires running with sudo, please try again!")

        self.led._pixel = FailingPixel()
        self.led.pixel_fill((12, 34, 56))

        assert self.led._pixel_failure_reason is not None
        assert "runtime write failed" in self.led._pixel_failure_reason

        # Subsequent writes use no-op pixel backend and should remain stable.
        self.led.pixel_fill((0, 0, 0))

    def test_pixel_runtime_failure_raises_in_strict_mode(self) -> None:
        class FailingPixel:
            def fill(self, _rgb: tuple[int, int, int]) -> None:
                raise RuntimeError("NeoPixel support requires running with sudo, please try again!")

        os.environ["AIRSOFT_REQUIRE_NEOPIXEL"] = "1"
        strict_led = Led()
        strict_led._pixel = FailingPixel()

        try:
            strict_led.pixel_fill((1, 2, 3))
            raise AssertionError("Expected strict NeoPixel mode to raise")
        except RuntimeError:
            pass
        finally:
            strict_led._require_neopixel = False
            strict_led.stop_all_blinkers()
            strict_led.turn_off_all()
            os.environ.pop("AIRSOFT_REQUIRE_NEOPIXEL", None)
