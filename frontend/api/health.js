/**
 * Vercel Serverless Function: GET /health
 */
export default function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  return res.status(200).json({
    status: 'ok',
    mode: 'serverless-edge',
    service: 'disha-telephony-core',
    timestamp: new Date().toISOString(),
  });
}

