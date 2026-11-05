import re
from typing import List, Dict, Any

class MockConversationalEngine:
    """
    Deterministic Mock Conversational Brain for offline testing and CI/CD.
    Generates authentic Hinglish responses strictly grounded in the prompt context.
    Uses regex word boundaries to avoid false substring collisions in code-mixed Hinglish.
    """

    @classmethod
    def generate_response(cls, messages: List[Dict[str, str]]) -> str:
        # Extract system prompt and user transcript
        system_text = ""
        user_text = ""
        for m in messages:
            if m["role"] == "system":
                system_text = m["content"]
            elif m["role"] == "user":
                user_text = m["content"].lower()

        # Clean tags
        user_text = re.sub(r"<[^>]+>", "", user_text).strip()

        # 1. Identity / Persona Check (Failure #4)
        if re.search(r"\b(insaan|robot|human|bot|asli ladki|who are you|kaun ho|naam|aap kaun)\b", user_text):
            return "Main Disha hoon, aapki AI health coach. Main aapke doctor ke care plan ke sath aapki health journey mein guide karti hoon."

        # 2. WhatsApp / Channel Delivery Boundary (Failure #3)
        if re.search(r"\b(whatsapp|wa|watsapp)\b", user_text):
            return "Aapka diet chart Disha app ke 'My Plan' tab mein already available hai, aap wahan se directly dekh sakte hain."

        # 3. Pricing & Subscription Catalog (Failure #1)
        if re.search(r"\b(paid|subscription|price|paise|kitne ka|fees|charges)\b", user_text):
            return "Aapke doctor ke treatment plan ke sath Disha basic voice follow-up calls 100% free hain. Personal dietitian plans ₹1,499 prati mahina se start hote hain."

        # 4. Meal Inquiry Grounded in DB (Failure #6)
        if re.search(r"\b(dinner|khana|diet chart|meal|lunch|breakfast)\b", user_text):
            if "paneer bhurji" in system_text.lower():
                return "Aaj aapke dinner mein 150g paneer bhurji, 2 multigrain rotis aur cucumber salad hai (~420 kcal). Yeh balanced aur high-protein hai!"
            elif "from db:" in system_text.lower():
                # Extract meal description from system prompt
                match = re.search(r"from db:\s*([^\n\.]+)", system_text, re.IGNORECASE)
                meal_summary = match.group(1).strip() if match else "150g paneer bhurji aur rotis"
                return f"Aaj aapke dinner mein {meal_summary} hai. Yeh aapke diet chart ke anusaar high-protein aur balanced hai!"
            elif "not found" in system_text.lower():
                return "Aapka aaj ka diet plan abhi dietitian team review kar rahi hai. Kripya Disha app ke 'My Plan' tab mein thodi der mein check karein."

        # 5. Symptom / Bloating Remedy Grounded in Clinical Rules (Failure #2)
        if re.search(r"\b(bloating|pet phool|gas|pet bhari|bloat)\b", user_text):
            return "Periods ke dauran bloating common hai. Aap din mein do baar gungune paani mein jeera aur saunf ubaal kar pijiye, isse pet ko kaafi aaram milega."

        # 6. Gym / Exercise PEP Alignment (Failure #7)
        if re.search(r"\b(gym|workout|exercise|kasrat)\b", user_text):
            if "gym" in system_text.lower():
                return "Bahut badhiya! Aapke care plan mein gym workouts approved hain. Shuru mein light weights aur machine exercises se start karein aur hydrate rahein."
            else:
                return "Aap abhi light walking aur home exercises se start karein, jaisa aapke doctor ne recommend kiya hai."

        # 7. Mango Stance Consensus (Failure #8)
        if re.search(r"\b(aam|mango|mangoes)\b", user_text):
            return "Aam seasonal fruit hai aur moderation mein bilkul le sakte hain! Din ke waqt lagbhag aadha aam (100g) enjoy karein, bas late night dessert ke roop mein avoid karein."

        # Default conversational Hinglish acknowledgement
        return "Haan bilkul, main samajh rahi hoon. Aap apni routine follow karte rahiye aur koi bhi doubt ho toh zaroor batayein."
