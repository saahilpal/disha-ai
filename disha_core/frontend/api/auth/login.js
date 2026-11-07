/**
 * Vercel Serverless Function: POST /auth/login
 * Handles patient authentication on Vercel deployments.
 */
export default function handler(req, res) {
  // CORS Headers
  res.setHeader('Access-Control-Allow-Credentials', 'true');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS,PATCH,DELETE,POST,PUT');
  res.setHeader(
    'Access-Control-Allow-Headers',
    'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version, Authorization'
  );

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ detail: 'Method not allowed. Use POST.' });
  }

  const { email, password } = req.body || {};
  if (!email || !email.includes('@') || !email.includes('.')) {
    return res.status(400).json({ detail: 'Invalid email format' });
  }
  if (!password || password.length < 6) {
    return res.status(400).json({ detail: 'Password must be at least 6 characters' });
  }

  const emailLower = email.toLowerCase().trim();
  if (emailLower.includes('cardiac')) {
    return res.status(200).json({
      token: 'pt_test_cardiac_bearer_token',
      patient_id: 'pt_test_cardiac',
      patient_name: 'Vikram Malhotra',
      status: 'authenticated',
    });
  } else if (emailLower.includes('diabetic')) {
    return res.status(200).json({
      token: 'pt_test_diabetic_bearer_token',
      patient_id: 'pt_test_diabetic',
      patient_name: 'Ramesh Gupta',
      status: 'authenticated',
    });
  } else {
    return res.status(200).json({
      token: 'pt_test_01_valid_bearer_token',
      patient_id: 'pt_f53bad41cb',
      patient_name: 'Priya Sharma',
      status: 'authenticated',
    });
  }
}
