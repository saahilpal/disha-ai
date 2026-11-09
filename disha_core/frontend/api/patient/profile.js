/** The profile API must be served by the authenticated application backend. */
export default function handler(_req, res) {
  res.setHeader('Allow', 'GET');
  return res.status(503).json({
    error: 'Patient profile service is unavailable. Configure the authenticated backend API.',
  });
}
