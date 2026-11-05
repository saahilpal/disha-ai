// Disha AI — Personal Health Coach Frontend Controller
// Pure JavaScript, zero external framework dependencies, clean 2-screen architecture

let currentPatientId = localStorage.getItem("disha_patient_id") || "pt_" + Math.random().toString(36).substring(2, 9);
if (!localStorage.getItem("disha_patient_id")) {
  localStorage.setItem("disha_patient_id", currentPatientId);
}
let currentSessionId = "sess_" + Math.random().toString(36).substring(2, 9);
let turnCounter = 1;
let dialogueHistory = [];

// Voice & Audio States
let isVoiceSessionActive = false;
let isAudioPlaying = false;
let currentAudio = null;
let mediaRecorder = null;
let audioChunks = [];
let micStream = null;
let isChatMicRecording = false;
let chatMediaRecorder = null;
let chatAudioChunks = [];

const API_BASE = window.location.origin;

// -------------------------------------------------------------
// 1. INITIALIZATION & SETUP
// -------------------------------------------------------------

document.addEventListener("DOMContentLoaded", async () => {
  if (window.lucide) lucide.createIcons();

  // Load patient context, persistent chat history, and active AI model settings
  await Promise.all([
    loadPatientProfile(currentPatientId),
    loadConversationHistory(currentPatientId),
    loadApiKeySettings()
  ]);
});

async function loadConversationHistory(patientId) {
  try {
    const res = await fetch(`${API_BASE}/conversations/${patientId}`);
    if (res.ok) {
      const data = await res.json();
      const messages = data.messages || [];
      if (messages.length > 0) {
        const container = document.getElementById("chat-messages-scroll");
        if (container) {
          container.innerHTML = "";
          dialogueHistory = [];
          for (const m of messages) {
            appendChatMessage(m.role, m.content, m.source === "voice" ? "Voice Call" : null);
            dialogueHistory.push({ role: m.role, content: m.content });
          }
        }
      }
    }
  } catch (err) {
    console.error("Failed to load conversation history:", err);
  }
}

// -------------------------------------------------------------
// 2. TWO-SCREEN NAVIGATION (Chat & Profile only)
// -------------------------------------------------------------

function navigateTo(viewName) {
  const isChat = viewName === "chat";
  
  const chatView = document.getElementById("view-chat");
  const profileView = document.getElementById("view-profile");
  const navChat = document.getElementById("nav-chat");
  const navProfile = document.getElementById("nav-profile");

  if (chatView) chatView.classList.toggle("hidden", !isChat);
  if (profileView) profileView.classList.toggle("hidden", isChat);

  if (navChat) {
    if (isChat) {
      navChat.className = "nav-btn px-4 py-2 rounded-xl text-primary bg-primary-light transition-all flex items-center space-x-1.5 font-semibold";
    } else {
      navChat.className = "nav-btn px-4 py-2 rounded-xl text-onSurface-variant hover:text-onSurface hover:bg-surface-low transition-all flex items-center space-x-1.5 font-semibold";
    }
  }

  if (navProfile) {
    if (!isChat) {
      navProfile.className = "nav-btn px-4 py-2 rounded-xl text-primary bg-primary-light transition-all flex items-center space-x-1.5 font-semibold";
    } else {
      navProfile.className = "nav-btn px-4 py-2 rounded-xl text-onSurface-variant hover:text-onSurface hover:bg-surface-low transition-all flex items-center space-x-1.5 font-semibold";
    }
  }

  if (!isChat) {
    populateProfileForm();
  }

  if (window.lucide) lucide.createIcons();
}

// -------------------------------------------------------------
// 3. CONSULTATION CHAT & STREAMING (Screen 1)
// -------------------------------------------------------------

async function handleChatSubmit(event) {
  if (event) event.preventDefault();
  const input = document.getElementById("chat-text-input");
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;

  input.value = "";
  await processChatTurn(text);
}

function sendQuickPrompt(promptText) {
  const input = document.getElementById("chat-text-input");
  if (input) input.value = promptText;
  navigateTo("chat");
  processChatTurn(promptText);
}

async function processChatTurn(utterance) {
  // Append user bubble to UI
  appendChatMessage("user", utterance);
  dialogueHistory.push({ role: "user", content: utterance });

  // Show typing indicator
  showChatTypingIndicator(true, getContextualFillerText(utterance));

  // Create an assistant response placeholder for streaming tokens
  const assistantBubbleInfo = createStreamingAssistantBubble();

  let accumulated = "";
  let isStreamSuccess = false;
  let sourceChips = [];

  try {
    // Attempt Server-Sent Events (SSE) streaming
    const res = await fetch(`${API_BASE}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        patient_id: currentPatientId,
        utterance: utterance,
        session_id: currentSessionId,
        turn_number: turnCounter++,
        history: dialogueHistory.slice(-6)
      })
    });

    if (res.ok && res.body) {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      showChatTypingIndicator(false);
      isStreamSuccess = true;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); // keep last incomplete line

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data:")) continue;

          const dataStr = trimmed.slice(5).trim();
          if (dataStr === "[DONE]") break;

          try {
            const parsed = JSON.parse(dataStr);
            if (parsed.type === "token") {
              accumulated += parsed.token;
              updateStreamingBubbleText(assistantBubbleInfo, accumulated);
            } else if (parsed.type === "replace_all") {
              accumulated = parsed.text;
              updateStreamingBubbleText(assistantBubbleInfo, accumulated);
            } else if (parsed.type === "emergency") {
              accumulated = parsed.text;
              updateStreamingBubbleText(assistantBubbleInfo, accumulated);
              showEmergencyBanner(parsed.text);
            }
          } catch (e) {
            // Raw text fallback
          }
        }
      }
    }
  } catch (err) {
    // Stream error, fallback to standard POST /chat
  }

  // Fallback to standard /chat if streaming was not successful
  if (!isStreamSuccess || !accumulated.trim()) {
    try {
      const fallbackRes = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: currentPatientId,
          utterance: utterance,
          session_id: currentSessionId,
          turn_number: turnCounter++,
          history: dialogueHistory.slice(-6)
        })
      });

      showChatTypingIndicator(false);

      if (fallbackRes.ok) {
        const data = await fallbackRes.json();
        accumulated = data.final_response;
        updateStreamingBubbleText(assistantBubbleInfo, accumulated);

        if (data.is_emergency) {
          showEmergencyBanner(data.final_response);
        } else {
          hideEmergencyBanner();
        }
      } else {
        accumulated = "Mujhe connect karne mein pareshani ho rahi hai. Kripya apna connection check karke dobara puchein.";
        updateStreamingBubbleText(assistantBubbleInfo, accumulated);
      }
    } catch (fallbackErr) {
      showChatTypingIndicator(false);
      accumulated = "Server response error. Please verify your connection.";
      updateStreamingBubbleText(assistantBubbleInfo, accumulated);
    }
  }

  // Detect and append clinical source attribution chips
  sourceChips = detectClinicalChips(utterance, accumulated);
  appendSourceChipsToBubble(assistantBubbleInfo, sourceChips);

  // Sync to dialogue history
  dialogueHistory.push({ role: "assistant", content: accumulated });

  // Update voice modal subtitle for shared context
  updateVoiceSubtitle(accumulated);

  // Auto-scroll to bottom
  const container = document.getElementById("chat-messages-scroll");
  if (container) container.scrollTop = container.scrollHeight;
  if (window.lucide) lucide.createIcons();
}

function detectClinicalChips(utterance, response) {
  const chips = [];
  const text = (utterance + " " + response).toLowerCase();

  if (text.includes("bloat") || text.includes("period") || text.includes("jeera") || text.includes("saunf")) {
    chips.push("Doctor Approved Remedy: Jeera Water & Saunf");
    chips.push("ICMR Nutritional Guidelines (2024)");
  }
  if (text.includes("mango") || text.includes("aam")) {
    chips.push("Clinical Stance: Seasonal Moderation (100g)");
  }
  if (text.includes("dinner") || text.includes("paneer bhurji") || text.includes("diet chart")) {
    chips.push("Grounded: Patient Meal Plan Database");
  }
  if (text.includes("gym") || text.includes("squat") || text.includes("clearance") || text.includes("pep")) {
    chips.push("PEP Clearance: Doctor Supervised Exercise");
  }
  if (text.includes("paid") || text.includes("subscription") || text.includes("price") || text.includes("free")) {
    chips.push("Verified Pricing Policy");
  }
  if (chips.length === 0) {
    chips.push("Clinically Grounded Protocol");
  }
  return chips;
}

function createStreamingAssistantBubble() {
  const container = document.getElementById("chat-messages-scroll");
  if (!container) return null;

  const msgDiv = document.createElement("div");
  msgDiv.className = "flex items-start space-x-3 max-w-3xl";
  
  const bubbleId = "bubble-" + Math.random().toString(36).substring(2, 9);
  const textId = "text-" + bubbleId;
  const chipsId = "chips-" + bubbleId;

  msgDiv.id = bubbleId;
  msgDiv.innerHTML = `
    <div class="w-9 h-9 rounded-xl bg-primary text-white flex items-center justify-center shrink-0 shadow-xs mt-1">
      <i data-lucide="spa" class="w-4 h-4 text-emerald-200"></i>
    </div>
    <div class="flex-1 bg-surface-card border border-surface-border rounded-2xl rounded-tl-xs p-5 text-onSurface text-sm space-y-3 shadow-xs">
      <div class="flex items-center justify-between pb-2 border-b border-surface-border">
        <span class="text-[11px] font-bold text-primary flex items-center gap-1.5">
          <span>Disha AI Clinician</span>
          <span class="px-2 py-0.5 rounded-full bg-secondary-container text-primary-dark text-[10px]">Integrative Protocol</span>
        </span>
        <span class="text-[11px] text-onSurface-variant">Just now</span>
      </div>
      <div id="${textId}" class="leading-relaxed space-y-2 text-onSurface">
        <span class="inline-block w-2 h-4 bg-primary/40 animate-pulse"></span>
      </div>
      <div id="${chipsId}" class="pt-2 flex flex-wrap gap-1.5 text-[11px]"></div>
    </div>
  `;

  container.appendChild(msgDiv);
  container.scrollTop = container.scrollHeight;
  if (window.lucide) lucide.createIcons();

  return { bubbleId, textId, chipsId };
}

function updateStreamingBubbleText(bubbleInfo, text) {
  if (!bubbleInfo) return;
  const el = document.getElementById(bubbleInfo.textId);
  if (el) {
    el.innerHTML = formatMessageContent(text);
  }
}

function appendSourceChipsToBubble(bubbleInfo, chips) {
  if (!bubbleInfo || !chips || chips.length === 0) return;
  const el = document.getElementById(bubbleInfo.chipsId);
  if (!el) return;

  el.innerHTML = chips.map(chip => `
    <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-surface-low border border-surface-border text-onSurface-variant font-medium text-[11px]">
      <i data-lucide="check-circle-2" class="w-3 h-3 text-primary"></i>
      <span>${escapeHtml(chip)}</span>
    </span>
  `).join("");

  if (window.lucide) lucide.createIcons();
}

function appendChatMessage(role, text, sourceBadge = null) {
  const container = document.getElementById("chat-messages-scroll");
  if (!container) return;

  const msgDiv = document.createElement("div");
  msgDiv.className = role === "user" ? "flex justify-end" : "flex items-start space-x-3 max-w-2xl";

  const badgeHtml = sourceBadge
    ? `<span class="ml-2 px-1.5 py-0.5 rounded-full bg-secondary-container text-primary-dark text-[9px] font-semibold tracking-wide uppercase">${escapeHtml(sourceBadge)}</span>`
    : "";

  if (role === "user") {
    msgDiv.innerHTML = `
      <div class="bg-primary text-white rounded-2xl rounded-tr-xs px-5 py-3 text-sm shadow-xs max-w-lg leading-relaxed">
        <div class="flex items-center justify-between gap-2 mb-1">
          <span class="text-[10px] text-emerald-200">You</span>
          ${sourceBadge ? `<span class="text-[9px] bg-emerald-800 text-emerald-100 px-1.5 py-0.5 rounded">${escapeHtml(sourceBadge)}</span>` : ""}
        </div>
        <p>${formatMessageContent(text)}</p>
      </div>
    `;
  } else {
    msgDiv.innerHTML = `
      <div class="w-9 h-9 rounded-xl bg-primary text-white flex items-center justify-center shrink-0 shadow-xs mt-1">
        <i data-lucide="spa" class="w-4 h-4 text-emerald-200"></i>
      </div>
      <div class="bg-surface-card border border-surface-border rounded-2xl rounded-tl-xs p-5 text-onSurface text-sm space-y-2 shadow-xs">
        <div class="flex items-center justify-between pb-2 border-b border-surface-border">
          <span class="text-[11px] font-bold text-primary flex items-center">
            <span>Disha AI Clinician</span>
            ${badgeHtml}
          </span>
          <span class="text-[11px] text-onSurface-variant">Active</span>
        </div>
        <div class="leading-relaxed">${formatMessageContent(text)}</div>
      </div>
    `;
  }

  container.appendChild(msgDiv);
  container.scrollTop = container.scrollHeight;
  if (window.lucide) lucide.createIcons();
}

async function clearConversation() {
  dialogueHistory = [];
  try {
    await fetch(`${API_BASE}/conversations/${currentPatientId}`, { method: "DELETE" });
  } catch (e) {}
  const container = document.getElementById("chat-messages-scroll");
  if (container) {
    container.innerHTML = `
      <div class="flex items-start space-x-3 max-w-2xl">
        <div class="w-9 h-9 rounded-xl bg-primary text-white flex items-center justify-center shrink-0 shadow-xs">
          <i data-lucide="spa" class="w-4 h-4 text-emerald-200"></i>
        </div>
        <div class="bg-surface-low border border-surface-border rounded-2xl rounded-tl-xs p-5 text-onSurface text-sm space-y-2 shadow-xs">
          <div class="flex items-center justify-between pb-2 border-b border-surface-border">
            <span class="text-[11px] font-bold text-primary flex items-center gap-1.5">
              <span>Disha AI Clinician</span>
              <span class="px-2 py-0.5 rounded-full bg-secondary-container text-primary-dark text-[10px]">Integrative Protocol</span>
            </span>
            <span class="text-[11px] text-onSurface-variant">Active</span>
          </div>
          <p class="leading-relaxed">
            Aaj aapki diet, workout ya health routine mein kahan guidance chahiye? Feel free to ask anything in Hindi, Hinglish, or English.
          </p>
        </div>
      </div>
    `;
  }
  hideEmergencyBanner();
  if (window.lucide) lucide.createIcons();
}

function getContextualFillerText(text) {
  const lower = text.toLowerCase();
  if (lower.includes("dinner") || lower.includes("lunch") || lower.includes("meal") || lower.includes("khana")) {
    return "Looking up your scheduled meal plan...";
  }
  if (lower.includes("price") || lower.includes("paid") || lower.includes("subscription")) {
    return "Checking verified clinic pricing records...";
  }
  if (lower.includes("gym") || lower.includes("workout") || lower.includes("exercise")) {
    return "Reviewing your Personal Exercise Plan clearances...";
  }
  if (lower.includes("bloat") || lower.includes("period") || lower.includes("pain")) {
    return "Retrieving doctor-approved clinical remedies...";
  }
  return "Consulting clinical guidelines...";
}

function showChatTypingIndicator(show, text = "Disha is thinking...") {
  const container = document.getElementById("chat-messages-scroll");
  let el = document.getElementById("chat-typing-bubble");

  if (show) {
    if (!el && container) {
      el = document.createElement("div");
      el.id = "chat-typing-bubble";
      el.className = "flex items-center space-x-2 text-xs text-onSurface-variant italic pl-12 py-1.5";
      el.innerHTML = `<span class="w-2 h-2 rounded-full bg-primary animate-ping"></span> <span>${escapeHtml(text)}</span>`;
      container.appendChild(el);
      container.scrollTop = container.scrollHeight;
    }
  } else {
    if (el) el.remove();
  }
}

function showEmergencyBanner(msg) {
  const b = document.getElementById("chat-emergency-banner");
  const t = document.getElementById("chat-emergency-text");
  if (b && t) {
    t.textContent = msg;
    b.classList.remove("hidden");
  }
}

function hideEmergencyBanner() {
  const b = document.getElementById("chat-emergency-banner");
  if (b) b.classList.add("hidden");
}

function formatMessageContent(rawText) {
  if (!rawText) return "";
  let safe = escapeHtml(rawText);
  // Bold **text**
  safe = safe.replace(/\*\*(.*?)\*\*/g, '<strong class="text-primary-dark font-semibold">$1</strong>');
  // Newlines to line breaks
  safe = safe.replace(/\n/g, '<br>');
  return safe;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// -------------------------------------------------------------
// 4. CHAT MICROPHONE INPUT (Speech-to-Text)
// -------------------------------------------------------------

async function toggleChatMicRecording() {
  if (isChatMicRecording) {
    stopChatMicRecording();
  } else {
    await startChatMicRecording();
  }
}

async function startChatMicRecording() {
  const pill = document.getElementById("mic-status-pill");
  const icon = document.getElementById("chat-mic-icon");
  const btn = document.getElementById("btn-chat-mic");

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chatAudioChunks = [];
    isChatMicRecording = true;

    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";

    chatMediaRecorder = new MediaRecorder(stream, { mimeType: mime });
    chatMediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) chatAudioChunks.push(e.data);
    };

    chatMediaRecorder.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop());
      if (chatAudioChunks.length > 0) {
        const audioBlob = new Blob(chatAudioChunks, { type: mime });
        await sendChatAudioBlobForSTT(audioBlob);
      }
    };

    chatMediaRecorder.start();

    if (pill) pill.classList.remove("hidden");
    if (btn) btn.classList.add("bg-red-50", "border-red-300", "text-red-700");
  } catch (err) {
    // Fallback: Web Speech API if getUserMedia fails
    startWebSpeechRecognitionForChat();
  }
}

function stopChatMicRecording() {
  isChatMicRecording = false;
  const pill = document.getElementById("mic-status-pill");
  const btn = document.getElementById("btn-chat-mic");

  if (chatMediaRecorder && chatMediaRecorder.state !== "inactive") {
    chatMediaRecorder.stop();
  }
  if (pill) pill.classList.add("hidden");
  if (btn) btn.classList.remove("bg-red-50", "border-red-300", "text-red-700");
}

async function sendChatAudioBlobForSTT(blob) {
  try {
    const formData = new FormData();
    formData.append("audio", blob, "recording.webm");

    const res = await fetch(`${API_BASE}/transcribe`, {
      method: "POST",
      body: formData
    });

    if (res.ok) {
      const data = await res.json();
      if (data.transcript && data.transcript.trim()) {
        const input = document.getElementById("chat-text-input");
        if (input) input.value = data.transcript;
        await processChatTurn(data.transcript);
      }
    }
  } catch (e) {
    // Transcription error handled gracefully
  }
}

function startWebSpeechRecognitionForChat() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    alert("Voice input is not supported in this browser. Please type your question.");
    return;
  }

  const rec = new SpeechRecognition();
  rec.lang = "en-IN";
  rec.interimResults = false;

  const pill = document.getElementById("mic-status-pill");
  if (pill) pill.classList.remove("hidden");

  rec.onresult = (e) => {
    const text = e.results[0][0].transcript;
    if (text) {
      const input = document.getElementById("chat-text-input");
      if (input) input.value = text;
      processChatTurn(text);
    }
  };

  rec.onerror = () => {
    if (pill) pill.classList.add("hidden");
  };

  rec.onend = () => {
    if (pill) pill.classList.add("hidden");
  };

  rec.start();
}

// -------------------------------------------------------------
// 5. PATIENT PROFILE & HEALTH DATA (Screen 2)
// -------------------------------------------------------------

async function loadPatientProfile(patientId) {
  try {
    const res = await fetch(`${API_BASE}/patient/${patientId}`);
    if (res.ok) {
      const data = await res.json();
      window.patientProfile = data;

      const p = data.patient;
      if (p) {
        const headerLabel = document.getElementById("chat-header-patient-label");
        if (headerLabel) {
          headerLabel.textContent = `${p.full_name} (${p.age}y) • Active Consultation`;
        }
      }

      populateProfileForm();
    }
  } catch (err) {}
}

function populateProfileForm() {
  if (!window.patientProfile) return;
  const p = window.patientProfile.patient;
  const pep = window.patientProfile.pep;

  if (p) {
    setVal("prof-name", p.full_name);
    setVal("prof-age", p.age);
    setVal("prof-gender", p.gender || "Male");
    setVal("prof-height", p.height_cm || 172);
    setVal("prof-weight", p.weight_kg || 78);
    setVal("prof-goal", p.primary_goal || "Weight management & fitness");
    setVal("prof-activity", p.activity_level || "Moderate");
    recalcBmi();
  }

  if (pep) {
    setVal("prof-diet", pep.dietary_preference || "Vegetarian");
    setVal("prof-conditions", (pep.medical_conditions || []).join(", "));
  }
}

function recalcBmi() {
  const h = parseFloat(document.getElementById("prof-height")?.value);
  const w = parseFloat(document.getElementById("prof-weight")?.value);
  const display = document.getElementById("prof-bmi-display");
  if (!display || !h || !w) return;

  const bmi = w / ((h / 100) * (h / 100));
  let category = "Normal Range";
  if (bmi < 18.5) category = "Underweight";
  else if (bmi >= 25 && bmi < 30) category = "Overweight / Moderate";
  else if (bmi >= 30) category = "Obese";

  display.textContent = `${bmi.toFixed(1)} (${category})`;
}

async function saveProfileData(e) {
  if (e) e.preventDefault();
  const name = document.getElementById("prof-name")?.value.trim();
  const age = parseInt(document.getElementById("prof-age")?.value);
  const gender = document.getElementById("prof-gender")?.value;
  const height = parseFloat(document.getElementById("prof-height")?.value);
  const weight = parseFloat(document.getElementById("prof-weight")?.value);
  const goal = document.getElementById("prof-goal")?.value.trim();
  const diet = document.getElementById("prof-diet")?.value;
  const activity = document.getElementById("prof-activity")?.value;
  const conditionsRaw = document.getElementById("prof-conditions")?.value || "";
  const conditions = conditionsRaw.split(",").map((c) => c.trim()).filter((c) => c.length > 0);

  try {
    const res = await fetch(`${API_BASE}/patient/${currentPatientId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_name: name,
        age: age,
        gender: gender,
        height_cm: height,
        weight_kg: weight,
        activity_level: activity,
        primary_goal: goal,
        dietary_preference: diet,
        medical_conditions: conditions
      })
    });

    if (res.ok) {
      const toast = document.getElementById("prof-save-toast");
      if (toast) {
        toast.classList.remove("hidden");
        setTimeout(() => toast.classList.add("hidden"), 3000);
      }
      await loadPatientProfile(currentPatientId);
    }
  } catch (err) {}
}

function setVal(id, val) {
  const el = document.getElementById(id);
  if (el && val !== undefined && val !== null) el.value = val;
}

// -------------------------------------------------------------
// 6. AI ENGINE & API KEY SETTINGS
// -------------------------------------------------------------

async function loadApiKeySettings() {
  try {
    const res = await fetch(`${API_BASE}/settings`);
    if (res.ok) {
      const data = await res.json();
      const badge = document.getElementById("chat-engine-badge");
      const label = document.getElementById("active-llm-label");

      let displayName = "Offline Local";
      if (data.active_provider === "gemini") displayName = "Google Gemini 2.0 Flash";
      else if (data.active_provider === "groq") displayName = "Groq Llama 3.3 70B";

      if (badge) badge.textContent = `Engine: ${displayName}`;
      if (label) label.textContent = `Active Engine: ${displayName} (Ready)`;

      if (data.has_gemini && document.getElementById("setting-gemini-key")) {
        document.getElementById("setting-gemini-key").placeholder = "Configured (••••••••)";
      }
      if (data.has_groq && document.getElementById("setting-groq-key")) {
        document.getElementById("setting-groq-key").placeholder = "Configured (••••••••)";
      }
    }
  } catch (e) {}
}

async function saveApiKeySettings() {
  const geminiInput = document.getElementById("setting-gemini-key");
  const groqInput = document.getElementById("setting-groq-key");
  const label = document.getElementById("active-llm-label");

  const geminiKey = geminiInput ? geminiInput.value.trim() : "";
  const groqKey = groqInput ? groqInput.value.trim() : "";

  try {
    const body = {};
    if (geminiKey) body.gemini_api_key = geminiKey;
    if (groqKey) body.groq_api_key = groqKey;

    const res = await fetch(`${API_BASE}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });

    if (res.ok) {
      if (label) label.textContent = "API Keys Saved! Testing latency...";
      setTimeout(async () => {
        await loadApiKeySettings();
      }, 600);
    }
  } catch (e) {}
}

// -------------------------------------------------------------
// 7. AI VOICE CALL MODAL OVERLAY (WebSockets + Real-Time Audio)
// -------------------------------------------------------------

let voiceWebSocket = null;
let voiceHeartbeatTimer = null;

function openVoiceCallModal() {
  const overlay = document.getElementById("voice-call-overlay");
  if (overlay) overlay.classList.remove("hidden");

  isVoiceSessionActive = true;
  setVoiceOrbState("listening");
  updateVoiceStatus("Connecting...", "bg-surface-low text-onSurface-variant");
  updateVoiceSubtitle("Connecting to Voice Gateway...");

  // Open real-time WebSocket connection to backend
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/call?patient_id=${encodeURIComponent(currentPatientId)}&session_id=${encodeURIComponent(currentSessionId)}`;

  try {
    voiceWebSocket = new WebSocket(wsUrl);

    voiceWebSocket.onopen = () => {
      voiceWebSocket.send(JSON.stringify({ type: "connect" }));
      if (voiceHeartbeatTimer) clearInterval(voiceHeartbeatTimer);
      voiceHeartbeatTimer = setInterval(() => {
        if (voiceWebSocket && voiceWebSocket.readyState === WebSocket.OPEN) {
          voiceWebSocket.send(JSON.stringify({ type: "ping" }));
        }
      }, 15000);
    };

    voiceWebSocket.onmessage = async (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "call_connected") {
          setVoiceOrbState("listening");
          updateVoiceStatus("Connected • Listening", "bg-primary-light text-primary-dark");
          updateVoiceSubtitle(msg.greeting || "Listening... aap diet, routine ya health ke baare mein baat kar sakte hain.");
          if (msg.greeting) await playAssistantVoiceResponse(msg.greeting);
        } else if (msg.type === "turn_result") {
          const botText = msg.text;
          updateVoiceSubtitle(botText);
          appendChatMessage("assistant", botText, "Voice Call");
          dialogueHistory.push({ role: "assistant", content: botText });
          if (msg.is_emergency) {
            showEmergencyBanner("Emergency detected: Contact 108/112 immediately.");
          }
        } else if (msg.type === "audio_payload") {
          await playAssistantVoiceResponse(null, msg.audio_base64);
        } else if (msg.type === "interrupted") {
          stopAudioPlayback();
          setVoiceOrbState("interrupted");
          updateVoiceStatus("Interrupted • Listening...", "bg-amber-100 text-amber-900");
          if (dialogueHistory.length > 0 && dialogueHistory[dialogueHistory.length - 1].role === "assistant") {
            const lastMsg = dialogueHistory[dialogueHistory.length - 1];
            const words = lastMsg.content.split(" ");
            const cutoff = Math.max(1, Math.floor(words.length * 0.5));
            lastMsg.content = words.slice(0, cutoff).join(" ") + "...";
            const assistantBubbles = document.querySelectorAll(".chat-bubble-assistant");
            if (assistantBubbles.length > 0) {
              const lastBubble = assistantBubbles[assistantBubbles.length - 1];
              const textElem = lastBubble.querySelector(".bubble-text");
              if (textElem) textElem.textContent = lastMsg.content;
            }
          }
        } else if (msg.type === "call_ended") {
          closeVoiceCallModal();
        }
      } catch (err) {}
    };

    voiceWebSocket.onerror = () => {
      updateVoiceStatus("Connected (Audio active)", "bg-primary-light text-primary-dark");
    };

    voiceWebSocket.onclose = () => {
      if (voiceHeartbeatTimer) clearInterval(voiceHeartbeatTimer);
    };
  } catch (e) {
    updateVoiceSubtitle("Listening... aap diet ya workout ke baare mein pooch sakte hain.");
  }

  if (window.lucide) lucide.createIcons();
}

function closeVoiceCallModal() {
  const overlay = document.getElementById("voice-call-overlay");
  if (overlay) overlay.classList.add("hidden");

  isVoiceSessionActive = false;
  stopAudioPlayback();
  stopVoiceMicStream();
  setVoiceOrbState("idle");

  if (voiceWebSocket && voiceWebSocket.readyState === WebSocket.OPEN) {
    try {
      voiceWebSocket.send(JSON.stringify({ type: "call_end" }));
      voiceWebSocket.close();
    } catch (e) {}
  }
  if (voiceHeartbeatTimer) clearInterval(voiceHeartbeatTimer);
}

function toggleModalVoiceSpeaking() {
  if (!isVoiceSessionActive) {
    openVoiceCallModal();
    return;
  }
  
  if (isAudioPlaying) {
    interruptDishaSpeech();
  } else {
    captureModalVoiceInput();
  }
}

async function captureModalVoiceInput() {
  try {
    setVoiceOrbState("listening");
    updateVoiceStatus("Listening • Speak naturally in Hindi/English...", "bg-primary-light text-primary-dark");
    
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    micStream = stream;
    audioChunks = [];

    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";

    mediaRecorder = new MediaRecorder(stream, { mimeType: mime });
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      stopVoiceMicStream();
      if (audioChunks.length > 0) {
        setVoiceOrbState("thinking");
        updateVoiceStatus("Processing your question...", "bg-surface-low text-onSurface-variant");
        const blob = new Blob(audioChunks, { type: mime });
        await handleVoiceTurnBlob(blob);
      }
    };

    mediaRecorder.start();

    // Auto stop after 5s or when user taps
    setTimeout(() => {
      if (mediaRecorder && mediaRecorder.state === "recording") {
        mediaRecorder.stop();
      }
    }, 5000);

  } catch (err) {
    // Fallback to Web Speech API
    startModalWebSpeech();
  }
}

function startModalWebSpeech() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return;

  const rec = new SpeechRecognition();
  rec.lang = "en-IN";
  rec.interimResults = false;

  setVoiceOrbState("listening");
  updateVoiceStatus("Listening • Speak now...", "bg-primary-light text-primary-dark");

  rec.onresult = async (e) => {
    const text = e.results[0][0].transcript;
    if (text) {
      updateVoiceSubtitle(`You: "${text}"`);
      await executeVoiceTurn(text);
    }
  };

  rec.onerror = () => {
    setVoiceOrbState("idle");
    updateVoiceStatus("Ready", "bg-surface-low text-onSurface-variant");
  };

  rec.start();
}

async function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const dataUrl = reader.result;
      const base64 = dataUrl.split(",")[1];
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

async function handleVoiceTurnBlob(audioBlob) {
  try {
    const b64 = await blobToBase64(audioBlob);

    // If real-time WebSocket is connected, stream audio payload directly
    if (voiceWebSocket && voiceWebSocket.readyState === WebSocket.OPEN) {
      voiceWebSocket.send(JSON.stringify({
        type: "audio",
        data: b64,
        synthesize_audio: true
      }));
      return;
    }

    // Fallback: POST /voice-turn with standard JSON payload
    const res = await fetch(`${API_BASE}/voice-turn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        patient_id: currentPatientId,
        audio_base64: b64,
        session_id: currentSessionId,
        turn_number: turnCounter++,
        history: dialogueHistory.slice(-6)
      })
    });

    if (res.ok) {
      const data = await res.json();
      const userText = data.user_utterance || data.user_transcript;
      const botText = data.final_response || data.bot_response;

      // Add turn to chat timeline so context is shared
      if (userText) {
        appendChatMessage("user", userText, "Voice Call");
        dialogueHistory.push({ role: "user", content: userText });
      }
      if (botText) {
        appendChatMessage("assistant", botText, "Voice Call");
        dialogueHistory.push({ role: "assistant", content: botText });
      }

      updateVoiceSubtitle(botText);
      await playAssistantVoiceResponse(botText, data.audio_base64);
    } else {
      setVoiceOrbState("idle");
    }
  } catch (e) {
    setVoiceOrbState("idle");
  }
}

async function executeVoiceTurn(utterance) {
  setVoiceOrbState("thinking");
  updateVoiceStatus("Thinking...", "bg-surface-low text-onSurface-variant");

  // Sync to chat timeline
  appendChatMessage("user", utterance, "Voice Call");
  dialogueHistory.push({ role: "user", content: utterance });

  if (voiceWebSocket && voiceWebSocket.readyState === WebSocket.OPEN) {
    voiceWebSocket.send(JSON.stringify({
      type: "utterance",
      patient_id: currentPatientId,
      text: utterance,
      synthesize_audio: true
    }));
  } else {
    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: currentPatientId,
          utterance: utterance,
          session_id: currentSessionId,
          turn_number: turnCounter++,
          history: dialogueHistory.slice(-6)
        })
      });

      if (res.ok) {
        const data = await res.json();
        const botText = data.final_response;

        appendChatMessage("assistant", botText, "Voice Call");
        dialogueHistory.push({ role: "assistant", content: botText });
        updateVoiceSubtitle(botText);

        await playAssistantVoiceResponse(botText);
      } else {
        setVoiceOrbState("idle");
      }
    } catch (e) {
      setVoiceOrbState("idle");
    }
  }
}

function interruptDishaSpeech() {
  let playedFraction = 0.5;
  if (currentAudio && currentAudio.duration && currentAudio.duration > 0) {
    playedFraction = Math.min(1.0, Math.max(0.01, currentAudio.currentTime / currentAudio.duration));
  }
  stopAudioPlayback();

  if (voiceWebSocket && voiceWebSocket.readyState === WebSocket.OPEN) {
    try {
      voiceWebSocket.send(JSON.stringify({
        type: "barge_in",
        played_fraction: playedFraction
      }));
    } catch (e) {}
  }
  setVoiceOrbState("interrupted");
  updateVoiceStatus("Interrupted • Listening", "bg-amber-100 text-amber-900");
  updateVoiceSubtitle("Listening to you...");

  setTimeout(() => {
    if (isVoiceSessionActive) {
      setVoiceOrbState("listening");
      updateVoiceStatus("Listening • Speak Naturally", "bg-primary-light text-primary-dark");
      captureModalVoiceInput();
    }
  }, 400);
}

// Global alias for compatibility with test suites
window.triggerManualBargeIn = interruptDishaSpeech;

function stopAudioPlayback() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    currentAudio = null;
  }
  isAudioPlaying = false;
  const bars = document.getElementById("modal-sound-bars");
  if (bars) bars.classList.add("opacity-0");

  const interruptBtn = document.getElementById("btn-modal-interrupt");
  if (interruptBtn) interruptBtn.disabled = true;
}

function stopVoiceMicStream() {
  if (micStream) {
    micStream.getTracks().forEach((track) => track.stop());
    micStream = null;
  }
}

async function playAssistantVoiceResponse(text, audioBase64 = null) {
  stopAudioPlayback();
  setVoiceOrbState("speaking");
  updateVoiceSubtitle(text);

  const interruptBtn = document.getElementById("btn-modal-interrupt");
  if (interruptBtn) interruptBtn.disabled = false;

  const bars = document.getElementById("modal-sound-bars");
  if (bars) bars.classList.remove("opacity-0");

  if (audioBase64) {
    return new Promise((resolve) => {
      currentAudio = new Audio(`data:audio/mpeg;base64,${audioBase64}`);
      isAudioPlaying = true;
      currentAudio.onended = () => {
        stopAudioPlayback();
        setVoiceOrbState(isVoiceSessionActive ? "listening" : "idle");
        resolve();
      };
      currentAudio.onerror = () => {
        fallbackWebSpeech(text).then(resolve);
      };
      currentAudio.play().catch(() => {
        fallbackWebSpeech(text).then(resolve);
      });
    });
  } else {
    try {
      const res = await fetch(`${API_BASE}/synthesize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text })
      });

      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        return new Promise((resolve) => {
          currentAudio = new Audio(url);
          isAudioPlaying = true;
          currentAudio.onended = () => {
            stopAudioPlayback();
            setVoiceOrbState(isVoiceSessionActive ? "listening" : "idle");
            resolve();
          };
          currentAudio.play().catch(() => {
            fallbackWebSpeech(text).then(resolve);
          });
        });
      } else {
        await fallbackWebSpeech(text);
      }
    } catch (e) {
      await fallbackWebSpeech(text);
    }
  }
}

function fallbackWebSpeech(text) {
  return new Promise((resolve) => {
    if (!("speechSynthesis" in window) || !text) {
      stopAudioPlayback();
      resolve();
      return;
    }
    const ut = new SpeechSynthesisUtterance(text);
    ut.lang = "en-IN";
    ut.rate = 1.0;
    isAudioPlaying = true;
    ut.onend = () => {
      stopAudioPlayback();
      setVoiceOrbState(isVoiceSessionActive ? "listening" : "idle");
      resolve();
    };
    ut.onerror = () => {
      stopAudioPlayback();
      resolve();
    };
    window.speechSynthesis.speak(ut);
  });
}

function setVoiceOrbState(state) {
  const orb = document.getElementById("modal-voice-orb");
  const icon = document.getElementById("modal-voice-orb-icon");
  if (!orb) return;

  orb.className = "voice-stage-orb voice-orb cursor-pointer " + `orb-state-${state}`;

  if (icon) {
    if (state === "listening") icon.setAttribute("data-lucide", "mic");
    else if (state === "speaking") icon.setAttribute("data-lucide", "volume-2");
    else if (state === "thinking") icon.setAttribute("data-lucide", "loader-2");
    else if (state === "interrupted") icon.setAttribute("data-lucide", "hand");
    else icon.setAttribute("data-lucide", "mic");
  }
  if (window.lucide) lucide.createIcons();
}

function updateVoiceStatus(text, pillClass) {
  const textEl = document.getElementById("voice-modal-status-text");
  const pillEl = document.getElementById("voice-modal-status-pill");
  if (textEl) textEl.textContent = text;
  if (pillEl && pillClass) {
    pillEl.className = `inline-flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-semibold ${pillClass} mb-1`;
  }
}

function updateVoiceSubtitle(text) {
  const sub = document.getElementById("modal-voice-subtitle");
  if (sub && text) {
    sub.textContent = `"${text}"`;
  }
}
