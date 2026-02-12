const titleEl = document.getElementById("title");
const contentEl = document.getElementById("content");
const logsEl = document.getElementById("logs");

const EXIT_CODE = "6969";
const games = ["Bombe", "Bunker", "Flagge"];
const diffs = ["Easy", "Medium", "Hard"];
const times = [5, 10, 15];
const keyset = new Set("0123456789ABCD".split(""));

const state = {
  phase: "menu",
  step: 0,
  selection: -1,
  selectedGame: null,
  selectedDiff: null,
  selectedTime: null,
  input: "",
  armed: false,
  armCode: "",
  defCode: "",
  bombArmTries: 3,
  bombDefTries: 3,
  bombRemaining: 0,
  bombHalfTriggered: false,
  bombInterval: null,
  bunkerInterval: null,
  blueSeconds: 0,
  redSeconds: 0,
  activeTeam: null,
};

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

function clearIntervals() {
  if (state.bombInterval) {
    clearInterval(state.bombInterval);
    state.bombInterval = null;
  }
  if (state.bunkerInterval) {
    clearInterval(state.bunkerInterval);
    state.bunkerInterval = null;
  }
}

function resetToMenu() {
  clearIntervals();
  state.phase = "menu";
  state.step = 0;
  state.selection = -1;
  state.selectedGame = null;
  state.selectedDiff = null;
  state.selectedTime = null;
  state.input = "";
  state.armed = false;
  state.bombArmTries = 3;
  state.bombDefTries = 3;
  state.bombRemaining = 0;
  state.bombHalfTriggered = false;
  state.blueSeconds = 0;
  state.redSeconds = 0;
  state.activeTeam = null;
  logGPIO("Reset state to main menu");
  render();
}

function startBombDefusePhase() {
  state.armed = true;
  state.input = "";
  state.bombRemaining = state.selectedTime * 60;
  state.bombHalfTriggered = false;

  logGPIO("Stop all blinkers");
  logGPIO("Turn off all outputs");
  logGPIO("Blue blinker started");
  logGPIO("Stripe base RGB -> (0, 255, 0)");
  logGPIO("Stripe blinker started (mode=pulse)");

  state.bombInterval = setInterval(() => {
    state.bombRemaining -= 1;
    if (!state.bombHalfTriggered && state.bombRemaining <= (state.selectedTime * 60) / 2) {
      state.bombHalfTriggered = true;
      logGPIO("Blue blinker stopped");
      logGPIO("Red blinker started");
    }

    if (state.bombRemaining <= 0) {
      clearInterval(state.bombInterval);
      state.bombInterval = null;
      logGPIO("Stop all blinkers");
      logGPIO("Turn off all outputs");
      logGPIO("Pin 20 (RED) -> ON");
      logGPIO("LED stripe fill -> (255, 0, 0)");
      alert("Bombe ist explodiert");
      resetToMenu();
      return;
    }

    render();
  }, 1000);
}

function renderMenu() {
  const title = state.step === 0 ? "Spielauswahl:" : state.step === 1 ? "Schwierigkeit:" : "Zeit:";
  const options = state.step === 0 ? games : state.step === 1 ? diffs : times.map((t) => `${t} Min`);

  titleEl.textContent = title;
  contentEl.innerHTML = options
    .map((option, i) => {
      const arrow = state.selection === i ? "<span class=\"arrow\">\u2190</span>" : "<span class=\"arrow\"></span>";
      return `<div class=\"option\">${arrow}<span>${i + 1}: ${option}</span></div>`;
    })
    .join("");
}

function renderBomb() {
  const mins = String(Math.floor(state.bombRemaining / 60)).padStart(2, "0");
  const secs = String(state.bombRemaining % 60).padStart(2, "0");

  if (!state.armed) {
    titleEl.textContent = "Bombe legen";
    contentEl.textContent = `Code: ${state.armCode}\nEingabe: ${state.input}\nVersuche: ${state.bombArmTries}\n(Enter=bestätigen, Delete=löschen, 6969=menü)`;
    return;
  }

  titleEl.textContent = `Timer: ${mins}:${secs}`;
  contentEl.textContent = `Defuse Code: ${state.defCode}\nEingabe: ${state.input}\nVersuche: ${state.bombDefTries}\n(Enter=bestätigen, Delete=löschen, 6969=menü)`;
}

function renderBunker() {
  const target = state.selectedTime * 60;
  titleEl.textContent = "Bunker";
  contentEl.textContent = `Blue: ${state.blueSeconds}s / ${target}s\nRed: ${state.redSeconds}s / ${target}s\nAktiv: ${state.activeTeam || "keiner"}\nExit-Eingabe: ${state.input}\n(Delete=Red, Enter=Blue, tick automatisch)`;
}

function renderFlag() {
  titleEl.textContent = "Flagge";
  contentEl.textContent = `Status: ${state.activeTeam ? state.activeTeam.toUpperCase() : "NONE"}\nExit-Eingabe: ${state.input}\n(Delete=RED, Enter=BLUE, 6969=menü)`;
}

function render() {
  if (state.phase === "menu") renderMenu();
  if (state.phase === "bomb") renderBomb();
  if (state.phase === "bunker") renderBunker();
  if (state.phase === "flag") renderFlag();
}

function handleMenuKey(key) {
  if (["1", "2", "3"].includes(key)) {
    state.selection = Number(key) - 1;
    render();
    return;
  }

  if (key === "Enter" && state.selection >= 0) {
    if (state.step === 0) {
      state.selectedGame = games[state.selection];
      state.step = 1;
      state.selection = -1;
      render();
      return;
    }

    if (state.step === 1) {
      state.selectedDiff = diffs[state.selection];
      state.step = 2;
      state.selection = -1;
      render();
      return;
    }

    state.selectedTime = times[state.selection];
    state.selection = -1;

    if (state.selectedGame === "Bombe") {
      state.phase = "bomb";
      state.armed = false;
      state.input = "";
      state.armCode = randomCode(16);
      state.defCode = randomCode(16);
      state.bombArmTries = 3;
      state.bombDefTries = 3;
      logGPIO("Pin 23 (BLUE) -> ON");
    } else if (state.selectedGame === "Bunker") {
      state.phase = "bunker";
      state.input = "";
      state.blueSeconds = 0;
      state.redSeconds = 0;
      state.activeTeam = null;
      state.bunkerInterval = setInterval(() => {
        if (state.activeTeam === "blue") state.blueSeconds += 1;
        if (state.activeTeam === "red") state.redSeconds += 1;

        const target = state.selectedTime * 60;
        if (state.blueSeconds >= target) {
          alert("Blue wins");
          resetToMenu();
          return;
        }

        if (state.redSeconds >= target) {
          alert("Red wins");
          resetToMenu();
          return;
        }

        render();
      }, 1000);
    } else {
      state.phase = "flag";
      state.input = "";
      state.activeTeam = null;
    }

    render();
    return;
  }

  if (key === "Backspace" || key === "Delete") {
    if (state.step > 0) {
      state.step -= 1;
      state.selection = -1;
      render();
    }
  }
}

function handleBombKey(key) {
  if (key === "Backspace" || key === "Delete") {
    state.input = "";
    render();
    return;
  }

  if (key === "Enter") {
    if (state.input === EXIT_CODE) {
      resetToMenu();
      return;
    }

    if (!state.armed) {
      if (state.input === state.armCode) {
        startBombDefusePhase();
      } else {
        state.bombArmTries -= 1;
        if (state.bombArmTries <= 0) {
          alert("Zu viele Versuche. Bombe deaktiviert.");
          resetToMenu();
          return;
        }
      }
    } else if (state.input === state.defCode) {
      logGPIO("Stop all blinkers");
      logGPIO("LED stripe fill -> (0, 255, 0)");
      alert("Bombe entschärft");
      resetToMenu();
      return;
    } else {
      state.bombDefTries -= 1;
      if (state.bombDefTries <= 0) {
        logGPIO("Stop all blinkers");
        logGPIO("LED stripe fill -> (255, 0, 0)");
        alert("Zu viele Versuche. Bombe explodiert.");
        resetToMenu();
        return;
      }
    }

    state.input = "";
    render();
    return;
  }

  const upper = key.toUpperCase();
  if (keyset.has(upper)) {
    if (state.input.length < 16) state.input += upper;
    render();
  }
}

function handleBunkerKey(key) {
  if (key === "Backspace" || key === "Delete") {
    state.input = "";
    state.activeTeam = "red";
    logGPIO("Pin 20 (RED) -> ON");
    logGPIO("Pin 23 (BLUE) -> OFF");
    logGPIO("LED stripe fill -> (255, 0, 0)");
    render();
    return;
  }

  if (key === "Enter") {
    if (state.input === EXIT_CODE) {
      resetToMenu();
      return;
    }

    state.input = "";
    state.activeTeam = "blue";
    logGPIO("Pin 20 (RED) -> OFF");
    logGPIO("Pin 23 (BLUE) -> ON");
    logGPIO("LED stripe fill -> (0, 0, 255)");
    render();
    return;
  }

  const upper = key.toUpperCase();
  if (keyset.has(upper)) {
    if (state.input.length < 4) state.input += upper;
    render();
  }
}

function handleFlagKey(key) {
  if (key === "Backspace" || key === "Delete") {
    state.input = "";
    state.activeTeam = "red";
    logGPIO("LED stripe fill -> (255, 0, 0)");
    logGPIO("Pin 20 (RED) -> ON");
    logGPIO("Pin 23 (BLUE) -> OFF");
    render();
    return;
  }

  if (key === "Enter") {
    if (state.input === EXIT_CODE) {
      resetToMenu();
      return;
    }

    state.input = "";
    state.activeTeam = "blue";
    logGPIO("Pin 20 (RED) -> OFF");
    logGPIO("Pin 23 (BLUE) -> ON");
    logGPIO("LED stripe fill -> (0, 0, 255)");
    render();
    return;
  }

  const upper = key.toUpperCase();
  if (keyset.has(upper)) {
    if (state.input.length < 4) state.input += upper;
    render();
  }
}

const actionKeys = new Set(["Enter", "Backspace", "Delete", "1", "2", "3"]);

window.addEventListener("keydown", (event) => {
  const key = event.key;
  const upper = key.toUpperCase?.() || key;
  if (actionKeys.has(key) || keyset.has(upper)) {
    event.preventDefault();
  }

  if (state.phase === "menu") {
    handleMenuKey(key);
    return;
  }
  if (state.phase === "bomb") {
    handleBombKey(key);
    return;
  }
  if (state.phase === "bunker") {
    handleBunkerKey(key);
    return;
  }
  if (state.phase === "flag") {
    handleFlagKey(key);
  }
});

logGPIO("Web preview initialized");
render();
