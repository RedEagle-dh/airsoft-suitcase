"""NFC card reader using PC/SC (pyscard) for the ACR1252 or compatible readers."""

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    from smartcard.Exceptions import CardConnectionException, NoCardException
    from smartcard.System import readers as pcsc_readers

    _PYSCARD_AVAILABLE = True
except ImportError:
    _PYSCARD_AVAILABLE = False


class NfcReader:
    """Polls a PC/SC contactless reader for card presence in a background thread."""

    POLL_INTERVAL = 0.3  # seconds between polls

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._reader_name: Optional[str] = None

        if not _PYSCARD_AVAILABLE:
            logger.warning("pyscard not installed – NFC reader unavailable")
            return

        try:
            available = pcsc_readers()
            # Prefer the PICC (contactless) interface
            for r in available:
                if "PICC" in str(r):
                    self._reader_name = str(r)
                    break
            if self._reader_name is None and available:
                self._reader_name = str(available[0])

            if self._reader_name:
                logger.info("NFC reader found: %s", self._reader_name)
            else:
                logger.warning("No PC/SC readers found")
        except Exception:
            logger.warning("Failed to enumerate PC/SC readers", exc_info=True)

    @property
    def available(self) -> bool:
        return self._reader_name is not None

    def start_polling(self, on_card_detected: Callable[[], None]) -> None:
        """Start background polling. Calls *on_card_detected* once when a card is seen."""
        self.stop_polling()

        if not self.available:
            logger.warning("NFC polling requested but no reader available")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            args=(on_card_detected,),
            daemon=True,
        )
        self._thread.start()

    def stop_polling(self) -> None:
        """Stop the background polling thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _poll_loop(self, callback: Callable[[], None]) -> None:
        from smartcard.System import readers as pcsc_readers

        logger.debug("NFC poll loop started for %s", self._reader_name)
        while not self._stop_event.is_set():
            try:
                available = pcsc_readers()
                reader = None
                for r in available:
                    if str(r) == self._reader_name:
                        reader = r
                        break
                if reader is None:
                    time.sleep(self.POLL_INTERVAL)
                    continue

                connection = reader.createConnection()
                connection.connect()
                # If connect() succeeds, a card is present
                uid = self._read_uid(connection)
                logger.info("NFC card detected (UID: %s)", uid or "unknown")
                connection.disconnect()
                callback()
                return  # fire once, then stop
            except (NoCardException, CardConnectionException):
                pass
            except Exception:
                logger.debug("NFC poll error", exc_info=True)

            time.sleep(self.POLL_INTERVAL)

        logger.debug("NFC poll loop stopped")

    @staticmethod
    def _read_uid(connection: object) -> Optional[str]:
        """Try to read the card UID via the standard GET UID APDU."""
        try:
            # GET DATA command for UID (works on most contactless cards)
            get_uid = [0xFF, 0xCA, 0x00, 0x00, 0x00]
            data, sw1, sw2 = connection.transmit(get_uid)  # type: ignore[union-attr]
            if sw1 == 0x90 and sw2 == 0x00:
                return ":".join(f"{b:02X}" for b in data)
        except Exception:
            pass
        return None
