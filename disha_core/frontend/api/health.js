/** Reports only that this static-preview function is reachable. */
export default function handler(_req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  return res.status(200).json({
    status: 'ok',
    service: 'static-preview',
    timestamp: new Date().toISOString(),
  });
}
