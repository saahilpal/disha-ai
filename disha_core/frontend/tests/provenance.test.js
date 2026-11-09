const assert = require('node:assert/strict');
const test = require('node:test');

const { state, handleServerMessage, dispatchTurn } = require('../app.js');

function createElement(tagName) {
  const element = {
    tagName,
    className: '',
    textContent: '',
    style: {},
    children: [],
    attributes: {},
    scrollTop: 0,
    scrollHeight: 0,
    classList: { remove() {}, add() {} },
    setAttribute(name, value) { this.attributes[name] = value; },
    appendChild(child) { this.children.push(child); return child; },
    closest() { return this; },
    querySelector(selector) {
      if (selector === '.msg-text') return this.messageText || null;
      if (selector === '.msg-bubble') return this.messageBubble || null;
      if (selector === '.source-trace') return this.children.find(child => child.className === 'source-trace') || null;
      return null;
    },
  };
  element.messageText = { textContent: '', classList: { remove() {} } };
  element.messageBubble = createBubble();
  Object.defineProperty(element, 'innerHTML', {
    set(value) { this._innerHTML = value; },
    get() { return this._innerHTML || ''; },
  });
  return element;
}

function createBubble() {
  return {
    children: [],
    appendChild(child) { this.children.push(child); return child; },
    querySelector(selector) {
      return selector === '.source-trace'
        ? this.children.find(child => child.className === 'source-trace') || null
        : null;
    },
  };
}

function setupChatDom() {
  const stream = {
    children: [],
    scrollTop: 0,
    scrollHeight: 0,
    appendChild(child) { this.children.push(child); return child; },
    closest() { return this; },
  };
  const previousDocument = global.document;
  global.document = {
    createElement,
    getElementById: id => id === 'chat-stream' ? stream : null,
  };
  return {
    stream,
    restore() {
      if (previousDocument === undefined) delete global.document;
      else global.document = previousDocument;
    },
  };
}

function lastAssistantTrace(stream) {
  const message = [...stream.children].reverse().find(item => item.className === 'chat-message assistant');
  return message && message.messageBubble.querySelector('.source-trace');
}

test('renders voice done evidence IDs and retrieval status with the assistant message', () => {
  const dom = setupChatDom();
  const previousHistory = state.transcriptHistory;
  const previousLastElement = state.lastAssistantMessageElement;
  const previousLastEntry = state.lastAssistantHistoryEntry;
  state.transcriptHistory = [];

  try {
    handleServerMessage({ type: 'sentence', text: 'Assistant reply.' });
    handleServerMessage({
      type: 'done',
      evidence_ids: ['chunk-voice-17'],
      retrieval_status: 'grounded',
    });

    assert.equal(lastAssistantTrace(dom.stream).textContent, 'Sources: chunk-voice-17 · Retrieval: grounded');
    assert.deepEqual(state.transcriptHistory.at(-1).evidence_ids, ['chunk-voice-17']);
    assert.equal(state.transcriptHistory.at(-1).retrieval_status, 'grounded');
  } finally {
    state.transcriptHistory = previousHistory;
    state.lastAssistantMessageElement = previousLastElement;
    state.lastAssistantHistoryEntry = previousLastEntry;
    dom.restore();
  }
});

test('preserves evidence IDs from SSE done payloads on streamed assistant messages', async () => {
  const dom = setupChatDom();
  const previousHistory = state.transcriptHistory;
  const previousFetch = global.fetch;
  state.transcriptHistory = [];
  const sse = [
    'event: sentence\ndata: {"sentence":"Streamed reply."}\n\n',
    'event: done\ndata: {"evidence_ids":["chunk-sse-42"],"retrieval_status":"grounded"}\n\n',
  ].join('');
  global.fetch = async () => ({
    ok: true,
    body: {
      getReader: () => {
        let sent = false;
        return {
          async read() {
            if (sent) return { done: true };
            sent = true;
            return { done: false, value: new TextEncoder().encode(sse) };
          },
        };
      },
    },
  });

  try {
    await dispatchTurn('Question');
    assert.equal(lastAssistantTrace(dom.stream).textContent, 'Sources: chunk-sse-42 · Retrieval: grounded');
    assert.deepEqual(state.transcriptHistory.at(-1).evidence_ids, ['chunk-sse-42']);
    assert.equal(state.transcriptHistory.at(-1).retrieval_status, 'grounded');
  } finally {
    state.transcriptHistory = previousHistory;
    global.fetch = previousFetch;
    dom.restore();
  }
});

test('preserves evidence IDs from the /chat fallback JSON response', async () => {
  const dom = setupChatDom();
  const previousHistory = state.transcriptHistory;
  const previousFetch = global.fetch;
  state.transcriptHistory = [];
  let requestCount = 0;
  global.fetch = async () => {
    requestCount += 1;
    if (requestCount === 1) return { ok: false, body: null };
    return {
      ok: true,
      json: async () => ({
        response: 'Fallback reply.',
        evidence_ids: ['chunk-json-9'],
        retrieval_status: 'grounded',
      }),
    };
  };

  try {
    await dispatchTurn('Question');
    assert.equal(lastAssistantTrace(dom.stream).textContent, 'Sources: chunk-json-9 · Retrieval: grounded');
    assert.deepEqual(state.transcriptHistory.at(-1).evidence_ids, ['chunk-json-9']);
    assert.equal(state.transcriptHistory.at(-1).retrieval_status, 'grounded');
  } finally {
    state.transcriptHistory = previousHistory;
    global.fetch = previousFetch;
    dom.restore();
  }
});
