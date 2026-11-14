-- ==============================================================================
-- DISHA AI — OFFICIAL CLINICAL EXERCISE GUIDELINES SCHEMA & SEED
-- Sources:
-- 1. Fit India Movement (MoHFW & Ministry of Youth Affairs and Sports, Govt of India)
-- 2. Ministry of AYUSH & Morarji Desai National Institute of Yoga (MDNIY, Govt of India)
-- 3. World Health Organization (WHO Guidelines on Physical Activity 2020)
-- 4. ICMR-NIN 2024 Physical Activity Guidelines for Indians
-- ==============================================================================
SET client_min_messages = warning;

CREATE TABLE IF NOT EXISTS clinical_exercise_guidelines (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE,
    aliases TEXT[] NOT NULL DEFAULT '{}',
    source_authority VARCHAR(128) NOT NULL,
    category VARCHAR(64) NOT NULL,
    stress_tags TEXT[] NOT NULL DEFAULT '{}',
    contraindicated_tags TEXT[] NOT NULL DEFAULT '{}',
    modifications TEXT[] NOT NULL DEFAULT '{}',
    alternatives TEXT[] NOT NULL DEFAULT '{}',
    default_level VARCHAR(32) NOT NULL DEFAULT 'all',
    required_equipment VARCHAR(64) NOT NULL DEFAULT 'none',
    default_location VARCHAR(64) NOT NULL DEFAULT 'home',
    guideline_notes TEXT NOT NULL,
    citation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_exercise_name ON clinical_exercise_guidelines(name);
CREATE INDEX IF NOT EXISTS idx_exercise_category ON clinical_exercise_guidelines(category);
CREATE INDEX IF NOT EXISTS idx_exercise_contraindicated ON clinical_exercise_guidelines USING GIN(contraindicated_tags);
CREATE INDEX IF NOT EXISTS idx_exercise_stress ON clinical_exercise_guidelines USING GIN(stress_tags);

-- Insert Official Exercise Guidelines
INSERT INTO clinical_exercise_guidelines (
    id, name, aliases, source_authority, category, stress_tags, contraindicated_tags, modifications, alternatives, default_level, required_equipment, default_location, guideline_notes, citation
) VALUES 
(
    'fit_india_brisk_walking',
    'brisk_walking',
    ARRAY['walking', 'walk', 'tehalna', 'morning walk', 'evening walk', 'brisk walk', 'tez chalna', 'step count', 'tahalna'],
    'Fit India Movement (MoHFW & MYAS, Govt of India)',
    'aerobic',
    ARRAY['low_impact', 'aerobic', 'joint_friendly', 'metabolic_conditioning'],
    ARRAY['acute_severe_gout_foot', 'acute_chest_pain', 'acute_severe_pain'],
    ARRAY['Short 10-15 minute bouts after meals to assist glucose blunting (ICMR-NIN 2024)', 'Wear supportive footwear with cushioned insoles on even flat ground', 'Maintain conversational pace (able to speak without breathlessness)'],
    ARRAY['Seated arm ergometer or gentle seated marching', 'Gentle stretching and mobility flow', 'Stationary recumbent cycling'],
    'all',
    'none',
    'outdoor',
    'Fit India standard cardio protocol: 30-45 minutes daily moderate aerobic activity (Fitness Ki Dose, Aadha Ghanta Roz). Ideal for glycemic and hypertension management.',
    'Fit India Age-Appropriate Fitness Protocols 18-64 Years, Ministry of Youth Affairs and Sports & MoHFW, Govt of India, Section 4.1'
),
(
    'fit_india_squats',
    'squats',
    ARRAY['squat', 'deep squats', 'air squats', 'bodyweight squats', 'baithak', 'dand baithak', 'chair squat'],
    'Fit India Movement (MoHFW & MYAS, Govt of India)',
    'muscular_strength',
    ARRAY['knee_joint_loading', 'patellar_shear', 'quadriceps', 'axial_spine'],
    ARRAY['knee_pain', 'knee_injury', 'patellar_tendonitis', 'severe_arthritis_knee'],
    ARRAY['Chair-supported shallow squats (limit knee bend to 45 degrees)', 'Wall slide with exercise ball supporting the lumbar spine', 'Keep knees tracking behind toes and avoid deep flexion past 90 degrees'],
    ARRAY['Glute bridges (floor-based movement, removes knee shear force)', 'Seated straight-leg raises to build quadriceps without joint loading', 'Gentle flat-surface walking'],
    'beginner',
    'none',
    'home',
    'Fit India lower body functional movement. Promotes bone density and leg endurance. Knee pain patients must limit flexion range.',
    'Fit India Age-Appropriate Fitness Protocols 18-64 Years, MoHFW & MYAS, Section 4.2'
),
(
    'who_heavy_deadlifts',
    'heavy_deadlifts',
    ARRAY['deadlift', 'deadlifts', 'heavy deadlift', 'barbell deadlift', 'max deadlift', 'powerlifting deadlift'],
    'WHO Guidelines on Physical Activity 2020',
    'muscular_strength',
    ARRAY['high_lumbar_shear', 'valsalva_maneuver', 'high_blood_pressure_spike', 'axial_spine_compression'],
    ARRAY['hypertension_stage2', 'hypertension_stage1', 'cardiac_history', 'aneurysm', 'lower_back_pain', 'slip_disc', 'lumbar_herniation', 'sciatica'],
    ARRAY['Bodyweight hip hinge practice with neutral lumbar spine', 'Light dumbbell Romanian deadlift with continuous rhythmic breathing (strictly no breath-holding)'],
    ARRAY['Bird-dog exercise on a soft mat (strengthens posterior chain with zero axial spine loading)', 'Glute bridges on mat for posterior glute/hamstring engagement', 'Brisk walking with active core bracing'],
    'intermediate',
    'full_gym',
    'gym',
    'WHO & ACSM Clinical Contraindication: High-load maximal resistance exercises causing acute Valsalva-induced systolic spikes (>200 mmHg) are strictly contraindicated in unmonitored hypertension.',
    'WHO Guidelines on Physical Activity and Sedentary Behaviour 2020, Section: Adults with Chronic Conditions'
),
(
    'fit_india_jumping_jacks',
    'jumping_jacks',
    ARRAY['jumping jack', 'star jumps', 'burpees', 'box jumps', 'jump rope', 'koodna'],
    'Fit India Movement (MoHFW & MYAS, Govt of India)',
    'aerobic',
    ARRAY['high_impact_landing', 'knee_impact', 'cardiovascular_spike', 'ankle_impact'],
    ARRAY['knee_pain', 'knee_injury', 'ankle_injury', 'hypertension_stage2', 'cardiac_history', 'plantar_fasciitis'],
    ARRAY['Low-impact step-jacks (step one foot out to the side without jumping)', 'Rhythmic arm raises while walking in place'],
    ARRAY['Brisk walking with synchronized arm pumping', 'Low-impact steady marching in place', 'Stationary cycling at a comfortable cadence'],
    'intermediate',
    'none',
    'home',
    'High-impact landing creates 3-4x bodyweight ground reaction forces. Unsuitable for active knee/ankle pain or unmanaged stage 2 hypertension.',
    'Fit India Fitness Assessment Protocol (Age 18-64), Section 3.3'
),
(
    'who_overhead_press',
    'overhead_press',
    ARRAY['shoulder press', 'military press', 'dumbbell shoulder press', 'overhead dumbbell press'],
    'WHO Guidelines on Physical Activity 2020',
    'muscular_strength',
    ARRAY['shoulder_impingement', 'hypertension_valsalva', 'lumbar_extension'],
    ARRAY['shoulder_pain', 'rotator_cuff_injury', 'hypertension_stage2', 'shoulder_impingement'],
    ARRAY['Seated neutral-grip dumbbell press with light resistance', 'Limit movement range below 90 degrees shoulder abduction'],
    ARRAY['Resistance band pull-aparts for scapular stability', 'Incline chest press with light dumbbells', 'Gentle wall-crawls and shoulder pendulum mobility exercises'],
    'intermediate',
    'dumbbells',
    'home',
    'Overhead loading can exacerbate rotator cuff impingement and trigger Valsalva response. Patients with stage 2 hypertension should avoid sustained overhead lifting.',
    'WHO Guidelines on Physical Activity 2020 & Clinical Exercise Guidelines for Hypertension'
),
(
    'fit_india_crunches',
    'crunches',
    ARRAY['sit-ups', 'situps', 'crunch', 'ab crunches', 'abdominal crunches'],
    'Fit India Movement (MoHFW & MYAS, Govt of India)',
    'core_conditioning',
    ARRAY['lumbar_flexion', 'cervical_strain', 'intra_abdominal_pressure'],
    ARRAY['lower_back_pain', 'slip_disc', 'lumbar_herniation', 'cervical_pain', 'diastasis_recti'],
    ARRAY['Pelvic tilts on a flat mat with knees bent', 'Deadbug exercise focusing on transverse abdominis engagement'],
    ARRAY['Bird-dog on all fours (safe isometric core stabilization)', 'Forearm plank from knees with neutral spine', 'Standing isometric ab bracing during daily walks'],
    'beginner',
    'none',
    'home',
    'Repetitive spinal flexion under compressive load aggravates lumbar disc herniation. Isometric stabilization is preferred for spine safety.',
    'Fit India Age-Appropriate Fitness Protocols 18-64 Years, Section 4.3'
),
(
    'fit_india_running',
    'running',
    ARRAY['jogging', 'run', 'jog', 'treadmill running', 'sprints', 'sprinting', 'daudna'],
    'Fit India Movement (MoHFW & MYAS, Govt of India)',
    'aerobic',
    ARRAY['repetitive_knee_strike', 'high_impact', 'cardiovascular_exertion', 'shin_splints'],
    ARRAY['knee_pain', 'knee_injury', 'ankle_injury', 'acute_shin_splints', 'plantar_fasciitis', 'cardiac_history'],
    ARRAY['Brisk walking intervals (walk fast 2 mins, gentle walk 1 min)', 'Walk on level grass or soft track rather than hard pavement'],
    ARRAY['Brisk outdoor walking or treadmill incline walking at low speed', 'Stationary cycling with smooth pedal stroke', 'Gentle swimming or shallow-water walking'],
    'intermediate',
    'none',
    'outdoor',
    'Vigorous aerobic activity. Individuals with joint pain or cardiac history should maintain low-impact cardio alternatives.',
    'Fit India Movement Protocols, MoHFW & MYAS, Section 4.1'
),
(
    'ayush_gentle_yoga',
    'gentle_yoga',
    ARRAY['yoga', 'pranayama', 'stretching', 'asanas', 'cat-cow', 'yogabhyas', 'sukshma vyayama'],
    'Ministry of AYUSH & MDNIY (Common Yoga Protocol, Govt of India)',
    'yoga_asana',
    ARRAY['mobility', 'low_intensity', 'joint_decompression'],
    ARRAY['severe_joint_instability', 'acute_severe_pain'],
    ARRAY['Use yoga blocks and wall support for balance', 'Avoid deep twists or inversions if blood pressure is elevated'],
    ARRAY['Chair yoga and seated spinal mobility', 'Guided diaphragmatic breathing and relaxation'],
    'all',
    'yoga_mat',
    'home',
    'Ministry of AYUSH Common Yoga Protocol: Safe, gentle loosening practices (Sadilaja) and restorative asanas for all age groups.',
    'Common Yoga Protocol (CYP), Ministry of AYUSH & MDNIY, Govt of India, Chapter 3'
),
(
    'ayush_vajrasana',
    'vajrasana',
    ARRAY['diamond pose', 'thunderbolt pose', 'vajrasan'],
    'Ministry of AYUSH & MDNIY (Common Yoga Protocol, Govt of India)',
    'yoga_asana',
    ARRAY['knee_hyperflexion', 'ankle_extension', 'pelvic_blood_flow'],
    ARRAY['knee_pain', 'knee_injury', 'acute_piles', 'severe_arthritis_knee'],
    ARRAY['Place a folded blanket or yoga cushion between heels and buttocks', 'Place a small rolled towel under ankles'],
    ARRAY['Sukhasana (Easy seated pose) on a cushion', 'Seated chair posture with upright spine'],
    'beginner',
    'yoga_mat',
    'home',
    'The only asana recommended to be practiced immediately after meals to stimulate digestion. Avoid in acute knee joint inflammation.',
    'Common Yoga Protocol, Ministry of AYUSH & MDNIY, Section 3.7'
),
(
    'ayush_bhujangasana',
    'bhujangasana',
    ARRAY['cobra pose', 'bhujangasan', 'serpent pose'],
    'Ministry of AYUSH & MDNIY (Common Yoga Protocol, Govt of India)',
    'yoga_asana',
    ARRAY['lumbar_extension', 'abdominal_stretch', 'chest_expansion'],
    ARRAY['acute_peptic_ulcer', 'abdominal_hernia', 'recent_abdominal_surgery', 'acute_severe_back_spasm'],
    ARRAY['Sarala Bhujangasana (Sphinx pose on forearms with gentle arch)', 'Keep elbows slightly bent and avoid hyperextension of lumbar spine'],
    ARRAY['Makarasana (Crocodile pose) for passive spinal relaxation', 'Seated gentle thoracic arch in chair'],
    'beginner',
    'yoga_mat',
    'home',
    'Strengthens back muscles and improves chest expansion. Effective for bronchial asthma and mild back stiffness.',
    'Common Yoga Protocol, Ministry of AYUSH & MDNIY, Section 3.11'
),
(
    'ayush_nadi_shodhana',
    'anulom_vilom',
    ARRAY['nadi shodhana', 'alternate nostril breathing', 'anuloma viloma', 'nadi shuddhi'],
    'Ministry of AYUSH & MDNIY (Common Yoga Protocol, Govt of India)',
    'pranayama',
    ARRAY['autonomic_regulation', 'parasympathetic_tone', 'cardiovascular_calming'],
    ARRAY['acute_nasal_blockage'],
    ARRAY['Perform without breath retention (Kumbhaka) in hypertension or cardiac conditions', 'Maintain smooth, rhythmic 1:1 inhalation-exhalation ratio'],
    ARRAY['Simple deep diaphragmatic breathing', 'Bhramari pranayama'],
    'all',
    'none',
    'any',
    'Principal calming pranayama. Reduces sympathetic activity, lowers heart rate and blood pressure, improves mental clarity. Safe for all patients.',
    'Common Yoga Protocol, Ministry of AYUSH & MDNIY, Section 4.1'
),
(
    'fit_india_plank',
    'plank',
    ARRAY['planks', 'forearm plank', 'front plank', 'kumbhakasana'],
    'Fit India Movement (MoHFW & MYAS, Govt of India)',
    'core_conditioning',
    ARRAY['isometric_core', 'intra_thoracic_pressure', 'shoulder_stability'],
    ARRAY['hypertension_stage2', 'hypertension_stage1', 'cardiac_history', 'rotator_cuff_injury'],
    ARRAY['Knee plank (knees on mat to reduce lever arm and intra-thoracic pressure)', 'Incline forearm plank against a sturdy table or wall', 'Short 10-second holds with continuous breathing (avoid breath-holding)'],
    ARRAY['Bird-dog on all fours', 'Deadbug on mat', 'Glute bridges'],
    'beginner',
    'none',
    'home',
    'Core endurance benchmark in Fit India. Hypertensive patients must not perform prolonged isometric breath holds.',
    'Fit India Age-Appropriate Fitness Protocols 18-64 Years, Section 4.3'
),
(
    'fit_india_pushups',
    'pushups',
    ARRAY['push up', 'push-ups', 'press ups', 'dand', 'wall pushups', 'knee pushups'],
    'Fit India Movement (MoHFW & MYAS, Govt of India)',
    'muscular_strength',
    ARRAY['pectoralis', 'anterior_deltoid', 'triceps', 'core_bracing'],
    ARRAY['shoulder_pain', 'rotator_cuff_injury', 'wrist_pain', 'acute_shoulder_impingement'],
    ARRAY['Wall push-ups (standing arms-length from wall, low joint load)', 'Incline push-ups on kitchen counter or bench', 'Knee push-ups on soft mat'],
    ARRAY['Resistance band chest press', 'Seated dumbbell chest press with neutral grip', 'Isometric chest press with palms joined'],
    'beginner',
    'none',
    'home',
    'Fit India upper body endurance standard. Regress to wall or knee pushups if shoulder or wrist pain is reported.',
    'Fit India Age-Appropriate Fitness Protocols 18-64 Years, Section 4.2'
)
ON CONFLICT (name) DO UPDATE SET
    aliases = EXCLUDED.aliases,
    source_authority = EXCLUDED.source_authority,
    category = EXCLUDED.category,
    stress_tags = EXCLUDED.stress_tags,
    contraindicated_tags = EXCLUDED.contraindicated_tags,
    modifications = EXCLUDED.modifications,
    alternatives = EXCLUDED.alternatives,
    default_level = EXCLUDED.default_level,
    required_equipment = EXCLUDED.required_equipment,
    default_location = EXCLUDED.default_location,
    guideline_notes = EXCLUDED.guideline_notes,
    citation = EXCLUDED.citation;

