(() => {
  const root = document.querySelector("[data-scanner]");
  if (!root) {
    return;
  }

  const video = root.querySelector(".scanner-video");
  const status = root.querySelector("[data-scanner-status]");
  const startButton = root.querySelector("[data-scan-start]");
  const stopButton = root.querySelector("[data-scan-stop]");
  const imageInput = root.querySelector("[data-scan-image]");
  const form = root.querySelector("[data-scan-form]");
  const input = root.querySelector("[data-scan-input]");

  let stream = null;
  let detector = null;
  let active = false;
  let frameRequest = null;

  function setStatus(message) {
    status.textContent = message;
  }

  function stopScanner() {
    active = false;
    if (frameRequest) {
      cancelAnimationFrame(frameRequest);
      frameRequest = null;
    }
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }
    video.srcObject = null;
    setStatus("Camera stopped. You can still paste a QR value or decode an image.");
  }

  async function detectFrame() {
    if (!active || !detector) {
      return;
    }
    try {
      const codes = await detector.detect(video);
      if (codes.length > 0 && codes[0].rawValue) {
        input.value = codes[0].rawValue;
        form.submit();
        return;
      }
    } catch (error) {
      setStatus("The browser could not read that frame. Trying again...");
    }
    frameRequest = requestAnimationFrame(detectFrame);
  }

  async function startScanner() {
    if (!("BarcodeDetector" in window)) {
      setStatus("Live camera scanning is not available in this browser. Paste the QR value or upload an image instead.");
      return;
    }
    try {
      detector = new window.BarcodeDetector({ formats: ["qr_code"] });
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      video.srcObject = stream;
      await video.play();
      active = true;
      setStatus("Point the camera at a QR badge.");
      detectFrame();
    } catch (error) {
      setStatus("The camera could not be started. Check permissions or use the manual fallback.");
    }
  }

  async function decodeImage(file) {
    if (!file) {
      return;
    }
    if (!("BarcodeDetector" in window)) {
      setStatus("Image decoding is not supported in this browser. Paste the QR value instead.");
      return;
    }
    try {
      detector = detector || new window.BarcodeDetector({ formats: ["qr_code"] });
      const bitmap = await createImageBitmap(file);
      const codes = await detector.detect(bitmap);
      if (!codes.length || !codes[0].rawValue) {
        setStatus("No QR code was found in that image.");
        return;
      }
      input.value = codes[0].rawValue;
      form.submit();
    } catch (error) {
      setStatus("That image could not be decoded. Try another photo or paste the QR value.");
    }
  }

  startButton?.addEventListener("click", startScanner);
  stopButton?.addEventListener("click", stopScanner);
  imageInput?.addEventListener("change", (event) => {
    const [file] = event.target.files || [];
    decodeImage(file);
  });
  window.addEventListener("beforeunload", stopScanner);
})();
