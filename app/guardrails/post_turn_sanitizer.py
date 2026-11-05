import re
from typing import List, Optional, Tuple
from pydantic import BaseModel

# Broadened channel allowlist catching colloquial variants (Failure #3)
FORBIDDEN_CHANNELS = re.compile(
    r"\b(whatsapp|wa|watsapp|wapp|sms|text\s+message|telegram|email|mail|inbox|pdf\s+link|forward)\b",
    re.IGNORECASE
)

# Persona protection catching human doctor / clinic claims (Failure #4)
FORBIDDEN_HUMAN_CLAIMS = re.compile(
    r"\b(insaan|human\s+(?:doctor|person|being|hoon)?|real\s+(?:human|person|doctor)|asli\s+(?:doctor|insaan|ladki)|clinic\s+mein\s+baith|not\s+an\s+ai)\b",
    re.IGNORECASE
)

# Regex to catch ungrounded pricing numbers (Failure #1)
PRICE_PATTERN = re.compile(r"(?:₹|rs\.?|rupees?\s*)\s*(\d{2,6})", re.IGNORECASE)
ALLOWED_PRICES = {0, 1499}

CANONICAL_AI_PERSONA = (
    "Main Disha hoon, aapki AI health coach. Main aapke doctor ke guidance mein "
    "aapki health journey track karne mein madad karti hoon."
)

CANONICAL_APP_CHANNEL = (
    "Aapka diet chart Disha mobile app ke 'My Plan' tab mein already available hai, "
    "aap wahan se directly dekh sakte hain."
)

CANONICAL_PRICING_FACT = (
    "Aapke doctor ke treatment plan ke sath Disha basic voice follow-up calls 100% free hain. "
    "Dedicated personal dietitian plans ₹1,499 prati mahina se start hote hain."
)

class PostTurnSanitizeResult(BaseModel):
    is_modified: bool
    modification_reason: Optional[str] = None
    sanitized_text: str

class PostTurnOutputSanitizer:
    """
    Deterministic Post-Turn Sanitizer & Interceptor.
    Validates model outputs before text-to-speech audio synthesis.
    """

    def sanitize(
        self,
        raw_text: str,
        required_remedy_tokens: Optional[List[str]] = None
    ) -> PostTurnSanitizeResult:
        """
        Sanitizes raw LLM output against persona, capability, pricing, and remedy assertions.
        """
        if not raw_text or not raw_text.strip():
            return PostTurnSanitizeResult(
                is_modified=False,
                modification_reason=None,
                sanitized_text=""
            )

        text = raw_text.strip()
        reasons = []

        # 1. Persona Identity Assertion (Failure #4)
        if FORBIDDEN_HUMAN_CLAIMS.search(text):
            text = CANONICAL_AI_PERSONA
            reasons.append("INTERCEPTED_PERSONA_VIOLATION")
            return PostTurnSanitizeResult(
                is_modified=True,
                modification_reason=", ".join(reasons),
                sanitized_text=text
            )

        # 2. Capability Channel Check (Failure #3: WhatsApp / External promises)
        if FORBIDDEN_CHANNELS.search(text):
            text = CANONICAL_APP_CHANNEL
            reasons.append("INTERCEPTED_CHANNEL_VIOLATION")
            return PostTurnSanitizeResult(
                is_modified=True,
                modification_reason=", ".join(reasons),
                sanitized_text=text
            )

        # 3. Pricing Sanity Check (Failure #1: Hallucinated price)
        price_matches = PRICE_PATTERN.findall(text)
        if price_matches:
            for p_str in price_matches:
                try:
                    val = int(p_str)
                    if val not in ALLOWED_PRICES:
                        text = CANONICAL_PRICING_FACT
                        reasons.append("INTERCEPTED_PRICE_HALLUCINATION")
                        break
                except ValueError:
                    pass

        # 4. Mandatory Clinical Remedy Verifier (Class B: Failure #2)
        if required_remedy_tokens:
            lower_text = text.lower()
            missing = [tok for tok in required_remedy_tokens if tok.lower() not in lower_text]
            if missing:
                # Append approved remedy line
                remedy_line = " Aap din mein do baar gungune paani mein jeera aur saunf ubaal kar pijiye, isse kaafi aaram milega."
                text = text.rstrip(".") + "." + remedy_line
                reasons.append("ENFORCED_MANDATORY_REMEDY")

        return PostTurnSanitizeResult(
            is_modified=len(reasons) > 0,
            modification_reason=", ".join(reasons) if reasons else None,
            sanitized_text=text
        )

# Global singleton
post_turn_sanitizer = PostTurnOutputSanitizer()
