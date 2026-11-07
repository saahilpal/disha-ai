/**
 * Vercel Serverless Function: GET /patient/profile
 * Returns authenticated patient profile, PEP permissions, and diet schedule.
 */
export default function handler(req, res) {
  res.setHeader('Access-Control-Allow-Credentials', 'true');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS');
  res.setHeader(
    'Access-Control-Allow-Headers',
    'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version, Authorization'
  );

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  const authHeader = req.headers.authorization || '';
  const token = authHeader.replace(/^Bearer\s+/i, '').trim();

  let patientId = 'pt_f53bad41cb';
  let name = 'Priya Sharma';
  let htn = 'STAGE_1';
  let clearance = false;

  if (token.includes('cardiac')) {
    patientId = 'pt_test_cardiac';
    name = 'Vikram Malhotra';
    htn = 'STAGE_2';
  } else if (token.includes('diabetic')) {
    patientId = 'pt_test_diabetic';
    name = 'Ramesh Gupta';
    htn = 'NORMAL';
  }

  return res.status(200).json({
    patient_id: patientId,
    name: name,
    age: 38,
    gender: 'Female',
    height_cm: 165,
    weight_kg: 68,
    dietary_preference: 'Vegetarian',
    health_goals: ['Blood Pressure Management', 'Sustainable Weight Loss'],
    pep: {
      hypertension_stage: htn,
      gym_clearance: clearance,
      allowed_modalities: ['Brisk walking (30 mins daily)', 'Gentle hatha yoga', 'Stretching'],
      restricted_modalities: ['Heavy deadlifts (>100kg)', 'CrossFit HIIT', 'Max sprint intervals'],
    },
    diet_schedule: {
      breakfast: 'Poha with roasted peanuts, curry leaves & unsweetened green tea',
      lunch: '2 Multigrain rotis, yellow dal tadka, steamed bottle gourd & cucumber salad',
      dinner: 'Moong dal khichdi with roasted cumin, turmeric & lightly tossed beans',
    },
  });
}

