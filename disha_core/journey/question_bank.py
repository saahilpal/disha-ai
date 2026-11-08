"""Structured Question Bank for the 5-Stage Patient Journey.

Provides trilingual natural conversational phrasings (English, Hindi, Hinglish),
priorities, target field links, clarification prompts, and eligibility predicates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class JourneyQuestion:
    question_id: str
    stage: int
    target_field: str
    priority: int  # 1 = Highest (Safety), 6 = Lowest (Optional)
    required: bool
    skip_allowed: bool
    phrasings: dict[str, str]  # 'en', 'hi', 'hinglish'
    clarification: dict[str, str] = field(default_factory=dict)
    eligibility_fn: Callable[[set[str]], bool] | None = None


# Trilingual Question Catalog
QUESTION_CATALOG: list[JourneyQuestion] = [
    # -------------------------------------------------------------
    # Stage 1: Basic Patient Profile
    # -------------------------------------------------------------
    JourneyQuestion(
        question_id="Q_STAGE1_NAME",
        stage=1,
        target_field="name",
        priority=2,
        required=True,
        skip_allowed=False,
        phrasings={
            "en": "May I know your full name please?",
            "hi": "क्या मैं आपका पूरा नाम जान सकती हूँ?",
            "hinglish": "Kya main aapka poora naam jaan sakti hoon?",
        },
        clarification={
            "en": "Please share your name so I can address you properly.",
            "hi": "कृपया अपना नाम बताएं ताकि हम बातचीत जारी रख सकें।",
            "hinglish": "Kripya apna naam batayein taaki hum baat aage badha sakein.",
        },
    ),
    JourneyQuestion(
        question_id="Q_STAGE1_AGE",
        stage=1,
        target_field="age",
        priority=2,
        required=True,
        skip_allowed=False,
        phrasings={
            "en": "How old are you?",
            "hi": "आपकी उम्र कितनी है?",
            "hinglish": "Aapki umar kitni hai?",
        },
        clarification={
            "en": "Sharing your age helps me tailor safe exercise and metabolic guidance.",
            "hi": "उम्र जानने से सही डाइट और एक्सरसाइज गाइडेंस में मदद मिलती है।",
            "hinglish": "Umar janne se safe diet aur exercise guidance plan karne mein madad milti hai.",
        },
    ),
    JourneyQuestion(
        question_id="Q_STAGE1_GENDER",
        stage=1,
        target_field="gender",
        priority=2,
        required=True,
        skip_allowed=False,
        phrasings={
            "en": "Could you share your biological sex or gender?",
            "hi": "क्या आप अपना जेंडर बता सकते हैं?",
            "hinglish": "Kya aap apna gender bata sakte hain?",
        },
    ),
    JourneyQuestion(
        question_id="Q_STAGE1_HEIGHT",
        stage=1,
        target_field="height_cm",
        priority=2,
        required=True,
        skip_allowed=False,
        phrasings={
            "en": "What is your height (in centimeters or feet/inches)?",
            "hi": "आपकी हाइट कितनी है (सेंटीमीटर या फीट में)?",
            "hinglish": "Aapki height kitni hai (centimeters ya feet mein)?",
        },
    ),
    JourneyQuestion(
        question_id="Q_STAGE1_WEIGHT",
        stage=1,
        target_field="weight_kg",
        priority=2,
        required=True,
        skip_allowed=False,
        phrasings={
            "en": "What is your current weight in kilograms?",
            "hi": "आपका मौजूदा वजन कितने किलोग्राम है?",
            "hinglish": "Aapka current weight kitne kg hai?",
        },
    ),

    # -------------------------------------------------------------
    # Stage 2: Health Background and Safety
    # -------------------------------------------------------------
    JourneyQuestion(
        question_id="Q_STAGE2_CONDITIONS",
        stage=2,
        target_field="diagnosed_conditions",
        priority=1,  # Safety Critical
        required=True,
        skip_allowed=False,
        phrasings={
            "en": "Do you have any diagnosed medical conditions like hypertension, high BP, diabetes, thyroid, or cardiac history?",
            "hi": "क्या आपको डॉक्टर द्वारा बताई गई कोई बीमारी है, जैसे हाई बीपी, डायबिटीज, थायरॉइड या दिल की परेशानी?",
            "hinglish": "Kya aapko doctor dwara diagnosed koi condition hai, jaise high BP, diabetes, thyroid ya cardiac history?",
        },
        clarification={
            "en": "If none, you can simply say 'No medical conditions'.",
            "hi": "अगर कोई बीमारी नहीं है, तो आप 'कोई नहीं' कह सकते हैं।",
            "hinglish": "Agar koi diagnosed condition nahi hai, toh aap simply 'koi nahi' bata sakte hain.",
        },
    ),
    JourneyQuestion(
        question_id="Q_STAGE2_MEDICATIONS",
        stage=2,
        target_field="medications",
        priority=2,
        required=False,
        skip_allowed=True,
        phrasings={
            "en": "Are you currently taking any regular prescription medicines?",
            "hi": "क्या आप वर्तमान में कोई नियमित दवाइयां ले रहे हैं?",
            "hinglish": "Kya aap abhi regular koi dawai le rahe hain?",
        },
    ),
    JourneyQuestion(
        question_id="Q_STAGE2_ALLERGIES",
        stage=2,
        target_field="allergies_intolerances",
        priority=2,
        required=False,
        skip_allowed=True,
        phrasings={
            "en": "Do you have any food allergies or ingredient restrictions, like lactose, gluten, nuts, or strict religious preferences?",
            "hi": "क्या आपको किसी खाने की चीज से एलर्जी है, जैसे दूध, ग्लूटेन, मूंगफली, या बिना प्याज-लहसुन?",
            "hinglish": "Kya aapko kisi khane se allergy ya restriction hai, jaise lactose, gluten, nuts ya bina pyaaz-lehsun?",
        },
    ),
    JourneyQuestion(
        question_id="Q_STAGE2_LIMITATIONS",
        stage=2,
        target_field="injuries_or_limitations",
        priority=2,
        required=False,
        skip_allowed=True,
        phrasings={
            "en": "Do you have any joint pain, back issues, or physical limitations that affect your workouts?",
            "hi": "क्या आपको जोड़ों का दर्द, कमर दर्द या कोई चोट है जो एक्सरसाइज को प्रभावित करती है?",
            "hinglish": "Kya aapko joints pain, back problem ya koi physical limitation hai jo exercise mein dikkat kare?",
        },
    ),

    # -------------------------------------------------------------
    # Stage 3: Lifestyle and Daily Routine
    # -------------------------------------------------------------
    JourneyQuestion(
        question_id="Q_STAGE3_WORK_SCHEDULE",
        stage=3,
        target_field="work_schedule",
        priority=3,
        required=True,
        skip_allowed=False,
        phrasings={
            "en": "What does your work schedule look like—regular day shift, night shift, or rotational?",
            "hi": "आपका काम का शेड्यूल कैसा रहता है—डे शिफ्ट, नाइट शिफ्ट या रोटेशनल?",
            "hinglish": "Aapka kaam ka schedule kaisa rehta hai—day shift, night shift ya rotational?",
        },
    ),
    JourneyQuestion(
        question_id="Q_STAGE3_WAKE_TIME",
        stage=3,
        target_field="wake_time",
        priority=3,
        required=True,
        skip_allowed=False,
        phrasings={
            "en": "What time do you usually wake up in the morning?",
            "hi": "आप सुबह आमतौर पर कितने बजे उठते हैं?",
            "hinglish": "Aap aam taur par subah kitne baje uthte hain?",
        },
    ),
    JourneyQuestion(
        question_id="Q_STAGE3_SLEEP_TIME",
        stage=3,
        target_field="sleep_time",
        priority=3,
        required=True,
        skip_allowed=False,
        phrasings={
            "en": "What time do you usually go to bed at night?",
            "hi": "आप रात को आमतौर पर कितने बजे सोते हैं?",
            "hinglish": "Aap raat ko kitne baje sote hain?",
        },
    ),
    JourneyQuestion(
        question_id="Q_STAGE3_MOVEMENT",
        stage=3,
        target_field="daily_movement_level",
        priority=4,
        required=False,
        skip_allowed=True,
        phrasings={
            "en": "How active is your typical day—mostly desk-bound, or do you get regular steps in?",
            "hi": "दिन भर में आपका मूवमेंट कैसा रहता है—ज्यादातर डेस्क पर बैठना या वॉक करना?",
            "hinglish": "Din bhar mein aapka movement kaisa rehta hai—desk job hai ya daily walk kar paate hain?",
        },
    ),
    JourneyQuestion(
        question_id="Q_STAGE3_WATER",
        stage=3,
        target_field="water_intake_target",
        priority=4,
        required=False,
        skip_allowed=True,
        phrasings={
            "en": "About how much water do you drink in a day (in glasses or liters)?",
            "hi": "आप दिन भर में लगभग कितना पानी पी लेते हैं (गिलास या लीटर में)?",
            "hinglish": "Aap din bhar mein lagbhag kitna paani pee lete hain (glasses ya litres mein)?",
        },
    ),
    JourneyQuestion(
        question_id="Q_STAGE3_TEA_COFFEE",
        stage=3,
        target_field="tea_coffee_frequency",
        priority=4,
        required=False,
        skip_allowed=True,
        phrasings={
            "en": "How many cups of tea or coffee do you have daily?",
            "hi": "आप दिन में कितनी कप चाय या कॉफ़ी पीते हैं?",
            "hinglish": "Aap din mein kitni cup chai ya coffee lete hain?",
        },
    ),

    # -------------------------------------------------------------
    # Stage 4: Goals, Diet and Personal Preferences
    # -------------------------------------------------------------
    JourneyQuestion(
        question_id="Q_STAGE4_PRIMARY_GOAL",
        stage=4,
        target_field="primary_health_goal",
        priority=2,
        required=True,
        skip_allowed=False,
        phrasings={
            "en": "What is your main health goal right now—managing weight, controlling blood pressure, improving stamina, or something else?",
            "hi": "इस समय आपका मुख्य हेल्थ गोल क्या है—वजन कम करना, बीपी कंट्रोल, स्टैमिना बढ़ाना, या कुछ और?",
            "hinglish": "Is samay aapka main health goal kya hai—weight loss, BP control, stamina badhana ya kuch aur?",
        },
    ),
    JourneyQuestion(
        question_id="Q_STAGE4_DIET_PREF",
        stage=4,
        target_field="dietary_preference",
        priority=2,
        required=True,
        skip_allowed=False,
        phrasings={
            "en": "What is your food preference—Vegetarian, Non-Vegetarian, Eggetarian, Jain, or Vegan?",
            "hi": "आपकी डाइट की प्राथमिकता क्या है—शाकाहारी, मांसाहारी, एगेटेरियन, जैन या वीगन?",
            "hinglish": "Aapki diet preference kya hai—Vegetarian, Non-Vegetarian, Eggetarian, Jain ya Vegan?",
        },
    ),
    JourneyQuestion(
        question_id="Q_STAGE4_DISLIKED_FOODS",
        stage=4,
        target_field="disliked_foods",
        priority=4,
        required=False,
        skip_allowed=True,
        phrasings={
            "en": "Are there any specific vegetables or dishes you really dislike and prefer not to have in your meal plan?",
            "hi": "क्या ऐसी कोई सब्जियां या खाना है जो आपको बिल्कुल पसंद नहीं, जैसे करेला या टिंडा?",
            "hinglish": "Kya aisi koi sabzi ya khana hai jo aap bilkul pasand nahi karte, jaise karela ya tinda?",
        },
    ),
    JourneyQuestion(
        question_id="Q_STAGE4_REGIONAL_CUISINE",
        stage=4,
        target_field="cultural_regional_preferences",
        priority=5,
        required=False,
        skip_allowed=True,
        phrasings={
            "en": "Do you prefer a specific regional style of food, like North Indian, South Indian, or Gujarati home cooking?",
            "hi": "क्या आप किसी खास क्षेत्रीय भोजन को प्राथमिकता देते हैं, जैसे नॉर्थ इंडियन या साउथ इंडियन?",
            "hinglish": "Kya aap kisi particular regional khane ko prefer karte hain, jaise North Indian, South Indian ya Gujarati?",
        },
    ),

    # -------------------------------------------------------------
    # Stage 5: Validation, Missing Gaps & Personalisation Readiness
    # -------------------------------------------------------------
    JourneyQuestion(
        question_id="Q_STAGE5_VALIDATION_CONFIRM",
        stage=5,
        target_field="personalisation_readiness",
        priority=2,
        required=True,
        skip_allowed=False,
        phrasings={
            "en": "We've got your core profile mapped! Shall we review your personalized care plan for the week?",
            "hi": "आपकी पूरी प्रोफाइल तैयार हो गई है! क्या हम इस हफ्ते का आपका पर्सनलाइज्ड डाइट और केयर प्लान शुरू करें?",
            "hinglish": "Aapki profile setup complete ho gayi hai! Kya hum aapka personalized diet aur care plan start karein?",
        },
    ),
]


QUESTION_BY_ID: dict[str, JourneyQuestion] = {q.question_id: q for q in QUESTION_CATALOG}
QUESTION_BY_FIELD: dict[str, JourneyQuestion] = {q.target_field: q for q in QUESTION_CATALOG}


def get_question_for_field(field_id: str) -> JourneyQuestion | None:
    return QUESTION_BY_FIELD.get(field_id)
