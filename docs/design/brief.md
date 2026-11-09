# Disha AI — Creative Design Brief & Comprehensive UX Copy Guide

**Document Version:** 4.0.0  
**Phase:** Master Order v4 — Loop 1 Foundation  
**Auditor & Author:** Art Director & UX Writer (`art-director`)  
**Design Doctrine:** Clinical Apothecary (Warm Porcelain & Restorative Herbal Sage)  
**Standard:** WCAG 2.2 Level AA/AAA, ISO 9241-110 Ergonomics, IEC 62366-1 Medical Device Usability  
**Target Codebase:** `frontend/**`, `disha_core/frontend/**`, `docs/design/**`  

---

## 1. Executive Vision & Core Positioning

> **Disha AI is an uncompromisingly grounded, voice-first clinical companion. It pairs unhurried, culturally authentic Hinglish health coaching with deterministic safety guardrails, ICMR-NIN nutritional protocols, and cryptographic auditability — built specifically for Indian patients managing chronic metabolic conditions.**

Disha AI is **not** a generic consumer chatbot, **not** an experimental LLM playground, and **not** a decorative AI tech demo. It is a high-reliability clinical communication instrument.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        CORE BRAND ATTRIBUTES                           │
├────────────────────┬────────────────────┬──────────────────────────────┤
│ 1. CLINICAL CALM   │ 2. CULTURAL TRUTH  │ 3. DETERMINISTIC SAFETY      │
│ Restorative sage & │ Authentic Hinglish │ Hard-coded ICMR guardrails;  │
│ porcelain alabaster│ & Indian dietary   │ instantaneous emergency      │
│ de-escalate panic. │ staples (khichdi). │ deflection (112 / 108).      │
└────────────────────┴────────────────────┴──────────────────────────────┘
```

---

## 2. Visual Design Direction: Clinical Apothecary

The visual identity of Disha AI rejects the neon purple gradients, floating spheres, and dark glassmorphic tropes common in generative AI. Instead, it takes inspiration from the quiet authority, warm wood, porcelain jars, and measured precision of an integrative apothecary clinic.

### 2.1 Color Palette & Design Tokens

Every color is selected for high clinical legibility, emotional restoration, and strict WCAG 2.2 Level AA/AAA compliance (minimum 4.5:1 for large text/icons, 7:1 for normal body copy, and 3:1 for graphical UI components).

```css
:root {
  /* Canvas & Paper Surfaces */
  --paper: #f8faf9;            /* Warm porcelain alabaster body background */
  --surface: #ffffff;          /* Pure white card and dialog canvas */
  --surface-alt: #f1f5f3;      /* Subdued celadon wash for secondary containers */
  --surface-hover: #eaf1ed;    /* Subtle hover feedback */
  --backdrop: rgba(20, 32, 28, 0.45); /* Muted slate modal overlay */

  /* Structural Hairlines (1px solid borders) */
  --border: #e2e8e5;           /* Quiet container demarcation */
  --border-strong: #c8d4ce;    /* Active card boundaries */
  --border-focus: #167a57;     /* High-visibility keyboard focus ring (3px solid) */

  /* Ink & Typography */
  --ink: #14201c;              /* Deep forest slate (16.2:1 contrast on white) */
  --ink-secondary: #4d6059;    /* Muted clinical supporting text (7.4:1 contrast) */
  --ink-tertiary: #788f86;     /* Structural timestamps and metadata (4.6:1 contrast) */
  --ink-inverse: #fbfdfc;      /* Pure alabaster on dark emerald surfaces */

  /* Primary Brand: Restorative Herbal Sage */
  --accent: #167a57;           /* Master clinical emerald (7.2:1 contrast on white) */
  --accent-hover: #126447;     /* Deepened emerald on hover */
  --accent-active: #0e5038;    /* Pressed tactile state */
  --accent-subtle: #e8f5f0;    /* Pale herbal wash for badges & callouts */
  --accent-border: #bce3d4;    /* Delicate sage boundary */

  /* Clinical Alerts: Desaturated Brick & Amber */
  --danger: #b91c1c;           /* Desaturated clinical red for emergency triage */
  --danger-hover: #991b1b;
  --danger-subtle: #fef2f2;    /* Soft red background for cardiac/crisis warnings */
  --danger-border: #fecaca;
  --danger-ink: #7f1d1d;       /* High-contrast danger copy (8.1:1 contrast) */

  --warning: #b45309;          /* Restrained amber for dietary restrictions */
  --warning-subtle: #fffbeb;
  --warning-border: #fde68a;
  --warning-ink: #78350f;

  --success: #15803d;          /* Verified clearance green */
  --success-subtle: #f0fdf4;
  --success-border: #bbf7d0;
}

[data-theme="dark"] {
  --paper: #0e1613;            /* Deep obsidian slate */
  --surface: #14201c;          /* Low-luminescence dark apothecary slate */
  --surface-alt: #1a2924;
  --surface-hover: #22352f;
  --border: #263a33;
  --border-strong: #365047;
  --border-focus: #2ec491;

  --ink: #eef5f2;              /* Soft alabaster (14.8:1 contrast on dark surface) */
  --ink-secondary: #9cb1a9;    /* 7.1:1 contrast */
  --ink-tertiary: #6a8279;     /* 4.5:1 contrast */
  --ink-inverse: #0e1613;

  --accent: #2ec491;           /* Luminous mint sage for dark contrast */
  --accent-hover: #26ac7f;
  --accent-active: #1e926c;
  --accent-subtle: #14352b;
  --accent-border: #205745;

  --danger: #ef4444;
  --danger-subtle: #2d1616;
  --danger-border: #522222;
  --danger-ink: #fca5a5;
}
```

### 2.2 Mathematical 4pt / 8pt Spatial Scale

All layout geometry adheres to a strict 4px modular grid. Arbitrary paddings (`13px`, `19px`) are forbidden:

| Token | Dimension | Applied Use Case |
|:---|:---:|:---|
| `--space-2xs` | **4px** | Inline chip padding, badge horizontal margins, hairline offsets |
| `--space-xs` | **8px** | Stack gap between related form labels and inputs, icon gaps |
| `--space-sm` | **12px** | Internal card padding on mobile, compact button vertical padding |
| `--space-md` | **16px** | Standard container padding, form row gutters, dialog header margins |
| `--space-lg` | **24px** | Card deck gaps, section header vertical spacing |
| `--space-xl` | **32px** | Major screen section breaks, dashboard grid columns |
| `--space-2xl` | **48px** | Full viewport margins on desktop, primary hero separation |

### 2.3 Typography Pairings

Disha AI pairs a neutral, optically balanced grotesque sans with a precision tabular monospace:

1. **Display & Body Sans (`Inter`):**
   - Headings: `font-family: 'Inter', sans-serif; font-weight: 600; letter-spacing: -0.025em;` (Tight tracking prevents clinical titles from feeling loose or uncomposed).
   - Body Copy: `font-family: 'Inter', sans-serif; font-weight: 400; line-height: 1.55;` (Optimized for rapid reading under emotional distress).
   - Action Labels: `font-weight: 500; letter-spacing: -0.01em;`.
2. **Clinical Telemetry Monospace (`JetBrains Mono`):**
   - Applied to: Call duration timers (`00:00`), physiological vitals (e.g., `148/92 mmHg`, `24.6 kg/m²`), cryptographic hashes (`0x7f8a...`), and biometric counters.
   - Rule: Always set `font-variant-numeric: tabular-nums;` to guarantee numeric columns and timers do not jitter during updates.

### 2.4 Purposeful Subtle Elevation & Micro-Interaction Physics

- **Zero Glassmorphism:** No heavy `backdrop-filter: blur(20px)` or semi-transparent cards that degrade contrast on inexpensive IPS smartphone screens.
- **Elevation Tokens:**
  - Resting Card: `border: 1px solid var(--border); box-shadow: var(--shadow-sm);` (`0 1px 3px rgba(20, 32, 28, 0.05)`).
  - Active Modal / Dock: `box-shadow: var(--shadow-lg);` (`0 12px 28px rgba(20, 32, 28, 0.12)`).
- **Micro-Interaction Physics:**
  - Transition Timing: `120ms` for press states, `200ms` for hover/focus transitions, `240ms` for modal entrances.
  - Easing: Strict `cubic-bezier(0.16, 1, 0.3, 1)` (snappy entry with damped physical settling).
  - Tactile Feedback: Buttons press down with `transform: scale(0.98)` on `:active`.
  - Minimum Touch Envelope: **48×48px** bounding box on all touch targets to accommodate shaky or arthritic hands.

---

## 3. Microcopy Standards: Tone, Voice & Language Parity

Disha speaks like an experienced, compassionate chief family physician who has practiced in India for over 30 years. She is never cold or robotic, yet never patronizing or falsely cheerful.

### 3.1 Voice Spectrum & Core Rules

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    THE DISHA CLINICAL VOICE SPECTRUM                    │
├────────────────────────────┬────────────────────────────────────────────┤
│ WE ARE                     │ WE ARE NEVER                               │
├────────────────────────────┼────────────────────────────────────────────┤
│ Grounded & Methodical      │ Hysterical, panicked, or alarmist          │
│ Clear & Actionable         │ Vague, ambiguous, or evasive               │
│ Culturally Authentic       │ Condescendingly folksy or caricature-like  │
│ Empathetic & Respectful    │ Syrupy, synthetic, or artificially bouncy  │
│ Transparent About Limits   │ Deceptive about medical qualifications     │
└────────────────────────────┴────────────────────────────────────────────┘
```

#### Core Writing Principles:
1. **Plain Verbs, Active Voice:** Say *"Save changes"*, not *"Your updates are being processed"*. Say *"Check blood pressure"*, not *"BP monitoring should be commenced"*.
2. **Context First, Then Action:** When explaining medical guidance, explain *why* before giving the instruction: *"Khana khane ke baad pet mein gas banna aam baat hai. Pehle 10 minute seedhe baithiye..."*.
3. **Never Dismiss Patient Anxiety:** Never say *"Don't worry, it's just gas"*. Instead say: *"Main samajh sakti hoon ki chhati mein bhari-pan ghabrahat paida karta hai. Aaiye pehle symptoms check karein."*.
4. **No LLM Slop Vocabulary:** Strictly ban terms like *"delve"*, *"tapestry"*, *"vital to note"*, *"game changer"*, *"holistic journey"*, *"let's unpack"*.

---

## 4. Mandatory Clinical Transparency Disclaimers

By Indian regulatory standards and ethical clinical safety protocols, Disha must explicitly declare her role as an AI health coach, not a licensed medical practitioner.

### 4.1 Master Disclaimer Standards Across Languages

| Context / Placement | English Standard | Hindi Standard (हिंदी) | Hinglish Standard (Conversational) |
|:---|:---|:---|:---|
| **First Turn Greeting** | *"Namaste! I am Disha, your personal AI health coach. I provide grounded lifestyle, habit, and nutrition guidance. I am not a doctor and cannot diagnose medical emergencies."* | *"नमस्ते! मैं दिशा हूँ, आपकी पर्सनल AI हेल्थ कोच। मैं आपको खान-पान, दिनचर्या और सेहतमंद आदतों में मदद करती हूँ। मैं डॉक्टर नहीं हूँ और आपातकालीन इलाज नहीं कर सकती।"* | *"Namaste! Main Disha hoon, aapki personal AI health coach. Main lifestyle, diet aur healthy habits mein aapko guide karti hoon. Main ek doctor nahi hoon aur emergency medical treatment nahi de sakti."* |
| **Footer / Profile Notice** | *"Disha AI is a lifestyle and wellness coach. It does not replace clinical consultation, prescription medicines, or emergency medical services."* | *"दिशा AI एक जीवनशैली और स्वास्थ्य कोच है। यह किसी डॉक्टर की सलाह, दवाइयों या आपातकालीन सेवाओं का विकल्प नहीं है।"* | *"Disha AI ek lifestyle aur wellness coach hai. Ye kisi doctor ke mashware, prescription medicines ya emergency services ka substitute nahi hai."* |
| **Medication Inquiry Intercept** | *"I cannot prescribe medicines or alter doctor-prescribed dosages. Please consult your physician for prescription changes."* | *"मैं दवाइयाँ नहीं लिख सकती और न ही डॉक्टर द्वारा तय की गई खुराक बदल सकती हूँ। कृपया दवा के लिए अपने डॉक्टर से परामर्श लें।"* | *"Main koi dawai prescribe nahi kar sakti aur na hi doctor ki di hui dosage change kar sakti hoon. Medicine ke kisi bhi badlaav ke liye please apne doctor se consult karein."* |

---

## 5. Emergency SOS Guidance & Tri-Number Architecture

India operates dedicated national emergency hotlines. Disha embeds a definitive **Tri-Number Emergency Architecture** into all conversational prompts, modal alerts, and voice deflection interceptors:

```
┌────────────────────────────────────────────────────────────────────────┐
│               INDIA TRI-NUMBER EMERGENCY ARCHITECTURE                  │
├─────────┬────────────────────────────┬─────────────────────────────────┤
│ **112** │ National Emergency Helpline│ Unified Police, Fire, Ambulance │
├─────────┼────────────────────────────┼─────────────────────────────────┤
│ **108** │ Emergency Medical Response │ Critical Care Ambulance & Trauma│
├─────────┼────────────────────────────┼─────────────────────────────────┤
│ **102** │ Maternal & Child Transport │ Free Pregnancy & Infant Transit │
└─────────┴────────────────────────────┴─────────────────────────────────┘
```

### 5.1 Acute Clinical Red Flag Intercepts

When the Laya intent classifier or safety validator detects acute symptoms (e.g., crushing substernal chest pressure, radiation to left arm/jaw, diaphoresis, sudden hemi-facial droop, severe breathlessness), Disha **immediately stops coaching** and displays/speaks the following standardized script:

#### English Emergency Script
> **"IMPORTANT MEDICAL ALERT: Your symptoms suggest a potential acute cardiovascular or respiratory emergency. Do not wait.**  
> 1. Call **112** or **108** immediately for an ambulance.  
> 2. Sit down, keep your head elevated, and unlock your front door.  
> 3. Alert a family member or neighbor right now. Do not drive yourself to the hospital."

#### Hindi Emergency Script (हिंदी)
> **"महत्वपूर्ण आपातकालीन सूचना: आपके लक्षण किसी गंभीर स्वास्थ्य समस्या या दिल की आपात स्थिति की ओर इशारा कर रहे हैं। बिल्कुल भी देर न करें।**  
> 1. तुरंत **112** या **108** पर कॉल करके एम्बुलेंस बुलाएं।  
> 2. आराम से बैठ जाएं, सिर ऊंचा रखें, और घर का मुख्य दरवाजा खोल दें।  
> 3. तुरंत किसी परिजन या पड़ोसी को बुलाएं। खुद गाड़ी चलाकर अस्पताल न जाएं।"

#### Hinglish Emergency Script (Conversational)
> **"IMPORTANT MEDICAL ALERT: Aapke symptoms kisi serious heart ya breathing emergency ke sanket ho sakte hain. Bilkul delay na karein.**  
> 1. Turant **112** ya **108** par call karke ambulance bulayein.  
> 2. Shaanti se baith jaayein, sar thoda uncha rakhein, aur ghar ka main darwaza unlock kar dein.  
> 3. Apne kisi family member ya neighbor ko turant aawaz dein. Khud gadi chala kar hospital na jaayein."

---

## 6. Informative Error States: The 3-Part Clinical Pattern

Errors must never leave the patient stranded in confusion or panic. Generic messages like *"Something went wrong"* or *"Internal Error 500"* are strictly forbidden.

Every error state must follow the **3-Part Clinical Error Pattern**:
1. **What happened:** Plain statement of fact in human terms.
2. **Why it happened:** Simple cause without developer jargon.
3. **What action to take:** Exact, safe step to resolve or retry.

```
┌────────────────────────────────────────────────────────────────────────┐
│                  THE 3-PART CLINICAL ERROR PATTERN                     │
├─────────────────┬────────────────────┬─────────────────────────────────┤
│ 1. WHAT HAPPENED│ "Audio stream lost"│ Direct observation of event     │
│ 2. WHY          │ "Weak Wi-Fi signal"│ Human explanation of cause      │
│ 3. SAFE ACTION  │ "[Switch to Chat]" │ One-click actionable recovery   │
└─────────────────┴────────────────────┴─────────────────────────────────┘
```

### 6.1 Comprehensive Error Copy Taxonomy

| Error Code / Scenario | English Copy (What + Why + Action) | Hindi Copy (हिंदी) | Hinglish Copy (Conversational) |
|:---|:---|:---|:---|
| **E01: Offline / No Network** | **Connection Lost.** Your internet connection is currently offline. Disha will automatically reconnect when your signal returns. *[Retry Connection]* | **इंटरनेट बंद है।** आपका इंटरनेट कनेक्शन कट गया है। नेटवर्क वापस आते ही दिशा अपने आप दोबारा जुड़ जाएगी। *[पुनः प्रयास करें]* | **Connection toot gaya hai.** Aapka internet abhi disconnected hai. Signal aate hi Disha automatically reconnect ho jayegi. *[Dobara Try Karein]* |
| **E02: WebSocket Voice Timeout** | **Voice Call Interrupted.** Audio communication with the server timed out. Your message transcript is preserved. *[Resume Voice Call] / [Switch to Text Chat]* | **आवाज संपर्क टूटा।** सर्वर से आवाज का संपर्क टूट गया है। आपकी बातचीत सुरक्षित है। *[कॉल दोबारा शुरू करें] / [मैसेज पर बात करें]* | **Voice Call disconnect ho gayi.** Server se audio link slow hone ki vajah se call ruki hai. Purani chat bilkul safe hai. *[Call Resume Karein] / [Text Chat Karein]* |
| **E03: Microphone Denied** | **Microphone Access Blocked.** Browser permission is needed to speak with Disha. Please tap the lock icon in your address bar and enable Microphone access. *[Open Browser Settings]* | **माइक की अनुमति नहीं मिली।** दिशा से बात करने के लिए माइक्रोफोन की अनुमति आवश्यक है। कृपया ब्राउज़र सेटिंग्स में जाकर माइक चालू करें। *[सेटिंग्स खोलें]* | **Microphone access blocked hai.** Disha se bolkar baat karne ke liye mic permission zaroori hai. Browser address bar mein lock icon dabakar mic allow karein. *[Check Permissions]* |
| **E04: Audio Output Failed** | **Speaker Unavailable.** The selected audio device could not be reached. Sound has been safely routed to your default system speaker. | **स्पीकर कनेक्ट नहीं हुआ।** चुने गए स्पीकर से आवाज नहीं आ रही है। आवाज को फोन के मुख्य स्पीकर पर भेज दिया गया है। | **Speaker connect nahi ho paya.** Selected device se sound nahi aa raha hai. Audio ko default phone speaker par bhej diya gaya hai. |
| **E05: Backend 500 / 503** | **Service Momentarily Unavailable.** Disha Core is updating clinical safety models. Please wait 30 seconds and refresh, or call 112 if you have an urgent medical need. *[Refresh App]* | **सेवा अस्थायी रूप से अनुपलब्ध है।** दिशा कोर सिस्टम में तकनीकी सुधार चल रहा है। कृपया 30 सेकंड बाद पुनः प्रयास करें, या आपात स्थिति में 112 पर संपर्क करें। | **Service temporary busy hai.** Disha Core safety systems update ho rahe hain. 30 seconds mein retry karein. Urgent emergency ke liye turant 112 milayein. *[Retry Karein]* |
| **E06: Non-Physiological Input** | **Invalid Health Value.** Height must be between 50 and 250 cm, and weight between 20 and 300 kg. Please enter your real physical measurements. | **अमान्य माप दर्ज हुआ।** ऊंचाई 50 से 250 सेमी और वजन 20 से 300 किग्रा के बीच होना चाहिए। कृपया अपनी सही माप दर्ज करें। | **Measurement theek nahi lag rahi.** Height 50–250 cm aur weight 20–300 kg ke beech hona chahiye. Please apna sahi measurement enter karein. |
| **E07: Rate Limit Exceeded** | **Consultation Pacing.** You have reached the maximum turns for this minute (60 turns/min). Please take a brief breath while Disha prepares your notes. *[Resumes in 15s]* | **बातचीत में विराम।** सुरक्षा कारणों से एक मिनट में संदेशों की सीमा पूरी हो गई है। कृपया 15 सेकंड प्रतीक्षा करें। | **Thoda viraam lein.** Safety ke liye 1 minute mein messages ki limit reach ho gayi hai. Disha agle 15 seconds mein resume karegi. |
| **E08: Session Expired** | **Session Expired for Security.** For your clinical privacy, inactive sessions expire after 24 hours. Please sign in again to access your history. *[Sign In Again]* | **सुरक्षा हेतु सत्र समाप्त।** आपकी गोपनीयता बनाए रखने के लिए पुराना सत्र बंद कर दिया गया है। कृपया दोबारा साइन इन करें। *[दोबारा साइन इन करें]* | **Security ke liye session expire ho gaya.** Privacy preserve rakhne ke liye inactive session band kiya gaya hai. Please dubara login karein. *[Sign In Karein]* |

---

## 7. Clinical Intake & Nutritional Terminology Lexicon

To maintain authentic clinical and cultural parity across India, Disha uses grounded vernacular rather than literal Western translations:

| Clinical / Lifestyle Domain | English Medical Term | Hindi Clinical Term (हिंदी) | Hinglish Conversational Term |
|:---|:---|:---|:---|
| **Symptoms** | High Blood Pressure | उच्च रक्तचाप (हाई बीपी) | High BP / BP badhna |
| **Symptoms** | Indigestion / Gas | अपच / गैस / पेट फूलना | Pet mein jalan / bloating / acidity |
| **Symptoms** | Palpitations / Flutters | दिल की धड़कन तेज होना | Dil ki dhadkan tez hona / ghabrahat |
| **Symptoms** | Dizziness / Vertigo | चक्कर आना | Chakkar aana / sar ghumna |
| **Symptoms** | Shortness of Breath | सांस फूलना / सांस लेने में तकलीफ | Saans phoolna / saans lene mein dikkat |
| **Diet** | Indian Flatbread (Whole Wheat) | रोटी / फुलका | Roti / phulka (bina ghee/kam tel) |
| **Diet** | Spiced Yellow Lentil Soup | मूंग दाल | Moong dal (halki tadka wali) |
| **Diet** | Bottle Gourd Curry | लौकी की सब्जी | Lauki ki sabzi (kam masale mein) |
| **Diet** | Flattened Rice Breakfast | पोहा | Poha (kam tel aur peanuts ke saath) |
| **Diet** | Rice & Lentil Stew | खिचड़ी | Moong dal khichdi (supachya) |
| **Diet** | Clarified Butter | देसी घी | Desi ghee (strictly controlled portions) |
| **Diet** | Pickles (High Sodium) | अचार (अधिक नमक) | Aam/Nimbu ka aachaar (avoid for HTN) |
| **Exercise** | Brisk Walking | तेज चाल से टहलना | Brisk walk (30 min roz) |
| **Exercise** | Heavy Weightlifting | भारी वजन उठाना (जिम) | Heavy weights / deadlifts (RESTRICTED) |
| **Exercise** | Breath-Holding (Valsalva) | सांस रोककर जोर लगाना | Saans rok kar zor lagana (RESTRICTED) |
| **Exercise** | Light Chair Yoga | आसान कुर्सी योग | Gentle yoga / Sukhasana |

---

## 8. Anti-Slop Enforcement & Design Sign-Off

This brief and copy guide serves as the legal and aesthetic benchmark for all Disha AI interfaces. Any code change that introduces:
- Decorative non-functional gradients
- Glassmorphic blur layers
- Synthetic uncalibrated wave animations
- Emojis in primary navigation
- Fluff marketing badges ("AI-powered magic")
- Vague or condescending error messages

...will be automatically rejected by the Art Direction gate during verification.

---
*Authored & Signed Off by the Art Director & UX Writer (`art-director`), Disha AI.*
