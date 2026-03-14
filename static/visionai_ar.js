const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");

canvas.width = 900;
canvas.height = 650;

const glasses = new Image();
glasses.src = "/static/armacoes/armacao1.png";

const faceMesh = new FaceMesh({
  locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}`,
});

faceMesh.setOptions({
  maxNumFaces: 1,
  refineLandmarks: true,
  minDetectionConfidence: 0.7,
  minTrackingConfidence: 0.7,
});

faceMesh.onResults((results) => {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (results.image) ctx.drawImage(results.image, 0, 0, canvas.width, canvas.height);

  if (results.multiFaceLandmarks && results.multiFaceLandmarks.length > 0) {
    const landmarks = results.multiFaceLandmarks[0];
    const leftEye = landmarks[33];
    const rightEye = landmarks[263];

    const lx = leftEye.x * canvas.width;
    const ly = leftEye.y * canvas.height;
    const rx = rightEye.x * canvas.width;
    const ry = rightEye.y * canvas.height;

    const width = Math.abs(rx - lx) * 2.2;
    const height = width / 2;
    const x = (lx + rx) / 2 - width / 2;
    const y = ly - height / 2;

    ctx.drawImage(glasses, x, y, width, height);
  }
});

const camera = new Camera(video, {
  onFrame: async () => {
    await faceMesh.send({ image: video });
  },
  width: 640,
  height: 480,
});

camera.start();