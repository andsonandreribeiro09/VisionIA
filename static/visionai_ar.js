// ==============================
// 📌 CONFIG INICIAL
// ==============================
let paciente_id = JSON.parse(document.body.dataset.paciente);
let armacaoSelecionada = null;
let dp_armacao = 64; // pode vir do backend depois

const video = document.getElementById("video");
const canvas = document.getElementById("overlay");
const ctx = canvas.getContext("2d");

let glasses = new Image();
glasses.crossOrigin = "anonymous";

// ==============================
// 🎥 CAMERA
// ==============================
navigator.mediaDevices.getUserMedia({ video: true })
.then(stream => video.srcObject = stream)
.catch(err => console.error("Erro câmera:", err));

// ==============================
// 🖱️ SELEÇÃO ARMAÇÃO
// ==============================
document.querySelectorAll(".card").forEach(card => {
  card.addEventListener("click", function(e){
    e.preventDefault();

    document.querySelectorAll(".card").forEach(c => c.classList.remove("selecionado"));
    this.classList.add("selecionado");

    armacaoSelecionada = this.dataset.id;

    glasses.src = this.querySelector("img").src + '?' + Date.now();
  });
});

// ==============================
// 🧠 MEDIAPIPE
// ==============================
const faceMesh = new FaceMesh({
  locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}`
});

faceMesh.setOptions({
  maxNumFaces: 1,
  refineLandmarks: true,
  minDetectionConfidence: 0.7,
  minTrackingConfidence: 0.7
});

// PONTOS IMPORTANTES
const LEFT_EYE = 33;
const RIGHT_EYE = 263;

// ==============================
// 🔄 RESPONSIVO
// ==============================
function resizeVideoCanvas(){
  const ratio = video.videoWidth / video.videoHeight || 16/9;

  const width = Math.min(window.innerWidth * 0.9, 900);
  const height = width / ratio;

  video.width = width;
  video.height = height;

  canvas.width = width;
  canvas.height = height;
}

window.addEventListener("resize", resizeVideoCanvas);
video.addEventListener("loadedmetadata", resizeVideoCanvas);

// ==============================
// 🧠 SMOOTH (ANTI-TREMEDEIRA)
// ==============================
let smooth = {
  lx:null, ly:null,
  rx:null, ry:null
};

// ==============================
// 🎯 PROCESSAMENTO
// ==============================
function processFace(landmarks){

  // -----------------------------
  // OLHOS
  // -----------------------------
  const lx = landmarks[LEFT_EYE].x * canvas.width;
  const ly = landmarks[LEFT_EYE].y * canvas.height;

  const rx = landmarks[RIGHT_EYE].x * canvas.width;
  const ry = landmarks[RIGHT_EYE].y * canvas.height;

  // -----------------------------
  // SMOOTH
  // -----------------------------
  if(smooth.lx === null){
    smooth.lx = lx; smooth.ly = ly;
    smooth.rx = rx; smooth.ry = ry;
  }

  smooth.lx = 0.7*smooth.lx + 0.3*lx;
  smooth.ly = 0.7*smooth.ly + 0.3*ly;

  smooth.rx = 0.7*smooth.rx + 0.3*rx;
  smooth.ry = 0.7*smooth.ry + 0.3*ry;

  // -----------------------------
  // DISTÂNCIA ENTRE OLHOS (px)
  // -----------------------------
  const dx = smooth.rx - smooth.lx;
  const dy = smooth.ry - smooth.ly;
  const distancia = Math.sqrt(dx*dx + dy*dy);

  // -----------------------------
  // LARGURA DO ROSTO (REAL)
  // -----------------------------
  const faceLeft = landmarks[234].x * canvas.width;
  const faceRight = landmarks[454].x * canvas.width;

  const faceWidth = Math.abs(faceRight - faceLeft);

  // escala aproximada real (mm)
  const escala = 140 / Math.max(faceWidth, 1);

  // -----------------------------
  // MEDIDAS REAIS
  // -----------------------------
  const dp_mm = distancia * escala;

  const centerX = (smooth.lx + smooth.rx) / 2;

  const dnp_e = Math.abs(smooth.lx - centerX) * escala;
  const dnp_d = Math.abs(smooth.rx - centerX) * escala;

  // -----------------------------
  // POSIÇÃO ÓCULOS
  // -----------------------------
  const centerY = (smooth.ly + smooth.ry) / 2;

  const width = distancia * 2.2;
  const height = width * 0.45;

  // -----------------------------
  // DESENHAR ÓCULOS
  // -----------------------------
  if(glasses.complete && glasses.naturalWidth !== 0){
    ctx.drawImage(
      glasses,
      centerX - width/2,
      centerY - height/2,
      width,
      height
    );
  }

  // -----------------------------
  // SCORE DE ENCAIXE
  // -----------------------------
  let score = Math.max(0, 100 - Math.abs(dp_mm - dp_armacao) * 1.5);

  document.getElementById("score").innerText = score.toFixed(0);

  // -----------------------------
  // STATUS
  // -----------------------------
  let status = "Posição OK";
  let cor = "#22c55e";

  if(dp_mm < 55 || dp_mm > 75){
    status = "Aproxime ou afaste o rosto";
    cor = "#ef4444";
  }

  document.getElementById("status").innerText = status;

  // -----------------------------
  // GUIA VISUAL
  // -----------------------------
  ctx.strokeStyle = cor;
  ctx.lineWidth = 2;

  ctx.beginPath();
  ctx.ellipse(
    canvas.width/2,
    canvas.height/2,
    canvas.width*0.25,
    canvas.height*0.35,
    0,
    0,
    Math.PI*2
  );
  ctx.stroke();

  // -----------------------------
  // ATUALIZA UI
  // -----------------------------
  document.getElementById("dp").innerText = dp_mm.toFixed(1);
  document.getElementById("dnp_e").innerText = dnp_e.toFixed(1);
  document.getElementById("dnp_d").innerText = dnp_d.toFixed(1);
}

// ==============================
// 🔄 LOOP MEDIAPIPE
// ==============================
faceMesh.onResults((results)=>{
  ctx.clearRect(0,0,canvas.width,canvas.height);

  if(!results.multiFaceLandmarks.length) return;

  processFace(results.multiFaceLandmarks[0]);
});

// ==============================
// 🎥 CAMERA LOOP
// ==============================
const cameraMP = new Camera(video,{
  onFrame: async ()=> await faceMesh.send({image: video}),
  width: 640,
  height: 480
});

cameraMP.start();

// ==============================
// 💾 SALVAR
// ==============================
function finalizar(){

  if(!paciente_id){
    alert("Paciente não encontrado");
    return;
  }

  if(!armacaoSelecionada){
    alert("Escolha uma armação!");
    return;
  }

  fetch("/salvar_medicao",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({
      paciente_id: paciente_id,
      armacao_id: armacaoSelecionada,
      dp: parseFloat(document.getElementById("dp").innerText),
      dnp_e: parseFloat(document.getElementById("dnp_e").innerText),
      dnp_d: parseFloat(document.getElementById("dnp_d").innerText),
      score: parseFloat(document.getElementById("score").innerText)
    })
  })
  .then(res => res.json())
  .then(res => {
    if(res.status === "ok"){
      window.location.href = "/dashboard/" + paciente_id;
    } else {
      alert("Erro ao salvar");
    }
  })
  .catch(err => console.error(err));
}