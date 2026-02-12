const titleEl = document.getElementById("title");
const contentEl = document.getElementById("content");
const footerEl = document.getElementById("footer");
const logsEl = document.getElementById("logs");

const games = ["Bombe", "Bunker", "Flagge"];
const bombDiffs = ["Einfach", "Mittel", "Schwer"];
const keyset = new Set("0123456789ABCD".split(""));

const BOMB_DURATION_SECONDS = 10 * 60;
const BOMB_CODE_LENGTH = 20;
const BOMB_LOCK_SECONDS = [30, 60];
const BUNKER_TARGET_SECONDS = 600;
const HASH_HOLD_MS = 3000;

const state = {
  phase: "menu",
  menuLevel: "game",
  selection: -1,
  selectedGame: null,
  selectedDiff: null,
  isInGame: false,

  hashHoldTimeout: null,
  hashKeyDown: false,
  gameEndTimeout: null,

  bombStage: "idle",
  bombExpectedCode: "",
  bombInput: "",
  bombRemaining: BOMB_DURATION_SECONDS,
  bombReentryTargets: [],
  bombAttempt: 0,
  bombLockRemaining: 0,
  bombResumeStage: "",
  bombEndMessage: "",
  bombTickTimeout: null,
  bombLockTimeout: null,
  bombBeepTimeout: null,
  bombPaceLevel: "slow",

  bunkerBlueSeconds: 0,
  bunkerRedSeconds: 0,
  bunkerActiveTeam: null,
  bunkerWinner: null,
  bunkerSignalActive: false,
  bunkerTickTimeout: null,
  bunkerSignalTimeout: null,

  flagTeam: null,
};

let audioContext = null;

function logGPIO(message) {
  const line = `[GPIO-SIM] ${message}`;
  console.log(line);
  logsEl.textContent += `${line}\n`;
  logsEl.scrollTop = logsEl.scrollHeight;
}

function randomCode(length) {
  const alphabet = "0123456789ABCD";
  let out = "";
  for (let i = 0; i < length; i += 1) {
    out += alphabet[Math.floor(Math.random() * alphabet.length)];
  }
  return out;
}

function formatTime(seconds) {
  const safe = Math.max(0, seconds);
  const mins = String(Math.floor(safe / 60)).padStart(2, "0");
  const secs = String(safe % 60).padStart(2, "0");
  return `${mins}:${secs}`;
}

function ensureAudioContext() {
  if (!audioContext) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) {
      return null;
    }
    audioContext = new Ctx();
  }

  if (audioContext.state === "suspended") {
    audioContext.resume().catch(() => undefined);
  }

  return audioContext;
}

function beepOnce(durationMs = 120, frequency = 880) {
  const ctx = ensureAudioContext();
  if (!ctx) {
    return;
  }

  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "square";
  osc.frequency.value = frequency;

  gain.gain.value = 0.03;
  osc.connect(gain);
  gain.connect(ctx.destination);

  const stopAt = ctx.currentTime + durationMs / 1000;
  osc.start();
  osc.stop(stopAt);
}

function clearTimeoutState(key) {
  if (state[key]) {
    clearTimeout(state[key]);
    state[key] = null;
  }
}

function clearAllTimers() {
  clearTimeoutState("hashHoldTimeout");
  clearTimeoutState("gameEndTimeout");
  clearTimeoutState("bombTickTimeout");
  clearTimeoutState("bombLockTimeout");
  clearTimeoutState("bombBeepTimeout");
  clearTimeoutState("bunkerTickTimeout");
  clearTimeoutState("bunkerSignalTimeout");
}

function resetToMenu() {
  clearAllTimers();

  state.phase = "menu";
  state.menuLevel = "game";
  state.selection = -1;
  state.selectedGame = null;
  state.selectedDiff = null;
  state.isInGame = false;

  state.hashKeyDown = false;

  state.bombStage = "idle";
  state.bombExpectedCode = "";
  state.bombInput = "";
  state.bombRemaining = BOMB_DURATION_SECONDS;
  state.bombReentryTargets = [];
  state.bombAttempt = 0;
  state.bombLockRemaining = 0;
  state.bombResumeStage = "";
  state.bombEndMessage = "";
  state.bombPaceLevel = "slow";

  state.bunkerBlueSeconds = 0;
  state.bunkerRedSeconds = 0;
  state.bunkerActiveTeam = null;
  state.bunkerWinner = null;
  state.bunkerSignalActive = false;

  state.flagTeam = null;

  logGPIO("Stop all blinkers");
  logGPIO("Turn off all outputs");
  logGPIO("Pin 20 (RED) -> ON");
  logGPIO("Pin 23 (BLUE) -> ON");
  logGPIO("Reset state to main menu");

  render();
}

function keypadCharFromEvent(event) {
  if (!event || !event.key) {
    return "";
  }

  const upper = event.key.length === 1 ? event.key.toUpperCase() : "";
  if (keyset.has(upper) || upper === "#" || upper === "*") {
    return upper;
  }

  if (event.key === "Multiply") {
    return "*";
  }

  return "";
}

function isBlueKey(event) {
  return event.key === "Enter";
}

function isRedKey(event) {
  return event.key === "Backspace" || event.key === "Delete";
}

function isHashKey(event) {
  return keypadCharFromEvent(event) === "#";
}

function isStarKey(event) {
  return keypadCharFromEvent(event) === "*";
}

function startHashHold() {
  if (state.hashHoldTimeout || !state.isInGame) {
    return;
  }
  state.hashHoldTimeout = setTimeout(() => {
    state.hashHoldTimeout = null;
    if (state.hashKeyDown && state.isInGame) {
      resetToMenu();
    }
  }, HASH_HOLD_MS);
}

function stopHashHold() {
  clearTimeoutState("hashHoldTimeout");
}

function renderMenu() {
  const title = state.menuLevel === "game" ? "Spielauswahl:" : "Bombe: Schwierigkeit";
  const options = state.menuLevel === "game" ? games : bombDiffs;

  titleEl.textContent = title;
  contentEl.innerHTML = options
    .map((option, idx) => {
      const marker = state.selection === idx ? "&larr;" : "&nbsp;";
      return `<div class="option"><span class="arrow">${marker}</span><span>${idx + 1}: ${option}</span></div>`;
    })
    .join("");

  footerEl.innerHTML = "<span>Rot: Zurück</span><span>Blau: Bestätigen</span>";
}

function renderBomb() {
  titleEl.textContent = `Bombe | Zeit: ${formatTime(state.bombRemaining)}`;

  if (state.bombStage === "await_nfc") {
    contentEl.textContent = [
      "Schwer-Modus: NFC-Karte scannen",
      "Simulation: Taste A",
      "# 3s halten = Hauptmenü",
    ].join("\n");
    footerEl.innerHTML = "<span>Rot: Eingabe löschen</span><span>Blau: Bestätigen</span>";
    return;
  }

  if (state.bombStage === "await_code" || state.bombStage === "await_reentry") {
    const prompt = state.bombStage === "await_code" ? "Code zum Start:" : "Neuer Code erforderlich:";
    contentEl.textContent = [
      prompt,
      state.bombExpectedCode,
      "",
      `Eingabe: ${state.bombInput}`,
      `Fehlversuche: ${state.bombAttempt}/3`,
      "# 3s halten = Hauptmenü",
    ].join("\n");
    footerEl.innerHTML = "<span>Rot: Eingabe löschen</span><span>Blau: Bestätigen</span>";
    return;
  }

  if (state.bombStage === "locked") {
    contentEl.textContent = `Eingabe gesperrt: ${state.bombLockRemaining}s\n# 3s halten = Hauptmenü`;
    footerEl.innerHTML = "<span>Rot: -</span><span>Blau: -</span>";
    return;
  }

  if (state.bombStage === "countdown") {
    contentEl.textContent = "Countdown läuft\n# 3s halten = Hauptmenü";
    footerEl.innerHTML = "<span>Rot: Eingabe löschen</span><span>Blau: Bestätigen</span>";
    return;
  }

  if (state.bombStage === "ended") {
    contentEl.textContent = `${state.bombEndMessage}\nRückkehr zum Hauptmenü...`;
    footerEl.innerHTML = "<span>Rot: -</span><span>Blau: -</span>";
    return;
  }

  contentEl.textContent = "";
}

function renderBunker() {
  titleEl.textContent = "Bunker";

  const activeTeam = state.bunkerActiveTeam ? state.bunkerActiveTeam.toUpperCase() : "-";
  const activeSeconds =
    state.bunkerActiveTeam === "blue"
      ? state.bunkerBlueSeconds
      : state.bunkerActiveTeam === "red"
        ? state.bunkerRedSeconds
        : 0;

  const lines = [];
  if (state.bunkerActiveTeam) {
    lines.push(`${activeTeam} ${formatTime(activeSeconds)}`);
  } else {
    lines.push("Warte auf Team...");
  }

  lines.push(`Blue: ${formatTime(state.bunkerBlueSeconds)}   Red: ${formatTime(state.bunkerRedSeconds)}`);

  if (state.bunkerWinner) {
    const winnerLabel = state.bunkerWinner.toUpperCase();
    if (state.bunkerSignalActive) {
      lines.push(`${winnerLabel} gewonnen - Signal aktiv`);
    } else {
      lines.push(`${winnerLabel} bei 600s - * gedrückt halten zum Beenden`);
    }
  } else {
    lines.push(`Ziel: ${BUNKER_TARGET_SECONDS}s | # 3s halten = Hauptmenü`);
  }

  contentEl.textContent = lines.join("\n\n");
  footerEl.innerHTML = "<span>Rot: Team Rot</span><span>Blau: Team Blau</span>";
}

function renderFlag() {
  titleEl.textContent = "Flagge";

  const label = state.flagTeam === "red" ? "ROT" : state.flagTeam === "blue" ? "BLAU" : "-";
  contentEl.textContent = `${label}\n# 3s halten = Hauptmenü`;
  footerEl.innerHTML = "<span>Rot: Team Rot</span><span>Blau: Team Blau</span>";
}

function render() {
  if (state.phase === "menu") {
    renderMenu();
    return;
  }
  if (state.phase === "bomb") {
    renderBomb();
    return;
  }
  if (state.phase === "bunker") {
    renderBunker();
    return;
  }
  if (state.phase === "flag") {
    renderFlag();
  }
}

function handleMenuKey(event) {
  const digit = keypadCharFromEvent(event);
  if (["1", "2", "3"].includes(digit)) {
    state.selection = Number(digit) - 1;
    render();
    return;
  }

  if (isBlueKey(event) && state.selection >= 0) {
    if (state.menuLevel === "game") {
      state.selectedGame = games[state.selection];
      state.selection = -1;

      if (state.selectedGame === "Bombe") {
        state.menuLevel = "bomb_diff";
        render();
        return;
      }

      if (state.selectedGame === "Bunker") {
        startBunkerGame();
      } else {
        startFlagGame();
      }
      return;
    }

    state.selectedDiff = bombDiffs[state.selection];
    startBombGame();
    return;
  }

  if (isRedKey(event) && state.menuLevel === "bomb_diff") {
    state.menuLevel = "game";
    state.selection = -1;
    state.selectedGame = null;
    render();
  }
}

function buildBombReentryTargets(diff) {
  if (diff === "Einfach") {
    return [];
  }
  if (diff === "Mittel") {
    return [Math.floor(Math.random() * (420 - 180 + 1)) + 180];
  }

  const values = new Set();
  while (values.size < 2) {
    values.add(Math.floor(Math.random() * (420 - 180 + 1)) + 180);
  }

  return Array.from(values).sort((a, b) => b - a);
}

function applyBombIdleLeds() {
  logGPIO("Stop all blinkers");
  logGPIO("Turn off all outputs");
  logGPIO("LED stripe fill -> (0, 0, 0)");
  logGPIO("Pin 23 (BLUE) -> ON");
}

function bombPaceLevel() {
  if (state.bombRemaining <= 60) {
    return "fast";
  }
  if (state.bombRemaining <= 300) {
    return "mid";
  }
  return "slow";
}

function bombBlueInterval() {
  if (state.bombRemaining <= 60) {
    return 0.2;
  }
  if (state.bombRemaining <= 300) {
    return 0.45;
  }
  return 0.85;
}

function bombTankInterval() {
  if (state.bombRemaining <= 60) {
    return 0.05;
  }
  if (state.bombRemaining <= 300) {
    return 0.1;
  }
  return 0.16;
}

function bombBeepIntervalMs() {
  if (state.bombRemaining <= 60) {
    return 180;
  }
  if (state.bombRemaining <= 300) {
    return 340;
  }
  return 650;
}

function logBombPaceIfChanged() {
  const pace = bombPaceLevel();
  if (state.bombPaceLevel !== pace) {
    state.bombPaceLevel = pace;
    logGPIO(`Blue blinker interval -> ${bombBlueInterval().toFixed(2)}s`);
    logGPIO(`Stripe pulse interval -> ${bombTankInterval().toFixed(2)}s`);
  }
}

function applyBombCountdownLeds() {
  logGPIO("Stop all blinkers");
  logGPIO("Turn off all outputs");
  logGPIO(`Blue blinker started (interval ${bombBlueInterval().toFixed(2)}s)`);
  logGPIO("Stripe base RGB -> (0, 255, 0)");
  logGPIO(`Stripe blinker started (mode=pulse, interval ${bombTankInterval().toFixed(2)}s)`);
  state.bombPaceLevel = bombPaceLevel();
}

function scheduleBombTick() {
  if (state.bombTickTimeout) {
    return;
  }
  state.bombTickTimeout = setTimeout(tickBomb, 1000);
}

function tickBomb() {
  state.bombTickTimeout = null;

  if (state.phase !== "bomb" || state.bombStage !== "countdown") {
    return;
  }

  state.bombRemaining -= 1;

  if (state.bombRemaining <= 0) {
    finishBombTimerElapsed();
    return;
  }

  if (state.bombReentryTargets.length > 0 && state.bombRemaining === state.bombReentryTargets[0]) {
    state.bombReentryTargets.shift();
    pauseBombForReentry();
    return;
  }

  logBombPaceIfChanged();
  render();
  scheduleBombTick();
}

function scheduleBombBeep() {
  if (state.bombBeepTimeout) {
    return;
  }
  state.bombBeepTimeout = setTimeout(tickBombBeep, bombBeepIntervalMs());
}

function tickBombBeep() {
  state.bombBeepTimeout = null;

  if (state.phase !== "bomb" || state.bombStage !== "countdown") {
    return;
  }

  beepOnce(110, 920);
  scheduleBombBeep();
}

function startBombCountdown(playArmSound) {
  clearTimeoutState("bombTickTimeout");
  clearTimeoutState("bombBeepTimeout");

  state.bombStage = "countdown";
  state.bombInput = "";

  applyBombCountdownLeds();
  if (playArmSound) {
    beepOnce(180, 760);
  }

  render();
  scheduleBombTick();
  scheduleBombBeep();
}

function pauseBombForReentry() {
  clearTimeoutState("bombTickTimeout");
  clearTimeoutState("bombBeepTimeout");

  state.bombStage = "await_reentry";
  state.bombExpectedCode = randomCode(BOMB_CODE_LENGTH);
  state.bombInput = "";
  state.bombAttempt = 0;

  applyBombIdleLeds();
  render();
}

function scheduleBombLockTick() {
  clearTimeoutState("bombLockTimeout");
  state.bombLockTimeout = setTimeout(tickBombLock, 1000);
}

function tickBombLock() {
  state.bombLockTimeout = null;

  if (state.phase !== "bomb" || state.bombStage !== "locked") {
    return;
  }

  state.bombLockRemaining -= 1;
  if (state.bombLockRemaining <= 0) {
    state.bombStage = state.bombResumeStage || "await_code";
    state.bombResumeStage = "";
    applyBombIdleLeds();
    render();
    return;
  }

  render();
  scheduleBombLockTick();
}

function startBombLock(seconds) {
  clearTimeoutState("bombTickTimeout");
  clearTimeoutState("bombBeepTimeout");
  clearTimeoutState("bombLockTimeout");

  state.bombResumeStage = state.bombStage;
  state.bombStage = "locked";
  state.bombLockRemaining = seconds;
  state.bombInput = "";

  logGPIO("Stop all blinkers");
  logGPIO("Turn off all outputs");
  logGPIO("LED stripe fill -> (0, 0, 0)");
  logGPIO("Red blinker started (interval 0.25s)");

  render();
  scheduleBombLockTick();
}

function finishBombFailedInput() {
  clearTimeoutState("bombTickTimeout");
  clearTimeoutState("bombBeepTimeout");
  clearTimeoutState("bombLockTimeout");

  state.bombStage = "ended";
  state.bombEndMessage = "Zu viele Fehlversuche. Platzierer-Team verliert.";

  logGPIO("Stop all blinkers");
  logGPIO("Turn off all outputs");
  logGPIO("Pin 20 (RED) -> ON");
  logGPIO("LED stripe fill -> (255, 0, 0)");

  beepOnce(240, 420);
  render();

  clearTimeoutState("gameEndTimeout");
  state.gameEndTimeout = setTimeout(resetToMenu, 3000);
}

function finishBombTimerElapsed() {
  clearTimeoutState("bombTickTimeout");
  clearTimeoutState("bombBeepTimeout");
  clearTimeoutState("bombLockTimeout");

  state.bombStage = "ended";
  state.bombEndMessage = "Zeit abgelaufen. Platzierer-Team gewinnt.";

  logGPIO("Stop all blinkers");
  logGPIO("Turn off all outputs");
  logGPIO("Pin 20 (RED) -> ON");
  logGPIO("LED stripe fill -> (255, 0, 0)");

  beepOnce(320, 260);
  render();

  clearTimeoutState("gameEndTimeout");
  state.gameEndTimeout = setTimeout(resetToMenu, 3000);
}

function handleWrongBombCode() {
  state.bombAttempt += 1;
  if (state.bombAttempt <= BOMB_LOCK_SECONDS.length) {
    startBombLock(BOMB_LOCK_SECONDS[state.bombAttempt - 1]);
    return;
  }

  finishBombFailedInput();
}

function startBombGame() {
  state.isInGame = true;
  state.phase = "bomb";

  const diff = state.selectedDiff || "Einfach";
  state.bombStage = diff === "Schwer" ? "await_nfc" : "await_code";
  state.bombExpectedCode = randomCode(BOMB_CODE_LENGTH);
  state.bombInput = "";
  state.bombRemaining = BOMB_DURATION_SECONDS;
  state.bombReentryTargets = buildBombReentryTargets(diff);
  state.bombAttempt = 0;
  state.bombLockRemaining = 0;
  state.bombResumeStage = "";
  state.bombEndMessage = "";
  state.bombPaceLevel = "slow";

  applyBombIdleLeds();
  render();
}

function handleBombKey(event) {
  if (state.bombStage === "ended" || state.bombStage === "locked") {
    return;
  }

  if (isRedKey(event)) {
    state.bombInput = "";
    render();
    return;
  }

  if (isBlueKey(event)) {
    const candidate = state.bombInput;
    if (!candidate) {
      return;
    }

    state.bombInput = "";

    if (state.bombStage !== "await_code" && state.bombStage !== "await_reentry") {
      render();
      return;
    }

    if (candidate === state.bombExpectedCode) {
      state.bombAttempt = 0;
      if (state.bombStage === "await_code") {
        startBombCountdown(true);
      } else {
        startBombCountdown(false);
      }
      return;
    }

    handleWrongBombCode();
    return;
  }

  const char = keypadCharFromEvent(event);
  if (state.bombStage === "await_nfc") {
    if (char === "A") {
      state.bombStage = "await_code";
      state.bombInput = "";
      state.bombAttempt = 0;
      render();
    }
    return;
  }

  if (state.bombStage !== "await_code" && state.bombStage !== "await_reentry") {
    return;
  }

  if (!keyset.has(char)) {
    return;
  }

  if (state.bombInput.length >= BOMB_CODE_LENGTH) {
    return;
  }

  state.bombInput += char;
  render();
}

function startBunkerGame() {
  state.isInGame = true;
  state.phase = "bunker";

  state.bunkerBlueSeconds = 0;
  state.bunkerRedSeconds = 0;
  state.bunkerActiveTeam = null;
  state.bunkerWinner = null;
  state.bunkerSignalActive = false;

  logGPIO("Stop all blinkers");
  logGPIO("Turn off all outputs");
  logGPIO("LED stripe fill -> (0, 0, 0)");

  render();
  scheduleBunkerTick();
}

function setBunkerTeam(team) {
  if (state.bunkerWinner) {
    return;
  }

  state.bunkerActiveTeam = team;

  logGPIO("Stop all blinkers");
  logGPIO("Turn off all outputs");
  if (team === "red") {
    logGPIO("Pin 20 (RED) -> ON");
    logGPIO("Stripe base RGB -> (255, 0, 0)");
  } else {
    logGPIO("Pin 23 (BLUE) -> ON");
    logGPIO("Stripe base RGB -> (0, 0, 255)");
  }
  logGPIO("Stripe blinker started (mode=pulse, interval 0.28s)");

  render();
}

function scheduleBunkerTick() {
  if (state.bunkerTickTimeout) {
    return;
  }
  state.bunkerTickTimeout = setTimeout(tickBunker, 1000);
}

function tickBunker() {
  state.bunkerTickTimeout = null;

  if (state.phase !== "bunker") {
    return;
  }

  if (!state.bunkerWinner) {
    if (state.bunkerActiveTeam === "blue") {
      state.bunkerBlueSeconds += 1;
    }
    if (state.bunkerActiveTeam === "red") {
      state.bunkerRedSeconds += 1;
    }

    if (state.bunkerBlueSeconds >= BUNKER_TARGET_SECONDS) {
      state.bunkerWinner = "blue";
      state.bunkerActiveTeam = "blue";
    } else if (state.bunkerRedSeconds >= BUNKER_TARGET_SECONDS) {
      state.bunkerWinner = "red";
      state.bunkerActiveTeam = "red";
    }
  }

  render();
  if (!state.bunkerWinner) {
    scheduleBunkerTick();
  }
}

function scheduleBunkerSignal() {
  if (state.bunkerSignalTimeout) {
    return;
  }
  state.bunkerSignalTimeout = setTimeout(tickBunkerSignal, 220);
}

function tickBunkerSignal() {
  state.bunkerSignalTimeout = null;

  if (state.phase !== "bunker" || !state.bunkerSignalActive) {
    return;
  }

  beepOnce(120, 980);
  scheduleBunkerSignal();
}

function startBunkerSignal() {
  if (state.phase !== "bunker" || !state.bunkerWinner || state.bunkerSignalActive) {
    return;
  }

  state.bunkerSignalActive = true;
  render();
  scheduleBunkerSignal();
}

function stopBunkerSignal() {
  if (state.phase !== "bunker" || !state.bunkerSignalActive) {
    return;
  }

  state.bunkerSignalActive = false;
  clearTimeoutState("bunkerSignalTimeout");
  resetToMenu();
}

function handleBunkerKey(event) {
  if (isRedKey(event)) {
    setBunkerTeam("red");
    return;
  }

  if (isBlueKey(event)) {
    setBunkerTeam("blue");
  }
}

function startFlagGame() {
  state.isInGame = true;
  state.phase = "flag";
  state.flagTeam = null;

  logGPIO("Stop all blinkers");
  logGPIO("Turn off all outputs");
  logGPIO("LED stripe fill -> (0, 0, 0)");

  render();
}

function setFlagTeam(team) {
  state.flagTeam = team;

  logGPIO("Stop all blinkers");
  logGPIO("Turn off all outputs");
  if (team === "red") {
    logGPIO("Pin 20 (RED) -> ON");
    logGPIO("Stripe base RGB -> (255, 0, 0)");
  } else {
    logGPIO("Pin 23 (BLUE) -> ON");
    logGPIO("Stripe base RGB -> (0, 0, 255)");
  }
  logGPIO("Stripe blinker started (mode=pulse, interval 0.25s)");

  render();
}

function handleFlagKey(event) {
  if (isRedKey(event)) {
    setFlagTeam("red");
    return;
  }

  if (isBlueKey(event)) {
    setFlagTeam("blue");
  }
}

function shouldPreventDefault(event) {
  const upper = keypadCharFromEvent(event);
  if (event.key === "Enter" || event.key === "Delete" || event.key === "Backspace") {
    return true;
  }
  if (["#", "*", "1", "2", "3"].includes(upper)) {
    return true;
  }
  if (keyset.has(upper)) {
    return true;
  }
  return false;
}

window.addEventListener("keydown", (event) => {
  if (shouldPreventDefault(event)) {
    event.preventDefault();
  }

  ensureAudioContext();

  if (isHashKey(event)) {
    state.hashKeyDown = true;
    if (state.isInGame) {
      startHashHold();
    }
    return;
  }

  if (isStarKey(event)) {
    startBunkerSignal();
    return;
  }

  if (!state.isInGame) {
    handleMenuKey(event);
    return;
  }

  if (state.phase === "bomb") {
    handleBombKey(event);
    return;
  }

  if (state.phase === "bunker") {
    handleBunkerKey(event);
    return;
  }

  if (state.phase === "flag") {
    handleFlagKey(event);
  }
});

window.addEventListener("keyup", (event) => {
  if (isHashKey(event)) {
    state.hashKeyDown = false;
    stopHashHold();
    return;
  }

  if (isStarKey(event)) {
    stopBunkerSignal();
  }
});

logGPIO("Web preview initialized");
resetToMenu();
