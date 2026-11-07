/**
 * Vercel Serverless Function: GET /ready
 */
export default function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  return res.status(200).json({
    status: 'ready',
    laya: {
      available: true,
      classifier: 'laya-multilingual',
      mode: 'edge-hybrid',
    },
    timestamp: new Date().toISOString(),
  });
}

