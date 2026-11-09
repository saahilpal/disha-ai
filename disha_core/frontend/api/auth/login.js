/** Vercel's static preview has no authenticated patient backend. */
export default function handler(req, res) {
  if (req.method === 'OPTIONS') {
    res.setHeader('Allow', 'POST, OPTIONS');
    return res.status(204).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ detail: 'Method not allowed. Use POST.' });
  }

  res.setHeader('Allow', 'POST, OPTIONS');
  return res.status(503).json({
    detail: 'Authentication is unavailable in the static preview. Configure the authenticated backend API.',
  });
}
