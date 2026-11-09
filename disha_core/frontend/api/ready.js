/** Vercel's static preview does not run the Disha backend or its model services. */
export default function handler(_req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  return res.status(503).json({
    status: 'unavailable',
    detail: 'Backend readiness is unavailable in the static preview.',
  });
}
