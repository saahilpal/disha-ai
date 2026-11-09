const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const appSource = fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf8');
const indexSource = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const { state, populateProfileView } = require('../app.js');

test('does not contain fixed BMI classification or coaching copy', () => {
  const removedCopy = [
    'Underweight (Nutritional support indicated)',
    'Normal (Healthy weight for Asian population)',
    'Overweight (Pre-hypertensive risk)',
    'Obese (Cardiometabolic risk)',
    'Nutritional Vitality:',
    'Optimal Balance:',
    'Metabolic Optimization:',
    'Cardiometabolic Care:',
    'bmi-encouragement-text',
    'bmi-gauge-pointer',
  ];

  for (const phrase of removedCopy) {
    assert.equal(appSource.includes(phrase), false, `Unexpected fixed BMI copy/reference: ${phrase}`);
  }
});

test('keeps height and weight inputs in onboarding', () => {
  assert.match(indexSource, /id="onboard-height"/);
  assert.match(indexSource, /id="onboard-weight"/);
  assert.match(appSource, /parseFloat\(dom\.onboardHeight/);
  assert.match(appSource, /parseFloat\(dom\.onboardWeight/);
});

test('displays a numeric BMI calculated from the profile metrics', () => {
  const previousDocument = global.document;
  const previousProfile = state.patientProfile;
  const bmiElement = { textContent: '--' };
  const elements = new Map([['profile-page-bmi', bmiElement]]);
  global.document = { getElementById: (id) => elements.get(id) || null };

  try {
    state.patientProfile = {
      profile: { height_cm: '170', weight_kg: '70' },
      pep: null,
    };
    populateProfileView();
    assert.equal(bmiElement.textContent, '24.2 kg/m²');

    state.patientProfile.profile = { height_cm: '0', weight_kg: '70' };
    populateProfileView();
    assert.equal(bmiElement.textContent, '--');
  } finally {
    state.patientProfile = previousProfile;
    if (previousDocument === undefined) delete global.document;
    else global.document = previousDocument;
  }

  assert.equal((appSource.match(/formatProfileBmi\(p\)/g) || []).length, 2);
});
