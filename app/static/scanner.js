(() => {
  const root = document.querySelector("[data-scanner]");
  if (!root) {
    return;
  }

  const reader = root.querySelector("[data-scan-reader]");
  const status = root.querySelector("[data-scanner-status]");
  const startButton = root.querySelector("[data-scan-start]");
  const stopButton = root.querySelector("[data-scan-stop]");
  const form = root.querySelector("[data-scan-form]");
  const input = root.querySelector("[data-scan-input]");

  let scanner = null;
  let scanning = false;
  let busy = false;

  function setStatus(message) {
    status.textContent = message;
  }

  function scannerAvailable() {
    return typeof window.Html5Qrcode === "function" && form && input;
  }

  function supportedFormats() {
    const qrFormat = window.Html5QrcodeSupportedFormats?.QR_CODE;
    return qrFormat ? [qrFormat] : undefined;
  }

  function createScanner() {
    if (!scanner) {
      scanner = new window.Html5Qrcode(
        reader.id,
        supportedFormats() ? { formatsToSupport: supportedFormats() } : undefined,
      );
    }
    return scanner;
  }

  async function resetScanner() {
    if (!scanner) {
      reader.innerHTML = "";
      return;
    }

    if (scanning) {
      try {
        await scanner.stop();
      } catch (error) {
        // Ignore stop failures and continue cleanup.
      }
    }

    try {
      await scanner.clear();
    } catch (error) {
      // Ignore clear failures and continue resetting state.
    }

    scanner = null;
    scanning = false;
    reader.innerHTML = "";
  }

  function chooseCamera(cameras) {
    if (!Array.isArray(cameras) || cameras.length === 0) {
      return null;
    }

    const backCamera = cameras.find((camera) => /back|rear|environment|wide/i.test(camera.label || ""));
    return backCamera || cameras[cameras.length - 1];
  }

  function buildScanConfig() {
    const size = Math.max(180, Math.min(reader.clientWidth || 280, 260));
    return {
      fps: 10,
      qrbox: { width: size, height: size },
      aspectRatio: 4 / 3,
      disableFlip: true,
    };
  }

  async function startWithConfig(cameraConfig) {
    const instance = createScanner();
    await instance.start(
      cameraConfig,
      buildScanConfig(),
      (decodedText) => {
        input.value = decodedText;
        setStatus("QR code found. Opening character...");
        void resetScanner();
        form.submit();
      },
      () => {
        // Scanning failures are expected while no QR code is in frame.
      },
    );
    scanning = true;
  }

  async function startScanner() {
    if (busy) {
      return;
    }
    if (!scannerAvailable()) {
      setStatus("Live camera scanning could not load in this browser.");
      return;
    }

    busy = true;
    try {
      await resetScanner();
      setStatus("Requesting camera access...");

      try {
        await startWithConfig({ facingMode: { ideal: "environment" } });
      } catch (facingModeError) {
        await resetScanner();
        const cameras = await window.Html5Qrcode.getCameras();
        const camera = chooseCamera(cameras);
        if (!camera) {
          throw facingModeError;
        }
        await startWithConfig({ deviceId: { exact: camera.id } });
      }

      setStatus("Point the camera at a QR badge.");
    } catch (error) {
      setStatus("The camera could not be started. Check permissions and try again.");
    } finally {
      busy = false;
    }
  }

  async function stopScanner() {
    if (busy) {
      return;
    }
    busy = true;
    try {
      await resetScanner();
      setStatus("Camera stopped.");
    } finally {
      busy = false;
    }
  }

  startButton?.addEventListener("click", () => {
    void startScanner();
  });
  stopButton?.addEventListener("click", () => {
    void stopScanner();
  });
  window.addEventListener("beforeunload", () => {
    void resetScanner();
  });
})();
